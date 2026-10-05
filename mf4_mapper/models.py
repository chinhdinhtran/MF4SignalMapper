from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MatchMode = Literal["any", "all"]
MappingStatus = Literal["mapped", "unknown", "ambiguous"]


@dataclass(frozen=True)
class MarkerRule:
    network: str
    message_ids: frozenset[int]
    match: MatchMode = "any"
    min_occurrences: int = 1

    def matches(self, message_id_counts: dict[int, int]) -> set[int]:
        eligible = {
            msg_id
            for msg_id in self.message_ids
            if message_id_counts.get(msg_id, 0) >= self.min_occurrences
        }

        if self.match == "all":
            return eligible if eligible == set(self.message_ids) else set()

        return eligible


@dataclass
class ChannelProfile:
    channel: int
    frame_count: int = 0
    message_id_counts: dict[int, int] = field(default_factory=dict)

    @property
    def message_ids(self) -> set[int]:
        return set(self.message_id_counts)


@dataclass(frozen=True)
class ChannelAssignment:
    channel: int
    status: MappingStatus
    logical_name: str | None
    matched_networks: tuple[str, ...] = ()
    matched_ids: tuple[int, ...] = ()

    @property
    def output_name(self) -> str:
        if self.logical_name:
            return self.logical_name
        return f"CAN{self.channel}"


@dataclass
class MapperConfig:
    marker_rules: list[MarkerRule]
    decode_unknown_channels: bool = True
    strict_mapping: bool = False
    apply_value_to_text: bool = False
    output_version: str = "4.10"
    output_compression: int = 1


@dataclass
class ConversionReport:
    input_file: str
    output_file: str
    dbc_file: str
    channels: list[ChannelAssignment] = field(default_factory=list)
    decoded_groups: int = 0
    decoded_signals: int = 0
    skipped_channels: list[int] = field(default_factory=list)
