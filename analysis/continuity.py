"""Signal C -- historical continuity (plan Sec 14.3): in how many distinct
calendar years did a developer touch a component. Repeated maintenance
across years is stronger evidence than one burst of commits."""
from datetime import datetime


def active_years(times: list[datetime]) -> int:
    return len({t.year for t in times})
