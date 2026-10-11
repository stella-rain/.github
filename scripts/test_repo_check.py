"""Tests for repo_check.py. Run: python3 -m unittest discover -s scripts

Follows enjay27/lakehouse's scripts/test_repo_check.py, without its line-ending checks
(eol-check.yml does those here).
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import repo_check as rc  # noqa: E402

# Built from parts so that this file does not itself match the patterns it tests.
PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIE\n-----END " + "RSA PRIVATE KEY-----\n"
AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"
GITHUB_TOKEN = "ghp_" + "a1" * 18


class RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.files = []

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, data):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data.encode("utf-8") if isinstance(data, str) else data)
        if rel not in self.files:
            self.files.append(rel)

    def errors(self):
        return rc.check_repo(self.root, self.files)


class Clean(RepoCase):
    def test_a_clean_tree_passes(self):
        self.write("README.md", "# core\n")
        self.write(".env.template", "BRIDGE_APP_ID=\nPROJECT_NUMBER=4\nBRIDGE_PRIVATE_KEY=\n")
        self.assertEqual(self.errors(), [])

    def test_an_empty_tree_passes(self):
        self.assertEqual(self.errors(), [])

    def test_crlf_is_not_this_checks_business(self):
        self.write("README.md", "# a\r\nb\r\n")
        self.assertEqual(self.errors(), [])


class EnvFiles(RepoCase):
    def test_a_committed_env_file_fails(self):
        for name in (".env", ".env.local", "tools/.env", "tools/.env.prod"):
            with self.subTest(name=name):
                self.files = []
                self.write(name, "X=1\n")
                self.assertEqual(self.errors(), [f"{name}: environment file is committed"])

    def test_the_template_is_allowed(self):
        self.write(".env.template", "PROJECT_NUMBER=\n")
        self.assertEqual(self.errors(), [])

    def test_a_credential_with_a_value_in_the_template_fails_without_printing_it(self):
        self.write(".env.template", "# comment\nPROJECT_NUMBER=4\nKEYSTORE_PASSWORD=hunter2\n"
                   "BRIDGE_CLIENT_ID=root\nKEYSTORE_USER=admin\nAPI_TOKEN=x\n"
                   "SOME_KEY=y\nBRIDGE_CLIENT_SECRET=  \nS3_ACCESS_KEY_ID=z\n")
        errors = self.errors()
        self.assertEqual(errors, [
            ".env.template:3: KEYSTORE_PASSWORD has a value; credentials stay empty",
            ".env.template:4: BRIDGE_CLIENT_ID has a value; credentials stay empty",
            ".env.template:5: KEYSTORE_USER has a value; credentials stay empty",
            ".env.template:6: API_TOKEN has a value; credentials stay empty",
            ".env.template:7: SOME_KEY has a value; credentials stay empty",
            ".env.template:9: S3_ACCESS_KEY_ID has a value; credentials stay empty",
        ])
        self.assertNotIn("hunter2", "\n".join(errors))


class KeyFiles(RepoCase):
    def test_key_and_keystore_files_fail(self):
        names = ["bridge.pem", "certs/server.key", "a.p12", "a.pfx", "a.jks", "release.keystore",
                 "id_rsa", "home/id_ed25519"]
        for name in names:
            self.write(name, "x\n")
        self.assertEqual(self.errors(), [
            f"{name}: key or keystore file is committed" for name in sorted(names)])

    def test_names_that_only_look_alike_pass(self):
        for name in ("docs/keystore.md", "src/key.rs", "pem.txt", "id_rsa.pub.md"):
            self.write(name, "x\n")
        self.assertEqual(self.errors(), [])


class Contents(RepoCase):
    def test_a_private_key_block_fails(self):
        self.write("ci/values.yaml", "a: 1\nkey: |\n" + PRIVATE_KEY)
        self.assertEqual(self.errors(), ["ci/values.yaml:3: private key block"])

    def test_an_aws_access_key_fails_without_printing_it(self):
        self.write("tools/conf.py", f"KEY = '{AWS_KEY}'\n")
        errors = self.errors()
        self.assertEqual(errors, ["tools/conf.py:1: AWS access key ID"])
        self.assertNotIn(AWS_KEY, "\n".join(errors))

    def test_a_github_token_fails_without_printing_it(self):
        self.write("notes.md", f"token {GITHUB_TOKEN}\n")
        errors = self.errors()
        self.assertEqual(errors, ["notes.md:1: GitHub token"])
        self.assertNotIn(GITHUB_TOKEN, "\n".join(errors))

    def test_every_finding_on_a_line_and_in_a_file_is_listed(self):
        self.write("a.txt", f"{AWS_KEY} {GITHUB_TOKEN}\nfine\n{AWS_KEY}\n")
        self.assertEqual(self.errors(), [
            "a.txt:1: AWS access key ID", "a.txt:1: GitHub token", "a.txt:3: AWS access key ID"])

    def test_binary_files_are_not_scanned(self):
        self.write("logo.png", b"\x89PNG\x00\x00" + AWS_KEY.encode() + b"\n")
        self.assertEqual(self.errors(), [])


class Main(unittest.TestCase):
    def test_main_checks_the_files_git_tracks(self):
        with tempfile.TemporaryDirectory() as root:
            def git(*args):
                subprocess.run(["git", "-C", root, *args], check=True, capture_output=True)
            git("init", "-q")
            for rel, text in ((".env", "X=1\n"), ("README.md", "# a\n")):
                with open(os.path.join(root, rel), "w", encoding="utf-8", newline="") as f:
                    f.write(text)
            git("add", "README.md")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(rc.main(["repo_check.py", root]), 0)
            self.assertEqual(out.getvalue(), "Repository checks pass\n")
            git("add", ".env")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(rc.main(["repo_check.py", root]), 1)
            self.assertEqual(out.getvalue(), ".env: environment file is committed\n")


class RealRepository(unittest.TestCase):
    def test_this_repository_passes(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        self.assertEqual(rc.check_repo(root, rc.tracked_files(root)), [])


if __name__ == "__main__":
    unittest.main()
