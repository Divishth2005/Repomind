import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection):
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
