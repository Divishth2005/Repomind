"""CLI: build the first developer <-> file knowledge-map visualization.

Usage:
    python -m visualization.cli --repo pallets/flask
"""
import argparse
from pathlib import Path

from database.connection import get_connection
from visualization.knowledge_map import build_graph
from visualization.render import render_html

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "repomind.sqlite"
DATA_PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"


def main():
    parser = argparse.ArgumentParser(description="Build the knowledge-map visualization")
    parser.add_argument("--repo", required=True, help="owner/name, e.g. pallets/flask")
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--top-developers", type=int, default=15)
    parser.add_argument("--files-per-dev", type=int, default=8)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    owner, name = args.repo.split("/")
    repository_id = f"{owner}/{name}"
    out_path = Path(args.out) if args.out else Path(args.db_path).parent / f"{name}_knowledge_map.html"

    conn = get_connection(args.db_path)
    graph = build_graph(conn, repository_id, args.top_developers, args.files_per_dev)
    print(f"[viz] graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    render_html(graph, out_path, args.repo, args.top_developers)
    print(f"[viz] wrote {out_path}")


if __name__ == "__main__":
    main()
