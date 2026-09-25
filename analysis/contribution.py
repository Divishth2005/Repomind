"""Signals A and change-magnitude (plan Sec 14.1, 14.4): who touched a
component, how often, and how much. Signals, not proof of expertise."""


def normalize_shares(values: dict) -> dict:
    total = sum(values.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in values.items() if v > 0}
