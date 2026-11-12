"""Tests for the lockin scripts. Run with: python3 -m unittest discover tests"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "lowkey" / "skills" / "lockin" / "scripts"

EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def git(repo: str, *args: str) -> str:
    """Run git in repo, return stdout as text, fail the test on error."""
    result = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def run_script(
    name: str, *args: str, cwd: str | None = None, input_bytes: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Run a script from the scripts folder with the current interpreter."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        input=input_bytes,
        capture_output=True,
        cwd=cwd,
        check=False,
        timeout=60,
    )


class ScriptRepoTestCase(unittest.TestCase):
    """Creates a git repo in a temp dir whose path holds a space, a quote, a double quote and an umlaut."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="lowkey ä'q\" ")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.realpath(os.path.join(self.tmp, "repo dir"))
        os.mkdir(self.repo)
        subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", "-q", self.repo], check=True
        )
        git(self.repo, "config", "core.autocrlf", "false")
        git(self.repo, "config", "user.name", "test")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "commit.gpgsign", "false")
        for rel in ("src/a b.txt", "it's.txt", 'quo"te.txt', "ümlaut.txt"):
            self.write(rel, f"content of {rel}\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "initial")

    def write(self, rel: str, content: str) -> str:
        """Write a file below the repo, create parent folders and return its absolute path."""
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        return path

    def snapshot(self, *args: str) -> dict:
        """Run snapshot.py for the test repo, assert exit 0 and return the parsed JSON."""
        result = run_script("snapshot.py", "--repo", self.repo, *args)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        return json.loads(result.stdout.decode("utf-8"))


class SnapshotTest(ScriptRepoTestCase):
    def test_clean_repo(self) -> None:
        snap = self.snapshot()
        self.assertEqual(snap["status"], [])
        self.assertEqual(snap["diff_hash"], EMPTY_BLOB)
        self.assertEqual(snap["untracked_hash"], EMPTY_BLOB)
        self.assertEqual(snap["untracked_files"], {})

    def test_matches_shell_pipeline(self) -> None:
        self.write("new file ü.txt", "fresh\n")
        self.write("it's.txt", "changed\n")
        snap = self.snapshot()
        diff_cmd = (
            "git diff --no-color --no-ext-diff --no-textconv HEAD -- . ':(exclude).lockin'"
            " | git hash-object --stdin"
        )
        untracked_cmd = (
            "git ls-files --others --exclude-standard -z -- . ':(exclude).lockin'"
            " | xargs -0 -r git hash-object -- | git hash-object --stdin"
        )
        expected = []
        for cmd in (diff_cmd, untracked_cmd):
            result = subprocess.run(
                cmd,
                shell=True,
                executable="/bin/bash",
                cwd=self.repo,
                capture_output=True,
                text=True,
                check=True,
            )
            expected.append(result.stdout.strip())
        self.assertEqual(snap["diff_hash"], expected[0])
        self.assertEqual(snap["untracked_hash"], expected[1])

    def test_tracked_change(self) -> None:
        before = self.snapshot()
        self.write("it's.txt", "changed\n")
        after = self.snapshot()
        self.assertNotEqual(before["status"], after["status"])
        self.assertNotEqual(before["diff_hash"], after["diff_hash"])
        self.assertEqual(before["untracked_hash"], after["untracked_hash"])

    def test_untracked_content_change(self) -> None:
        self.write("new.txt", "one\n")
        before = self.snapshot()
        self.write("new.txt", "two\n")
        after = self.snapshot()
        self.assertEqual(before["status"], after["status"])
        self.assertEqual(before["diff_hash"], after["diff_hash"])
        self.assertNotEqual(before["untracked_hash"], after["untracked_hash"])
        self.assertNotEqual(before["untracked_files"]["new.txt"], after["untracked_files"]["new.txt"])
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])

    def test_lockin_folder_is_ignored(self) -> None:
        before = self.snapshot()
        self.write(".lockin/s/state.md", "state\n")
        after = self.snapshot()
        self.assertEqual(before, after)

    def test_exclude(self) -> None:
        self.write("it's.txt", "changed\n")
        snap = self.snapshot("--exclude", "it's.txt")
        self.assertEqual(snap["status"], [])
        self.assertEqual(snap["diff_hash"], EMPTY_BLOB)

    def test_paths(self) -> None:
        self.write('quo"te.txt', "changed\n")
        self.write("ümlaut.txt", "changed\n")
        self.write("neu ä.txt", "new\n")
        snap = self.snapshot("--paths")
        self.assertIn('quo"te.txt', snap["changed"])
        self.assertIn("ümlaut.txt", snap["changed"])
        self.assertEqual(snap["untracked"], ["neu ä.txt"])

    def test_unborn_repo(self) -> None:
        unborn = os.path.realpath(os.path.join(self.tmp, "unborn"))
        os.mkdir(unborn)
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", unborn], check=True)
        result = run_script("snapshot.py", "--repo", unborn)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(json.loads(result.stdout.decode("utf-8"))["base"], EMPTY_TREE)

    def test_base_starting_with_dash(self) -> None:
        result = run_script("snapshot.py", "--repo", self.repo, "--base=-x")
        self.assertEqual(result.returncode, 2)

    def test_outside_repo(self) -> None:
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, True)
        ceiling = os.path.dirname(os.path.realpath(outside))
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": ceiling}):
            result = run_script("snapshot.py", cwd=outside)
        self.assertEqual(result.returncode, 2)
        self.assertIn("snapshot.py", result.stderr.decode("utf-8", "replace"))


