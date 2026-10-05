from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DecodedGroup:
    message_name: str
    acq_source: object | None
    signals: list[object]


class MdfSignalDecoder:
    """Decode one physical CAN channel using one shared DBC."""

    def __init__(self, dbc_path: str | Path, apply_value_to_text: bool = False):
        self.dbc_path = Path(dbc_path)
        self.apply_value_to_text = apply_value_to_text

    def decode_channel(self, mdf, channel: int) -> list[DecodedGroup]:
        if not self.dbc_path.exists():
            raise FileNotFoundError(self.dbc_path)

        extracted = mdf.extract_bus_logging(
            database_files={
                "CAN": [(str(self.dbc_path), int(channel))],
            },
            version=mdf.version,
            ignore_value2text_conversion=not self.apply_value_to_text,
        )

        result: list[DecodedGroup] = []

        for group_index, group in enumerate(extracted.groups):
            master_index = extracted.masters_db.get(group_index, -1)
            signals: list[object] = []

            for channel_index, _channel in enumerate(group.channels):
                if channel_index == master_index:
                    continue

                signal = extracted.get(
                    None,
                    group=group_index,
                    index=channel_index,
                    ignore_invalidation_bits=True,
                )
                signals.append(signal)

            if not signals:
                continue

            message_name = group.channel_group.acq_name or "DecodedMessage"
            acq_source = group.channel_group.acq_source
            result.append(
                DecodedGroup(
                    message_name=str(message_name),
                    acq_source=acq_source,
                    signals=signals,
                )
            )

        return result
