"""LLM access, kept behind a tiny interface so the provider can change.

GeminiClient talks to Google's Gemini REST API with `requests` (no extra SDK).
The API key is read from GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment
or the git-ignored .env file, sent only in a request header, and never logged
or included in error messages.

FakeClient is a scripted stand-in used by the tests and by --dry-run style
checks; it makes no network calls.
"""
import os
import re
import time
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

load_dotenv()

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash"  # Google's suggested replacement once 2.5 closed to new accounts; override with LLM_MODEL


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    finish_reason: str | None = None


class LLMClient:
    model: str = "unknown"

    def complete(self, system: str, user: str, max_output_tokens: int = 4096) -> LLMResponse:
        raise NotImplementedError


class GeminiClient(LLMClient):
    def __init__(self, api_key=None, model=None, timeout=120, max_retries=4, min_interval=0.0, post=None, sleep=time.sleep):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise LLMError(
                "No Gemini API key found. Create one at https://aistudio.google.com/apikey, then add a line "
                "GEMINI_API_KEY=<your key> to the .env file in the project folder (do not paste it into chat or code)."
            )
        self.model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        self.timeout, self.max_retries, self.min_interval = timeout, max_retries, min_interval
        self._post = post or requests.post
        self._get = requests.get
        self._sleep = sleep
        self._last_call = 0.0

    def _headers(self):
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _pace(self):
        wait = self.min_interval - (time.time() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.time()

    @staticmethod
    def _api_message(resp) -> str:
        try:
            return str(resp.json().get("error", {}).get("message", ""))[:300]
        except Exception:
            return (resp.text or "")[:300]

    def complete(self, system, user, max_output_tokens=4096) -> LLMResponse:
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_output_tokens},
        }
        url = f"{API_ROOT}/models/{self.model}:generateContent"
        last = None
        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                resp = self._post(url, headers=self._headers(), json=body, timeout=self.timeout)
            except requests.RequestException as e:
                last = f"network error: {type(e).__name__}"
                self._sleep(min(2 ** attempt, 30))
                continue
            if resp.status_code == 200:
                return self._parse(resp.json())
            msg = self._api_message(resp)
            if resp.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {resp.status_code}: {msg}"
                m = re.search(r"retry in ([\d.]+)s", msg)
                self._sleep(min(float(m.group(1)) + 1 if m else 2 ** (attempt + 1), 65))
                continue
            if resp.status_code in (400, 401, 403) and "key" in msg.lower():
                raise LLMError("Gemini rejected the API key (check GEMINI_API_KEY in .env).")
            if resp.status_code == 403:
                raise LLMError(f"Google refused this API key's project for model '{self.model}': {msg} "
                               "(an account or project restriction, not a problem in this code; try a key made in a "
                               "new project with a personal Google account, or check the project in Google AI Studio).")
            if resp.status_code == 404:
                raise LLMError(f"Model '{self.model}' is unavailable: {msg} Run: python -m llm.cli --list-models "
                               "and set LLM_MODEL in .env to a model that works for your key.")
            raise LLMError(f"Gemini error HTTP {resp.status_code}: {msg}")
        raise LLMError(f"Gemini request failed after {self.max_retries + 1} attempts ({last}).")

    def _parse(self, data: dict) -> LLMResponse:
        cands = data.get("candidates") or []
        if not cands:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise LLMError(f"Gemini returned no answer (blocked: {block or 'unknown reason'}).")
        cand = cands[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        reason = cand.get("finishReason")
        if not text:
            raise LLMError(f"Gemini returned an empty answer (finish reason: {reason}). "
                           "If MAX_TOKENS, the model spent its budget on reasoning; retry or raise the limit.")
        u = data.get("usageMetadata") or {}
        return LLMResponse(text, self.model, u.get("promptTokenCount"), u.get("candidatesTokenCount"),
                           u.get("thoughtsTokenCount"), reason)

    def list_models(self) -> list[str]:
        resp = self._get(f"{API_ROOT}/models", headers=self._headers(), params={"pageSize": 200}, timeout=self.timeout)
        if resp.status_code != 200:
            raise LLMError(f"Could not list models: HTTP {resp.status_code}: {self._api_message(resp)}")
        return sorted(
            m["name"].split("/", 1)[-1] for m in resp.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", []))


@dataclass
class FakeClient(LLMClient):
    """Scripted stand-in: `responder(system, user) -> text`. Records every call."""
    responder: object = None
    model: str = "fake"
    calls: list = field(default_factory=list)

    def complete(self, system, user, max_output_tokens=4096) -> LLMResponse:
        self.calls.append((system, user))
        text = self.responder(system, user) if self.responder else "fake answer"
        return LLMResponse(text, self.model, len(user) // 4, len(text) // 4, None, "STOP")


def make_client(provider: str | None = None, model: str | None = None, **kw) -> LLMClient:
    provider = (provider or os.environ.get("LLM_PROVIDER") or "gemini").lower()
    if provider == "gemini":
        return GeminiClient(model=model, **kw)
    raise LLMError(f"Unknown provider '{provider}'. Supported: gemini.")
