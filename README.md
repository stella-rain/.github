# stella-rain/.github

Organization-wide files for **Stella Rain**:

- Default issue forms and the pull request template for every repository that has none of its own.
- The **Project bridge** (ADR-031): `scripts/project_bridge.py` and the reusable workflow
  `.github/workflows/project-sync.yml`, which add issues to the organization Project and apply
  command labels such as `cmd:status-now`. Claude Code cloud sessions cannot reach the Project
  API, so they work through issues and labels, and read a snapshot (`STATUS.md` on the `status`
  branch of the app repository).
- The **CLAUDE.md check**: `scripts/claude_md_check.py` and the reusable workflow
  `.github/workflows/claude-md-check.yml`, called from `app`, `core` and `moderation` and run
  here. It fails when `CLAUDE.md` passes 100 lines, or a `.claude/rules/*.md` file passes
  80 lines or has no `paths:`.
- The **line-ending check**: the workflow `.github/workflows/eol-check.yml`, run here and called
  from `app` and `core`. It fails if `.gitattributes` loses `* text=auto eol=lf` or a file with
  CRLF endings is committed.

This repository holds no project data. Its Actions logs are public, so the bridge never prints
issue titles.

## Command labels

| Label | Sets |
|---|---|
| `cmd:status-backlog` · `-next` · `-now` · `-in-review` · `-done` | Status |
| `cmd:phase-p0` … `cmd:phase-p4` | Phase |
| `cmd:verify-verified` · `-not-verified` · `-needs-windows` · `-needs-macos` · `-needs-android` · `-needs-iphone` | Verification |
| `cmd:priority-p1` … `cmd:priority-p3` | Priority |

A command label is applied only when the person who added it has write access, then removed.

A decision that is the maintainer's has no label: the issue is assigned to the maintainer
(`MAINTAINERS` in `project_bridge.py`) and the snapshot lists it under *Waiting on Kade* until
it is closed or unassigned. A check that needs a machine or a device is a *Needs …* Verification
value, listed in its own section until it is set to *Verified*.

## Run locally

```bash
python3 -m unittest discover -s scripts -v
GH_TOKEN=$(gh auth token) python3 scripts/project_bridge.py snapshot --org stella-rain --project <N> --out STATUS.md
```

## License

[MIT](LICENSE)
