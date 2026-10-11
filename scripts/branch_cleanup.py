"""Branch cleanup: which `claude/*` branches have outlived their work.

A `claude/<task>` branch goes when a merged PR of this repository has it as its head, the
branch still points at that PR's head commit, and no open PR has it as its head. Everything
else stays: `main`, `rc`, `status`, Kade's branches, and a `claude/` branch with commits
after its merge. Auto-merge deletes the branches it merges; this catches the ones Kade
merges by hand.

Usage:
  python3 branch_cleanup.py BRANCHES_JSON PRS_JSON OWNER/REPO
      BRANCHES_JSON is a list of {name, sha}; PRS_JSON a list of {ref, sha, repo, state,
      merged} for every PR, open and closed. Prints the branches to delete, one per line,
      and nothing else: no PR titles.

Follows enjay27/lakehouse's scripts/branch_cleanup.py, without its `gate/` branches.
"""

import json
import sys


def to_delete(branches, prs, repo):
    open_refs = {p["ref"] for p in prs if p["state"] == "open"}
    merged = {(p["ref"], p["sha"]) for p in prs if p.get("merged") and p.get("repo") == repo}
    return sorted(b["name"] for b in branches
                  if b["name"].startswith("claude/")
                  and (b["name"], b["sha"]) in merged
                  and b["name"] not in open_refs)


def main(argv):
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    branches_path, prs_path, repo = argv[1:4]
    with open(branches_path, encoding="utf-8") as f:
        branches = json.load(f)
    with open(prs_path, encoding="utf-8") as f:
        prs = json.load(f)
    for name in to_delete(branches, prs, repo):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
