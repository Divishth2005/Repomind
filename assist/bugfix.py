"""Which past changes were bug fixes.

Two independent signals, both imperfect:
  * wording: the commit subject or PR title says fix / bug / crash / regression ...
  * label: the issue a PR closed carries a bug-like label (bug, defect, crash, regression)
A change counts as a fix if either fires, and the reason is kept. The wording
rule is checked against the label signal in assist/evaluate.py.
"""
import json
import re

FIX_RE = re.compile(r"\b(fix(es|ed|ing)?|bugfix|bug|bugs|crash(es|ed)?|regression|hotfix|broken)\b", re.IGNORECASE)
NOT_A_BUG_RE = re.compile(r"\b(typos?|spelling|grammar|docs?|documentation|readme|comments?|docstrings?|links?|lint(ing)?|ci|workflow|changelog)\b", re.IGNORECASE)
BUG_LABEL_RE = re.compile(r"bug|defect|crash|regression", re.IGNORECASE)


def looks_like_fix(text: str | None) -> bool:
    """Fix wording, unless the text is about docs/typos/CI, which are not bug fixes."""
    return bool(text) and bool(FIX_RE.search(text)) and not NOT_A_BUG_RE.search(text)


def has_bug_label(labels) -> bool:
    if isinstance(labels, str):
        try:
            labels = json.loads(labels)
        except ValueError:
            labels = []
    return any(BUG_LABEL_RE.search(str(l)) for l in labels or [])


def classify_change(subject: str | None, pr_title: str | None = None, issue_label_sets=()) -> list[str]:
    """Reasons this change looks like a fix (empty list = no evidence it was a fix)."""
    reasons = []
    if looks_like_fix(subject):
        reasons.append("commit subject wording")
    if looks_like_fix(pr_title):
        reasons.append("PR title wording")
    if any(has_bug_label(ls) for ls in issue_label_sets):
        reasons.append("closed an issue labelled as a bug")
    return reasons
