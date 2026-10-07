#!/usr/bin/env bash
# One-time setup of the Stella Rain organization Project and command labels (ADR-031).
#
# Run from local Claude Code or a terminal with your own gh login. Cloud sessions cannot
# do this: they have no access to the Project API.
#
#   gh auth refresh -h github.com -s project      # once: adds the Project scope to your login
#   bash scripts/setup-project.sh                 # safe to re-run; it skips what exists
#
# Not automated (the API cannot do it): the Status options, the views, and the Project's
# built-in workflows. The setup runbook in the app repo lists those clicks.
set -euo pipefail

ORG=${ORG:-stella-rain}
TITLE=${TITLE:-"Stella Rain"}
SYNCED_REPOS=${SYNCED_REPOS:-"app core"}

need() { command -v "$1" >/dev/null || { echo "missing: $1" >&2; exit 1; }; }
need gh
need jq

echo "== Project"
number=$(gh project list --owner "$ORG" --format json --limit 100 \
  | jq -r --arg t "$TITLE" '.projects[] | select(.title == $t) | .number' | head -1)
if [ -z "$number" ]; then
  number=$(gh project create --owner "$ORG" --title "$TITLE" --format json | jq -r '.number')
  echo "created project #$number"
else
  echo "exists: project #$number"
fi
gh project edit "$number" --owner "$ORG" --visibility PRIVATE >/dev/null
gh project edit "$number" --owner "$ORG" \
  --description "Issues and roadmap for every Stella Rain repository (ADR-031)" >/dev/null

echo "== Fields"
existing=$(gh project field-list "$number" --owner "$ORG" --format json --limit 100 | jq -r '.fields[].name')
add_select() {  # name, comma-separated options
  if grep -qxF "$1" <<<"$existing"; then echo "exists: $1"; return; fi
  gh project field-create "$number" --owner "$ORG" --name "$1" \
    --data-type SINGLE_SELECT --single-select-options "$2" >/dev/null
  echo "created: $1"
}
add_date() {
  if grep -qxF "$1" <<<"$existing"; then echo "exists: $1"; return; fi
  gh project field-create "$number" --owner "$ORG" --name "$1" --data-type DATE >/dev/null
  echo "created: $1"
}
add_select "Phase" "P0 Android spike,P1 Vertical slice,P2 Editor + replay + publish,P3 Closed test,P4 Ads"
add_select "Verification" "Verified,NOT VERIFIED,Needs Kade"
add_select "Priority" "P1,P2,P3"
add_date "Start"
add_date "Target"

echo "== Link repositories and create command labels"
label() {  # repo, name, color, description
  gh label create "$2" --repo "$ORG/$1" --color "$3" --description "$4" --force >/dev/null
}
for repo in $SYNCED_REPOS; do
  gh project link "$number" --owner "$ORG" --repo "$ORG/$repo" >/dev/null 2>&1 || true
  for s in backlog next now in-review "done"; do
    label "$repo" "cmd:status-$s" "C5DEF5" "Bridge command: set Project Status (removed once applied)"
  done
  for p in 0 1 2 3 4; do
    label "$repo" "cmd:phase-p$p" "D4C5F9" "Bridge command: set Project Phase (removed once applied)"
  done
  label "$repo" "cmd:verify-verified" "0E8A16" "Bridge command: Verification = Verified"
  label "$repo" "cmd:verify-not-verified" "FBCA04" "Bridge command: Verification = NOT VERIFIED"
  label "$repo" "cmd:verify-needs-kade" "D93F0B" "Bridge command: Verification = Needs Kade"
  for p in 1 2 3; do
    label "$repo" "cmd:priority-p$p" "BFDADC" "Bridge command: set Project Priority (removed once applied)"
  done
  echo "labels ready: $ORG/$repo"
done

echo "== Organization variable"
gh variable set PROJECT_NUMBER --org "$ORG" --body "$number" --visibility selected \
  --repos "$(for r in $SYNCED_REPOS; do printf '%s,' "$r"; done | sed 's/,$//')"
echo "PROJECT_NUMBER=$number"

cat <<NEXT

Done. Still to do by hand (see app/docs/setup/project-bridge-setup.md):
  1. Status options: Backlog, Next, Now, In review, Done
  2. Views: Board, Roadmap, Needs Kade, NOT VERIFIED, one per repository
  3. Built-in workflows: item closed -> Done, pull request merged -> Done, auto-archive
  4. The stella-rain-bridge GitHub App, its client ID variable and private key secret
Project URL: https://github.com/orgs/$ORG/projects/$number
NEXT
