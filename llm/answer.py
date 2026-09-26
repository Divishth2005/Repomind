"""Question -> retrieval -> evidence context -> LLM -> checked answer.

Checks made on every answer (all mechanical):
  * citations: each [kind:id] the model cites must be an id that was shown
    in the evidence; unknown ones are reported as invalid
  * identifiers: PR/issue numbers (#123) and commit hashes in the answer that
    never appear in the evidence are reported as unverified
These catch invented references. They do NOT prove that a cited item really
supports the sentence it is attached to; that needs a human (or a judge).

If retrieval finds nothing relevant the model is not called at all.
"""
import re
import sqlite3

from llm.client import LLMClient
from llm.context_builder import HEX, NUM, build_context
from llm.prompts import SYSTEM_PROMPT, build_user_prompt
from retrieval.hybrid import Retriever

CITE = re.compile(r"\[((?:commit|pr|issue|review|fact|code|cochange):[^\]\s]+)\]")
NO_EVIDENCE_REPLY = ("I could not find repository evidence relevant to this question, so I can't answer it. "
                     "Try naming a file, directory, PR/issue number or person that exists in this repository.")
ABSTAIN = re.compile(
    r"not enough (evidence|information)|insufficient|no (repository )?evidence|does not (contain|include|provide)|"
    r"doesn't (contain|include|provide)|cannot (answer|determine|find)|can't (answer|determine|find)|"
    r"could not find|not (found|available|present)|no (record|information|data|match)", re.IGNORECASE)


def check_answer(text: str, refs: set, numbers: set, hashes: set) -> dict:
    cited = list(dict.fromkeys(CITE.findall(text)))
    body = CITE.sub("", text)
    seen_numbers = {int(n) for n in NUM.findall(body)}
    seen_hashes = {h for h in HEX.findall(body.lower()) if not h.isdigit()}
    return {
        "citations": cited,
        "invalid_citations": [c for c in cited if c not in refs],
        "unverified_identifiers": sorted(f"#{n}" for n in seen_numbers - numbers)
        + sorted(h for h in seen_hashes if not any(k.startswith(h) or h.startswith(k) for k in hashes)),
        "abstained": bool(ABSTAIN.search(text)),
    }


def answer_question(conn: sqlite3.Connection, repo: str, question: str, client: LLMClient,
                    retriever: Retriever | None = None, max_context_chars: int = 14000) -> dict:
    retriever = retriever or Retriever(conn, repo)
    retrieval = retriever.retrieve(question)
    ctx = build_context(retrieval, repo, max_context_chars)
    base = {"question": question, "repo": repo, "plan": retrieval["plan"], "retrieval_notes": retrieval["notes"],
            "context_refs": sorted(ctx.refs), "context_truncated": ctx.truncated, "context_chars": len(ctx.text)}
    if ctx.empty:
        return {**base, "answer": NO_EVIDENCE_REPLY, "llm_called": False, "model": None, "usage": None,
                "citations": [], "invalid_citations": [], "unverified_identifiers": [], "abstained": True}
    resp = client.complete(SYSTEM_PROMPT, build_user_prompt(question, ctx.text))
    return {**base, "answer": resp.text, "llm_called": True, "model": resp.model,
            "usage": {"prompt_tokens": resp.prompt_tokens, "output_tokens": resp.output_tokens,
                      "thinking_tokens": resp.thinking_tokens, "finish_reason": resp.finish_reason},
            **check_answer(resp.text, ctx.refs, ctx.numbers, ctx.hashes)}


def prepare_prompt(conn, repo, question, retriever=None, max_context_chars=14000) -> dict:
    """Everything up to (not including) the model call, for --dry-run."""
    retriever = retriever or Retriever(conn, repo)
    retrieval = retriever.retrieve(question)
    ctx = build_context(retrieval, repo, max_context_chars)
    return {"system": SYSTEM_PROMPT, "user": build_user_prompt(question, ctx.text), "context": ctx,
            "would_call_llm": not ctx.empty}
