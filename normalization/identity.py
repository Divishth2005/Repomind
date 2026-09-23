"""Identity resolution: map Git author/committer strings and GitHub logins
onto a shared Developer identity, conservatively.

Resolution strategy, strongest signal first:
  1. GitHub's own "noreply" commit email (e.g. 123+octocat@users.noreply.github.com)
     directly reveals a GitHub login -- this is the one place we can link a Git
     identity to a GitHub identity with high confidence, since GitHub itself
     generated the address.
  2. Otherwise, cluster Git commits by lowercased email (medium confidence).
  3. If no email is present at all, fall back to clustering by raw name
     (low confidence) rather than dropping the record.
GitHub-only identities (PR/issue/review authors with no matching commit
email) get their own developer keyed by login. Nothing is merged without
one of the above signals -- an unresolved identity is preserved, not deleted
or guessed away, per the build plan.
"""
import hashlib
import re
from typing import Optional

GITHUB_NOREPLY_RE = re.compile(
    r"^(?:\d+\+)?([A-Za-z0-9_.\[\]-]+)@users\.noreply\.github\.com$", re.IGNORECASE
)
BOT_RE = re.compile(r"\[bot\]$|^dependabot(-preview)?$|^github-actions$", re.IGNORECASE)


def is_bot_name(name_or_login: Optional[str]) -> bool:
    return bool(name_or_login) and bool(BOT_RE.search(name_or_login))


def extract_github_login_from_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    m = GITHUB_NOREPLY_RE.match(email.strip())
    return m.group(1) if m else None


def stable_id(*parts: str) -> str:
    key = "||".join(p.lower().strip() for p in parts if p)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


class IdentityResolver:
    def __init__(self):
        self._by_login: dict[str, str] = {}
        self._by_email: dict[str, str] = {}
        self._by_name_only: dict[str, str] = {}
        self.developers: dict[str, dict] = {}

    def _new_developer(self, dev_id, login, name, email_norm, confidence, source, bot):
        self.developers[dev_id] = {
            "developer_id": dev_id,
            "github_login": login,
            "display_name": name,
            "email_hash": stable_id("email", email_norm) if email_norm else None,
            "is_bot": bot,
            "identity_confidence": confidence,
            "identity_sources": [source],
        }

    def resolve_git_identity(self, name: Optional[str], email: Optional[str]) -> str:
        email_norm = (email or "").strip().lower()
        login = extract_github_login_from_email(email_norm)
        bot = is_bot_name(name) or is_bot_name(login)

        if login and login in self._by_login:
            dev_id = self._by_login[login]
        elif email_norm and email_norm in self._by_email:
            dev_id = self._by_email[email_norm]
        elif not email_norm and name and name in self._by_name_only:
            dev_id = self._by_name_only[name]
        elif login:
            dev_id = stable_id("login", login)
            self._new_developer(dev_id, login, name, email_norm, "high", "git_noreply_email", bot)
        elif email_norm:
            dev_id = stable_id("email", email_norm)
            self._new_developer(dev_id, None, name, email_norm, "medium", "git_email", bot)
        else:
            dev_id = stable_id("name", name or "unknown")
            self._new_developer(dev_id, None, name, None, "low", "git_name_only", bot)

        if login:
            self._by_login[login] = dev_id
        if email_norm:
            self._by_email[email_norm] = dev_id
        if not email_norm and name:
            self._by_name_only[name] = dev_id

        dev = self.developers.get(dev_id)
        if dev is not None and not dev.get("display_name") and name:
            dev["display_name"] = name

        return dev_id

    def resolve_github_login(self, login: Optional[str]) -> Optional[str]:
        if not login:
            return None
        bot = is_bot_name(login)
        if login in self._by_login:
            return self._by_login[login]

        dev_id = stable_id("login", login)
        self._new_developer(dev_id, login, login, None, "medium", "github_login_only", bot)
        self._by_login[login] = dev_id
        return dev_id
