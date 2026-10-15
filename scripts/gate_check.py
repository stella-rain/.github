"""gate-check (app's ADR-063): a PR passes only when passing runs of the gates its files need
cover its head.

The caller names its gates, one per line: `<name> <workflow> <path>...`. A path ending in `/`
is a directory, any other a whole file; blank lines and `#` comments are ignored. A gate's
runs come from its workflow on `gate/<name>/<task>`.

1. Fails if the head branch starts with `gate/`.
2. Picks the gates whose paths the PR changes. Passes if it needs none.
3. For each gate it needs, takes the latest successful run of its workflow on its branch and
   that run's commit X.
4. Passes only if, for every gate it needs, X is an ancestor of the head and every file
   changed since X is `*.md`. The gates may cover the head from different commits.
5. Prints which commits and runs it relied on: paths, commits, branches and run links only,
   never a title (Actions logs are public). The workflow adds it to the job summary.

`<task>` is the head branch without its first segment: `claude/<task>`, and the same for
Kade's own branches (`kade/x` -> `x`); a branch without `/` is its own task.

Usage:
  python3 gate_check.py --gate-branches GATES_FILE HEAD_BRANCH
      prints each gate's branch, one per line.
  python3 gate_check.py GATES_FILE HEAD_BRANCH BASE_SHA HEAD_SHA RUNS_JSON [REPO_DIR]
      RUNS_JSON is `GET /repos/{repo}/actions/runs?branch=<gate branch>` for each gate branch,
      merged (the object or its `workflow_runs` list); REPO_DIR holds the PR head with full
      history. Exits 0 on pass, 1 on fail, 2 on bad arguments or a bad gates file.

Follows enjay27/lakehouse's scripts/gate_check.py (its ADR-039), with the gates from the caller.
"""

import json
import re
import subprocess
import sys
from typing import NamedTuple

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Gate(NamedTuple):
    name: str
    workflow: str
    paths: tuple

    def covers(self, path):
        return any(path.startswith(p) if p.endswith("/") else path == p for p in self.paths)

    def branch(self, head_branch):
        return f"gate/{self.name}/{task_of(head_branch)}"


def parse_gates(text):
    """The gates of a spec; raises ValueError naming the line that is wrong."""
    gates = []
    for number, line in enumerate(text.splitlines(), 1):
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if len(fields) < 3:
            raise ValueError(f"line {number}: needs a name, a workflow and at least one path")
        name, workflow, paths = fields[0], fields[1], tuple(fields[2:])
        if not NAME_RE.match(name):
            raise ValueError(f"line {number}: gate name `{name}` must be lowercase letters, "
                             "digits and dashes")
        if any(g.name == name for g in gates):
            raise ValueError(f"line {number}: gate `{name}` is named twice")
        gates.append(Gate(name, workflow, paths))
    if not gates:
        raise ValueError("no gates: the spec names none, so every PR would pass")
    return gates


def task_of(head_branch):
    return head_branch.split("/", 1)[1] if "/" in head_branch else head_branch


def gate_branches(gates, head_branch):
    return [g.branch(head_branch) for g in gates]


def latest_run(runs, workflow, branch):
    passing = [r for r in runs
               if r.get("path") == workflow and r.get("head_branch") == branch
               and r.get("conclusion") == "success"]
    return max(passing, key=lambda r: r.get("created_at", ""), default=None)


def covers(gate, branch, runs, git):
    """Returns (passed, lines) for one gate: its latest successful run covers the head."""
    run = latest_run(runs, gate.workflow, branch)
    if run is None:
        return False, [f"No successful {gate.name} run on `{branch}`. Push the head there: "
                       f"`git push origin HEAD:refs/heads/{branch}`."]
    sha, url = run.get("head_sha", ""), run.get("html_url", "")
    lines = [f"Latest successful {gate.name} run on `{branch}`: commit `{sha}`, run {url}."]
    if not git.is_ancestor(sha):
        return False, lines + [f"Commit `{sha}` is not an ancestor of the head: push the new "
                               f"head to `{branch}`."]
    code = sorted(p for p in git.changed_since(sha) if not p.endswith(".md"))
    if code:
        return False, lines + [f"Changed since the {gate.name} run's commit, not "
                               "documentation: " + ", ".join(f"`{p}`" for p in code)
                               + f". Push the new head to `{branch}`."]
    return True, lines + [f"The {gate.name} gate passes: the head is `{sha}` or adds only "
                          "documentation to it."]


def decide(gates, head_branch, changed, runs, git):
    """Returns (passed, lines). `git` answers is_ancestor(sha) and changed_since(sha)."""
    if head_branch.startswith("gate/"):
        return False, [f"Head branch `{head_branch}` is a gate/ branch: never opened as a PR "
                       "(ADR-063)."]
    lines, passed, needed = [], True, False
    for gate in gates:
        hits = sorted(p for p in changed if gate.covers(p))
        if not hits:
            continue
        needed = True
        lines.append(f"Files for the {gate.name} gate changed: "
                     + ", ".join(f"`{p}`" for p in hits) + ".")
        ok, gate_lines = covers(gate, gate.branch(head_branch), runs, git)
        passed, lines = passed and ok, lines + gate_lines
    if not needed:
        return True, ["The PR changes no gated file; no gate run needed."]
    verdict = ("Passed: every gate the PR needs covers the head." if passed
               else "Failed: not every gate the PR needs covers the head.")
    return passed, lines + [verdict]


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=False)


def _names(result):
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line]


def changed_files(repo, base, head):
    """Files the PR changes: since the merge base, renames listed under both names."""
    return _names(_git(repo, "diff", "--no-renames", "--name-only", f"{base}...{head}"))


class Git:
    def __init__(self, repo, head):
        self.repo, self.head = repo, head

    def is_ancestor(self, sha):
        return _git(self.repo, "merge-base", "--is-ancestor", sha, self.head).returncode == 0

    def changed_since(self, sha):
        return _names(_git(self.repo, "diff", "--no-renames", "--name-only", sha, self.head))


def load_runs(text):
    data = json.loads(text)
    return data.get("workflow_runs", []) if isinstance(data, dict) else data


def read_gates(path):
    with open(path, encoding="utf-8") as f:
        return parse_gates(f.read())


def main(argv):
    try:
        if len(argv) == 4 and argv[1] == "--gate-branches":
            print("\n".join(gate_branches(read_gates(argv[2]), argv[3])))
            return 0
        if len(argv) not in (6, 7):
            print(__doc__.strip().splitlines()[0], file=sys.stderr)
            return 2
        gates = read_gates(argv[1])
    except ValueError as e:
        print(f"gates file: {e}", file=sys.stderr)
        return 2
    head_branch, base, head, runs_path = argv[2:6]
    repo = argv[6] if len(argv) == 7 else "."
    with open(runs_path, encoding="utf-8") as f:
        runs = load_runs(f.read())
    passed, lines = decide(gates, head_branch, changed_files(repo, base, head), runs,
                           Git(repo, head))
    print("\n\n".join(lines))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
