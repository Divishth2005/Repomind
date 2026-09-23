-- RepoMind normalized relational schema (SQLite).
-- Mirrors normalization/schema.py. Regeneratable from data/processed/*.jsonl
-- at any time -- this database is a derived artifact, not a source of truth.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS repository (
    repository_id   TEXT PRIMARY KEY,
    owner           TEXT NOT NULL,
    name            TEXT NOT NULL,
    url             TEXT,
    default_branch  TEXT,
    head_sha        TEXT
);

CREATE TABLE IF NOT EXISTS developer (
    developer_id        TEXT PRIMARY KEY,
    github_login         TEXT,
    display_name          TEXT,
    email_hash            TEXT,
    is_bot                 INTEGER NOT NULL DEFAULT 0,
    identity_confidence    TEXT,
    identity_sources       TEXT  -- JSON array
);
CREATE INDEX IF NOT EXISTS idx_developer_login ON developer(github_login);

CREATE TABLE IF NOT EXISTS file (
    file_id         TEXT PRIMARY KEY,
    repository_id   TEXT NOT NULL REFERENCES repository(repository_id),
    path            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_file_repo_path ON file(repository_id, path);

CREATE TABLE IF NOT EXISTS commit_ (
    commit_id               TEXT PRIMARY KEY,
    repository_id           TEXT NOT NULL REFERENCES repository(repository_id),
    author_developer_id      TEXT REFERENCES developer(developer_id),
    committer_developer_id    TEXT REFERENCES developer(developer_id),
    timestamp                 TEXT,
    subject                    TEXT,
    body                        TEXT,
    parent_shas                  TEXT,  -- JSON array
    is_merge                      INTEGER NOT NULL DEFAULT 0,
    raw_source_reference           TEXT
);
CREATE INDEX IF NOT EXISTS idx_commit_repo ON commit_(repository_id);
CREATE INDEX IF NOT EXISTS idx_commit_author ON commit_(author_developer_id);
CREATE INDEX IF NOT EXISTS idx_commit_timestamp ON commit_(timestamp);

CREATE TABLE IF NOT EXISTS commit_file (
    commit_file_id   TEXT PRIMARY KEY,
    commit_id         TEXT NOT NULL REFERENCES commit_(commit_id),
    file_id            TEXT NOT NULL REFERENCES file(file_id),
    additions           INTEGER,
    deletions            INTEGER
);
CREATE INDEX IF NOT EXISTS idx_commit_file_commit ON commit_file(commit_id);
CREATE INDEX IF NOT EXISTS idx_commit_file_file ON commit_file(file_id);

CREATE TABLE IF NOT EXISTS issue (
    issue_id           TEXT PRIMARY KEY,
    repository_id       TEXT NOT NULL REFERENCES repository(repository_id),
    github_number         INTEGER,
    title                   TEXT,
    body                     TEXT,
    state                     TEXT,
    author_developer_id        TEXT REFERENCES developer(developer_id),
    created_at                  TEXT,
    closed_at                    TEXT,
    labels                        TEXT,  -- JSON array
    raw_source_reference            TEXT
);
CREATE INDEX IF NOT EXISTS idx_issue_repo ON issue(repository_id);
CREATE INDEX IF NOT EXISTS idx_issue_author ON issue(author_developer_id);

CREATE TABLE IF NOT EXISTS pull_request (
    pr_id                    TEXT PRIMARY KEY,
    repository_id             TEXT NOT NULL REFERENCES repository(repository_id),
    github_number               INTEGER,
    title                         TEXT,
    body                           TEXT,
    state                           TEXT,
    author_developer_id               TEXT REFERENCES developer(developer_id),
    created_at                         TEXT,
    merged_at                           TEXT,
    labels                                TEXT,  -- JSON array
    commit_shas                            TEXT,  -- JSON array
    closing_issue_numbers                    TEXT,  -- JSON array
    raw_source_reference                       TEXT
);
CREATE INDEX IF NOT EXISTS idx_pr_repo ON pull_request(repository_id);
CREATE INDEX IF NOT EXISTS idx_pr_author ON pull_request(author_developer_id);

CREATE TABLE IF NOT EXISTS review (
    review_id                TEXT PRIMARY KEY,
    pr_id                      TEXT NOT NULL REFERENCES pull_request(pr_id),
    reviewer_developer_id        TEXT REFERENCES developer(developer_id),
    state                          TEXT,
    submitted_at                     TEXT,
    body                                TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_pr ON review(pr_id);
CREATE INDEX IF NOT EXISTS idx_review_reviewer ON review(reviewer_developer_id);

CREATE TABLE IF NOT EXISTS label (
    label_id         TEXT PRIMARY KEY,
    repository_id     TEXT NOT NULL REFERENCES repository(repository_id),
    name                TEXT,
    color                 TEXT
);

-- PR <-> Commit is many-to-many via PullRequest.commit_shas; materialized
-- here as its own edge table so it can be joined/indexed directly.
CREATE TABLE IF NOT EXISTS pr_commit (
    pr_id       TEXT NOT NULL REFERENCES pull_request(pr_id),
    commit_id   TEXT NOT NULL,
    PRIMARY KEY (pr_id, commit_id)
);

-- PR <-> Issue ("closes #N") likewise materialized as an edge table.
CREATE TABLE IF NOT EXISTS pr_issue (
    pr_id           TEXT NOT NULL REFERENCES pull_request(pr_id),
    issue_number    INTEGER NOT NULL,
    PRIMARY KEY (pr_id, issue_number)
);
