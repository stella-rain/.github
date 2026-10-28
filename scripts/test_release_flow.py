"""Tests for release_flow.py and the three release reusables. Run: python3 -m unittest discover -s scripts"""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import release_flow as rf  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(__file__), "release_flow.py")
WORKFLOWS = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows")


class TagCase(unittest.TestCase):
    def test_rc_tags_do_not_count_as_releases(self):
        self.assertIsNone(rf.latest_release(["v0.2.0-rc.1", "other"]))

    def test_latest_release_compares_numbers_not_text(self):
        self.assertEqual(rf.latest_release(["v0.9.0", "v0.10.0", "v0.2.1"]), "v0.10.0")

    def test_rc_tag_is_the_next_number_of_the_version(self):
        self.assertEqual(rf.rc_tag("v0.1.0", []), "v0.1.0-rc.1")
        self.assertEqual(rf.rc_tag("v0.1.0", ["v0.1.0-rc.1", "v0.1.0-rc.2", "v0.2.0-rc.7"]), "v0.1.0-rc.3")
        self.assertEqual(rf.rc_tag("v0.1.0", ["v0.1.0-rc.9"]), "v0.1.0-rc.10")
        self.assertEqual(rf.rc_tag("v0.1.0", ["v0.1.0-rc.1"]), "v0.1.0-rc.2")

    def test_rc_tag_wants_a_final_tag(self):
        with self.assertRaisesRegex(rf.ReleaseError, "not a release tag"):
            rf.rc_tag("v0.1.0-rc.1", [])


class FloorCase(unittest.TestCase):
    """The version is a floor: the release is that version when it is above the latest final tag, else
    the next patch of that tag."""

    def test_a_version_above_the_latest_release_is_the_release(self):
        self.assertEqual(rf.final_tag("0.1.0", ["v0.0.5"]), "v0.1.0")
        self.assertEqual(rf.final_tag("0.10.0", ["v0.9.0", "v0.2.0-rc.1"]), "v0.10.0")

    def test_a_version_equal_to_the_latest_release_gives_the_next_patch(self):
        self.assertEqual(rf.final_tag("0.0.5", ["v0.0.5", "v0.0.5-rc.1"]), "v0.0.6")
        self.assertEqual(rf.final_tag("0.0.1", ["v0.0.1"]), "v0.0.2")

    def test_a_version_below_the_latest_release_gives_the_next_patch_of_that_release(self):
        self.assertEqual(rf.final_tag("0.0.3", ["v0.0.5", "v0.0.2"]), "v0.0.6")
        self.assertEqual(rf.final_tag("0.1.0", ["v0.2.9"]), "v0.2.10")

    def test_with_no_release_yet_the_version_is_the_release(self):
        self.assertEqual(rf.final_tag("0.0.1", []), "v0.0.1")
        self.assertEqual(rf.final_tag("0.0.1", ["v0.0.1-rc.3"]), "v0.0.1")

    def test_a_second_candidate_of_the_next_patch_is_rc_2(self):
        tags = ["v0.0.5", "v0.0.6-rc.1"]
        self.assertEqual(rf.rc_tag(rf.final_tag("0.0.5", tags), tags), "v0.0.6-rc.2")

    def test_a_version_that_is_not_x_y_z_is_refused(self):
        for bad in ("1.2", "v1.2.3", ""):
            with self.subTest(bad=bad), self.assertRaisesRegex(rf.ReleaseError, "not X.Y.Z"):
                rf.final_tag(bad, [])


class BranchCase(unittest.TestCase):
    def test_rc_of_branch(self):
        self.assertEqual(rf.rc_of_branch("rc/v0.1.0-rc.2"), "v0.1.0-rc.2")
        for bad in ("rc", "rc/v0.1.0", "candidate/0123456789ab", "", None):
            with self.subTest(bad=bad), self.assertRaisesRegex(rf.ReleaseError, "not rc/"):
                rf.rc_of_branch(bad)

    def test_superseded_are_the_same_versions_lower_rcs(self):
        branches = ["rc/v0.1.0-rc.1", "rc/v0.1.0-rc.2", "rc/v0.1.0-rc.3", "rc/v0.2.0-rc.1", "main"]
        self.assertEqual(rf.superseded_branches(branches, "v0.1.0-rc.3"), ["rc/v0.1.0-rc.1", "rc/v0.1.0-rc.2"])

    def test_released_are_that_version_and_every_older_one(self):
        branches = ["rc/v0.1.0-rc.2", "rc/v0.2.0-rc.1", "rc/v0.10.0-rc.1", "rc/v0.1.5-rc.1"]
        self.assertEqual(rf.released_branches(branches, "v0.2.0"), ["rc/v0.1.0-rc.2", "rc/v0.2.0-rc.1", "rc/v0.1.5-rc.1"])


