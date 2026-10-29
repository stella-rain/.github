"""Tests for .github/workflows/auto-merge.yml, read as text. Run: python3 -m unittest discover -s scripts"""

import os
import re
import unittest

PATH = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "auto-merge.yml")
with open(PATH, encoding="utf-8") as f:
    TEXT = f.read()


class UpToDateRule(unittest.TestCase):
    def test_reads_compare_and_comments(self):
        for needle in ("compare/main...", '--compare "$RUNNER_TEMP/compare.json"',
                       "--behind-comment", "gh pr comment"):
            self.assertIn(needle, TEXT)

    def test_never_updates_the_branch(self):
        self.assertNotIn("update-branch", TEXT)

    def test_compare_precedes_merge_and_merge_matches_head(self):
        self.assertLess(TEXT.index("compare/main..."), TEXT.index("gh pr merge"))
        merge_line = next(l for l in TEXT.splitlines() if "gh pr merge" in l and "--merge" in l)
        self.assertIn("--match-head-commit", merge_line)


class Hardening(unittest.TestCase):
    def test_permissions_empty_first(self):
        first = next(l for l in TEXT.splitlines() if re.match(r"permissions:", l))
        self.assertEqual(first.strip(), "permissions: {}")

    def test_actions_pinned_to_major(self):
        for line in TEXT.splitlines():
            m = re.match(r"\s*-?\s*uses:\s*(\S+)", line)
            if m:
                self.assertRegex(m.group(1), r"@v\d+$")

    def test_checkout_does_not_persist_credentials(self):
        steps = re.split(r"\n\s+- ", TEXT)
        for step in steps:
            if "actions/checkout" in step:
                self.assertIn("persist-credentials: false", step)

    def test_no_pull_request_target(self):
        self.assertNotIn("pull_request_target", TEXT)


if __name__ == "__main__":
    unittest.main()
