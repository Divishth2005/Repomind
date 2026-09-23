"""First knowledge-map visualization (build plan, Phase 5): a developer <->
file network built directly from the relational queries in
database/queries.py. Its purpose is to validate that the normalized
relationship model is actually sensible -- not to be a polished product UI.
"""
import sqlite3

from database import queries as q


def build_graph(
    conn: sqlite3.Connection,
    repository_id: str,
    top_developers: int = 15,
    files_per_dev: int = 8,
) -> dict:
    top = q.top_contributors(conn, repository_id, limit=top_developers)

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for dev in top:
        dev_node_id = f"dev:{dev['developer_id']}"
        nodes[dev_node_id] = {
            "id": dev_node_id,
            "label": dev["display_name"] or dev["github_login"] or "unknown",
            "group": "developer",
            "value": dev["commit_count"],
        }

        for f in q.developer_files(conn, dev["developer_id"], limit=files_per_dev):
            file_node_id = f"file:{f['path']}"
            if file_node_id not in nodes:
                nodes[file_node_id] = {
                    "id": file_node_id,
                    "label": f["path"].split("/")[-1],
                    "title": f["path"],
                    "group": "file",
                    "value": f["touches"],
                }
            edges.append({"from": dev_node_id, "to": file_node_id, "value": f["touches"]})

    return {"nodes": list(nodes.values()), "edges": edges}
