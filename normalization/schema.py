"""Normalized entity shapes (plain dicts, not ORM models -- kept simple for
a SQLite-backed prototype). See docs/DATA_MODEL.md for field definitions.
"""
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Repository:
    repository_id: str
    owner: str
    name: str
    url: str
    default_branch: Optional[str] = None
    head_sha: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class Developer:
    developer_id: str
    github_login: Optional[str]
    display_name: Optional[str]
    email_hash: Optional[str]
    is_bot: bool
    identity_confidence: str  # high | medium | low
    identity_sources: list

    def to_dict(self):
        return asdict(self)


@dataclass
class File:
    file_id: str
    repository_id: str
    path: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Commit:
    commit_id: str
    repository_id: str
    author_developer_id: str
    committer_developer_id: str
    timestamp: str
    subject: str
    body: str
    parent_shas: list
    is_merge: bool
    raw_source_reference: str

    def to_dict(self):
        return asdict(self)


@dataclass
class CommitFile:
    commit_file_id: str
    commit_id: str
    file_id: str
    additions: Optional[int]
    deletions: Optional[int]

    def to_dict(self):
        return asdict(self)


@dataclass
class Issue:
    issue_id: str
    repository_id: str
    github_number: int
    title: str
    body: str
    state: str
    author_developer_id: Optional[str]
    created_at: Optional[str]
    closed_at: Optional[str]
    labels: list
    raw_source_reference: str

    def to_dict(self):
        return asdict(self)


@dataclass
class PullRequest:
    pr_id: str
    repository_id: str
    github_number: int
    title: str
    body: str
    state: str
    author_developer_id: Optional[str]
    created_at: Optional[str]
    merged_at: Optional[str]
    labels: list
    commit_shas: list
    closing_issue_numbers: list
    raw_source_reference: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Review:
    review_id: str
    pr_id: str
    reviewer_developer_id: Optional[str]
    state: str
    submitted_at: Optional[str]
    body: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Label:
    label_id: str
    repository_id: str
    name: str
    color: str

    def to_dict(self):
        return asdict(self)
