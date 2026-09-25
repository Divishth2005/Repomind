"""Concentration formulations (plan Sec 14.7-14.8, 15). Several candidates
are implemented so they can be compared, not one declared correct."""


def herfindahl_index(shares: dict) -> float:
    """Sum of squared shares. 1.0 = one contributor; 1/n = perfectly even."""
    return sum(s * s for s in shares.values())


def effective_contributors(shares: dict) -> float:
    """1/HHI: how many equally-weighted contributors would give the same concentration."""
    hhi = herfindahl_index(shares)
    return 1.0 / hhi if hhi > 0 else 0.0


def top_share(shares: dict) -> float:
    return max(shares.values()) if shares else 0.0
