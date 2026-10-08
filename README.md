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

## Another organization (a second bridge)

The bridge code is shared; only the organization, its Project and its GitHub App are new. Used
for `star-resonance` (Resonance: `resonance-stream`, `resonance-lab`).

1. **Browser:** create the organization (Free plan). Create a GitHub App owned by it, named for
   the project (for example `resonance-bridge`), with the same settings as in the runbook
   (`app/docs/setup/project-bridge-setup.md`, step 5): webhook off; Issues, Pull requests and
   Metadata read-only; organization Projects read and write; installed only on that organization,
   on the synced repositories. Generate a private key and note the Client ID. An app cannot be
   shared across organizations unless it is public, so each organization has its own.
2. **gh (needs the `project` scope):**
   `ORG=<org> TITLE=<Title> SYNCED_REPOS="<repo> <repo>" PHASES="" bash scripts/setup-project.sh`.
   `PHASES=""` means no Phase field; leave it unset for Stella Rain's five. The last step of the
   script sets the organization variable `PROJECT_NUMBER` and needs the `admin:org` scope
   (`gh auth refresh -h github.com -s admin:org`).
3. **Status options:** `Backlog, Next, Now, In review, Done`, in that order. The bridge looks them
   up by name. Rename the built-in ones (their ids keep the built-in workflows): the GraphQL
   mutation `updateProjectV2Field` with the existing option ids does it without the browser.
4. **Variable and secret, by Kade:** organization variable `BRIDGE_APP_CLIENT_ID`, organization
   secret `BRIDGE_APP_PRIVATE_KEY` (`gh secret set BRIDGE_APP_PRIVATE_KEY --org <org> --visibility
   selected --repos <repo>,<repo> < key.pem`); delete the key file afterwards.
5. **Each repository** gets `.github/workflows/project-sync.yml` (the caller of
   `stella-rain/.github/.github/workflows/project-sync.yml@main`); one of them also gets
   `project-snapshot.yml`. The caller passes the key by name,
   `secrets: {BRIDGE_APP_PRIVATE_KEY: ${{ secrets.BRIDGE_APP_PRIVATE_KEY }}}`: `secrets: inherit`
   does not cross organizations (the first test of star-resonance failed on it). Both are skipped while `PROJECT_NUMBER` is unset.
6. **Browser:** the views and the Project's built-in workflows (item closed: Done; pull request
   merged: Done; item added: Backlog), as in the runbook; GitHub has no API for views.

The snapshot of a public repository lists the titles of its issues. Draft items must never be
added to such a Project.

## Run locally

```bash
python3 -m unittest discover -s scripts -v
GH_TOKEN=$(gh auth token) python3 scripts/project_bridge.py snapshot --org stella-rain --project <N> --out STATUS.md
```

## License

[MIT](LICENSE)