def run_(name, conclusion="success", status="completed", run=1):
    return {"name": name, "status": status, "conclusion": conclusion, "details_url": f"https://github.com/o/r/actions/runs/{run}/job/9"}


class ChecksCase(unittest.TestCase):
    def test_failed_or_unfinished_runs_are_refused(self):
        rf.checks_passed([run_("a")], "5")
        for bad in (run_("a", "failure"), run_("a", "cancelled"), run_("a", None, "in_progress")):
            with self.subTest(bad=bad), self.assertRaisesRegex(rf.ReleaseError, "not passed"):
                rf.checks_passed([run_("ok"), bad], "5")

    def test_a_skipped_or_neutral_run_passes(self):
        rf.checks_passed([run_("a", "skipped"), run_("b", "neutral")], "5")

    def test_no_run_at_all_passes_unless_one_is_required(self):
        rf.checks_passed([], "5")
        with self.assertRaisesRegex(rf.ReleaseError, "no check run"):
            rf.checks_passed([], "5", require_any=True)
        with self.assertRaisesRegex(rf.ReleaseError, "no check run"):
            rf.checks_passed([run_("x / y", "failure", run=5)], "5", require_any=True)
        rf.checks_passed([run_("ok")], "5", require_any=True)

    def test_this_runs_own_jobs_are_left_out(self):
        rf.checks_passed([run_("x / y", "failure", run=5), run_("ok")], "5")

    def test_the_built_in_names_are_left_out_from_any_run(self):
        for name in rf.BUILTIN_CHECKS:
            for shown in (name, f"release / {name}"):
                with self.subTest(shown=shown):
                    rf.checks_passed([run_(shown, "failure", run=3)], "5")

    def test_ignore_and_ignore_prefix_leave_out_a_callers_gates(self):
        gate = run_("Candidate: godot / checks", "cancelled", run=3)
        with self.assertRaisesRegex(rf.ReleaseError, "not passed"):
            rf.checks_passed([gate], "5")
        rf.checks_passed([gate], "5", ignore=["Candidate: godot"])
        rf.checks_passed([gate], "5", ignore_prefix=["Candidate: "])

    def test_a_name_that_only_contains_an_ignored_name_is_not_left_out(self):
        with self.assertRaisesRegex(rf.ReleaseError, "not passed"):
            rf.checks_passed([run_("not check the candidate", "failure", run=3)], "5")


class PromoteCase(unittest.TestCase):
    TAGS = ["v0.1.0-rc.1", "v0.1.0-rc.2"]

    def test_the_highest_rc_of_a_new_version_is_promoted(self):
        self.assertEqual(rf.check_promote("v0.1.0-rc.2", self.TAGS, "0.1.0"), "v0.1.0")

    def test_an_older_rc_is_refused(self):
        with self.assertRaisesRegex(rf.ReleaseError, "newer"):
            rf.check_promote("v0.1.0-rc.1", self.TAGS, "0.1.0")

    def test_a_released_version_is_refused(self):
        with self.assertRaisesRegex(rf.ReleaseError, "already released"):
            rf.check_promote("v0.1.0-rc.2", self.TAGS + ["v0.1.0"], "0.1.0")

    def test_a_version_not_above_the_latest_release_is_refused(self):
        with self.assertRaisesRegex(rf.ReleaseError, "not above"):
            rf.check_promote("v0.1.0-rc.2", self.TAGS + ["v0.2.0"], "0.1.0")

    def test_the_version_at_the_rc_must_be_the_version(self):
        with self.assertRaisesRegex(rf.ReleaseError, "0.1.1"):
            rf.check_promote("v0.1.0-rc.2", self.TAGS, "0.1.1")

    def test_a_non_candidate_tag_is_refused(self):
        with self.assertRaisesRegex(rf.ReleaseError, "not a candidate tag"):
            rf.check_promote("v0.1.0", self.TAGS, "0.1.0")