class CleanupTest(ScriptRepoTestCase):
    def cleanup(self, slug: str, target: str) -> subprocess.CompletedProcess[bytes]:
        return run_script("cleanup.py", "--slug", slug, "--target", target, "--repo", self.repo)

    def test_invalid_slugs(self) -> None:
        for slug in ("", "a/b", "..", "a..b", ".", "a\\b"):
            with self.subTest(slug=slug):
                self.assertEqual(self.cleanup(slug, "run").returncode, 2)

    def test_target_review(self) -> None:
        self.write(".lockin/s/review/r.md", "review\n")
        self.write(".lockin/s/state.md", "state\n")
        result = self.cleanup("s", "review")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".lockin", "s", "review")))
        self.assertTrue(os.path.exists(os.path.join(self.repo, ".lockin", "s", "state.md")))

    def test_target_run_removes_empty_lockin(self) -> None:
        self.write(".lockin/s/state.md", "state\n")
        result = self.cleanup("s", "run")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".lockin")))
        self.assertTrue(json.loads(result.stdout.decode("utf-8"))["lockin_removed"])

    def test_target_run_keeps_lockin_with_active_json(self) -> None:
        self.write(".lockin/s/state.md", "state\n")
        self.write(".lockin/active.json", "{}\n")
        result = self.cleanup("s", "run")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".lockin", "s")))
        self.assertTrue(os.path.exists(os.path.join(self.repo, ".lockin", "active.json")))
        self.assertFalse(json.loads(result.stdout.decode("utf-8"))["lockin_removed"])

    def test_symlinked_run_folder(self) -> None:
        outside = os.path.join(self.tmp, "outside")
        os.mkdir(outside)
        keep = os.path.join(outside, "keep.txt")
        with open(keep, "w", encoding="utf-8") as handle:
            handle.write("keep\n")
        os.makedirs(os.path.join(self.repo, ".lockin"))
        os.symlink(outside, os.path.join(self.repo, ".lockin", "s"))
        result = self.cleanup("s", "run")
        self.assertEqual(result.returncode, 2)
        self.assertTrue(os.path.exists(keep))

    def test_symlinked_lockin_folder(self) -> None:
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(os.path.join(outside, "s"))
        keep = os.path.join(outside, "s", "keep.txt")
        with open(keep, "w", encoding="utf-8") as handle:
            handle.write("keep\n")
        os.symlink(outside, os.path.join(self.repo, ".lockin"))
        result = self.cleanup("s", "run")
        self.assertEqual(result.returncode, 2)
        self.assertTrue(os.path.exists(keep))

    def test_missing_target(self) -> None:
        result = self.cleanup("s", "run")
        self.assertEqual(result.returncode, 0)
        self.assertIn("nothing to delete", result.stdout.decode("utf-8"))


