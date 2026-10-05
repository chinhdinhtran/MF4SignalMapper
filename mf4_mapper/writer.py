from __future__ import annotations

from pathlib import Path

from asammdf import MDF

from .decoder import DecodedGroup


class MappedMdfWriter:
    """Keep the original raw CAN groups and append decoded signal groups."""

    def __init__(self, raw_path: str | Path):
        self.mdf = MDF(str(raw_path))

    def append_decoded(
        self,
        network: str,
        physical_channel: int,
        decoded_groups: list[DecodedGroup],
    ) -> tuple[int, int]:
        group_count = 0
        signal_count = 0

        for decoded in decoded_groups:
            acq_name = f"{network}.CAN{physical_channel}.{decoded.message_name}"
            self.mdf.append(
                decoded.signals,
                acq_name=acq_name,
                acq_source=decoded.acq_source,
                comment="Decoded from CAN bus logging using DBC by MF4 Signal Mapper",
                common_timebase=False,
            )
            group_count += 1
            signal_count += len(decoded.signals)

        return group_count, signal_count

    def save(self, output_path: str | Path, version: str, compression: int = 1) -> Path:
        # raw_path is the original measurement; output_path is always a new file.
        if version != self.mdf.version:
            raise ValueError(
                f"This writer expects output version {self.mdf.version} to preserve "
                f"the original raw measurement, got {version}"
            )

        return self.mdf.save(
            str(output_path),
            overwrite=True,
            compression=compression,
            add_history_block=True,
        )

    def close(self) -> None:
        self.mdf.close()
