"""Tests for auto_merge_sweep.py. Run: python3 -m unittest discover -s scripts"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import auto_merge_sweep as sweep  # noqa: E402


def pr(number, branch, draft=False, fork=False, sha=None):
    return {"number": number, "headRefName": branch, "headRefOid": sha or f"sha{number}",
            "isDraft": draft, "isCrossRepository": fork}


class Candidates(unittest.TestCase):
    def test_filters_and_orders(self):
        prs = [pr(9, "claude/z"), pr(3, "feature/b"), pr(4, "claude/c", draft=True),
               pr(5, "claude/d", fork=True), pr(2, "claude/a")]
        self.assertEqual(sweep.candidates(prs, ""), [(2, "sha2"), (9, "sha9")])

    def test_empty(self):
        self.assertEqual(sweep.candidates([], "claude/"), [])

    def test_several_prefixes(self):
        prs = [pr(1, "claude/a"), pr(2, "bot/e"), pr(3, "other/x")]
        self.assertEqual(sweep.candidates(prs, "claude/ bot/"), [(1, "sha1"), (2, "sha2")])

    def test_default_prefix_is_claude_only(self):
        prs = [pr(1, "claude/a"), pr(2, "bot/e")]
        self.assertEqual(sweep.candidates(prs, ""), [(1, "sha1")])


class UpToDate(unittest.TestCase):
    def test_values(self):
        self.assertTrue(sweep.up_to_date({"behind_by": 0}))
        self.assertFalse(sweep.up_to_date({"behind_by": 2}))
        self.assertFalse(sweep.up_to_date({}))


class CommandLine(unittest.TestCase):
    def run_cli(self, args, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "in.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            first, *rest = args
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = sweep.main(["auto_merge_sweep.py", first, path] + rest)
            return code, out.getvalue()

    def test_candidates_prints_number_and_sha(self):
        code, out = self.run_cli(["candidates", "claude/"], [pr(12, "claude/a", sha="abc123")])
        self.assertEqual((code, out), (0, "12 abc123\n"))

    def test_up_to_date_prints_yes_no(self):
        self.assertEqual(self.run_cli(["up-to-date"], {"behind_by": 0}), (0, "yes\n"))
        self.assertEqual(self.run_cli(["up-to-date"], {"behind_by": 1}), (0, "no\n"))


if __name__ == "__main__":
    unittest.main()
