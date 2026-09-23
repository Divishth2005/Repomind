"""Clone or update a local mirror of a public GitHub repository."""
from pathlib import Path

from git import Repo


def repo_slug_to_url(slug: str) -> str:
    """'owner/name' -> full clone URL. A full URL is passed through unchanged."""
    if slug.startswith("http://") or slug.startswith("https://") or slug.endswith(".git"):
        return slug
    return f"https://github.com/{slug}.git"


def clone_or_update(slug: str, workdir: Path) -> Repo:
    """Ensure a full-history local clone of `slug` exists under `workdir`, return it.

    Idempotent: re-running fetches new commits instead of re-cloning.
    """
    workdir = Path(workdir)
    repo_name = slug.rstrip("/").split("/")[-1].removesuffix(".git")
    dest = workdir / repo_name

    if dest.exists() and (dest / ".git").exists():
        repo = Repo(dest)
        origin = repo.remotes.origin
        origin.fetch()
        return repo

    dest.parent.mkdir(parents=True, exist_ok=True)
    url = repo_slug_to_url(slug)
    return Repo.clone_from(url, dest)