class CollectReviewTest(ScriptRepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.out = os.path.join(self.repo, ".lockin", "s", "review")
        os.makedirs(os.path.join(self.repo, ".lockin", "s"))

    def prepare(self, *args: str, out: str | None = None) -> subprocess.CompletedProcess[bytes]:
        return run_script(
            "collect_review.py", "prepare", "--out", out or self.out, "--repo", self.repo, *args
        )

    def run_test_command(
        self, command: str, *args: str, index: str = "1"
    ) -> subprocess.CompletedProcess[bytes]:
        return run_script(
            "collect_review.py",
            "run",
            "--out",
            self.out,
            "--index",
            index,
            "--command",
            command,
            "--repo",
            self.repo,
            *args,
        )

    def prepared(self, *args: str) -> None:
        result = self.prepare(*args)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def read_out(self, name: str) -> bytes:
        with open(os.path.join(self.out, name), "rb") as handle:
            return handle.read()

    def test_prepare_mode(self) -> None:
        self.prepared()
        self.assertEqual(stat.S_IMODE(os.stat(self.out).st_mode), 0o700)

    def test_second_prepare_removes_old_file(self) -> None:
        self.write(".lockin/s/review/old.txt", "old\n")
        self.prepared()
        self.assertFalse(os.path.exists(os.path.join(self.out, "old.txt")))
        self.prepared()
        self.assertTrue(os.path.exists(os.path.join(self.out, "diff.patch")))

    def test_diff_patch(self) -> None:
        self.write("it's.txt", "changed\n")
        self.prepared()
        self.assertIn(b"+changed", self.read_out("diff.patch"))

    def test_exclude(self) -> None:
        self.write('quo"te.txt', "changed\n")
        self.write("it's.txt", "changed\n")
        self.prepared("--exclude", 'quo"te.txt')
        patch = self.read_out("diff.patch")
        self.assertNotIn(b"quo", patch)
        self.assertIn(b"+changed", patch)

    def test_new_files(self) -> None:
        self.write("neu ä.txt", "new\n")
        self.write("skip.txt", "skip\n")
        self.write(".lockin/s/other.txt", "state\n")
        self.prepared("--exclude", "skip.txt")
        lines = self.read_out("new-files.txt").decode("utf-8").splitlines()
        self.assertEqual(lines, ["neu ä.txt"])

    def test_run_records_output(self) -> None:
        self.prepared()
        result = self.run_test_command("echo hi")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        lines = self.read_out("test-1.txt").decode("utf-8").splitlines()
        self.assertEqual(lines[0], "echo hi")
        self.assertEqual(lines[1], "hi")
        self.assertEqual(lines[-1], "exit: 0")

    def test_failing_command_exits_zero(self) -> None:
        self.prepared()
        result = self.run_test_command("exit 3", index="2")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.read_out("test-2.txt").decode("utf-8").splitlines()[-1], "exit: 3")

    def test_tracked_change_is_fatal(self) -> None:
        self.prepared()
        result = self.run_test_command('printf x >> "ümlaut.txt"')
        self.assertEqual(result.returncode, 4, result.stderr.decode("utf-8", "replace"))

    def test_new_file_rewrite_is_fatal(self) -> None:
        self.write("neu.txt", "one\n")
        self.prepared()
        result = self.run_test_command("echo changed > neu.txt")
        self.assertEqual(result.returncode, 4, result.stderr.decode("utf-8", "replace"))

    def test_created_file_is_warning(self) -> None:
        self.prepared()
        result = self.run_test_command("echo x > created.txt")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        data = json.loads(result.stdout.decode("utf-8"))
        self.assertTrue(any("created.txt" in warning for warning in data["warnings"]))
        self.assertNotIn(b"created.txt", self.read_out("new-files.txt"))

    def test_other_untracked_rewrite_is_warning(self) -> None:
        self.write("cache.txt", "one\n")
        self.prepared("--head", "HEAD")
        result = self.run_test_command("echo y > cache.txt")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        data = json.loads(result.stdout.decode("utf-8"))
        self.assertTrue(any("cache.txt" in warning for warning in data["warnings"]))

    def test_run_without_prepare(self) -> None:
        result = self.run_test_command("echo hi")
        self.assertEqual(result.returncode, 2)

    def test_out_outside_lockin(self) -> None:
        result = self.prepare(out=os.path.join(self.repo, "review"))
        self.assertEqual(result.returncode, 2)

    def test_out_via_symlinked_lockin(self) -> None:
        shutil.rmtree(os.path.join(self.repo, ".lockin"))
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(os.path.join(outside, "s"))
        os.symlink(outside, os.path.join(self.repo, ".lockin"))
        result = self.prepare()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(os.listdir(os.path.join(outside, "s")), [])

    def test_review_form_creates_lockin(self) -> None:
        shutil.rmtree(os.path.join(self.repo, ".lockin"))
        out = os.path.join(self.repo, ".lockin", "review-x")
        result = self.prepare(out=out)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertTrue(os.path.isfile(os.path.join(out, "diff.patch")))

    def test_head_mode(self) -> None:
        self.write("it's.txt", "second\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "second")
        self.write("neu.txt", "untracked\n")
        self.prepared("--base", "HEAD~1", "--head", "HEAD")
        self.assertIn(b"+second", self.read_out("diff.patch"))
        self.assertEqual(self.read_out("new-files.txt"), b"")

    def test_diff_file(self) -> None:
        source = os.path.join(self.tmp, "in.patch")
        with open(source, "wb") as handle:
            handle.write(b"abc\n\xff\n")
        self.prepared("--diff-file", source)
        self.assertEqual(self.read_out("diff.patch"), b"abc\n\xff\n")

    def test_empty_diff_file(self) -> None:
        source = os.path.join(self.tmp, "empty.patch")
        with open(source, "wb"):
            pass
        result = self.prepare("--diff-file", source)
        self.assertEqual(result.returncode, 5)

    def test_stdin_is_closed(self) -> None:
        self.prepared()
        result = self.run_test_command("cat")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.read_out("test-1.txt").decode("utf-8").splitlines()[-1], "exit: 0")

    def test_timeout(self) -> None:
        self.prepared()
        result = self.run_test_command("echo start; sleep 5", "--timeout", "1")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        content = self.read_out("test-1.txt").decode("utf-8")
        self.assertIn("start", content.splitlines())
        self.assertEqual(content.splitlines()[-1], "exit: timeout")

    def test_refs_starting_with_dash(self) -> None:
        for option in ("--base=-x", "--head=-x"):
            with self.subTest(option=option):
                self.assertEqual(self.prepare(option).returncode, 2)

    def test_background_child_is_killed(self) -> None:
        self.prepared()
        result = self.run_test_command("(sleep 1; echo late >> late.txt) & echo done")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        time.sleep(2)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "late.txt")))

    def test_sigterm_kills_the_process_group(self) -> None:
        self.prepared()
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPTS / "collect_review.py"), "run", "--out", self.out, "--index", "1",
             "--command", "(sleep 3; echo late >> late.txt) & wait", "--repo", self.repo],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        proc.terminate()
        self.assertEqual(proc.wait(timeout=10), 143)
        time.sleep(3)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "late.txt")))

    def test_bash_only_command(self) -> None:
        self.prepared()
        result = self.run_test_command("[[ 1 == 1 ]]")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.read_out("test-1.txt").decode("utf-8").splitlines()[-1], "exit: 0")


class RedactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "test-1.txt")

    def put(self, content: str) -> None:
        with open(self.path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)

    def get(self) -> str:
        with open(self.path, "r", encoding="utf-8", newline="\n") as handle:
            return handle.read()

    def redact(self) -> subprocess.CompletedProcess[bytes]:
        return run_script("redact.py", self.path)

    def test_forms(self) -> None:
        cases = [
            ("password=hunter2", "password=[REDACTED]"),
            ("password: hunter2", "password: [REDACTED]"),
            ('"api_key": "abc def"', '"api_key": "[REDACTED]"'),
            ("token = abc", "token = [REDACTED]"),
            ("DB_PASSWORD=x", "DB_PASSWORD=[REDACTED]"),
            ("Authorization: Bearer abc", "Authorization: Bearer [REDACTED]"),
            ("bearer xyz", "bearer [REDACTED]"),
            ("SECRET_THING=abc", "SECRET_THING=[REDACTED]"),
            ("HOME=/root", "HOME=[REDACTED]"),
            (
                "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----",
                "[REDACTED PRIVATE KEY]",
            ),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.put(f"vendor/bin/phpunit\n{source}\nexit: 0\n")
                result = self.redact()
                self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8", "replace"))
                self.assertEqual(self.get(), f"vendor/bin/phpunit\n{expected}\nexit: 0\n")

    def test_first_line_stays(self) -> None:
        content = "APP_ENV=test vendor/bin/phpunit\nOK\nexit: 0\n"
        self.put(content)
        result = self.redact()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.get(), content)

    def test_exit_line_stays(self) -> None:
        content = "cmd\nexit: 0\n"
        self.put(content)
        self.assertEqual(self.redact().returncode, 0)
        self.assertEqual(self.get(), content)

    def test_idempotent(self) -> None:
        self.put(
            "cmd\npassword=hunter2\nAuthorization: Bearer abc\nauthorization: token abc\n"
            '"api_key": "abc def"\nSECRET_THING=abc\nbearer xyz\n'
            "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\nexit: 0\n"
        )
        self.assertEqual(self.redact().returncode, 0)
        first = self.get()
        self.assertEqual(self.redact().returncode, 0)
        self.assertEqual(self.get(), first)
        self.assertNotIn("hunter2", first)
        self.assertNotIn("abc def", first)

    def test_unterminated_private_key(self) -> None:
        self.put("cmd\n-----BEGIN RSA PRIVATE KEY-----\nabc\nexit: 0\n")
        result = self.redact()
        self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8", "replace"))
        content = self.get()
        self.assertNotIn("BEGIN", content)
        self.assertNotIn("abc", content)
        self.assertEqual(content, "cmd\n[REDACTED PRIVATE KEY]\nexit: 0\n")

    def test_unterminated_private_key_with_base64_lines(self) -> None:
        self.put("cmd\n-----BEGIN PRIVATE KEY-----\nMIIabc\nQUJDREVG\nexit: 1\n")
        result = self.redact()
        self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8", "replace"))
        content = self.get()
        self.assertNotIn("MIIabc", content)
        self.assertNotIn("QUJDREVG", content)
        self.assertEqual(content.splitlines()[-1], "exit: 1")

    def test_long_lines_are_fast(self) -> None:
        # Each input starts a pattern and fails late, which used to backtrack quadratically.
        for name, line in (
            ("plain", "a" * 1_000_000),
            ("key-prefix", "token" + "a" * 1_000_000),
            ("repeated-keys", "password" * 100_000),
            ("unterminated-quote", 'password: "' + "a" * 1_000_000),
            ("key-begins", "-----BEGIN PRIVATE KEY-----\n" * 37_000),
        ):
            with self.subTest(name=name):
                self.put("cmd\n" + line + "\nexit: 0\n")
                start = time.monotonic()
                result = self.redact()
                self.assertLess(time.monotonic() - start, 5)
                self.assertIn(result.returncode, (0, 1))

    def test_escaped_json_key(self) -> None:
        self.put('cmd\n{"context":"{\\"password\\":\\"hunter2\\"}"}\nexit: 0\n')
        self.assertEqual(self.redact().returncode, 0)
        with open(self.path, encoding="utf-8") as handle:
            content = handle.read()
        self.assertNotIn("hunter2", content)
        self.assertIn('\\"password\\":\\"[REDACTED]\\"', content)
        self.assertEqual(self.redact().returncode, 0)
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), content)

    def test_escaped_quote_and_prefix(self) -> None:
        cases = [
            ('"password": "a\\"b"', '"password": "[REDACTED]"'),
            ("DB_PASSWORD=x", "DB_PASSWORD=[REDACTED]"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.put(f"cmd\n{source}\nexit: 0\n")
                self.assertEqual(self.redact().returncode, 0)
                self.assertEqual(self.get(), f"cmd\n{expected}\nexit: 0\n")

    def test_more_secret_forms(self) -> None:
        cases = [
            ("postgres://user:pw@host/db", "postgres://user:[REDACTED]@host/db"),
            ("ghp_" + "a1B2" * 9, "[REDACTED]"),
            ("AKIAABCDEFGHIJKLMNOP", "[REDACTED]"),
            ("eyJabcdefghijk.eyJabcdefghijk.abcdefghijklmn", "[REDACTED]"),
            ("Set-Cookie: session=abc; Path=/", "Set-Cookie: [REDACTED]"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.put(f"cmd\n{source}\nexit: 0\n")
                self.assertEqual(self.redact().returncode, 0)
                first = self.get()
                self.assertEqual(first, f"cmd\n{expected}\nexit: 0\n")
                self.assertEqual(self.redact().returncode, 0)
                self.assertEqual(self.get(), first)

    def test_form_feed_keeps_line_numbers(self) -> None:
        self.put("cmd\nbefore\x0cafter\npassword=hunter2\nexit: 0\n")
        self.assertEqual(self.redact().returncode, 0)
        self.assertIn("[REDACTED]", self.get().split("\n")[2])
        self.assertNotIn("hunter2", self.get())

    def test_missing_file(self) -> None:
        result = run_script("redact.py", os.path.join(self.tmp, "missing.txt"))
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
