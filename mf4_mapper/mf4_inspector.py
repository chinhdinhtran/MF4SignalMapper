from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from .models import ChannelProfile


class Mf4Inspector:
    """Inspect raw CAN_DataFrame channel groups in an MDF/MF4 file."""

    ID_CHANNEL = "CAN_DataFrame.ID"
    BUS_CHANNEL = "CAN_DataFrame.BusChannel"

    @staticmethod
    def _as_int_array(values: Any) -> np.ndarray:
        array = np.asarray(values)
        if array.dtype.kind in "SUO":
            array = array.astype(np.int64)
        return array.astype(np.int64, copy=False)

    @staticmethod
    def _normalise_id(values: np.ndarray) -> np.ndarray:
        # Matches the 29-bit CAN ID masking used by asammdf for CAN frame views.
        return values.astype(np.int64, copy=False) & 0x1FFFFFFF

    def inspect(self, mdf) -> dict[int, ChannelProfile]:
        profiles: dict[int, ChannelProfile] = {}

        for group_index, _group in enumerate(mdf.groups):
            try:
                ids = mdf.get(
                    self.ID_CHANNEL,
                    group=group_index,
                    samples_only=True,
                    ignore_invalidation_bits=True,
                )
                buses = mdf.get(
                    self.BUS_CHANNEL,
                    group=group_index,
                    samples_only=True,
                    ignore_invalidation_bits=True,
                )
            except Exception:
                # Non-CAN groups are ignored. Raw CAN groups expose both fields.
                continue

            ids_array = self._normalise_id(self._as_int_array(ids))
            bus_array = self._as_int_array(buses)

            if ids_array.size != bus_array.size:
                raise ValueError(
                    f"MF4 group {group_index}: ID and BusChannel sample counts "
                    f"differ ({ids_array.size} != {bus_array.size})"
                )

            if ids_array.size == 0:
                continue

            for channel in np.unique(bus_array):
                channel_int = int(channel)
                channel_ids = ids_array[bus_array == channel]
                counts = Counter(int(msg_id) for msg_id in channel_ids)

                profile = profiles.setdefault(channel_int, ChannelProfile(channel_int))
                profile.frame_count += int(channel_ids.size)
                for msg_id, count in counts.items():
                    profile.message_id_counts[msg_id] = (
                        profile.message_id_counts.get(msg_id, 0) + count
                    )

        return dict(sorted(profiles.items()))