class MainOnlyCase(unittest.TestCase):
    def test_main_is_accepted(self):
        rf.check_main("refs/heads/main")

    def test_any_other_ref_is_refused(self):
        for ref in ("refs/heads/claude/x", "refs/heads/rc/v0.1.0-rc.1", "refs/heads/candidate/0123456789ab", "refs/tags/v0.1.0", "refs/heads/main2", ""):
            with self.subTest(ref=ref), self.assertRaisesRegex(rf.ReleaseError, "main"):
                rf.check_main(ref)


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True, text=True).stdout.strip()


class CliCase(unittest.TestCase):
    """The commands read real git repositories: an origin, and a clone of it. They read the
    clone's remote-tracking branches, as a workflow's full checkout leaves them (no credentials
    are kept to ask a private origin again)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = self._tmp.name
        self.origin = os.path.join(base, "origin.git")
        self.work = os.path.join(base, "work")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], check=True)
        subprocess.run(["git", "clone", "-q", self.origin, self.work], check=True, capture_output=True)
        git(self.work, "checkout", "-q", "-b", "main")
        self.write("VERSION", "0.1.0\n")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "first")
        git(self.work, "push", "-q", "origin", "main")
        self.head = git(self.work, "rev-parse", "HEAD")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        with open(os.path.join(self.work, name), "w", newline="\n") as f:
            f.write(text)

    def cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.work, capture_output=True, text=True, input=stdin)

    def commit(self, message="more"):
        git(self.work, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.work, "rev-parse", "HEAD")

    def release_commit(self, rc, subject=None):
        """A release commit as Candidate makes it: a child of main's commit that main never has."""
        git(self.work, "checkout", "-q", "--detach")
        self.write("VERSION", rc[1:].split("-")[0] + "\n")
        git(self.work, "add", "-A")
        sha = self.commit(subject or f"Release {rc[:rc.index('-')] if '-' in rc else rc}")
        git(self.work, "tag", rc, sha)
        git(self.work, "checkout", "-q", "main")
        return sha

    def test_check_main_reads_the_ref_given(self):
        self.assertEqual(self.cli("check-main", "refs/heads/main").returncode, 0)
        r = self.cli("check-main", "refs/heads/candidate/0123456789ab")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("main", r.stderr)
        self.assertIn("release_flow:", r.stderr)

    def test_final_prints_the_floor_rule_tag(self):
        r = self.cli("final", "0.1.0")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "v0.1.0"))
        git(self.work, "tag", "v0.1.0")
        self.assertEqual(self.cli("final", "0.1.0").stdout.strip(), "v0.1.1")
        self.assertNotEqual(self.cli("final", "1.2").returncode, 0)

    def test_check_new_passes_with_no_release(self):
        self.assertEqual(self.cli("check-new").returncode, 0)

    def test_check_new_refuses_when_nothing_came_after_the_latest_release(self):
        git(self.work, "tag", "v0.1.0")
        r = self.cli("check-new")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing to release", r.stderr)
        self.commit()
        self.assertEqual(self.cli("check-new").returncode, 0)

    def test_check_new_counts_from_the_main_commit_below_a_release_commit(self):
        self.release_commit("v0.1.1")
        r = self.cli("check-new")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing to release", r.stderr)
        self.commit()
        self.assertEqual(self.cli("check-new").returncode, 0)

    def test_check_new_refuses_a_commit_that_is_already_a_candidate(self):
        git(self.work, "tag", "v0.0.1")
        self.commit()
        git(self.work, "tag", "v0.1.0-rc.1")
        r = self.cli("check-new")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already a candidate", r.stderr)

    def test_check_new_refuses_a_commit_whose_release_commit_is_a_candidate(self):
        git(self.work, "tag", "v0.1.0")
        self.commit()
        self.release_commit("v0.1.1-rc.1")
        r = self.cli("check-new")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already a candidate", r.stderr)
        self.commit()
        self.assertEqual(self.cli("check-new").returncode, 0)

    def test_a_commit_that_is_not_a_release_commit_is_not_looked_through(self):
        git(self.work, "tag", "v0.1.0")
        self.commit()
        self.release_commit("v0.1.1-rc.1", subject="Release notes")
        self.assertEqual(self.cli("check-new").returncode, 0)

    def test_rc_prints_the_next_number_from_the_tags(self):
        git(self.work, "tag", "v0.1.0-rc.1")
        self.assertEqual(self.cli("rc", "v0.1.0").stdout.strip(), "v0.1.0-rc.2")

    def test_latest_prints_the_highest_release_or_nothing(self):
        self.assertEqual(self.cli("latest").stdout.strip(), "")
        git(self.work, "tag", "v0.2.0")
        git(self.work, "tag", "v0.10.0")
        git(self.work, "tag", "v0.11.0-rc.1")
        self.assertEqual(self.cli("latest").stdout.strip(), "v0.10.0")

    def test_branches_are_read_without_asking_origin_again(self):
        git(self.work, "push", "-q", "origin", f"{self.head}:refs/heads/rc/v0.1.0-rc.1")
        git(self.work, "fetch", "-q", "origin")
        git(self.work, "remote", "set-url", "origin", os.path.join(self._tmp.name, "gone.git"))
        self.assertEqual(self.cli("released", "v0.1.0").stdout.split(), ["rc/v0.1.0-rc.1"])

    def test_rc_branch_superseded_and_released_read_origins_rc_branches(self):
        for b in ("rc/v0.1.0-rc.1", "rc/v0.1.0-rc.2", "rc/v0.2.0-rc.1"):
            git(self.work, "push", "-q", "origin", f"{self.head}:refs/heads/{b}")
        git(self.work, "fetch", "-q", "origin")
        self.assertEqual(self.cli("rc-branch", "rc/v0.1.0-rc.2").stdout.strip(), "v0.1.0-rc.2")
        self.assertEqual(self.cli("superseded", "v0.1.0-rc.2").stdout.split(), ["rc/v0.1.0-rc.1"])
        self.assertEqual(sorted(self.cli("released", "v0.1.0").stdout.split()), ["rc/v0.1.0-rc.1", "rc/v0.1.0-rc.2"])

    def test_check_promote_reads_the_tags(self):
        git(self.work, "tag", "v0.1.0-rc.1")
        r = self.cli("check-promote", "v0.1.0-rc.1", "0.1.0")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "v0.1.0"))
        self.assertNotEqual(self.cli("check-promote", "v0.1.0-rc.1", "0.1.1").returncode, 0)

    def test_checks_passed_reads_the_api_json_on_stdin(self):
        ok = '{"check_runs": [{"name": "a", "status": "completed", "conclusion": "success", "details_url": ""}]}'
        bad = '{"check_runs": [{"name": "a", "status": "completed", "conclusion": "failure", "details_url": ""}]}'
        self.assertEqual(self.cli("checks-passed", "5", stdin=ok).returncode, 0)
        self.assertNotEqual(self.cli("checks-passed", "5", stdin=bad).returncode, 0)
        self.assertEqual(self.cli("checks-passed", "5", "--ignore", "a", stdin=bad).returncode, 0)
        self.assertEqual(self.cli("checks-passed", "5", "--ignore-prefix", "a", stdin=bad).returncode, 0)
        self.assertNotEqual(self.cli("checks-passed", "5", "--require-any", stdin='{"check_runs": []}').returncode, 0)

    def test_a_flag_never_takes_the_next_flag_as_its_value(self):
        runs = '{"check_runs": []}'
        for args in (("--ignore", "--require-any"), ("--ignore-prefix",), ("--ignore", "")):
            with self.subTest(args=args):
                r = self.cli("checks-passed", "5", *args, stdin=runs)
                self.assertEqual(r.returncode, 2, r.stderr)

    def test_an_unknown_command_is_a_usage_error(self):
        self.assertEqual(self.cli("nope").returncode, 2)
        self.assertEqual(self.cli().returncode, 2)


class AssetsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        for name, body in (("stage-verify-b", "b"), ("stage-verify-a", "a"), ("other", "o"), ("SHA256SUMS", "x"), ("RELEASE_NOTES.md", "n")):
            with open(os.path.join(self.dir, name), "w", newline="\n") as f:
                f.write(body)
        os.mkdir(os.path.join(self.dir, "stage-verify-dir"))

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)

    def test_assets_selects_by_glob_sorted_and_never_the_sums_or_the_notes(self):
        r = self.cli("assets", self.dir, "stage-verify-*")
        self.assertEqual((r.returncode, r.stdout.split()), (0, ["stage-verify-a", "stage-verify-b"]))
        self.assertEqual(self.cli("assets", self.dir, "*").stdout.split(), ["other", "stage-verify-a", "stage-verify-b"])

    def test_an_empty_selection_is_refused(self):
        r = self.cli("assets", self.dir, "nothing-*")
        self.assertEqual(r.returncode, 1)
        self.assertIn("release_flow:", r.stderr)

    def test_sums_writes_sorted_hash_lines_and_verify_passes(self):
        self.assertEqual(self.cli("sums", self.dir, "stage-verify-*").returncode, 0)
        with open(os.path.join(self.dir, "SHA256SUMS"), "rb") as f:
            raw = f.read()
        want = "".join(f"{hashlib.sha256(n.encode()).hexdigest()}  stage-verify-{n}\n" for n in ("a", "b"))
        self.assertEqual(raw.decode(), want)
        self.assertNotIn(b"\r", raw)
        os.remove(os.path.join(self.dir, "other"))
        os.rmdir(os.path.join(self.dir, "stage-verify-dir"))
        os.remove(os.path.join(self.dir, "RELEASE_NOTES.md"))
        self.assertEqual(self.cli("verify-sums", self.dir).returncode, 0, self.cli("verify-sums", self.dir).stderr)

    def sums_over_all(self):
        os.remove(os.path.join(self.dir, "RELEASE_NOTES.md"))
        os.rmdir(os.path.join(self.dir, "stage-verify-dir"))
        self.cli("sums", self.dir, "*")

    def test_verify_refuses_a_changed_file(self):
        self.sums_over_all()
        with open(os.path.join(self.dir, "other"), "w") as f:
            f.write("changed")
        r = self.cli("verify-sums", self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn("differ", r.stderr)

    def test_verify_refuses_a_file_that_is_not_listed(self):
        self.sums_over_all()
        with open(os.path.join(self.dir, "extra"), "w") as f:
            f.write("e")
        r = self.cli("verify-sums", self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn("extra", r.stderr)

    def test_verify_refuses_a_listed_file_that_is_missing(self):
        self.sums_over_all()
        os.remove(os.path.join(self.dir, "other"))
        r = self.cli("verify-sums", self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn("other", r.stderr)

    def test_verify_refuses_without_sums(self):
        os.remove(os.path.join(self.dir, "SHA256SUMS"))
        r = self.cli("verify-sums", self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn("SHA256SUMS", r.stderr)


class NotesCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self._tmp.name, "log")
        with open(self.log, "w") as f:
            f.write("abc1234 one\ndef5678 two\n")

    def tearDown(self):
        self._tmp.cleanup()

    def notes(self, previous):
        r = subprocess.run([sys.executable, SCRIPT, "notes", "v0.1.1-rc.2", "0123abc", previous, self.log], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_notes_name_the_final_the_rc_the_commit_and_the_commits_since(self):
        text = self.notes("v0.1.0")
        for part in ("# v0.1.1", "v0.1.1-rc.2", "0123abc", "Commits since v0.1.0:", "- abc1234 one", "- def5678 two"):
            self.assertIn(part, text)
        self.assertEqual(len([l for l in text.splitlines() if l.startswith("- ")]), 2)

    def test_the_first_release_has_no_previous(self):
        text = self.notes("-")
        self.assertIn("# v0.1.1", text)
        self.assertIn("First release.", text)
        self.assertNotIn("- abc1234", text)


def block_lines(text, header_re):
    """The indented lines under every line matching header_re (a `run: |` style block)."""
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        m = re.match(header_re, line)
        if not m:
            continue
        indent = len(line) - len(line.lstrip())
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > indent):
            out.append(lines[j])
            j += 1
    return out


def jobs_of(text):
    """{job id: its text} for the top-level `jobs:` of a workflow."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\n", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


class WorkflowCase(unittest.TestCase):
    FILES = ("release-candidate.yml", "release-promote.yml", "candidate-guard.yml")

    def text(self, name):
        with open(os.path.join(WORKFLOWS, name), encoding="utf-8", newline="") as f:
            return f.read()

    def each(self):
        for name in self.FILES:
            with self.subTest(file=name):
                yield name, self.text(name)

    def test_they_are_reusable_only(self):
        for name, text in self.each():
            self.assertRegex(text, r"(?m)^  workflow_call:")
            self.assertNotRegex(text, r"(?m)^  (workflow_dispatch|push|pull_request|schedule):")
            self.assertNotIn("\r", text)

    def test_permissions_are_empty_at_the_top_and_granted_per_job(self):
        for name, text in self.each():
            self.assertRegex(text, r"(?m)^permissions: \{\}$")
            for job, body in jobs_of(text).items():
                self.assertRegex(body, r"(?m)^    permissions:", f"{name} {job}")

    def test_actions_are_pinned_to_a_major_and_checkouts_keep_no_credentials(self):
        for name, text in self.each():
            for m in re.finditer(r"uses: (actions/\S+)", text):
                self.assertRegex(m.group(1), r"@v\d+$", name)
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if "uses: actions/checkout@" in line:
                    self.assertIn("persist-credentials: false", "\n".join(lines[i : i + 8]), name)

    def test_no_expression_inside_a_run_block(self):
        for name, text in self.each():
            run = block_lines(text, r"^\s*(- )?run: [|>]")
            self.assertNotIn("${{", "\n".join(run), name)
            for line in text.split("\n"):
                if re.match(r"^\s*(- )?run: [^|>\s]", line):
                    self.assertNotIn("${{", line, name)

    def test_the_guard_deletes_a_pushed_candidate_branch(self):
        text = self.text("candidate-guard.yml")
        self.assertIn("name: candidate branch unchanged", text)
        self.assertRegex(text, r"if: \$\{\{ !github\.event\.deleted \}\}")
        self.assertIn("contents: write", text)
        self.assertNotIn("actions/checkout", text)

    def test_the_candidate_declares_its_inputs_and_two_phases(self):
        text = self.text("release-candidate.yml")
        for name in ("phase", "runs-on", "version-command", "check-command", "stamp-command", "stamp-files", "ignore-checks", "require-check-run", "assets-artifact", "assets-glob", "plan"):
            self.assertRegex(text, rf"(?m)^      {name}:", name)
        jobs = jobs_of(text)
        self.assertEqual(sorted(jobs), ["check", "tag"])
        self.assertIn("name: check the candidate", jobs["check"])
        self.assertIn("name: rc tag and prerelease", jobs["tag"])
        self.assertRegex(jobs["check"], r"if: inputs\.phase == 'check'")
        self.assertRegex(jobs["tag"], r"if: inputs\.phase == 'tag'")
        self.assertIn("contents: read", jobs["check"])
        self.assertIn("checks: read", jobs["check"])
        self.assertIn("contents: write", jobs["tag"])
        self.assertNotIn("path: repo", jobs["tag"])

    def test_the_promote_has_a_check_and_a_tag_job(self):
        jobs = jobs_of(self.text("release-promote.yml"))
        self.assertEqual(sorted(jobs), ["check", "tag"])
        self.assertIn("name: check the candidate", jobs["check"])
        self.assertIn("name: tag and GitHub release", jobs["tag"])
        self.assertIn("contents: write", jobs["tag"])
        self.assertNotIn("actions/checkout@v7\n        with:\n          fetch-depth", jobs["tag"])

    def test_the_built_in_check_names_are_the_job_names_of_the_three_files(self):
        names = set()
        for _, text in self.each():
            for body in jobs_of(text).values():
                names.update(re.findall(r"(?m)^    name: (.+)$", body))
        self.assertEqual(names, set(rf.BUILTIN_CHECKS))


if __name__ == "__main__":
    unittest.main()
