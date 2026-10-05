from __future__ import annotations

from .models import ChannelAssignment, ChannelProfile, MarkerRule


class ChannelAutoMapper:
    """Map physical CAN channels to logical networks using observed marker IDs."""

    def __init__(self, rules: list[MarkerRule]):
        self._rules = rules

    def classify(self, profile: ChannelProfile) -> ChannelAssignment:
        matched: list[tuple[MarkerRule, set[int]]] = []

        for rule in self._rules:
            matched_ids = rule.matches(profile.message_id_counts)
            if matched_ids:
                matched.append((rule, matched_ids))

        if len(matched) == 1:
            rule, matched_ids = matched[0]
            return ChannelAssignment(
                channel=profile.channel,
                status="mapped",
                logical_name=rule.network,
                matched_networks=(rule.network,),
                matched_ids=tuple(sorted(matched_ids)),
            )

        if not matched:
            return ChannelAssignment(
                channel=profile.channel,
                status="unknown",
                logical_name=None,
            )

        networks = tuple(rule.network for rule, _ in matched)
        ids = tuple(sorted({msg_id for _, values in matched for msg_id in values}))
        return ChannelAssignment(
            channel=profile.channel,
            status="ambiguous",
            logical_name=None,
            matched_networks=networks,
            matched_ids=ids,
        )

    def classify_all(
        self,
        profiles: dict[int, ChannelProfile],
    ) -> list[ChannelAssignment]:
        return [self.classify(profile) for profile in profiles.values()]
