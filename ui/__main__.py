"""Run the UI:  python -m ui   (then open http://127.0.0.1:8765)"""
import argparse
import webbrowser

from ui.app import create_app

p = argparse.ArgumentParser()
p.add_argument("--port", type=int, default=8765)
p.add_argument("--no-browser", action="store_true")
args = p.parse_args()
url = f"http://127.0.0.1:{args.port}"
print(f"RepoMind UI at {url}  (local only; Ctrl+C to stop)")
if not args.no_browser:
    webbrowser.open(url)
create_app().run(host="127.0.0.1", port=args.port, threaded=True, debug=False)
