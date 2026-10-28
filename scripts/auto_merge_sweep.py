"""Helpers for the auto-merge workflow's scheduled sweep.

Usage:
  python3 auto_merge_sweep.py candidates PRS_JSON [PREFIXES]
  python3 auto_merge_sweep.py up-to-date COMPARE_JSON

`candidates` reads the `gh pr list --json number,headRefName,headRefOid,isDraft,isCrossRepository`
array and prints `number sha` lines, ascending by number, for the open PRs that are not drafts,
not from a fork, and whose head branch starts with one of the space-separated PREFIXES
(default `claude/`). `up-to-date` reads `GET /repos/{repo}/compare/main...{sha}` and prints
`yes` when the PR is not behind main, else `no`. Prints numbers and shas only, never titles.
"""

import json
import sys


def candidates(prs, prefixes=""):
    """[(number, sha)] of the PRs the sweep may merge, ascending by number."""
    wanted = tuple((prefixes or "").split()) or ("claude/",)
    found = [
        (p["number"], p["headRefOid"])
        for p in prs
        if p.get("headRefName", "").startswith(wanted)
        and not p.get("isDraft")
        and not p.get("isCrossRepository")
    ]
    return sorted(found)


def up_to_date(compare):
    """True when the PR head is not behind main; a missing key is False."""
    return compare.get("behind_by") == 0


def main(argv):
    if len(argv) < 3 or argv[1] not in ("candidates", "up-to-date"):
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    with open(argv[2], encoding="utf-8") as f:
        data = json.load(f)
    if argv[1] == "candidates":
        for number, sha in candidates(data, argv[3] if len(argv) > 3 else ""):
            print(number, sha)
    else:
        print("yes" if up_to_date(data) else "no")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
