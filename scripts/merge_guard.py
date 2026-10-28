"""The agent merge guard: passes or fails a pull request's check before it can merge.

Usage: python3 merge_guard.py --event EVENT [--protect PATHS] [--pr PR_JSON --files FILES_JSON]
EVENT is the caller's `github.event_name`. Prints `pass` or `fail` on stdout and the reasons
(paths and label names only, never titles) on stderr. Exit 0 = pass, 1 = fail, 2 = usage.

- `merge_group`: pass (there is no PR to read);
- `pull_request`: pass when the label `kade-ok` is set; otherwise fail for a draft, a file
  list not read whole, or a protected path (the paths below, `.github/workflows/`, and the
  caller's `--protect` newline list; a path ending in `/` is a directory, any other a whole
  file at the repository root);
- any other event: fail (fail closed).

PR_JSON holds `draft`, `changed_files` and `labels` (names) from `GET /repos/{repo}/pulls/{n}`;
FILES_JSON is the array of `filename` and `previous_filename` from its files, all pages.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import auto_merge_gate as gate  # noqa: E402

OVERRIDE_LABEL = "kade-ok"
PROTECTED = (".claude/rules/", "docs/adr/", "CLAUDE.md", "AGENTS.md")


def verdict(event, pr, files, protected=""):
    """(passes, reasons) for the caller's event, the PR and its files."""
    if event == "merge_group":
        return True, []
    if event != "pull_request":
        return False, [f"event {event} is not checked"]
    if OVERRIDE_LABEL in (pr.get("labels") or []):
        return True, []
    reasons = []
    if pr.get("draft"):
        reasons.append("draft")
    if files is None or len(files) != pr.get("changed_files"):
        reasons.append("file list not read whole")
    else:
        touched = gate.protected_paths(files, PROTECTED + tuple(gate.name_list(protected)))
        if touched:
            reasons.append("protected paths: " + ", ".join(touched))
    return not reasons, reasons


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv):
    options, args = {}, argv[1:]
    while len(args) >= 2 and args[0] in ("--event", "--protect", "--pr", "--files"):
        options[args[0]] = args[1]
        args = args[2:]
    event = options.get("--event")
    if args or not event or (event == "pull_request" and not {"--pr", "--files"} <= options.keys()):
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    pr = load(options["--pr"]) if "--pr" in options else None
    files = load(options["--files"]) if "--files" in options else None
    ok, reasons = verdict(event, pr, files, options.get("--protect", ""))
    print("pass" if ok else "fail")
    for reason in reasons:
        print(reason, file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
