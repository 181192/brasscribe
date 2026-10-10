#!/usr/bin/env bash
# One issue for one thing that a scheduled or after-merge run watches, found by its exact title.
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

# The open issues, newest first; the title must be the same, not only alike.
number="$(gh issue list --repo "$repo" --state open --limit 500 --json number,title \
  | jq -r --arg title "$title" '[.[] | select(.title == $title)][0].number // empty')"

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
