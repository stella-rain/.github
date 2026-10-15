"""Tests for gate_check.py. Run: python3 -m unittest discover -s scripts

Follows enjay27/lakehouse's scripts/test_gate_check.py, with the gates read from the caller's
spec instead of named in the script (app's ADR-063).
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import gate_check as gate  # noqa: E402

APPLE = ".github/workflows/apple.yml"
LINUX = ".github/workflows/linux.yml"
SPEC = f"""
apple {APPLE} godot/export_presets.cfg godot-ext/Cargo.toml .github/scripts/ {APPLE}

# a comment, then a second gate
linux {LINUX} godot-ext/
"""


def gates():
    return gate.parse_gates(SPEC)


def run(sha, gate_name="apple", task="task", conclusion="success", path=None,
        created="2026-10-15T12:00:00Z", run_id=1, branch=None):
    path = path or {"apple": APPLE, "linux": LINUX}[gate_name]
    return {"id": run_id, "head_sha": sha, "head_branch": branch or f"gate/{gate_name}/{task}",
            "path": path, "conclusion": conclusion, "status": "completed",
            "created_at": created, "html_url": f"https://github.com/o/r/actions/runs/{run_id}"}


class FakeGit:
    """Ancestry and changed files as a dict: sha -> files changed from sha to the head."""

    def __init__(self, since=None):
        self.since = since or {}

    def is_ancestor(self, sha):
        return sha in self.since

    def changed_since(self, sha):
        return self.since[sha]


class ParseGates(unittest.TestCase):
    def test_each_line_is_a_name_a_workflow_and_its_paths(self):
        apple, linux = gates()
        self.assertEqual((apple.name, apple.workflow), ("apple", APPLE))
        self.assertEqual(apple.paths, ("godot/export_presets.cfg", "godot-ext/Cargo.toml",
                                       ".github/scripts/", APPLE))
        self.assertEqual((linux.name, linux.workflow, linux.paths),
                         ("linux", LINUX, ("godot-ext/",)))

    def test_blank_lines_comments_and_spacing_are_ignored(self):
        self.assertEqual(gate.parse_gates("\n  # x\n\tapple  a.yml   b  \n\n"),
                         [gate.Gate("apple", "a.yml", ("b",))])

    def test_a_line_without_paths_is_refused(self):
        with self.assertRaises(ValueError):
            gate.parse_gates("apple .github/workflows/apple.yml")

    def test_a_name_that_is_not_a_branch_segment_is_refused(self):
        for name in ("Apple", "a/b", "-x", "a.b", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                gate.parse_gates(f"{name} w.yml p")

    def test_a_name_used_twice_is_refused(self):
        with self.assertRaises(ValueError):
            gate.parse_gates("apple a.yml p\napple b.yml q")

    def test_no_gates_is_refused(self):
        # An empty spec would pass every PR: fail closed instead.
        for text in ("", "\n# only a comment\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                gate.parse_gates(text)


class GatedPaths(unittest.TestCase):
    def test_a_path_ending_in_a_slash_is_a_directory(self):
        apple = gates()[0]
        self.assertTrue(apple.covers(".github/scripts/install-godot.sh"))
        self.assertTrue(apple.covers(".github/scripts/sub/x.sh"))
        self.assertFalse(apple.covers(".github/scriptsx/a.sh"))
        self.assertFalse(apple.covers(".github/scripts"))

    def test_any_other_path_is_a_whole_file(self):
        apple = gates()[0]
        self.assertTrue(apple.covers("godot/export_presets.cfg"))
        self.assertTrue(apple.covers(APPLE))
        self.assertFalse(apple.covers("godot/export_presets.cfg.bak"))
        self.assertFalse(apple.covers("godot/project.godot"))
        self.assertFalse(apple.covers("x/godot/export_presets.cfg"))


class TaskBranch(unittest.TestCase):
    def test_claude_branch_maps_to_one_branch_per_gate(self):
        self.assertEqual(gate.gate_branches(gates(), "claude/macos-export"),
                         ["gate/apple/macos-export", "gate/linux/macos-export"])

    def test_other_prefixes_drop_the_first_segment(self):
        self.assertEqual(gate.gate_branches(gates(), "kade/a/b"),
                         ["gate/apple/a/b", "gate/linux/a/b"])

    def test_a_branch_without_a_slash_is_its_own_task(self):
        self.assertEqual(gate.gate_branches(gates(), "feature"),
                         ["gate/apple/feature", "gate/linux/feature"])


class Decide(unittest.TestCase):
    def decide(self, changed, runs=(), git=None, branch="claude/task"):
        return gate.decide(gates(), branch, changed, list(runs), git or FakeGit())

    def test_a_gate_branch_as_head_fails(self):
        ok, lines = self.decide(["README.md"], branch="gate/apple/task")
        self.assertFalse(ok)
        self.assertIn("gate/", lines[0])

    def test_no_gated_path_passes_without_a_run(self):
        ok, lines = self.decide(["README.md", "godot/play/play.gd", "godot/project.godot"])
        self.assertTrue(ok)
        self.assertIn("no gate run needed", lines[0])

    def test_a_gated_path_without_a_run_fails_and_says_how_to_push(self):
        ok, lines = self.decide(["godot/export_presets.cfg"])
        self.assertFalse(ok)
        self.assertIn("git push origin HEAD:refs/heads/gate/apple/task", "\n".join(lines))

    def test_a_run_on_the_head_passes_and_names_its_commit_and_run(self):
        ok, lines = self.decide(["godot/export_presets.cfg"], [run("aaa", run_id=7)],
                                FakeGit({"aaa": []}))
        self.assertTrue(ok)
        text = "\n".join(lines)
        self.assertIn("aaa", text)
        self.assertIn("actions/runs/7", text)

    def test_docs_only_since_the_gated_commit_passes(self):
        git = FakeGit({"aaa": ["docs/adr/063-x.md", "README.md"]})
        ok, _ = self.decide(["godot/export_presets.cfg"], [run("aaa")], git)
        self.assertTrue(ok)

    def test_any_non_markdown_file_since_the_gated_commit_fails(self):
        # ADR-063's strict rule: a GDScript change outside the gated paths counts too.
        git = FakeGit({"aaa": ["README.md", "godot/play/play.gd"]})
        ok, lines = self.decide(["godot/export_presets.cfg"], [run("aaa")], git)
        self.assertFalse(ok)
        self.assertIn("godot/play/play.gd", "\n".join(lines))

    def test_a_gated_commit_that_is_not_an_ancestor_fails(self):
        ok, lines = self.decide(["godot/export_presets.cfg"], [run("zzz")], FakeGit())
        self.assertFalse(ok)
        self.assertIn("zzz", "\n".join(lines))

    def test_only_the_latest_successful_run_counts(self):
        runs = [run("aaa", created="2026-10-15T10:00:00Z", run_id=1),
                run("zzz", created="2026-10-15T11:00:00Z", run_id=2)]
        ok, _ = self.decide(["godot/export_presets.cfg"], runs, FakeGit({"aaa": []}))
        self.assertFalse(ok)

    def test_failed_runs_other_tasks_and_other_workflows_are_ignored(self):
        runs = [run("bbb", conclusion="failure"), run("ccc", task="other"),
                run("ddd", path=LINUX), run("eee", conclusion=None)]
        git = FakeGit({"bbb": [], "ccc": [], "ddd": [], "eee": []})
        ok, _ = self.decide(["godot/export_presets.cfg"], runs, git)
        self.assertFalse(ok)

    def test_only_the_gates_whose_paths_changed_are_needed(self):
        ok, lines = self.decide(["godot/export_presets.cfg"], [run("aaa")],
                                FakeGit({"aaa": []}))
        self.assertTrue(ok)
        self.assertNotIn("gate/linux/", "\n".join(lines))

    def test_a_path_in_two_gates_needs_both(self):
        changed = ["godot-ext/Cargo.toml"]
        git = FakeGit({"aaa": [], "bbb": []})
        ok, lines = self.decide(changed, [run("aaa")], git)
        self.assertFalse(ok)
        self.assertIn("gate/linux/task", "\n".join(lines))
        ok, _ = self.decide(changed, [run("aaa"), run("bbb", gate_name="linux")], git)
        self.assertTrue(ok)

    def test_the_gates_may_cover_the_head_from_different_commits(self):
        git = FakeGit({"aaa": ["README.md"], "bbb": []})
        ok, lines = self.decide(["godot-ext/Cargo.toml"],
                                [run("aaa"), run("bbb", gate_name="linux")], git)
        self.assertTrue(ok)
        self.assertIn("aaa", "\n".join(lines))
        self.assertIn("bbb", "\n".join(lines))

    def test_lines_never_hold_more_than_paths_shas_branches_and_urls(self):
        # Actions logs are public: the summary names files and runs, never a title.
        ok, lines = self.decide(["godot/export_presets.cfg"],
                                [{**run("aaa"), "display_title": "SECRET TITLE"}],
                                FakeGit({"aaa": []}))
        self.assertTrue(ok)
        self.assertNotIn("SECRET", "\n".join(lines))


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


class GitHelpers(unittest.TestCase):
    """The git calls, on a throwaway repository."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "user.email", "t@example.invalid")
        self.base = self.commit({"README.md": "a\n", "godot/export_presets.cfg": "x\n"})

    def tearDown(self):
        self._tmp.cleanup()

    def commit(self, files=None, remove=()):
        for name, text in (files or {}).items():
            path = os.path.join(self.repo, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        for name in remove:
            git(self.repo, "rm", "-q", name)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "c")
        return git(self.repo, "rev-parse", "HEAD")

    def test_changed_files_since_the_merge_base(self):
        git(self.repo, "checkout", "-q", "-b", "claude/task")
        head = self.commit({"docs/x.md": "d\n"})
        git(self.repo, "checkout", "-q", "main")
        base = self.commit({"other.txt": "o\n"})
        self.assertEqual(gate.changed_files(self.repo, base, head), ["docs/x.md"])

    def test_a_rename_lists_both_names(self):
        head = self.commit({"docs/presets.cfg": "x\n"}, remove=["godot/export_presets.cfg"])
        self.assertEqual(sorted(gate.changed_files(self.repo, self.base, head)),
                         ["docs/presets.cfg", "godot/export_presets.cfg"])

    def test_ancestry_and_changes_since(self):
        gated = self.commit({"godot/export_presets.cfg": "y\n"})
        head = self.commit({"docs/proof.md": "p\n"})
        repo = gate.Git(self.repo, head)
        self.assertTrue(repo.is_ancestor(gated))
        self.assertEqual(repo.changed_since(gated), ["docs/proof.md"])

    def test_unknown_or_unrelated_commit_is_not_an_ancestor(self):
        head = self.commit({"docs/x.md": "x\n"})
        repo = gate.Git(self.repo, head)
        self.assertFalse(repo.is_ancestor("0" * 40))
        git(self.repo, "checkout", "-q", "-b", "side", self.base)
        side = self.commit({"side.txt": "s\n"})
        self.assertFalse(repo.is_ancestor(side))


