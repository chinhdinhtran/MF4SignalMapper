from __future__ import annotations

import json
from pathlib import Path

from .models import MapperConfig, MarkerRule


def parse_can_id(value: int | str) -> int:
    if isinstance(value, int):
        return value & 0x1FFFFFFF

    text = str(value).strip().lower()
    if text.startswith("0x"):
        return int(text, 16) & 0x1FFFFFFF

    # Mapping configuration is intentionally CAN-ID oriented, so bare strings
    # are interpreted as hexadecimal as well (e.g. "51b").
    return int(text, 16) & 0x1FFFFFFF


def load_config(path: str | Path) -> MapperConfig:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    rules: list[MarkerRule] = []
    for item in raw.get("marker_rules", []):
        ids = frozenset(parse_can_id(v) for v in item["message_ids"])
        if not ids:
            raise ValueError(f"Rule {item.get('network')} has no message_ids")

        match = item.get("match", "any")
        if match not in ("any", "all"):
            raise ValueError(
                f"Invalid match mode '{match}' for {item.get('network')}"
            )

        rules.append(
            MarkerRule(
                network=str(item["network"]),
                message_ids=ids,
                match=match,
                min_occurrences=max(1, int(item.get("min_occurrences", 1))),
            )
        )

    if not rules:
        raise ValueError("No marker rules configured")

    return MapperConfig(
        marker_rules=rules,
        decode_unknown_channels=bool(raw.get("decode_unknown_channels", True)),
        strict_mapping=bool(raw.get("strict_mapping", False)),
        apply_value_to_text=bool(raw.get("apply_value_to_text", False)),
        output_version=str(raw.get("output_version", "4.10")),
        output_compression=int(raw.get("output_compression", 1)),
    )
