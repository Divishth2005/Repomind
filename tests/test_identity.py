from normalization.identity import (
    IdentityResolver,
    extract_github_login_from_email,
    is_bot_name,
)


def test_extract_login_from_noreply_email_with_id_prefix():
    assert extract_github_login_from_email("12345+octocat@users.noreply.github.com") == "octocat"


def test_extract_login_from_noreply_email_without_id_prefix():
    assert extract_github_login_from_email("octocat@users.noreply.github.com") == "octocat"


def test_extract_login_returns_none_for_regular_email():
    assert extract_github_login_from_email("octocat@example.com") is None


def test_extract_login_returns_none_for_missing_email():
    assert extract_github_login_from_email(None) is None


def test_bot_detection():
    assert is_bot_name("dependabot[bot]")
    assert is_bot_name("github-actions[bot]")
    assert not is_bot_name("David Lord")


def test_same_email_clusters_to_same_developer():
    r = IdentityResolver()
    d1 = r.resolve_git_identity("John Doe", "john@example.com")
    d2 = r.resolve_git_identity("john.doe", "John@Example.com")  # case-insensitive
    assert d1 == d2
    assert len(r.developers) == 1


def test_noreply_email_links_to_github_login_with_high_confidence():
    r = IdentityResolver()
    dev_id = r.resolve_git_identity("Some Name", "42+octocat@users.noreply.github.com")
    dev = r.developers[dev_id]
    assert dev["github_login"] == "octocat"
    assert dev["identity_confidence"] == "high"


def test_git_noreply_identity_merges_with_github_login_identity():
    r = IdentityResolver()
    git_dev_id = r.resolve_git_identity("Octo Cat", "octocat@users.noreply.github.com")
    gh_dev_id = r.resolve_github_login("octocat")
    assert git_dev_id == gh_dev_id


def test_different_emails_stay_separate_when_unresolved():
    r = IdentityResolver()
    d1 = r.resolve_git_identity("A", "a@example.com")
    d2 = r.resolve_git_identity("B", "b@example.com")
    assert d1 != d2


def test_no_email_falls_back_to_name_with_low_confidence():
    r = IdentityResolver()
    dev_id = r.resolve_git_identity("Anonymous Dev", None)
    assert r.developers[dev_id]["identity_confidence"] == "low"


def test_github_login_only_developer_is_medium_confidence():
    r = IdentityResolver()
    dev_id = r.resolve_github_login("someuser")
    assert r.developers[dev_id]["identity_confidence"] == "medium"
    assert r.developers[dev_id]["identity_sources"] == ["github_login_only"]