class Main(unittest.TestCase):
    def write(self, folder, name, text):
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_gate_branches_mode_prints_one_branch_per_gate(self):
        with tempfile.TemporaryDirectory() as d:
            spec = self.write(d, "gates.txt", SPEC)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = gate.main(["gate_check.py", "--gate-branches", spec, "claude/t"])
        self.assertEqual((code, out.getvalue()), (0, "gate/apple/t\ngate/linux/t\n"))

    def test_a_bad_spec_exits_2_and_says_why(self):
        with tempfile.TemporaryDirectory() as d:
            spec = self.write(d, "gates.txt", "apple only-a-workflow.yml\n")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = gate.main(["gate_check.py", "--gate-branches", spec, "claude/t"])
        self.assertEqual(code, 2)
        self.assertIn("line 1", err.getvalue())

    def test_full_mode_on_a_repository_passes_then_fails_after_code_changes(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(repo)
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.name", "t")
            git(repo, "config", "user.email", "t@example.invalid")

            def commit(name, text):
                path = os.path.join(repo, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                git(repo, "add", "-A")
                git(repo, "commit", "-q", "-m", "c")
                return git(repo, "rev-parse", "HEAD")

            base = commit("README.md", "a\n")
            gated = commit("godot/export_presets.cfg", "x\n")
            docs = commit("docs/proof.md", "p\n")
            spec = self.write(d, "gates.txt", SPEC)
            runs = self.write(d, "runs.json", json.dumps({"workflow_runs": [run(gated)]}))

            def main(head):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = gate.main(["gate_check.py", spec, "claude/task", base, head, runs,
                                      repo])
                return code, out.getvalue()

            code, text = main(docs)
            self.assertEqual(code, 0, text)
            self.assertIn(gated, text)
            code, text = main(commit("godot/play.gd", "g\n"))
            self.assertEqual(code, 1)
            self.assertIn("godot/play.gd", text)

    def test_wrong_arguments_exit_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gate.main(["gate_check.py"]), 2)

    def test_runs_file_may_be_the_api_object_or_a_list(self):
        runs = [run("aaa")]
        self.assertEqual(gate.load_runs(json.dumps({"workflow_runs": runs})), runs)
        self.assertEqual(gate.load_runs(json.dumps(runs)), runs)


if __name__ == "__main__":
    unittest.main()
