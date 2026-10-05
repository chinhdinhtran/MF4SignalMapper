from __future__ import annotations

import logging
from pathlib import Path

from .channel_mapper import ChannelAutoMapper
from .config import load_config
from .decoder import MdfSignalDecoder
from .mf4_inspector import Mf4Inspector
from .models import ConversionReport
from .writer import MappedMdfWriter

LOGGER = logging.getLogger(__name__)


class ConversionPipeline:
    def __init__(self, config_path: str | Path):
        self.config = load_config(config_path)
        self.inspector = Mf4Inspector()
        self.mapper = ChannelAutoMapper(self.config.marker_rules)

    def convert(
        self,
        input_mf4: str | Path,
        dbc_path: str | Path,
        output_mf4: str | Path,
        progress_callback=None,
    ) -> ConversionReport:
        input_mf4 = Path(input_mf4)
        dbc_path = Path(dbc_path)
        output_mf4 = Path(output_mf4)

        if not input_mf4.exists():
            raise FileNotFoundError(input_mf4)
        if not dbc_path.exists():
            raise FileNotFoundError(dbc_path)
        if input_mf4.resolve() == output_mf4.resolve():
            raise ValueError("Output MF4 must be different from input MF4")

        writer = MappedMdfWriter(input_mf4)
        report = ConversionReport(
            input_file=str(input_mf4),
            output_file=str(output_mf4),
            dbc_file=str(dbc_path),
        )

        try:
            self._progress(progress_callback, 15, "Inspecting raw CAN channels...")
            LOGGER.info("Inspecting raw CAN channels...")
            profiles = self.inspector.inspect(writer.mdf)
            assignments = self.mapper.classify_all(profiles)
            report.channels = assignments

            self._validate_assignments(assignments)
            self._log_mapping(profiles, assignments)
            self._progress(progress_callback, 30, f"Detected {len(assignments)} CAN channel(s)")

            decoder = MdfSignalDecoder(
                dbc_path,
                apply_value_to_text=self.config.apply_value_to_text,
            )

            decodable = [
                assignment
                for assignment in assignments
                if assignment.status == "mapped"
                or (
                    assignment.status == "unknown"
                    and self.config.decode_unknown_channels
                )
                or assignment.status == "ambiguous"
            ]

            for index, assignment in enumerate(decodable, start=1):
                physical_channel = assignment.channel
                output_network = assignment.output_name
                percent = 30 + int(55 * (index - 1) / max(1, len(decodable)))
                self._progress(progress_callback, percent, f"Decoding CAN{assignment.channel}...")
                LOGGER.info(
                    "[%d/%d] Decoding CAN%d as %s",
                    index,
                    len(decodable),
                    physical_channel,
                    output_network,
                )

                if assignment.status == "ambiguous":
                    LOGGER.warning(
                        "CAN%d is ambiguous (%s); no logical network name is inferred. "
                        "Using physical name CAN%d.",
                        physical_channel,
                        ", ".join(assignment.matched_networks),
                        physical_channel,
                    )

                decoded_groups = decoder.decode_channel(writer.mdf, physical_channel)
                groups, signals = writer.append_decoded(
                    output_network,
                    physical_channel,
                    decoded_groups,
                )
                report.decoded_groups += groups
                report.decoded_signals += signals

                if not decoded_groups:
                    LOGGER.warning(
                        "CAN%d: no DBC-defined signal was extracted.",
                        physical_channel,
                    )

            skipped = [
                assignment.channel
                for assignment in assignments
                if assignment.status != "mapped"
                and assignment.status != "ambiguous"
                and not self.config.decode_unknown_channels
            ]
            report.skipped_channels = skipped

            output_mf4.parent.mkdir(parents=True, exist_ok=True)
            self._progress(progress_callback, 90, "Writing mapped MF4...")
            writer.save(
                output_mf4,
                version=self.config.output_version,
                compression=self.config.output_compression,
            )
            self._progress(progress_callback, 100, "Export completed")
            return report
        finally:
            writer.close()

    @staticmethod
    def _progress(callback, percent: int, message: str) -> None:
        if callback is not None:
            callback(int(percent), message)

    def _validate_assignments(self, assignments) -> None:
        ambiguous = [a for a in assignments if a.status == "ambiguous"]
        unknown = [a for a in assignments if a.status == "unknown"]

        if ambiguous:
            details = "; ".join(
                f"CAN{a.channel}: {','.join(a.matched_networks)}" for a in ambiguous
            )
            if self.config.strict_mapping:
                raise ValueError(
                    "Ambiguous channel mapping in strict mode: " + details
                )
            LOGGER.warning("Ambiguous channel mapping: %s", details)

        if unknown:
            details = ", ".join(f"CAN{a.channel}" for a in unknown)
            if self.config.strict_mapping:
                raise ValueError(
                    "Unmapped physical CAN channels in strict mode: " + details
                )
            LOGGER.info("Unmapped physical CAN channels: %s", details)

    @staticmethod
    def _log_mapping(profiles, assignments) -> None:
        LOGGER.info("Detected CAN channels:")
        for assignment in assignments:
            profile = profiles[assignment.channel]
            marker_text = ""
            if assignment.matched_ids:
                marker_text = ", markers=" + ",".join(
                    f"0x{msg_id:X}" for msg_id in assignment.matched_ids
                )

            LOGGER.info(
                "  CAN%d: frames=%d, status=%s, network=%s%s",
                assignment.channel,
                profile.frame_count,
                assignment.status,
                assignment.logical_name or "<none>",
                marker_text,
            )
