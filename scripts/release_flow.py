#!/usr/bin/env python3
"""release_flow: the commands the release reusables (release-candidate.yml, release-promote.yml) run,
ported from app's scripts/release.py (the release-flow skill). Candidate runs on main, tags a commit
v<final>-rc.N and makes the branch rc/v<final>-rc.N; Promote, run on that branch, adds v<final> on
the same commit. The version a caller reports is a floor: when it is above every final tag it is
the release, else the release is the latest final tag's next patch.

Runs inside the caller's checkout (git reads only; branches come from the remote-tracking refs the
full checkout fetched). Exit 0 done, 1 refused (reason on stderr, never a title or a body), 2 usage.

  check-main REF            refuses unless REF (GITHUB_REF) is refs/heads/main
  latest                    the highest final tag, or nothing
  final X.Y.Z               the floor rule: vX.Y.Z when above every final tag, else the latest one's next patch
  rc FINAL                  the next candidate tag of FINAL: FINAL-rc.1, FINAL-rc.2, ...
  check-new                 refuses unless HEAD has a commit since the latest release's main commit and
                            is not already a candidate (an rc tag on HEAD, or on a release commit
                            whose only parent is HEAD)
  checks-passed RUN_ID [--ignore NAME]... [--ignore-prefix P]... [--require-any]
                            reads a commit's check runs (the API's JSON) on stdin; refuses when one is
                            unfinished or failed, leaving out run RUN_ID's own jobs, the release
                            jobs and the ignored names
  rc-branch BRANCH          the rc tag of a branch rc/<rc tag>
  superseded RC             origin's rc branches of RC's version below RC, space-separated
  released FINAL            origin's rc branches of FINAL's version and every older one
  check-promote RC VERSION  refuses unless RC is the highest rc of a new version above the latest
                            release, whose version at the rc is VERSION; prints the final tag
  assets DIR GLOB           the files of DIR matching GLOB, one per line, never SHA256SUMS or RELEASE_NOTES.md
  sums DIR GLOB             writes DIR/SHA256SUMS over those files
  verify-sums DIR           refuses unless SHA256SUMS lists exactly the files of DIR with their hashes
  notes RC COMMIT PREVIOUS|- LOG_FILE
                            the default release notes; "-" means there is no previous release

Run the tests: python3 -m unittest discover -s scripts
"""

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys

VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
FINAL = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
CANDIDATE = re.compile(r"^(v\d+\.\d+\.\d+)-rc\.(\d+)$")
RC_BRANCH = re.compile(r"^rc/(v\d+\.\d+\.\d+-rc\.\d+)$")
RELEASE_SUBJECT = re.compile(r"^Release v\d+\.\d+\.\d+$")

# The job names of release-candidate.yml, release-promote.yml and candidate-guard.yml: their check
# runs on a commit, from this run or an earlier release run, are not the commit's CI. A reusable's
# job is reported as `<caller job> / <job name>`.
BUILTIN_CHECKS = (
    "check the candidate",
    "rc tag and prerelease",
    "tag and GitHub release",
    "candidate branch unchanged",
)
PASSED = {"success", "skipped", "neutral"}
FAILED = {"failure", "timed_out", "cancelled", "action_required", "stale", "startup_failure"}
SUMS = "SHA256SUMS"
NOTES_FILE = "RELEASE_NOTES.md"


class ReleaseError(Exception):
    pass


class UsageError(Exception):
    pass


def _numbers(version):
    return tuple(int(n) for n in re.findall(r"\d+", version.split("-")[0]))


def final_tags(tags):
    return [t for t in tags if FINAL.match(t)]


def latest_release(tags):
    finals = final_tags(tags)
    return max(finals, key=_numbers) if finals else None


def final_tag(version, tags):
    """The release: the version when it is above every final tag, else the latest final tag's next patch."""
    if not VERSION.match(version or ""):
        raise ReleaseError(f"{version or '(none)'} is not X.Y.Z")
    latest = latest_release(tags)
    if not latest or _numbers("v" + version) > _numbers(latest):
        return "v" + version
    major, minor, patch = _numbers(latest)
    return f"v{major}.{minor}.{patch + 1}"


def check_main(ref):
    if ref != "refs/heads/main":
        raise ReleaseError(f"a candidate is made from main only; this run is on {ref or '(no ref)'}")


def candidates(final, tags):
    return [int(m.group(2)) for m in map(CANDIDATE.match, tags) if m and m.group(1) == final]


def rc_tag(final, tags):
    if not FINAL.match(final or ""):
        raise ReleaseError(f"{final or '(none)'} is not a release tag")
    return f"{final}-rc.{max([0, *candidates(final, tags)]) + 1}"


