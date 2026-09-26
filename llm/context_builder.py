"""Turn Module 7's retrieval result into the evidence text given to the LLM.

Every item shown carries a citable id ([fact:N], [commit:abc1234], [pr:#12],
[issue:#7]); the set of ids shown is returned so an answer's citations can be
checked afterwards. Data limitations (unlinked PRs, split identities) are
included so the model can mention them. If the material is too big it is
shrunk in steps and `truncated` says so -- it is never cut silently.
"""
import re
from dataclasses import dataclass, field

HEX = re.compile(r"\b[0-9a-f]{7,40}\b")
NUM = re.compile(r"#(\d+)")
SIZES = [(8, 10, 300), (6, 8, 220), (5, 6, 160), (3, 4, 120), (2, 3, 80)]  # list items, evidence items, snippet chars


@dataclass
class Context:
    text: str
    refs: set = field(default_factory=set)
    numbers: set = field(default_factory=set)
    hashes: set = field(default_factory=set)
    truncated: bool = False
    empty: bool = False


def _d(x):
    return (x or "")[:10]


def _flat(x, n):
    s = " ".join((x or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _render(result: dict, repo: str, n_list: int, n_evid: int, snip: int):
    lines: list[str] = []
    refs: set[str] = set()
    fid = [0]
    content = [False]

    def fact(header: str) -> None:
        fid[0] += 1
        ref = f"fact:{fid[0]}"
        refs.add(ref)
        lines.append(f"[{ref}] {header}")
        content[0] = True

    def cited(ref: str, text: str) -> None:
        refs.add(ref)
        lines.append(f"  [{ref}] {text}")
        content[0] = True

    plan = result["plan"]
    lines.append(f"Repository: {repo}")
    lines.append(f"Question interpreted as: {', '.join(plan['intents'])}"
                 + (f"; about: {', '.join(plan['scopes'])}" if plan["scopes"] else ""))
    if result["notes"]:
        lines.append("\nDATA LIMITATIONS")
        lines += [f"- {n}" for n in result["notes"]]

    lines.append("\nFACTS FROM THE DATABASE")
    for scope, block in result["answers"].items():
        if scope in ("lookups", "developers"):
            continue
        if "contributors" in block:
            c = block["contributors"]
            people = "; ".join(f"{x['name']} {x['commits']} commits ({x['share']:.0%}, last {_d(x['last_commit'])})"
                               for x in c["contributors"][:n_list]) or "none found"
            fact(f"Commit authors for {scope} ({c['total_commits']} commits, bots excluded): {people}")
        if "reviewers" in block:
            people = "; ".join(f"{x['name']} {x['prs_reviewed']} PRs (last {_d(x['last_review'])})"
                               for x in block["reviewers"][:n_list]) or "none found (PRs may not be linkable to this code)"
            fact(f"Reviewers of pull requests that touched {scope} (own PRs excluded): {people}")
        if "history" in block:
            fact(f"Most recent changes to {scope}:")
            for h in block["history"][:n_list]:
                pr = h["prs_linked"] or ([h["pr_from_subject"]] if h["pr_from_subject"] else [])
                cited(f"commit:{h['sha'][:7]}",
                      f"{_d(h['date'])} {h['author']}: {_flat(h['subject'], snip)}" + (f" (PR #{pr[0]})" if pr else ""))
        if "prs" in block:
            fact(f"Pull requests that touched {scope}:")
            for p in block["prs"][:n_list]:
                how = "linked by GitHub" if p["link"] == "linked" else "inferred from '(#N)' in a commit subject"
                cited(f"pr:#{p['number']}", f"{p['state']} {_d(p['merged_at'] or p['created_at'])} by {p['author']}: "
                                             f"{_flat(p['title'], snip)} ({how})")
        if "assessment" in block:
            a = block["assessment"]
            if a["available"]:
                sig = "; ".join(f"{s['name']} - {s['detail']}" for s in a["risk_signals"]) or "none triggered"
                fact(f"Concentration/risk signals for {scope} (heuristic, not a finding about any person): risk level "
                     f"{a['risk_level']}; top commit author {a['top_contributor']} with {a['top_commit_share']:.0%} of "
                     f"{a['total_commits']} commits; {a['effective_contributors']} effective contributors; signals: {sig}")
            else:
                fact(f"No commit activity found for {scope}.")

    for item in result["answers"].get("lookups", []):
        if item["type"] == "pr":
            reviews = "; ".join(f"{r['reviewer']} {r['state']}" for r in item["reviews"][:n_list]) or "none recorded"
            closes = "; ".join(f"#{i['number']} {_flat(i['title'], 80)}" for i in item["closes_issues"]) or "none"
            files = ", ".join(item["files"][:n_list]) or "not linked"
            cited(f"pr:#{item['number']}",
                  f"PR #{item['number']} \"{_flat(item['title'], snip)}\" {item['state']}, by {item['author']}, created "
                  f"{_d(item['created_at'])}, merged {_d(item['merged_at']) or 'no'}. Description: {_flat(item['body'], snip * 2)} "
                  f"Reviews: {reviews}. Closes issues: {closes}. Files: {files}.")
        elif item["type"] == "issue":
            prs = "; ".join(f"#{p['number']} {_flat(p['title'], 80)}" for p in item["closed_by_prs"]) or "none linked"
            cited(f"issue:#{item['number']}",
                  f"Issue #{item['number']} \"{_flat(item['title'], snip)}\" {item['state']}, by {item['author']}, created "
                  f"{_d(item['created_at'])}, closed {_d(item['closed_at']) or 'no'}. Description: {_flat(item['body'], snip * 2)} "
                  f"Closed by PRs: {prs}.")
        elif item["type"] == "commit":
            files = ", ".join(f["path"] for f in item["files"][:n_list])
            pr = item["prs_linked"] or ([item["pr_from_subject"]] if item["pr_from_subject"] else [])
            cited(f"commit:{item['sha'][:7]}",
                  f"Commit {item['sha'][:7]} on {_d(item['date'])} by {item['author']}: {_flat(item['subject'], snip)}. "
                  f"Files: {files}." + (f" PR #{pr[0]}." if pr else ""))

    for d in result["answers"].get("developers", []):
        top = ", ".join(f"{f['path']} ({f['commits']})" for f in d["top_files"][:n_list])
        fact(f"Activity of '{d['name']}' as identified in this data: {d['commits']} commits "
             f"({_d(d['first_commit'])} to {_d(d['last_commit'])}), {d['prs_authored']} PRs authored, "
             f"{d['reviews_given']} reviews given; most-changed files: {top or 'none'}")

    shown = result["evidence"][:n_evid]
    if shown:
        lines.append("\nTEXT SEARCH MATCHES (ranked by keyword relevance, may be only loosely related)")
        for e in shown:
            cited(e["ref"], f"{_d(e['date'])} {e['author'] or ''}: {_flat(e['title'], snip)}"
                            + (f" - {_flat(e['snippet'], snip)}" if e["snippet"] and e["kind"] != "commit" else ""))
    return "\n".join(lines), refs, content[0]


def build_context(result: dict, repo: str, max_chars: int = 14000) -> Context:
    for i, (n_list, n_evid, snip) in enumerate(SIZES):
        text, refs, has_content = _render(result, repo, n_list, n_evid, snip)
        if len(text) <= max_chars or i == len(SIZES) - 1:
            break
    truncated = i > 0
    if truncated:
        text += "\n\nCONTEXT NOTE: some results were omitted to fit the size limit."
    return Context(text, refs, {int(n) for n in NUM.findall(text)}, set(HEX.findall(text.lower())),
                   truncated, empty=not has_content)
