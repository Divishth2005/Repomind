"""Engineering briefing: history-based things to check before changing code.
Same grounding checks as Modules 8-9 (cited ids must have been shown)."""
import sqlite3

from assist.briefing import gather_briefing
from assist.context import build_briefing_context
from assist.prompts import DEFAULT_REQUEST, SYSTEM_PROMPT, build_user_prompt
from llm.answer import check_answer
from llm.client import LLMClient


def prepare(conn: sqlite3.Connection, repo, path, function=None, lines=None, plan=None, max_context_chars=14000, **kw) -> dict:
    b = gather_briefing(conn, repo, path, function, lines, **kw)
    return {"briefing": b, "context": build_briefing_context(repo, path, b, plan, max_context_chars)}


def brief(conn, repo, path, client: LLMClient, function=None, lines=None, plan=None, max_context_chars=14000, **kw) -> dict:
    prep = prepare(conn, repo, path, function, lines, plan, max_context_chars, **kw)
    ctx, b = prep["context"], prep["briefing"]
    resp = client.complete(SYSTEM_PROMPT, build_user_prompt(DEFAULT_REQUEST, ctx.text))
    return {
        "repo": repo, "file": path, "target": b["label"], "lines": [b["start"], b["end"]], "plan": plan,
        "answer": resp.text, "model": resp.model,
        "usage": {"prompt_tokens": resp.prompt_tokens, "output_tokens": resp.output_tokens, "thinking_tokens": resp.thinking_tokens},
        "evidence": {"commits_changing_lines": b["history"]["range_commits_found_in_git"], "fix_like": len(b["fixes"]),
                     "cochange_files": len(b["cochange"]["code"]) + len(b["cochange"]["tests"]) + len(b["cochange"]["housekeeping"]),
                     "open_issues": len(b["open_issues"])},
        "context_refs": sorted(ctx.refs), "context_truncated": ctx.truncated,
        **check_answer(resp.text, ctx.refs, ctx.numbers, ctx.hashes),
    }
