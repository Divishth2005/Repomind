"""A single retrieved piece of repository evidence.

`ref` is a stable, human-readable citation ("commit:ab12cd3", "pr:#123",
"issue:#7", "review:<id>") so later stages can cite exactly what an answer
was based on. `source` says whether it came from a structured query or
text search; `meta` carries the raw fields."""
from dataclasses import asdict, dataclass, field


@dataclass
class Evidence:
    kind: str  # commit | pr | issue | review
    ref: str
    title: str
    snippet: str
    date: str | None
    author: str | None
    score: float
    source: str  # "structured" | "text"
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
