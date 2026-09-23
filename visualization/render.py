"""Render a knowledge-map graph dict to a self-contained interactive HTML
page (vis-network via CDN). No server needed -- open the file directly.
"""
import json
from pathlib import Path

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>RepoMind Knowledge Map — {repo_name}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f1115; color: #e6e6e6; }}
  #header {{ padding: 16px 24px; border-bottom: 1px solid #2a2d35; }}
  #header h1 {{ margin: 0 0 4px 0; font-size: 18px; }}
  #header p {{ margin: 0; color: #9a9fab; font-size: 13px; }}
  #legend {{ display: flex; gap: 20px; margin-top: 10px; font-size: 12px; color: #c8ccd6; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }}
  #network {{ width: 100vw; height: calc(100vh - 90px); }}
</style>
</head>
<body>
<div id="header">
  <h1>RepoMind Knowledge Map — {repo_name}</h1>
  <p>Developer &lt;-&gt; File network, derived from the normalized relationship model (top {top_developers} contributors by commit count).</p>
  <div id="legend">
    <span><span class="dot" style="background:#4f8cff"></span>Developer</span>
    <span><span class="dot" style="background:#ff9d4f"></span>File</span>
    <span style="color:#6b7080">Edge thickness = number of touches</span>
  </div>
</div>
<div id="network"></div>
<script>
  const nodes = new vis.DataSet({nodes_json});
  const edges = new vis.DataSet({edges_json});

  nodes.forEach(function(n) {{
    if (n.group === 'developer') {{
      n.color = {{ background: '#4f8cff', border: '#2f5fbf' }};
      n.shape = 'dot';
      n.size = 10 + Math.min(n.value, 200) / 8;
      n.font = {{ color: '#e6e6e6' }};
    }} else {{
      n.color = {{ background: '#ff9d4f', border: '#cc7a2f' }};
      n.shape = 'dot';
      n.size = 6 + Math.min(n.value, 100) / 10;
      n.font = {{ color: '#c8ccd6', size: 11 }};
    }}
  }});
  nodes.update(nodes.get());

  edges.forEach(function(e) {{
    e.width = Math.max(1, Math.min(e.value, 20) / 3);
    e.color = {{ color: '#3a3f4b', opacity: 0.6 }};
  }});
  edges.update(edges.get());

  const container = document.getElementById('network');
  const data = {{ nodes: nodes, edges: edges }};
  const options = {{
    physics: {{ stabilization: true, barnesHut: {{ gravitationalConstant: -8000, springLength: 120 }} }},
    interaction: {{ hover: true, tooltipDelay: 100 }},
  }};
  new vis.Network(container, data, options);
</script>
</body>
</html>
"""


def render_html(graph: dict, out_path: Path, repo_name: str, top_developers: int):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.format(
        repo_name=repo_name,
        top_developers=top_developers,
        nodes_json=json.dumps(graph["nodes"]),
        edges_json=json.dumps(graph["edges"]),
    )
    out_path.write_text(html, encoding="utf-8")
