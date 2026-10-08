"""Tests for setup-project.sh, run with DRY_RUN=<file> so that every gh command is only logged.
Run: python3 -m unittest discover -s scripts"""

import os
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup-project.sh")


def dry_run(**env):
    """The gh commands the script would run, one per line."""
    merged = {k: v for k, v in os.environ.items() if k not in ("ORG", "TITLE", "SYNCED_REPOS", "PHASES")}
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "gh.log")
        merged.update(env, DRY_RUN=log)
        done = subprocess.run(["bash", SCRIPT], env=merged, capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            raise AssertionError(f"exit {done.returncode}: {done.stderr}")
        with open(log, encoding="utf-8") as f:
            return f.read().splitlines()


@unittest.skipUnless(shutil.which("bash") and shutil.which("jq"), "needs bash and jq")
class SetupProject(unittest.TestCase):
    def test_default_is_stella_rain_with_phases(self):
        commands = "\n".join(dry_run())
        self.assertIn("--owner stella-rain --title Stella Rain", commands)
        self.assertIn("--name Phase --data-type SINGLE_SELECT --single-select-options P0 Android spike,", commands)
        for repo in ("app", "core"):
            for n in range(5):
                self.assertIn(f"gh label create cmd:phase-p{n} --repo stella-rain/{repo} ", commands)
        self.assertIn("--repos app,core", commands)

    def test_verification_has_the_environments_and_no_needs_kade_field_option(self):
        verification = [c for c in dry_run() if "--name Verification" in c][0]
        self.assertIn("Verified,NOT VERIFIED,Needs Windows,Needs macOS,Needs Android device,Needs iPhone", verification)
        self.assertNotIn("Needs Kade", verification)

    def test_environment_labels_exist_and_the_old_one_is_deleted(self):
        commands = dry_run()
        for env in ("windows", "macos", "android", "iphone"):
            self.assertTrue(any(f"gh label create cmd:verify-needs-{env} --repo stella-rain/app " in c for c in commands), env)
        self.assertTrue(any("gh label delete cmd:verify-needs-kade --repo stella-rain/app" in c for c in commands))

    def test_another_organization_with_no_phases(self):
        commands = dry_run(
            ORG="star-resonance", TITLE="Resonance", SYNCED_REPOS="resonance-stream resonance-lab", PHASES=""
        )
        text = "\n".join(commands)
        self.assertIn("--owner star-resonance --title Resonance", text)
        self.assertNotIn("--name Phase", text)
        self.assertNotIn("cmd:phase-", text)
        self.assertNotIn("stella-rain", text)
        for repo in ("resonance-stream", "resonance-lab"):
            self.assertIn(f"gh label create cmd:status-now --repo star-resonance/{repo} ", text)
            self.assertIn(f"gh label create cmd:verify-needs-macos --repo star-resonance/{repo} ", text)
        self.assertIn("--repos resonance-stream,resonance-lab", text)

    def test_description_names_the_title_not_stella_rain(self):
        text = "\n".join(dry_run(ORG="star-resonance", TITLE="Resonance", SYNCED_REPOS="resonance-lab", PHASES=""))
        self.assertIn("Issues and roadmap for every Resonance repository", text)

    def test_a_custom_phase_list_makes_that_many_phase_labels(self):
        text = "\n".join(dry_run(PHASES="Alpha,Beta", SYNCED_REPOS="app"))
        self.assertIn("--single-select-options Alpha,Beta", text)
        self.assertIn("cmd:phase-p0 ", text)
        self.assertIn("cmd:phase-p1 ", text)
        self.assertNotIn("cmd:phase-p2 ", text)


if __name__ == "__main__":
    unittest.main()
