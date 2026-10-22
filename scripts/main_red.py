#!/usr/bin/env python3
"""Decide what a finished run on main means for the `main-red` issues (main-red.yml).

  main_red.py --event E --conclusion C --branch B --workflow NAME --sha SHA --issues FILE

FILE is the JSON list of open `main-red` issues ({number, title}). Prints one JSON action:
  {"action": "open", "title": ...}   a push/schedule run failed and no issue is open for it
  {"action": "comment", "issue": N}  it failed and an issue for that workflow is open
  {"action": "close", "issue": N}    it succeeded and an issue for that workflow is open
  {"action": "none"}                 anything else (other events or branches, cancelled, ...)

Public repositories log this: the only titles it ever creates hold the workflow name and the
short sha, and it never prints the titles it reads.
"""

import argparse
import json
import sys

EVENTS = ("push", "schedule")
PREFIX = "main is red: "


def title_for(workflow, sha):
    return f"{PREFIX}{workflow} at {sha[:7]}"


def matches(issue, workflow):
    """True for `main is red: <workflow> at <sha>`; a longer workflow name is another workflow."""
    title = issue.get("title") or ""
    rest = title[len(PREFIX):] if title.startswith(PREFIX) else None
    if rest is None or not rest.startswith(workflow + " at "):
        return False
    return " " not in rest[len(workflow) + 4:]


def decide(event, conclusion, branch, workflow, sha, open_issues):
    if event not in EVENTS or branch != "main" or conclusion not in ("failure", "success"):
        return {"action": "none"}
    mine = sorted((i for i in open_issues if matches(i, workflow)), key=lambda i: i["number"])
    if conclusion == "failure":
        if mine:
            return {"action": "comment", "issue": mine[0]["number"]}
        return {"action": "open", "title": title_for(workflow, sha)}
    if mine:
        return {"action": "close", "issue": mine[0]["number"]}
    return {"action": "none"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--event", required=True)
    p.add_argument("--conclusion", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--workflow", required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--issues", required=True, help="JSON file: the open main-red issues")
    a = p.parse_args(argv)
    with open(a.issues, encoding="utf-8") as f:
        issues = json.load(f)
    print(json.dumps(decide(a.event, a.conclusion, a.branch, a.workflow, a.sha, issues)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
