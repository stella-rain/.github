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


def env_int(name):
    m = re.search(rf'^\s*{name}: "?(\d+)"?\s*$', TEXT, re.M)
    assert m, name
    return int(m.group(1))


def line_of(needle):
    return next(i for i, l in enumerate(TEXT.splitlines()) if needle in l)


class StaleRetry(unittest.TestCase):
    def test_reads_the_suite_id(self):
        for needle in ("check_suite_id: .check_suite.id", '--completed-suite "$SUITE_ID"',
                       "github.event.workflow_run.check_suite_id"):
            self.assertIn(needle, TEXT)

    def test_sleeps_once_and_only_after_the_stale_test(self):
        sleeps = [i for i, l in enumerate(TEXT.splitlines()) if re.search(r"\bsleep\b", l)]
        self.assertEqual(len(sleeps), 1)
        self.assertIn('sleep "$STALE_SLEEP"', TEXT.splitlines()[sleeps[0]])
        self.assertGreater(sleeps[0], line_of("!= stale"))
        self.assertLess(sleeps[0], line_of("gh pr merge"))

    def test_bound_fits_the_job_cap(self):
        retries, sleep = env_int("STALE_RETRIES"), env_int("STALE_SLEEP")
        self.assertLessEqual(retries * sleep, 180)
        self.assertLess(retries * (sleep + 5) + 30, 300)
        self.assertIn("timeout-minutes: 5", TEXT)

    def test_rereads_inside_the_loop(self):
        loop = line_of("while :")
        for needle in ("check-runs?per_page", "compare/main...", "auto_merge_gate.py --require"):
            self.assertGreater(line_of(needle), loop)
        for needle in ("repos/$REPO/pulls/$number\"", "/files?per_page"):
            self.assertLess(line_of(needle), loop)
        done = max(i for i, l in enumerate(TEXT.splitlines()) if l.strip() == "done"
                   and i < line_of("gh pr merge"))
        self.assertLess(done, line_of("gh pr merge"))
        self.assertGreater(done, loop)


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
