"""Tests for main_red.py. Run: python3 -m unittest discover -s scripts"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import main_red  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"


def issue(number, workflow, sha="aaaaaaa"):
    return {"number": number, "title": f"main is red: {workflow} at {sha}"}


def decide(event="push", conclusion="failure", branch="main", workflow="Rust", issues=()):
    return main_red.decide(event, conclusion, branch, workflow, SHA, list(issues))


class Decide(unittest.TestCase):
    def test_failure_on_push_opens_an_issue(self):
        action = decide()
        self.assertEqual(action["action"], "open")
        self.assertEqual(action["title"], "main is red: Rust at 0123456")

    def test_failure_on_schedule_opens_an_issue(self):
        self.assertEqual(decide(event="schedule")["action"], "open")

    def test_failure_with_an_open_issue_for_the_workflow_comments(self):
        action = decide(issues=[issue(7, "Rust")])
        self.assertEqual((action["action"], action["issue"]), ("comment", 7))

    def test_failure_ignores_open_issues_of_other_workflows(self):
        self.assertEqual(decide(issues=[issue(7, "Docs")])["action"], "open")

    def test_workflow_name_prefix_is_not_a_match(self):
        self.assertEqual(decide(issues=[issue(7, "Rust nightly")])["action"], "open")

    def test_success_with_an_open_issue_closes_it(self):
        action = decide(conclusion="success", issues=[issue(7, "Rust")])
        self.assertEqual((action["action"], action["issue"]), ("close", 7))

    def test_success_without_an_open_issue_does_nothing(self):
        self.assertEqual(decide(conclusion="success")["action"], "none")

    def test_pull_request_events_do_nothing(self):
        self.assertEqual(decide(event="pull_request")["action"], "none")
        self.assertEqual(
            decide(event="pull_request", conclusion="success", issues=[issue(7, "Rust")])["action"], "none")

    def test_other_branches_do_nothing(self):
        self.assertEqual(decide(branch="claude/x")["action"], "none")

    def test_cancelled_does_nothing(self):
        self.assertEqual(decide(conclusion="cancelled", issues=[issue(7, "Rust")])["action"], "none")

    def test_skipped_does_nothing(self):
        self.assertEqual(decide(conclusion="skipped")["action"], "none")


class CommandLine(unittest.TestCase):
    def run_cli(self, issues, **kw):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "issues.json")
            with open(path, "w") as f:
                json.dump(issues, f)
            argv = ["--event", kw.get("event", "push"), "--conclusion", kw.get("conclusion", "failure"),
                    "--branch", "main", "--workflow", "Rust", "--sha", SHA, "--issues", path]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main_red.main(argv)
            return code, json.loads(out.getvalue())

    def test_prints_the_action_as_json(self):
        code, action = self.run_cli([issue(3, "Rust")], conclusion="success")
        self.assertEqual(code, 0)
        self.assertEqual(action, {"action": "close", "issue": 3})


if __name__ == "__main__":
    unittest.main()
