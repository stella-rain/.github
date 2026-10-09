#!/usr/bin/env bash
# One-time setup of the Stella Rain organization Project and command labels (ADR-044).
#
# Run from local Claude Code or a terminal with your own gh login. Cloud sessions cannot
# do this: they have no access to the Project API.
#
#   gh auth refresh -h github.com -s project      # once: adds the Project scope to your login
#   bash scripts/setup-project.sh                 # safe to re-run; it skips what exists
#
# Not automated (the API cannot do it): the Status options, the views, and the Project's
# built-in workflows. The setup runbook in the app repo lists those clicks. A field that
# exists is skipped, so changing the options of an existing field (for example Verification)
# is also a click: rename an option in the Project's field settings to keep its items.
set -euo pipefail

ORG=${ORG:-stella-rain}
TITLE=${TITLE:-"Stella Rain"}
SYNCED_REPOS=${SYNCED_REPOS:-"app core"}
# Phase options, comma separated. Unset: Stella Rain's. Set to empty: the project has no Phase
# field and no cmd:phase-* labels. The nth option is set by cmd:phase-p<n-1>.
PHASES=${PHASES-"P0 Android spike,P1 Vertical slice,P2 Editor + replay + publish,P3 Closed test,P4 Ads"}

need() { command -v "$1" >/dev/null || { echo "missing: $1" >&2; exit 1; }; }
need jq
if [ -n "${DRY_RUN:-}" ]; then
  # DRY_RUN is a file: every gh command is appended to it and nothing is changed (the tests).
  gh() {
    echo "gh $*" >> "$DRY_RUN"
    case "$1 $2" in
      "project list") echo '{"projects":[]}' ;;
      "project create") echo '{"number":9}' ;;
      "project field-list") echo '{"fields":[]}' ;;
    esac
  }
else
  need gh
fi

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
  --description "Issues and roadmap for every $TITLE repository" >/dev/null

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
if [ -n "$PHASES" ]; then add_select "Phase" "$PHASES"; fi
add_select "Verification" "Verified,NOT VERIFIED,Needs Windows,Needs macOS,Needs Android device,Needs iPhone"
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
  if [ -n "$PHASES" ]; then
    phase_count=$(tr ',' '
' <<<"$PHASES" | wc -l)
    for ((p = 0; p < phase_count; p++)); do
      label "$repo" "cmd:phase-p$p" "D4C5F9" "Bridge command: set Project Phase (removed once applied)"
    done
  fi
  label "$repo" "cmd:verify-verified" "0E8A16" "Bridge command: Verification = Verified"
  label "$repo" "cmd:verify-not-verified" "FBCA04" "Bridge command: Verification = NOT VERIFIED"
  for env in windows:Windows macos:macOS android:"Android device" iphone:iPhone; do
    label "$repo" "cmd:verify-needs-${env%%:*}" "D93F0B" "Bridge command: Verification = Needs ${env#*:}"
  done
  # Replaced by the four labels above: a decision is an issue assigned to a maintainer.
  gh label delete "cmd:verify-needs-kade" --repo "$ORG/$repo" --yes >/dev/null 2>&1 || true
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
  2. Views: Board, Roadmap, Waiting on Kade, one per Needs option, NOT VERIFIED, one per repository
  3. Built-in workflows: item closed -> Done, pull request merged -> Done, auto-archive
  4. The stella-rain-bridge GitHub App, its client ID variable and private key secret
Project URL: https://github.com/orgs/$ORG/projects/$number
NEXT
