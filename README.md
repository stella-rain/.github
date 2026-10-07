# stella-rain/.github

Organization-wide files for **Stella Rain**:

- Default issue forms and the pull request template for every repository that has none of its own.
- The **Project bridge** (ADR-031): `scripts/project_bridge.py` and the reusable workflow
  `.github/workflows/project-sync.yml`, which add issues to the organization Project and apply
  command labels such as `cmd:status-now`. Claude Code cloud sessions cannot reach the Project
  API, so they work through issues and labels, and read a snapshot (`STATUS.md` on the `status`
  branch of the app repository).

This repository holds no project data. Its Actions logs are public, so the bridge never prints
issue titles.

## Command labels

| Label | Sets |
|---|---|
| `cmd:status-backlog` · `-next` · `-now` · `-in-review` · `-done` | Status |
| `cmd:phase-p0` … `cmd:phase-p4` | Phase |
| `cmd:verify-verified` · `-not-verified` · `-needs-kade` | Verification |
| `cmd:priority-p1` … `cmd:priority-p3` | Priority |

A command label is applied only when the person who added it has write access, then removed.

## Run locally

```bash
python3 -m unittest discover -s scripts -v
GH_TOKEN=$(gh auth token) python3 scripts/project_bridge.py snapshot --org stella-rain --project <N> --out STATUS.md
```

## License

[MIT](LICENSE)
