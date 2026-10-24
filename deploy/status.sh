#!/usr/bin/env bash
# Wait for the deploy workflow's run on a pushed commit and print its result and URLs: deploy/status.sh [commit]
# (default HEAD). Exits non-zero if the run failed. Needs only read access to Actions (gh). See deploy/README.md.
set -euo pipefail
sha=$(git rev-parse "${1:-HEAD}")

id=
for _ in $(seq 18); do   # a run appears a few seconds after the push
  id=$(gh run list --workflow deploy.yml --commit "$sha" --limit 1 --json databaseId --jq '.[0].databaseId // empty')
  [ -n "$id" ] && break
  sleep 10
done
if [ -z "$id" ]; then
  echo "no deploy run for ${sha:0:7}: not pushed, not on main or a preview* branch, or it changes nothing under css-physics/, js-minus-js/, paint/, deploy/" >&2
  exit 1
fi

status=0
gh run watch "$id" --exit-status --interval 15 > /dev/null || status=$?
# the run's jobs, then its annotations: one notice per deployment with its URL, errors from the checks
gh run view "$id"
exit "$status"
