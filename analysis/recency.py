"""Signal B -- recency (plan Sec 14.2). Exponential decay with a stated
half-life. The half-life is a hypothesis: it is a parameter on every entry
point and reported in the output, never a hidden constant."""
from datetime import datetime

DEFAULT_HALF_LIFE_DAYS = 365.0


def recency_weight(when: datetime, reference: datetime, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    age_days = max((reference - when).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age_days / half_life_days)
