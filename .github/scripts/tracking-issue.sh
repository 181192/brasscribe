#!/usr/bin/env bash
# One issue for one thing that a scheduled or after-merge run watches, found by its exact title among the issues
# that GitHub Actions opened: an issue someone else opens with the same title is never touched.
#
#   .github/scripts/tracking-issue.sh failing TITLE BODY_FILE   open the issue with that body, or add the body as
#                                                               a comment to the one already open
#   .github/scripts/tracking-issue.sh passing TITLE BODY_FILE   close the open one, with the body as a comment;
#                                                               nothing when none is open
#
# So there is never more than one open issue with the title. Needs gh, GH_TOKEN with issues: write, and
# GITHUB_REPOSITORY. DRY_RUN=1 prints what it would do.
set -euo pipefail
state="$1" title="$2" body="$3"
repo="${GITHUB_REPOSITORY:?}"

run() { if [ -n "${DRY_RUN:-}" ]; then printf 'would run:'; printf ' %q' "$@"; printf '\n'; else "$@"; fi; }

# The open issues that this workflow's own account opened; the title must be the same, not only alike.
author="${TRACKING_ISSUE_AUTHOR:-github-actions[bot]}"
number="$(gh api --paginate "repos/$repo/issues?state=open&per_page=100" \
  | jq -r --arg title "$title" --arg author "$author" \
      '.[] | select(.pull_request | not) | select(.user.login == $author and .title == $title) | .number' | head -1)"

case "$state" in
  failing)
    if [ -n "$number" ]; then
      echo "issue #$number is open: adding a comment"
      run gh issue comment "$number" --repo "$repo" --body-file "$body"
    else
      echo "opening an issue"
      run gh issue create --repo "$repo" --title "$title" --body-file "$body"
    fi
    ;;
  passing)
    if [ -n "$number" ]; then
      echo "closing issue #$number"
      run gh issue close "$number" --repo "$repo" --comment "$(cat "$body")"
    else
      echo "no open issue: nothing to do"
    fi
    ;;
  *) echo "tracking-issue: failing or passing, not '$state'" >&2; exit 2 ;;
esac
