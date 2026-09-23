"""CLI: build/refresh the SQLite database from normalized JSONL, then run a
few relationship queries as a smoke test that the model is actually usable.

Usage:
    python -m database.cli --repo pallets/flask
"""
import argparse
from pathlib import Path

from database.connection import get_connection, init_schema
from database.load import load_all
from database import queries as q

DATA_PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "repomind.sqlite"


def main():
    parser = argparse.ArgumentParser(description="Build the RepoMind SQLite database")
    parser.add_argument("--repo", required=True, help="owner/name, e.g. pallets/flask")
    parser.add_argument("--processed-dir", default=str(DATA_PROCESSED))
    parser.add_argument("--db-path", default=str(DB_PATH))
    args = parser.parse_args()

    owner, name = args.repo.split("/")
    repository_id = f"{owner}/{name}"
    processed_dir = Path(args.processed_dir) / name

    print(f"[db] initializing schema at {args.db_path} ...")
    conn = get_connection(args.db_path)
    init_schema(conn)

    print(f"[db] loading normalized data from {processed_dir} ...")
    counts = load_all(conn, processed_dir)
    print(f"[db] loaded: {counts}")

    print("\n[db] --- smoke test: top 5 human contributors ---")
    for row in q.top_contributors(conn, repository_id, limit=5):
        print(f"  {row['display_name'] or row['github_login']:30s} {row['commit_count']} commits")

    print("\n[db] --- smoke test: top files by touch count (via top contributor) ---")
    top = q.top_contributors(conn, repository_id, limit=1)
    if top:
        dev_id = top[0]["developer_id"]
        for row in q.developer_files(conn, dev_id, limit=5):
            print(f"  {row['path']:50s} {row['touches']} touches")

    conn.close()
    print(f"\n[db] database ready at {args.db_path}")


if __name__ == "__main__":
    main()
