"""Evidence text for a code explanation: the code itself plus its recorded
history. Every item has a citable id ([code:L10-L40], [commit:abc1234],
[pr:#12], [issue:#7], [fact:N]). Too-large material is shrunk in steps and
flagged, never cut silently."""
from llm.context_builder import HEX, NUM, Context, _d, _flat

SIZES = [(150, 25, 6, 300), (100, 15, 5, 220), (60, 10, 4, 160), (40, 6, 3, 120)]  # code lines, commits, PRs, snippet chars


def _render(repo, path, label, start, end, code_lines, history, n_code, n_commits, n_prs, snip):
    lines: list[str] = []
    refs: set[str] = set()
    fid = [0]

    def fact(text):
        fid[0] += 1
        refs.add(f"fact:{fid[0]}")
        lines.append(f"[fact:{fid[0]}] {text}")

    shown = code_lines[:n_code]
    shown_end = start + len(shown) - 1
    code_ref = f"code:L{start}-L{shown_end}"
    refs.add(code_ref)
    lines.append(f"Repository: {repo}")
    lines.append(f"Code under explanation: {label} in {path} (lines {start}-{end})")
    lines.append(f"\n[{code_ref}]")
    lines += [f"{start + i:5d}| {ln}" for i, ln in enumerate(shown)]
    if len(shown) < len(code_lines):
        lines.append(f"      [only the first {len(shown)} of {len(code_lines)} lines are shown]")

    lines.append("\nDATA LIMITATIONS")
    lines.append("- History is the list of commits that changed these exact lines, found with git; it follows the "
                 "lines if the code was moved, and commit messages often do not explain intent.")
    if any(c["pr_link"] == "subject" for c in history["commits"]):
        lines.append("- Some PR links are inferred from '(#N)' in a commit subject, not from GitHub's own link.")
    if history["commits_missing_from_database"]:
        lines.append(f"- {history['commits_missing_from_database']} commit(s) touching these lines are missing from the database.")
    if history["prs_beyond_limit"]:
        lines.append(f"- {history['prs_beyond_limit']} more pull request(s) are related but not shown.")
    if len(history["commits"]) > n_commits:
        lines.append(f"- {len(history['commits']) - n_commits} older commit(s) are not shown.")
    lines.append("- A person can appear under a Git name and a separate GitHub login (not always linked).")

    commits = history["commits"][:n_commits]
    lines.append(f"\nHISTORY OF THESE LINES (newest first; {history['range_commits_found_in_git']} commits changed them)")
    if not commits:
        lines.append("  none recorded")
    for c in commits:
        pr = f" (PR #{c['prs'][0]})" if c["prs"] else ""
        refs.add(f"commit:{c['commit_id'][:7]}")
        lines.append(f"  [commit:{c['commit_id'][:7]}] {_d(c['timestamp'])} {c['author']}: {_flat(c['subject'], snip)}{pr}")

    prs = history["prs"][:n_prs]
    if prs:
        lines.append("\nPULL REQUESTS BEHIND THESE CHANGES")
    for p in prs:
        revs = ", ".join(sorted({r["reviewer"] for r in p["reviews"] if r["reviewer"] and r["reviewer"] != p["author"]})) or "none recorded"
        closes = ", ".join(f"#{i['number']}" for i in p["closes_issues"]) or "none"
        how = "" if p.get("link") == "linked" else " (linked via commit subject)"
        refs.add(f"pr:#{p['number']}")
        lines.append(f"  [pr:#{p['number']}] {p['state']} {_d(p['merged_at'] or p['created_at'])} by {p['author']}: "
                     f"{_flat(p['title'], snip)}{how}. Description: {_flat(p['body'], snip * 2) or 'none'} "
                     f"Reviewed by: {revs}. Closes issues: {closes}.")
    if history["issues"]:
        lines.append("\nISSUES THESE CHANGES CLOSED")
    for i in history["issues"][:n_prs]:
        refs.add(f"issue:#{i['number']}")
        lines.append(f"  [issue:#{i['number']}] {i['state']} {_d(i['created_at'])} by {i['author']}: "
                     f"{_flat(i['title'], snip)}. Description: {_flat(i['body'], snip * 2) or 'none'}")

    lines.append("\nPEOPLE AND SIGNALS")
    people = "; ".join(f"{a['name']}{' (bot)' if a['is_bot'] else ''} {a['commits']} commits ({_d(a['first'])} to {_d(a['last'])})"
                       for a in history["authors"][:6]) or "none"
    fact(f"Authors of the commits that changed these lines (as listed above, counted within the shown history): {people}")
    if history["reviewers"]:
        fact("Reviewers of the pull requests above (own PRs excluded): "
             + "; ".join(f"{n} {c} PRs" for n, c in history["reviewers"][:6]))
    a = history["file_assessment"]
    if a.get("available"):
        sig = "; ".join(f"{s['name']} - {s['detail']}" for s in a["risk_signals"]) or "none triggered"
        fact(f"Signals for the whole file {path} (heuristic, not a finding about any person): risk level {a['risk_level']}; "
             f"top commit author {a['top_contributor']} with {a['top_commit_share']:.0%} of {a['total_commits']} commits; "
             f"{a['effective_contributors']} effective contributors; triggered: {sig}")
    return "\n".join(lines), refs


def build_explain_context(repo, path, label, start, end, code_lines, history, max_chars=16000) -> Context:
    for i, (n_code, n_commits, n_prs, snip) in enumerate(SIZES):
        text, refs = _render(repo, path, label, start, end, code_lines, history, n_code, n_commits, n_prs, snip)
        if len(text) <= max_chars or i == len(SIZES) - 1:
            break
    truncated = i > 0 or len(code_lines) > SIZES[0][0]
    if i > 0:
        text += "\n\nCONTEXT NOTE: some results were omitted to fit the size limit."
    return Context(text, refs, {int(n) for n in NUM.findall(text)}, set(HEX.findall(text.lower())), truncated, empty=False)
