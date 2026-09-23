"""GraphQL query templates for GitHub repository acquisition.

Each query is paginated via a $cursor variable and returns its own
rateLimit block so the client can back off before hitting API limits.
"""

ISSUES_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  rateLimit { remaining resetAt }
  repository(owner: $owner, name: $name) {
    issues(first: 50, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        body
        state
        createdAt
        closedAt
        author { login }
        labels(first: 20) { nodes { name color } }
      }
    }
  }
}
"""

PULL_REQUESTS_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  rateLimit { remaining resetAt }
  repository(owner: $owner, name: $name) {
    pullRequests(first: 25, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        body
        state
        createdAt
        mergedAt
        author { login }
        labels(first: 20) { nodes { name color } }
        commits(first: 100) { nodes { commit { oid } } }
        closingIssuesReferences(first: 10) { nodes { number } }
        reviews(first: 50) {
          nodes {
            state
            submittedAt
            body
            author { login }
          }
        }
      }
    }
  }
}
"""

LABELS_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  rateLimit { remaining resetAt }
  repository(owner: $owner, name: $name) {
    labels(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { name color }
    }
  }
}
"""
