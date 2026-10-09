# Stella Rain: organization `.github`

Public organization-wide files for Stella Rain: the Project bridge (ADR-031), the shared CI
checks, and the default issue forms and pull request template. It holds no project data.

## Layout

| Path | What |
|---|---|
| `scripts/project_bridge.py` | Bridge: `sync` (issue event to Project fields) and `snapshot` (Project to `STATUS.md`) |
| `scripts/claude_md_check.py` | `CLAUDE.md` at most 100 lines; `.claude/rules/*.md` at most 80 lines with `paths:` |
| `scripts/auto_merge_gate.py` | Auto-merge verdict (`merge`, `wait`, `stop`) from a commit's checks; the issues a merged PR closes |
| `scripts/test_*.py` | Unit tests for the scripts |
| `scripts/setup-project.sh` | One-time Project and label setup; needs Kade's `gh` login with the `project` scope |
| `.github/workflows/project-sync.yml` | Reusable: called by `app` and `core` on issue events |
| `.github/workflows/claude-md-check.yml` | Reusable: called by `app`, `core`, `moderation` and this repo |
| `.github/workflows/eol-check.yml` | Reusable, and runs here: LF line endings |
| `.github/workflows/auto-merge.yml` | Reusable: called by `app` and `core`; merges a green `claude/*` PR into `main` |
| `.github/workflows/test.yml` | Unit tests on push and PR |
| `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md` | Defaults for repos without their own |

## Rules

- **The bridge never prints issue titles or bodies** (Actions logs are public); keep it that
  way in every new log line, error message and test fixture.
- **Callers use `@main`.** A change merged here applies to every calling repository on its
  next run. Keep inputs, outputs and behaviour backward compatible, or change the callers in
  the same task.
- Command labels are honoured only from people with write access (ADR-031); never relax that.
- `stage-template` must never call workflows from here: creators copy it.
- The PR template's sections (*What changed and why*, *Verified*, *NOT VERIFIED*,
  *Wrong turns*) are what `repo-workflow` relies on; change them together.

## Gates

| Part | Gate |
|---|---|
| `scripts/` | `python3 -m unittest discover -s scripts -v` (CI: `test.yml`) |
| Bridge against the real Project | Kade: `scripts/check_setup.py` in `app`, or a test issue with a `cmd:` label |
| Workflows | YAML parses; NOT VERIFIED until they have run on GitHub |
| `CLAUDE.md`, line endings | `claude_md_check.py .`; CI `eol-check` |

## State and version control

- Work on this repository is tracked in `stella-rain/app` issues (only `app` and `core` sync).
- **Local sessions** (on Kade's PC): the remote file tools cannot write anywhere in this
  repository and git cannot commit here from them. Deliver every file as a zip laid out from
  the `stella-rain` root, with the commit command for Kade to run.
- Push this repository before the callers when they depend on a change here.

## Overrides of global rules

- **No auto-merge.** A cloud session opens a PR and Kade merges it; GitHub auto-merge stays
  off. A merge here reaches every calling repository on its next run.