def rc_of_branch(branch):
    m = RC_BRANCH.match(branch or "")
    if not m:
        raise ReleaseError(f"{branch or '(none)'} is not rc/<rc tag>")
    return m.group(1)


def _rc_branches(branches):
    return [(b, CANDIDATE.match(m.group(1))) for b in branches for m in [RC_BRANCH.match(b)] if m]


def superseded_branches(branches, rc):
    final, n = CANDIDATE.match(rc).groups()
    return [b for b, m in _rc_branches(branches) if m.group(1) == final and int(m.group(2)) < int(n)]


def released_branches(branches, final):
    return [b for b, m in _rc_branches(branches) if _numbers(m.group(1)) <= _numbers(final)]


def _named(name, wanted):
    return name == wanted or name.endswith(f" / {wanted}") or name.startswith(f"{wanted} / ")


def checks_passed(runs, run_id, ignore=(), ignore_prefix=(), require_any=False):
    """Runs that exist must have passed. A caller whose merges start no push run (GITHUB_TOKEN) may
    have none on main's commit, so none passes unless require_any."""
    own = f"/actions/runs/{run_id}/"
    skip = [*BUILTIN_CHECKS, *ignore]
    others = [
        c for c in runs
        if own not in str(c.get("details_url") or "")
        and not any(_named(c["name"], n) for n in skip)
        and not any(c["name"].startswith(p) for p in ignore_prefix)
    ]
    bad = [
        f"{c['name']}: {c['conclusion'] if c['status'] == 'completed' else c['status']}"
        for c in others
        if c["status"] != "completed" or c.get("conclusion") in FAILED
    ]
    if bad:
        raise ReleaseError("checks not passed: " + "; ".join(bad))
    if require_any and not others:
        raise ReleaseError("no check run on the commit to count")


def check_promote(rc, tags, version_at_rc):
    m = CANDIDATE.match(rc or "")
    if not m:
        raise ReleaseError(f"{rc or '(none)'} is not a candidate tag vX.Y.Z-rc.N")
    final, n = m.group(1), int(m.group(2))
    highest = max([*candidates(final, tags), n])
    if highest > n:
        raise ReleaseError(f"{final}-rc.{highest} is newer than {rc}")
    if final in tags:
        raise ReleaseError(f"{final} is already released")
    latest = latest_release(tags)
    if latest and _numbers(final) <= _numbers(latest):
        raise ReleaseError(f"{final} is not above the latest release {latest}")
    if "v" + (version_at_rc or "") != final:
        raise ReleaseError(f"the version at {rc} is {version_at_rc}, not {final[1:]}")
    return final


def git(*args):
    try:
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError as e:
        raise ReleaseError(f"git {' '.join(args)}: {e.stderr.strip() or e.returncode}")


def release_tags():
    return [t for t in git("tag", "-l", "v*").split("\n") if t]


def origin_branches(prefix):
    """origin's branches under prefix (like "rc/"), from the remote-tracking refs the workflows'
    full checkout fetched: the checkout keeps no credentials to ask a private origin again."""
    out = git("for-each-ref", "--format=%(refname:strip=3)", f"refs/remotes/origin/{prefix}")
    return [b for b in out.split("\n") if b]


def main_commit(tag):
    """The main commit a release tag stands for: its commit, or the only parent of a release commit
    (subject `Release vX.Y.Z`) that Candidate made on top of main."""
    commit, *parents = git("rev-list", "--parents", "-n", "1", f"{tag}^{{commit}}").split()
    if len(parents) == 1 and RELEASE_SUBJECT.match(git("log", "-1", "--format=%s", commit)):
        return parents[0]
    return commit


def check_new_here():
    head = git("rev-parse", "HEAD")
    tags = release_tags()
    for t in tags:
        if CANDIDATE.match(t) and main_commit(t) == head:
            raise ReleaseError(f"{head} is already a candidate ({t})")
    latest = latest_release(tags)
    if latest and int(git("rev-list", "--count", f"{main_commit(latest)}..HEAD")) == 0:
        raise ReleaseError(f"nothing to release: {head} has no commit since {latest}")


def assets(directory, pattern):
    try:
        names = os.listdir(directory)
    except OSError as e:
        raise ReleaseError(f"cannot read {directory}: {e.strerror}")
    found = sorted(
        n for n in names
        if n not in (SUMS, NOTES_FILE) and fnmatch.fnmatchcase(n, pattern) and os.path.isfile(os.path.join(directory, n))
    )
    if not found:
        raise ReleaseError(f"no file in {directory} matches {pattern}")
    return found


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sums(directory, pattern):
    lines = "".join(f"{_sha256(os.path.join(directory, n))}  {n}\n" for n in assets(directory, pattern))
    with open(os.path.join(directory, SUMS), "w", encoding="utf-8", newline="\n") as f:
        f.write(lines)


