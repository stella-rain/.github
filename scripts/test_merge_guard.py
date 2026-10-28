"""Tests for merge_guard.py. Run: python3 -m unittest discover -s scripts"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import merge_guard as guard  # noqa: E402


def pr(draft=False, labels=(), changed_files=1):
    return {"draft": draft, "labels": list(labels), "changed_files": changed_files}


def file(name, previous=None):
    return {"filename": name, "previous_filename": previous}


def verdict(files, event="pull_request", protected="", **kwargs):
    kwargs.setdefault("changed_files", len(files))
    return guard.verdict(event, pr(**kwargs), files, protected)


class Verdict(unittest.TestCase):
    def test_plain_code_pr_passes(self):
        ok, reasons = verdict([file("src/lib.rs"), file("README.md")])
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_draft_fails(self):
        ok, reasons = verdict([file("src/lib.rs")], draft=True)
        self.assertFalse(ok)
        self.assertEqual(reasons, ["draft"])

    def test_each_protected_path_fails_and_is_named(self):
        for path in (".github/workflows/ci.yml", "CLAUDE.md", "AGENTS.md",
                     ".claude/rules/ci.md", "docs/adr/ADR-001.md"):
            with self.subTest(path=path):
                ok, reasons = verdict([file(path)])
                self.assertFalse(ok)
                self.assertIn(path, " ".join(reasons))

    def test_root_only_files_and_directory_prefix(self):
        for path in ("docs/CLAUDE.md", "docs/adr-notes.md"):
            with self.subTest(path=path):
                self.assertTrue(verdict([file(path)])[0])

    def test_rename_out_of_a_protected_path_fails(self):
        ok, _ = verdict([file("ci/a.yml", previous=".github/workflows/a.yml")])
        self.assertFalse(ok)

    def test_protected_input(self):
        text = "benches/budgets.toml\n\nfixtures/\n"
        for path in ("benches/budgets.toml", "fixtures/x.bin"):
            with self.subTest(path=path):
                self.assertFalse(verdict([file(path)], protected=text)[0])
        self.assertTrue(verdict([file("benches/other.toml")], protected=text)[0])

    def test_kade_ok_clears_protected_paths_and_draft(self):
        self.assertTrue(verdict([file("CLAUDE.md")], labels=["kade-ok"])[0])
        self.assertTrue(verdict([file("src/a.rs")], labels=["kade-ok"], draft=True)[0])

    def test_other_labels_do_not(self):
        self.assertFalse(verdict([file("CLAUDE.md")], labels=["ok"])[0])

    def test_file_list_not_read_whole_fails(self):
        ok, reasons = verdict([file("a"), file("b")], changed_files=3)
        self.assertFalse(ok)
        self.assertIn("file list not read whole", reasons)
        self.assertTrue(verdict([file("a"), file("b")], changed_files=3, labels=["kade-ok"])[0])

    def test_merge_group_passes_without_a_pr(self):
        self.assertEqual(guard.verdict("merge_group", None, None, ""), (True, []))

    def test_other_events_fail_closed(self):
        self.assertFalse(verdict([file("src/a.rs")], event="push")[0])


class CommandLine(unittest.TestCase):
    def run_cli(self, args, pr_json=None, files=None):
        with tempfile.TemporaryDirectory() as tmp:
            if pr_json is not None:
                args = args + ["--pr", os.path.join(tmp, "pr.json")]
                with open(os.path.join(tmp, "pr.json"), "w", encoding="utf-8") as f:
                    json.dump(pr_json, f)
            if files is not None:
                args = args + ["--files", os.path.join(tmp, "files.json")]
                with open(os.path.join(tmp, "files.json"), "w", encoding="utf-8") as f:
                    json.dump(files, f)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = guard.main(["merge_guard.py"] + args)
            return code, out.getvalue(), err.getvalue()

    def fixture(self):
        return dict(pr(), title="SECRET")

    def test_plain_pr_passes(self):
        code, out, err = self.run_cli(["--event", "pull_request"], self.fixture(), [file("a.rs")])
        self.assertEqual((code, out.strip()), (0, "pass"))
        self.assertNotIn("SECRET", out + err)

    def test_protected_pr_fails_with_path_on_stderr(self):
        code, out, err = self.run_cli(["--event", "pull_request"], self.fixture(), [file("CLAUDE.md")])
        self.assertEqual((code, out.strip()), (1, "fail"))
        self.assertIn("CLAUDE.md", err)
        self.assertNotIn("CLAUDE.md", out)
        self.assertNotIn("SECRET", out + err)

    def test_merge_group_needs_nothing_else(self):
        code, out, _ = self.run_cli(["--event", "merge_group"])
        self.assertEqual((code, out.strip()), (0, "pass"))

    def test_missing_event_is_a_usage_error(self):
        self.assertEqual(self.run_cli([])[0], 2)

    def test_pull_request_without_files_is_a_usage_error(self):
        self.assertEqual(self.run_cli(["--event", "pull_request"], self.fixture())[0], 2)


if __name__ == "__main__":
    unittest.main()
