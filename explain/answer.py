"""Explain a piece of code together with its history (build plan Phase 10).

Flow: read the code from the local clone -> find the commits that changed
those lines -> look them up in the database (PRs, issues, reviews, people)
-> put code + history in front of the model with grounding rules -> check
the citations in the answer exactly as Module 8 does.
"""
import sqlite3

from explain.context import build_explain_context
from explain.history import gather
from explain.prompts import DEFAULT_QUESTION, SYSTEM_PROMPT, build_user_prompt
from explain.source import SourceError, find_symbols, python_symbols, read_file
from llm.answer import check_answer
from llm.client import LLMClient
from retrieval.hybrid import Retriever


def resolve_target(source: str, function: str | None, lines: tuple[int, int] | None):
    total = len(source.splitlines())
    if function:
        found = find_symbols(source, function)
        if not found:
            names = ", ".join(s.name for s in python_symbols(source)[:15])
            raise SourceError(f"No function or class named '{function}' in this file. Some that exist: {names}")
        if len(found) > 1:
            raise SourceError("'" + function + "' is ambiguous; use one of: " + ", ".join(s.name for s in found))
        s = found[0]
        return s.start, s.end, s.name
    if lines:
        a, b = lines
        if not (1 <= a <= b <= total):
            raise SourceError(f"Line range {a}-{b} is outside the file (1-{total}).")
        return a, b, f"lines {a}-{b}"
    return 1, total, "whole file"


def prepare(conn: sqlite3.Connection, repo: str, path: str, function=None, lines=None,
            max_context_chars: int = 16000, retriever: Retriever | None = None) -> dict:
    source = read_file(repo, path)
    start, end, label = resolve_target(source, function, lines)
    history = gather(conn, repo, path, start, end, retriever=retriever)
    code_lines = source.splitlines()[start - 1 : end]
    ctx = build_explain_context(repo, path, label, start, end, code_lines, history, max_context_chars)
    return {"label": label, "start": start, "end": end, "history": history, "context": ctx}


def explain(conn, repo, path, client: LLMClient, function=None, lines=None, question=None,
            max_context_chars: int = 16000, retriever: Retriever | None = None) -> dict:
    prep = prepare(conn, repo, path, function, lines, max_context_chars, retriever)
    ctx, h = prep["context"], prep["history"]
    request = question or DEFAULT_QUESTION
    resp = client.complete(SYSTEM_PROMPT, build_user_prompt(request, ctx.text))
    return {
        "repo": repo, "file": path, "target": prep["label"], "lines": [prep["start"], prep["end"]],
        "question": request, "answer": resp.text, "model": resp.model,
        "usage": {"prompt_tokens": resp.prompt_tokens, "output_tokens": resp.output_tokens,
                  "thinking_tokens": resp.thinking_tokens, "finish_reason": resp.finish_reason},
        "history": {"commits": len(h["commits"]), "prs": len(h["prs"]), "issues": len(h["issues"]),
                    "commits_missing_from_database": h["commits_missing_from_database"]},
        "context_refs": sorted(ctx.refs), "context_truncated": ctx.truncated, "context_chars": len(ctx.text),
        **check_answer(resp.text, ctx.refs, ctx.numbers, ctx.hashes),
    }