def verify_sums(directory):
    """SHA256SUMS lists every file of directory with its hash, and nothing else is there."""
    try:
        with open(os.path.join(directory, SUMS), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        raise ReleaseError(f"{directory} has no {SUMS}")
    listed = {}
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{64}) [ *](.+)$", line)
        if not m:
            raise ReleaseError(f"{SUMS} has a line that is not '<sha256>  <name>'")
        listed[m.group(2)] = m.group(1)
    present = {n for n in os.listdir(directory) if n != SUMS and os.path.isfile(os.path.join(directory, n))}
    problems = [f"{n} is not listed" for n in sorted(present - set(listed))]
    problems += [f"{n} is listed but missing" for n in sorted(set(listed) - present)]
    problems += [f"{n} differs from its hash" for n in sorted(present & set(listed)) if _sha256(os.path.join(directory, n)) != listed[n]]
    if problems:
        raise ReleaseError(f"the files and {SUMS} differ: " + "; ".join(problems))


def notes(rc, commit, previous, log_lines):
    m = CANDIDATE.match(rc or "")
    if not m:
        raise ReleaseError(f"{rc or '(none)'} is not a candidate tag vX.Y.Z-rc.N")
    out = [f"# {m.group(1)}", "", f"Candidate {rc} of commit {commit}.", ""]
    if previous and previous != "-":
        out += [f"Commits since {previous}:", ""] + [f"- {line}" for line in log_lines if line.strip()]
    else:
        out += ["First release."]
    return "\n".join(out) + "\n"


def _flag_values(args, flag):
    values = [args[i + 1] for i, a in enumerate(args) if a == flag and i + 1 < len(args)]
    if sum(1 for a in args if a == flag) != len(values):
        raise UsageError(f"{flag} wants a value")
    return values


def _need(rest, count, usage):
    if len(rest) != count:
        raise UsageError(usage)
    return rest


def main(argv):
    cmd, rest = (argv[0] if argv else ""), argv[1:]
    if cmd == "check-main":
        check_main(_need(rest, 1, "check-main REF")[0])
    elif cmd == "latest":
        print(latest_release(release_tags()) or "")
    elif cmd == "final":
        print(final_tag(_need(rest, 1, "final X.Y.Z")[0], release_tags()))
    elif cmd == "rc":
        print(rc_tag(_need(rest, 1, "rc FINAL")[0], release_tags()))
    elif cmd == "check-new":
        check_new_here()
    elif cmd == "checks-passed":
        if not rest:
            raise UsageError("checks-passed RUN_ID [--ignore NAME]... [--ignore-prefix P]... [--require-any]")
        flags = rest[1:]
        checks_passed(
            json.load(sys.stdin).get("check_runs", []), rest[0],
            ignore=_flag_values(flags, "--ignore"), ignore_prefix=_flag_values(flags, "--ignore-prefix"),
            require_any="--require-any" in flags,
        )
    elif cmd == "rc-branch":
        print(rc_of_branch(_need(rest, 1, "rc-branch BRANCH")[0]))
    elif cmd == "superseded":
        print(" ".join(superseded_branches(origin_branches("rc/"), rc_of_branch(f"rc/{_need(rest, 1, 'superseded RC')[0]}"))))
    elif cmd == "released":
        final = _need(rest, 1, "released FINAL")[0]
        if not FINAL.match(final):
            raise ReleaseError(f"{final or '(none)'} is not a release tag")
        print(" ".join(released_branches(origin_branches("rc/"), final)))
    elif cmd == "check-promote":
        rc, version = _need(rest, 2, "check-promote RC VERSION_AT_RC")
        print(check_promote(rc, release_tags(), version))
    elif cmd == "assets":
        print("\n".join(assets(*_need(rest, 2, "assets DIR GLOB"))))
    elif cmd == "sums":
        write_sums(*_need(rest, 2, "sums DIR GLOB"))
    elif cmd == "verify-sums":
        verify_sums(_need(rest, 1, "verify-sums DIR")[0])
    elif cmd == "notes":
        rc, commit, previous, log_file = _need(rest, 4, "notes RC COMMIT PREVIOUS|- LOG_FILE")
        try:
            with open(log_file, encoding="utf-8") as f:
                log = f.read().splitlines()
        except OSError as e:
            raise ReleaseError(f"cannot read {log_file}: {e.strerror}")
        sys.stdout.write(notes(rc, commit, previous, log))
    else:
        raise UsageError("check-main | latest | final | rc | check-new | checks-passed | rc-branch | superseded | released | check-promote | assets | sums | verify-sums | notes")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except UsageError as e:
        print(f"release_flow: usage: {e}", file=sys.stderr)
        sys.exit(2)
    except ReleaseError as e:
        print(f"release_flow: {e}", file=sys.stderr)
        sys.exit(1)
