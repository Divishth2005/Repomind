"""Evidence text for an engineering briefing. Items carry citable ids:
[commit:..] [pr:#..] [issue:#..] [cochange:N] [fact:N]."""
from llm.context_builder import HEX, NUM, Context, _d, _flat

SIZES = [(12, 10, 6, 240), (8, 7, 4, 160), (5, 5, 3, 110)]  # fixes, co-change files, issues, snippet chars


def _render(repo, path, b, plan, n_fix, n_co, n_iss, snip):
    lines, refs, fid = [], set(), [0]
    h = b["history"]

    def fact(text):
        fid[0] += 1
        refs.add(f"fact:{fid[0]}")
        lines.append(f"[fact:{fid[0]}] {text}")

    lines.append(f"Repository: {repo}")
    lines.append(f"Code about to be changed: {b['label']} in {path} (lines {b['start']}-{b['end']})")
    if plan:
        lines.append(f"Planned change (stated by the user, not verified): {_flat(plan, 400)}")
    lines.append("\nDATA LIMITATIONS")
    lines.append("- 'Looks like a fix' is a heuristic: wording (fix/bug/crash/regression) or a closed issue labelled as a bug. "
                 "It is often right but not always, and misses fixes that are worded differently.")
    lines.append("- Co-change is a statistical association from past commits, not a dependency: files can change together "
                 "because of one large refactor or a habit.")
    lines.append("- History covers the commits that changed these exact lines; commit messages often do not give reasons.")
    if any(c["pr_link"] == "subject" for c in h["commits"]):
        lines.append("- Some PR links are inferred from '(#N)' in commit subjects.")
    lines.append("- A person can appear under a Git name and a separate GitHub login (not always linked).")

    lines.append(f"\nCHANGE HISTORY OF THESE LINES: {h['range_commits_found_in_git']} commits changed them; "
                 f"{len(b['fixes'])} look like fixes.")
    for f in b["fixes"][:n_fix]:
        refs.add(f"commit:{f['commit_id'][:7]}")
        pr = f" (PR #{f['pr']})" if f["pr"] else ""
        lines.append(f"  [commit:{f['commit_id'][:7]}] {_d(f['timestamp'])} {f['author']}: {_flat(f['subject'], snip)}{pr} "
                     f"-- flagged because: {', '.join(f['reasons'])}")
    if len(b["fixes"]) > n_fix:
        lines.append(f"  ({len(b['fixes']) - n_fix} older fix-like changes not shown)")
    fix_prs = {f["pr"] for f in b["fixes"][:n_fix] if f["pr"]}
    for p in h["prs"]:
        if p["number"] in fix_prs:
            refs.add(f"pr:#{p['number']}")
            revs = ", ".join(sorted({r["reviewer"] for r in p["reviews"] if r["reviewer"] and r["reviewer"] != p["author"]})) or "none recorded"
            lines.append(f"  [pr:#{p['number']}] {p['state']} by {p['author']}: {_flat(p['title'], snip)}. "
                         f"Description: {_flat(p['body'], snip) or 'none'} Reviewed by: {revs}.")
    for i in h["issues"][:n_iss]:
        refs.add(f"issue:#{i['number']}")
        lines.append(f"  [issue:#{i['number']}] {i['state']} by {i['author']}: {_flat(i['title'], snip)}. {_flat(i['body'], snip)}")

    co = b["cochange"]
    lines.append(f"\nFILES THAT USUALLY CHANGE WITH {path} (association from its {co['file_commits']} commits)")
    idx = 0
    for kind, items in (("code", co["code"][:n_co]), ("test", co["tests"]), ("housekeeping", co["housekeeping"])):
        for r in items:
            idx += 1
            refs.add(f"cochange:{idx}")
            lines.append(f"  [cochange:{idx}] ({kind}) {r['path']}: changed in {r['cochanges']} of this file's {co['file_commits']} "
                         f"commits ({r['confidence']:.0%}); this file changed in {r['reverse_confidence']:.0%} of that file's commits")
    if idx == 0:
        lines.append("  none with enough history")

    if b["open_issues"]:
        lines.append("\nOPEN ISSUES THAT MENTION THIS FILE (text match only, may be unrelated)")
        for i in b["open_issues"][:n_iss]:
            refs.add(f"issue:#{i['github_number']}")
            lines.append(f"  [issue:#{i['github_number']}] opened {_d(i['created_at'])}: {_flat(i['title'], snip)}. {_flat(i['body'], snip)}")

    lines.append("\nPEOPLE AND SIGNALS")
    people = "; ".join(f"{a['name']}{' (bot)' if a['is_bot'] else ''} {a['commits']} commits" for a in h["authors"][:5]) or "none"
    fact(f"Authors of the commits that changed these lines: {people}")
    if h["reviewers"]:
        fact("Reviewers of the related pull requests (own PRs excluded): " + "; ".join(f"{n} {c} PRs" for n, c in h["reviewers"][:5]))
    a = h["file_assessment"]
    if a.get("available"):
        sig = "; ".join(f"{s['name']} - {s['detail']}" for s in a["risk_signals"]) or "none triggered"
        fact(f"Signals for the whole file (heuristic, not a finding about any person): risk level {a['risk_level']}; top commit author "
             f"{a['top_contributor']} with {a['top_commit_share']:.0%} of {a['total_commits']} commits; triggered: {sig}")
    return "\n".join(lines), refs


def build_briefing_context(repo, path, b, plan=None, max_chars=14000) -> Context:
    for i, (n_fix, n_co, n_iss, snip) in enumerate(SIZES):
        text, refs = _render(repo, path, b, plan, n_fix, n_co, n_iss, snip)
        if len(text) <= max_chars or i == len(SIZES) - 1:
            break
    if i > 0:
        text += "\n\nCONTEXT NOTE: some results were omitted to fit the size limit."
    return Context(text, refs, {int(n) for n in NUM.findall(text)}, set(HEX.findall(text.lower())), i > 0, empty=False)
