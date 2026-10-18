# Stella Rain: organization `.github`

Public organization-wide files for Stella Rain: the Project bridge (ADR-044), the shared CI
checks, and the default issue forms and pull request template. It holds no project data.

## Layout

| Path | What |
|---|---|
| `scripts/project_bridge.py` | Bridge: `sync` (issue event to Project fields) and `snapshot` (Project to `STATUS.md`) |
| `scripts/claude_md_check.py` | `CLAUDE.md` at most 100 lines; `.claude/rules/*.md` at most 80 lines with `paths:` |
| `scripts/auto_merge_gate.py` | Auto-merge verdict (`merge`, `wait`, `stop`) from a commit's checks, required checks, draft state and changed files; the issues a merged PR closes |
| `scripts/branch_cleanup.py` | Which `claude/*` and `gate/*` branches to delete: a merged PR's branch still at its head, and a gate branch whose task has no branch or open PR left |
| `scripts/gate_check.py` | gate-check verdict: the gates a PR's files need (from the caller's spec), each covered by a passing run on `gate/<name>/<task>` (app's ADR-063) |
| `scripts/repo_check.py` | No environment, key or keystore file is tracked, and no private key block, AWS access key ID or GitHub token in a text file; prints file, line and kind, never the value |
| `scripts/test_*.py` | Unit tests for the scripts |
| `scripts/setup-project.sh` | One-time Project and label setup; needs Kade's `gh` login with the `project` scope |
| `.github/workflows/project-sync.yml` | Reusable: called by `app` and `core` on issue events |
| `.github/workflows/claude-md-check.yml` | Reusable: called by `app`, `core`, `moderation` and this repo |
| `.github/workflows/eol-check.yml` | Reusable, and runs here: LF line endings |
| `.github/workflows/auto-merge.yml` | Reusable: called by `app` and `core`; merges a green `claude/*` PR into `main`; optional inputs `require` (checks) and `protected` (paths); output `merged`; drafts and PRs touching `.github/workflows/` are left to Kade |
| `.github/workflows/test.yml` | Unit tests on push and PR |
| `.github/workflows/branch-cleanup.yml` | Reusable, and runs here: deletes merged `claude/*` branches and leftover `gate/*` branches; called by `app`, `core` and `moderation` |
| `.github/workflows/gate-check.yml` | Reusable: gate-check on PRs into `main`; input `gates`, one per line: name, workflow, paths (app's ADR-063) |
| `.github/workflows/delete-gate-branch.yml` | Reusable: a gate workflow's last job; deletes the run's `gate/*` branch under a lease, never failing the run |
| `.github/workflows/actionlint.yml` | Reusable, and runs here: actionlint (with shellcheck) on PRs that touch `.github/workflows/`; a pinned, checksum-checked release |
| `.github/workflows/repo-check.yml` | Reusable, and runs here: `repo_check.py` on every PR and push to `main`; called by `core` and `moderation`, never by `stage-template` |
| `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md` | Defaults for repos without their own |

## Rules

- **The bridge never prints issue titles or bodies** (Actions logs are public); keep it that
  way in every new log line, error message and test fixture.
- **Callers use `@main`.** A change merged here applies to every calling repository on its
  next run. Keep inputs, outputs and behaviour backward compatible, or change the callers in
  the same task.
- The reusable workflows `app` calls take an optional `runs-on` input (JSON, default
  `"ubuntu-latest"`): `app` points it at its self-hosted runners (app's ADR-096). Public
  callers never pass it; a self-hosted runner never runs a public repository's jobs.
- Command labels are honoured only from people with write access (ADR-044); never relax that.
- `stage-template` must never call workflows from here: creators copy it.
- The PR template's sections (*What changed and why*, *Verified*, *NOT VERIFIED*,
  *Wrong turns*) are what `repo-workflow` relies on; change them together.

## Gates

| Part | Gate |
|---|---|
| `scripts/` | `python3 -m unittest discover -s scripts -v` (CI: `test.yml`) |
| Bridge against the real Project | Kade: `check_setup.py` in `app`, or a test issue with a `cmd:` label |
| Workflows | YAML parses; NOT VERIFIED until they have run on GitHub |
| `CLAUDE.md`, line endings | `claude_md_check.py .`; CI `eol-check` |

## State and version control

- Work on this repository is tracked in `stella-rain/app` issues (only `app` and `core` sync).
- **Local and cloud sessions** work on `claude/<task>`; a task may hold several commits and
  gets one PR. Kade merges it (see Overrides). On the Windows PC the remote file tools cannot
  write anywhere in this repository and git cannot commit here from them: deliver every file
  there as a zip laid out from the `stella-rain` root, with the commands for Kade to run
  (branch, commit, push, PR).
- Push this repository before the callers when they depend on a change here.

## Overrides of global rules

- **No auto-merge.** A cloud session opens a PR and Kade merges it; GitHub auto-merge stays
  off. A merge here reaches every calling repository on its next run.
