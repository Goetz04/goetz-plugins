"""Tests for the typo3-upgrade scripts. Run with: python3 -m unittest discover tests"""

from __future__ import annotations

import hashlib
import http.server
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "lowkey" / "skills" / "typo3-upgrade" / "scripts"

OLD_HOST = "old.example.test"
NEW_HOST = "new.example.test"


def run_script(
    name: str,
    *args: str,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run a script from the scripts folder with the current interpreter.

    The environment is a copy of os.environ without OLD_HOST and NEW_HOST.
    Entries in env override it.
    """
    full_env = {
        key: value for key, value in os.environ.items() if key not in ("OLD_HOST", "NEW_HOST")
    }
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True,
        cwd=cwd,
        env=full_env,
        timeout=60,
        check=False,
    )


def text(result: subprocess.CompletedProcess[bytes]) -> str:
    """Return stdout and stderr of a finished process as one string."""
    return result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")


def load_module(name: str) -> ModuleType:
    """Import a script from the scripts folder as a module."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TempDirTestCase(unittest.TestCase):
    """Provides a temp dir whose path holds a space and helpers to build crawl dirs."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="typo3 upgrade ")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, path: str, content: str) -> str:
        """Write a file, create parent folders and return the path."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        return path

    def make_crawl(
        self,
        name: str,
        pages: dict[str, str],
        codes: dict[str, str] | None = None,
        complete: bool = True,
        listed: list[str] | None = None,
        baseline: bool = True,
    ) -> str:
        """Build a crawl dir with pages (uid -> HTML), status codes and the .complete marker.

        `listed` sets the uids written to status.tsv. It defaults to the page uids.
        """
        directory = os.path.join(self.tmp, name)
        os.makedirs(directory)
        uids = listed if listed is not None else list(pages)
        rows = "".join(
            f"{uid}\tslug-{uid}\t{(codes or {}).get(uid, '200')}\n" for uid in uids
        )
        self.write(os.path.join(directory, "status.tsv"), rows)
        for uid, html in pages.items():
            self.write(os.path.join(directory, f"{uid}.html"), html)
        if complete:
            self.write(os.path.join(directory, ".complete"), "")
        if baseline:
            self.write(os.path.join(directory, ".baseline"), "")
        return directory

    def residual(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
        """Run residual.py with the given arguments."""
        return run_script("residual.py", *args, env=env)


class ResidualNormalizeTest(unittest.TestCase):
    """Tests for the line normalization."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.residual = load_module("residual")

    def norm(self, line: str, host: tuple[str, str] | None = None) -> str | None:
        return self.residual.normalize_line(line, host)

    def test_cache_buster_removed(self) -> None:
        self.assertEqual(self.norm('<script src="a.js?1700000000"></script>'), '<script src="a.js"></script>')

    def test_assets_hash_masked(self) -> None:
        line = "x _assets/" + "a" * 32 + "/f.css"
        self.assertEqual(self.norm(line), "x _assets/HASH/f.css")

    def test_generator_meta_masked(self) -> None:
        self.assertEqual(self.norm('<meta name="generator" content="TYPO3 CMS">'), "GEN")

    def test_processed_path_masked(self) -> None:
        line = '<img src="/fileadmin/_processed_/a/b/csm_x_123.jpg" alt="x">'
        self.assertEqual(self.norm(line), '<img alt="x" src="/fileadmin/PROCESSED">')

    def test_void_slash_removed(self) -> None:
        self.assertEqual(self.norm('<br />'), "<br>")
        self.assertEqual(self.norm('<img src="a.png"/>'), '<img src="a.png">')

    def test_attribute_order_equal(self) -> None:
        self.assertEqual(
            self.norm('<a href="x" class="y">'),
            self.norm('<a class="y" href="x">'),
        )

    def test_single_quoted_and_at_attributes_keep_all(self) -> None:
        result = self.norm("<button @click='open()' x-on:click=\"b\" data-foo=bar disabled>")
        self.assertEqual(
            result,
            "<button " + " ".join(sorted(["@click='open()'", 'x-on:click="b"', "data-foo=bar", "disabled"])) + ">",
        )

    def test_noise_lines_dropped(self) -> None:
        self.assertIsNone(self.norm('<input style="margin:0 0 0 -999em">'))
        self.assertIsNone(self.norm('<input name="tx[__state]" value="x">'))
        self.assertIsNone(self.norm('<meta name="twitter:card" content="summary">'))

    def test_empty_line_dropped(self) -> None:
        self.assertIsNone(self.norm("   \n"))

    def test_noise_tag_removed_and_text_kept(self) -> None:
        self.assertEqual(
            self.norm('<div class="a">x</div><input name="x[__state]" value="1">'),
            '<div class="a">x</div>',
        )

    def test_twitter_card_only_line_disappears(self) -> None:
        self.assertIsNone(self.norm('  <meta name="twitter:card" content="summary">  \n'))

    def test_host_replaced_with_pair(self) -> None:
        self.assertEqual(
            self.norm(f"https://{OLD_HOST}/a", (OLD_HOST, NEW_HOST)),
            f"https://{NEW_HOST}/a",
        )

    def test_host_untouched_without_pair(self) -> None:
        self.assertEqual(self.norm(f"https://{OLD_HOST}/a"), f"https://{OLD_HOST}/a")

    def test_host_match_is_literal(self) -> None:
        self.assertEqual(self.norm("axb a.b", ("a.b", "c")), "axb c")


class ResidualCompareTest(TempDirTestCase):
    """Tests for the comparison and its exit codes."""

    def test_identical_crawls_pass(self) -> None:
        pages = {"1": "<p>a</p>\n", "2": "<p>b</p>\n"}
        base = self.make_crawl("base dir", pages)
        new = self.make_crawl("new dir", pages)
        result = self.residual(base, new)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertIn("RESULT pass compared=2 unmatched=0 matched=0", text(result))

    def test_changed_line_fails(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n", "2": "<p>b</p>\n"})
        new = self.make_crawl("new", {"1": "<p>a</p>\n", "2": "<p>c</p>\n"})
        result = self.residual(base, new)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertIn("=== 2 (2)", text(result))
        self.assertNotIn("=== 1 ", text(result))
        self.assertIn("RESULT fail compared=2 unmatched=2 matched=0", text(result))

    def test_subset_crawl_compares_only_listed_uids(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n", "2": "<p>x</p>\n", "3": "<p>y</p>\n"})
        new = self.make_crawl("new", {"1": "<p>a</p>\n"})
        result = self.residual(base, new)
        self.assertEqual(result.returncode, 0, text(result))

    def test_status_change_fails(self) -> None:
        pages = {"1": "<p>a</p>\n"}
        base = self.make_crawl("base", pages, {"1": "200"})
        new = self.make_crawl("new", pages, {"1": "404"})
        result = self.residual(base, new)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertIn("STATUS 1 200 404", text(result))

    def test_missing_complete_marker_fails_with_2(self) -> None:
        pages = {"1": "<p>a</p>\n"}
        complete = self.make_crawl("complete", pages)
        partial_a = self.make_crawl("partial a", pages, complete=False)
        partial_b = self.make_crawl("partial b", pages, complete=False)
        self.assertEqual(self.residual(partial_a, complete).returncode, 2)
        self.assertEqual(self.residual(complete, partial_b).returncode, 2)

    def test_missing_html_in_new_dir(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n"})
        new = self.make_crawl("new", {}, listed=["1"])
        result = self.residual(base, new)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertIn("MISSING 1 new", text(result))

    def test_only_one_host_variable_fails_with_2(self) -> None:
        pages = {"1": "<p>a</p>\n"}
        base = self.make_crawl("base", pages)
        new = self.make_crawl("new", pages)
        self.assertEqual(self.residual(base, new, env={"OLD_HOST": OLD_HOST}).returncode, 2)
        self.assertEqual(self.residual(base, new, env={"NEW_HOST": NEW_HOST}).returncode, 2)

    def test_host_pair_hides_host_difference(self) -> None:
        base = self.make_crawl("base", {"1": f"<a href=\"https://{OLD_HOST}/\">x</a>\n"})
        new = self.make_crawl("new", {"1": f"<a href=\"https://{NEW_HOST}/\">x</a>\n"})
        self.assertEqual(self.residual(base, new).returncode, 1)
        env = {"OLD_HOST": OLD_HOST, "NEW_HOST": NEW_HOST}
        self.assertEqual(self.residual(base, new, env=env).returncode, 0)

    def test_malformed_status_fails_with_2(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n"})
        new = self.make_crawl("new", {"1": "<p>a</p>\n"})
        self.write(os.path.join(new, "status.tsv"), "1\tonly-two\n")
        self.assertEqual(self.residual(base, new).returncode, 2)

    def test_minified_line_reports_text_change_but_not_state_change(self) -> None:
        state = '<input name="x[__state]" value="%s">\n'
        base = self.make_crawl("base", {"1": '<div class="a">unchanged</div>' + state % "1"})
        changed = self.make_crawl("changed", {"1": '<div class="a">changed</div>' + state % "2"})
        same = self.make_crawl("same", {"1": '<div class="a">unchanged</div>' + state % "2"})
        result = self.residual(base, changed)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertIn("changed</div>", text(result))
        self.assertNotIn("__state", text(result))
        self.assertEqual(self.residual(base, same).returncode, 0)

    def test_empty_new_status_fails_with_2(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n"})
        new = self.make_crawl("new", {}, listed=[])
        result = self.residual(base, new)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("no uid", text(result))

    def test_result_line_holds_compared(self) -> None:
        pages = {"1": "<p>a</p>\n"}
        result = self.residual(self.make_crawl("base", pages), self.make_crawl("new", pages))
        self.assertRegex(text(result), r"RESULT pass compared=1 unmatched=0 matched=0")

    def pages_file(self, content: str) -> tuple[str, str]:
        """Write a page list and return its path and SHA-256."""
        path = self.write(os.path.join(self.tmp, "pages.tsv"), content)
        with open(path, "rb") as handle:
            return path, hashlib.sha256(handle.read()).hexdigest()

    def test_pages_uid_missing_in_new_status_fails(self) -> None:
        pages = {"1": "<p>a</p>\n"}
        base = self.make_crawl("base", pages)
        new = self.make_crawl("new", pages)
        path, sha = self.pages_file("# list\r\n1\t/a\r\n\r\n2\t/b\r\n")
        result = self.residual("--pages", path, "--pages-sha256", sha.upper(), base, new)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertIn("MISSING 2 new-status", text(result))
        self.assertIn(f"pages sha256: {sha}", text(result))

    def test_pages_covered_passes(self) -> None:
        pages = {"1": "<p>a</p>\n"}
        base = self.make_crawl("base", pages)
        new = self.make_crawl("new", pages)
        path, sha = self.pages_file("1\t/a\n")
        result = self.residual("--pages", path, "--pages-sha256", sha, base, new)
        self.assertEqual(result.returncode, 0, text(result))

    def test_pages_wrong_hash_fails_with_2(self) -> None:
        pages = {"1": "<p>a</p>\n"}
        base = self.make_crawl("base", pages)
        new = self.make_crawl("new", pages)
        path, _ = self.pages_file("1\t/a\n")
        result = self.residual("--pages", path, "--pages-sha256", "0" * 64, base, new)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("mismatch", text(result))

    def test_pages_without_hash_fails_with_2(self) -> None:
        pages = {"1": "<p>a</p>\n"}
        base = self.make_crawl("base", pages)
        new = self.make_crawl("new", pages)
        path, sha = self.pages_file("1\t/a\n")
        self.assertEqual(self.residual("--pages", path, base, new).returncode, 2)
        self.assertEqual(self.residual("--pages-sha256", sha, base, new).returncode, 2)

    def test_limit_limits_printed_lines(self) -> None:
        old_html = "".join(f"<p>old{i}</p>\n" for i in range(5))
        new_html = "".join(f"<p>new{i}</p>\n" for i in range(5))
        base = self.make_crawl("base", {"1": old_html})
        new = self.make_crawl("new", {"1": new_html})
        out = text(self.residual("--limit", "1", base, new))
        self.assertIn("=== 1 (10)", out)
        self.assertEqual(sum(1 for line in out.splitlines() if line.startswith(("+<p>", "-<p>"))), 1)


class ResidualRoundTwoTest(TempDirTestCase):
    """Baseline marker, same folder, slug check, twitter default and probe threshold."""

    def test_baseline_without_marker_fails_with_2(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n"}, baseline=False)
        new = self.make_crawl("new", {"1": "<p>a</p>\n"})
        self.assertEqual(self.residual(base, new).returncode, 2)

    def test_same_folder_fails_with_2(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n"})
        self.assertEqual(self.residual(base, base).returncode, 2)

    def test_changed_slug_is_unmatched(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n"})
        new = self.make_crawl("new", {"1": "<p>a</p>\n"})
        self.write(os.path.join(new, "status.tsv"), "1\tother-slug\t200\n")
        result = self.residual(base, new)
        self.assertEqual(result.returncode, 1)
        self.assertIn("SLUG 1", result.stdout.decode("utf-8"))

    def test_only_default_twitter_card_is_noise(self) -> None:
        base = self.make_crawl("base", {"1": '<meta name="twitter:card" content="summary">\n'})
        new = self.make_crawl("new", {"1": '<meta content="summary_large_image" name="twitter:card">\n'})
        result = self.residual(base, new)
        self.assertEqual(result.returncode, 1)
        self.assertIn("summary_large_image", result.stdout.decode("utf-8"))

    def test_default_twitter_card_in_either_order_disappears(self) -> None:
        base = self.make_crawl("base", {"1": '<meta content="summary" name="twitter:card">\n<p>a</p>\n'})
        new = self.make_crawl("new", {"1": "<p>a</p>\n"})
        self.assertEqual(self.residual(base, new).returncode, 0)

    def test_broad_patterns_are_refused(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n"})
        new = self.make_crawl("new", {"1": "<p>b</p>\n"})
        for pattern in ("\\S", "[^ ]", ".{2,}", "[a-z]"):
            expect = os.path.join(self.tmp, "expect.tsv")
            self.write(expect, f"*\t{pattern}\n")
            digest = hashlib.sha256(Path(expect).read_bytes()).hexdigest()
            result = self.residual("--expect", expect, "--expect-sha256", digest, base, new)
            self.assertEqual(result.returncode, 2, pattern)

    def test_narrow_pattern_still_works(self) -> None:
        base = self.make_crawl("base", {"1": "<p>a</p>\n"})
        new = self.make_crawl("new", {"1": "<p>b</p>\n"})
        expect = os.path.join(self.tmp, "expect.tsv")
        self.write(expect, "1\t^<p>[ab]</p>$\n")
        digest = hashlib.sha256(Path(expect).read_bytes()).hexdigest()
        result = self.residual("--expect", expect, "--expect-sha256", digest, base, new)
        self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8"))


class ResidualExpectTest(TempDirTestCase):
    """Tests for the expect file."""

    def setUp(self) -> None:
        super().setUp()
        self.base = self.make_crawl("base", {"1": "<p>a</p>\n", "22": "<p>a</p>\n"})
        self.new = self.make_crawl("new", {"1": "<p>b</p>\n", "22": "<p>b</p>\n"})

    def expect_file(self, content: str) -> tuple[str, str]:
        """Write an expect file and return its path and SHA-256."""
        path = self.write(os.path.join(self.tmp, "expect.tsv"), content)
        with open(path, "rb") as handle:
            return path, hashlib.sha256(handle.read()).hexdigest()

    def run_expect(self, content: str, sha: str | None = None) -> subprocess.CompletedProcess[bytes]:
        path, real = self.expect_file(content)
        return self.residual("--expect", path, "--expect-sha256", sha or real, self.base, self.new)

    def test_uid_rule_matches(self) -> None:
        both = "1\t^<p>[ab]</p>$\n22\t^<p>[ab]</p>$\n"
        result = self.run_expect(both)
        self.assertEqual(result.returncode, 0, text(result))
        out = text(result)
        self.assertIn("## matched", out)
        self.assertIn("1 2", out)
        self.assertIn("RESULT pass compared=2 unmatched=0 matched=4", out)

    def test_rule_for_other_uid_does_not_match(self) -> None:
        result = self.run_expect("1\t^<p>[ab]</p>$\n")
        self.assertEqual(result.returncode, 1, text(result))
        self.assertIn("=== 22 (2)", text(result))

    def test_star_rule_applies_to_all_uids(self) -> None:
        result = self.run_expect("# comment\n\n*\t<p>[ab]</p>\n")
        self.assertEqual(result.returncode, 0, text(result))
        self.assertIn("matched=4", text(result))

    def test_status_rule_matches_status_change(self) -> None:
        base = self.make_crawl("sbase", {"1": "<p>a</p>\n"}, {"1": "200"})
        new = self.make_crawl("snew", {"1": "<p>a</p>\n"}, {"1": "301"})
        path, sha = self.expect_file("1\tSTATUS 200 301\n")
        result = self.residual("--expect", path, "--expect-sha256", sha, base, new)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertIn("matched=1", text(result))

    def test_wrong_hash_fails_with_2(self) -> None:
        result = self.run_expect("*\t<p>\n", sha="0" * 64)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("mismatch", text(result))

    def test_expect_without_hash_fails_with_2(self) -> None:
        path, _ = self.expect_file("*\t<p>\n")
        self.assertEqual(self.residual("--expect", path, self.base, self.new).returncode, 2)

    def test_hash_without_expect_fails_with_2(self) -> None:
        self.assertEqual(self.residual("--expect-sha256", "0" * 64, self.base, self.new).returncode, 2)

    def test_catch_all_fails_with_2(self) -> None:
        for pattern in (".*", ".+", "^.*$", "^", "$", ""):
            with self.subTest(pattern=pattern):
                self.assertEqual(self.run_expect(f"*\t{pattern}\n").returncode, 2)

    def test_probe_catch_all_fails_with_2(self) -> None:
        for pattern in (".", ".*?", r"\S*", "(?s).*"):
            with self.subTest(pattern=pattern):
                result = self.run_expect(f"*\t{pattern}\n")
                self.assertEqual(result.returncode, 2, text(result))
                self.assertIn("catch-all", text(result))

    def test_narrow_pattern_still_works(self) -> None:
        result = self.run_expect('*\t^<p class="x">\n')
        self.assertEqual(result.returncode, 1, text(result))

    def test_line_without_tab_fails_with_2(self) -> None:
        result = self.run_expect("# ok\n*<p>\n")
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("line 2", text(result))

    def test_invalid_regex_fails_with_2(self) -> None:
        result = self.run_expect("*\t(unclosed\n")
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("line 1", text(result))

    def test_status_rule_with_star_fails_with_2(self) -> None:
        self.assertEqual(self.run_expect("*\tSTATUS 200 301\n").returncode, 2)

    def test_output_contains_expect_hash(self) -> None:
        path, sha = self.expect_file("*\t<p>[ab]</p>\n")
        result = self.residual("--expect", path, "--expect-sha256", sha.upper(), self.base, self.new)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertEqual(text(result).splitlines()[0], f"expect sha256: {sha}")


class TreeHashTest(TempDirTestCase):
    """Tests for tree_hash.py."""

    def tree(self, name: str, files: dict[str, str]) -> str:
        """Create a folder with the given files in dict order and return its path."""
        directory = os.path.join(self.tmp, name)
        os.makedirs(directory)
        for rel, content in files.items():
            self.write(os.path.join(directory, rel), content)
        return directory

    def hash(self, *dirs: str) -> subprocess.CompletedProcess[bytes]:
        return run_script("tree_hash.py", *dirs)

    def test_same_content_same_hash(self) -> None:
        directory = self.tree("data", {"a.txt": "1", "sub/b.txt": "2"})
        first, second = self.hash(directory), self.hash(directory)
        self.assertEqual(first.returncode, 0, text(first))
        self.assertEqual(first.stdout, second.stdout)
        self.assertRegex(first.stdout.decode("ascii"), r"^[0-9a-f]{64}\n$")

    def test_edit_changes_hash(self) -> None:
        directory = self.tree("data", {"a.txt": "1"})
        before = self.hash(directory).stdout
        self.write(os.path.join(directory, "a.txt"), "2")
        self.assertNotEqual(before, self.hash(directory).stdout)

    def test_rename_changes_hash(self) -> None:
        directory = self.tree("data", {"a.txt": "1"})
        before = self.hash(directory).stdout
        os.rename(os.path.join(directory, "a.txt"), os.path.join(directory, "b.txt"))
        self.assertNotEqual(before, self.hash(directory).stdout)

    def test_missing_dir_fails_with_2(self) -> None:
        result = self.hash(os.path.join(self.tmp, "missing"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("tree_hash: ", text(result))

    def test_duplicate_labels_fail_with_2(self) -> None:
        first = self.tree("one/data", {"a.txt": "1"})
        second = self.tree("two/data", {"a.txt": "1"})
        self.assertEqual(self.hash(first, second).returncode, 2)

    @unittest.skipIf(not hasattr(os, "symlink"), "os.symlink is not available")
    def test_symlink_fails_with_2(self) -> None:
        directory = self.tree("data", {"a.txt": "1"})
        try:
            os.symlink(os.path.join(directory, "a.txt"), os.path.join(directory, "link.txt"))
        except OSError as error:
            self.skipTest(f"cannot create symlink: {error}")
        result = self.hash(directory)
        self.assertEqual(result.returncode, 2)
        self.assertIn("link.txt", text(result))

    @unittest.skipIf(not hasattr(os, "symlink"), "os.symlink is not available")
    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read every folder")
    def test_unreadable_folder_fails_with_2(self) -> None:
        directory = self.tree("data", {"sub/a.txt": "1"})
        sub = os.path.join(directory, "sub")
        os.chmod(sub, 0)
        self.addCleanup(os.chmod, sub, 0o755)
        result = self.hash(directory)
        self.assertEqual(result.returncode, 2, text(result))

    def test_symlinked_root_fails_with_2(self) -> None:
        directory = self.tree("data", {"a.txt": "1"})
        link = os.path.join(self.tmp, "link")
        try:
            os.symlink(directory, link)
        except OSError as error:
            self.skipTest(f"cannot create symlink: {error}")
        result = self.hash(link)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("symlink", text(result))

    @unittest.skipIf(not hasattr(os, "mkfifo"), "os.mkfifo is not available")
    def test_named_pipe_fails_with_2(self) -> None:
        directory = self.tree("data", {"a.txt": "1"})
        os.mkfifo(os.path.join(directory, "pipe"))
        result = self.hash(directory)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("pipe", text(result))

    def test_empty_dir_hashes_empty_input(self) -> None:
        directory = self.tree("empty", {})
        result = self.hash(directory)
        self.assertEqual(result.stdout.decode("ascii").strip(), hashlib.sha256(b"").hexdigest())

    def test_creation_order_does_not_matter(self) -> None:
        first = self.tree("one/data", {"a.txt": "1", "b.txt": "2", "c/d.txt": "3"})
        second = self.tree("two/data", {"c/d.txt": "3", "b.txt": "2", "a.txt": "1"})
        self.assertEqual(self.hash(first).stdout, self.hash(second).stdout)


def run_bash(
    script: str,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run a Bash script from the scripts folder.

    The environment is a copy of os.environ without OLD_HOST, NEW_HOST and CRAWL_INSECURE.
    Entries in env override it.
    """
    full_env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("OLD_HOST", "NEW_HOST", "CRAWL_INSECURE")
    }
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        capture_output=True,
        env=full_env,
        timeout=60,
        check=False,
    )


class PageHandler(http.server.BaseHTTPRequestHandler):
    """Serves /ok and /ok2 with 200 and everything else with 404."""

    def do_GET(self) -> None:
        if self.path in ("/ok", "/ok2"):
            status, body = 200, f"<p>page {self.path}</p>\n".encode("utf-8")
        else:
            status, body = 404, b"<p>not found</p>\n"
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Silence the request log."""


@unittest.skipUnless(shutil.which("bash") and shutil.which("curl"), "needs bash and curl")
class CrawlTest(TempDirTestCase):
    """Tests for crawl.sh against a local HTTP server."""

    def setUp(self) -> None:
        super().setUp()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), PageHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_address[1]}"

    def pages(self, content: str) -> str:
        """Write a pages file and return its path."""
        return self.write(os.path.join(self.tmp, "pages.tsv"), content)

    def crawl(
        self, pages: str, out: str, *flags: str, base: str | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        return run_bash("crawl.sh", *flags, pages, out, base or self.base)

    def read(self, path: str) -> str:
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_smoke_crawl_records_pages_and_markers(self) -> None:
        out = os.path.join(self.tmp, "out")
        result = self.crawl(self.pages("1\t/ok\n2\t/missing\n"), out)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertTrue(os.path.isfile(os.path.join(out, "1.html")))
        self.assertEqual(
            self.read(os.path.join(out, "status.tsv")), "1\t/ok\t200\n2\t/missing\t404\n"
        )
        self.assertTrue(os.path.isfile(os.path.join(out, ".smoke")))
        self.assertTrue(os.path.isfile(os.path.join(out, ".complete")))

    def test_smoke_crawl_is_idempotent(self) -> None:
        out = os.path.join(self.tmp, "out")
        self.assertEqual(self.crawl(self.pages("1\t/ok\n"), out).returncode, 0)
        self.assertIn("/ok", self.read(os.path.join(out, "1.html")))
        result = self.crawl(self.pages("1\t/ok2\n"), out)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertIn("/ok2", self.read(os.path.join(out, "1.html")))
        self.assertEqual(self.read(os.path.join(out, "status.tsv")), "1\t/ok2\t200\n")

    def test_baseline_into_new_folder(self) -> None:
        out = os.path.join(self.tmp, "base")
        result = self.crawl(self.pages("1\t/ok\n"), out, "--baseline")
        self.assertEqual(result.returncode, 0, text(result))
        self.assertTrue(os.path.isfile(os.path.join(out, ".baseline")))
        self.assertTrue(os.path.isfile(os.path.join(out, ".complete")))
        self.assertFalse(os.path.exists(os.path.join(out, ".smoke")))

    def test_baseline_into_existing_empty_folder_fails(self) -> None:
        out = os.path.join(self.tmp, "base")
        os.makedirs(out)
        result = self.crawl(self.pages("1\t/ok\n"), out, "--baseline")
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("refusing to overwrite", text(result))

    def test_unknown_option_fails(self) -> None:
        out = os.path.join(self.tmp, "out")
        self.assertEqual(self.crawl(self.pages("1\t/ok\n"), out, "--force").returncode, 2)

    def test_smoke_into_baseline_fails(self) -> None:
        out = os.path.join(self.tmp, "base")
        pages = self.pages("1\t/ok\n")
        self.assertEqual(self.crawl(pages, out, "--baseline").returncode, 0)
        before = self.read(os.path.join(out, "1.html"))
        result = self.crawl(self.pages("1\t/ok2\n"), out)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("is a baseline", text(result))
        self.assertEqual(self.read(os.path.join(out, "1.html")), before)
        self.assertTrue(os.path.isfile(os.path.join(out, ".baseline")))

    def test_smoke_into_folder_without_marker_fails(self) -> None:
        out = os.path.join(self.tmp, "other")
        keep = self.write(os.path.join(out, "keep.txt"), "keep")
        result = self.crawl(self.pages("1\t/ok\n"), out)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertEqual(self.read(keep), "keep")
        self.assertEqual(sorted(os.listdir(out)), ["keep.txt"])

    def test_smoke_into_file_fails(self) -> None:
        path = self.write(os.path.join(self.tmp, "file"), "x")
        self.assertEqual(self.crawl(self.pages("1\t/ok\n"), path).returncode, 2)

    def test_invalid_uid_and_slug_are_skipped(self) -> None:
        out = os.path.join(self.tmp, "sub", "out")
        os.makedirs(os.path.dirname(out))
        result = self.crawl(self.pages("../evil\t/ok\n5\tno-slash\n1\t/ok\n"), out)
        self.assertEqual(result.returncode, 0, text(result))
        err = result.stderr.decode("utf-8", "replace")
        self.assertIn("skipping invalid uid: ../evil", err)
        self.assertIn("skipping uid 5", err)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "sub", "evil.html")))
        self.assertEqual(self.read(os.path.join(out, "status.tsv")), "1\t/ok\t200\n")

    def test_repeated_uid_is_skipped(self) -> None:
        out = os.path.join(self.tmp, "out")
        result = self.crawl(self.pages("1\t/ok\n1\t/ok2\n"), out)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertEqual(self.read(os.path.join(out, "status.tsv")), "1\t/ok\t200\n")
        self.assertIn("repeated uid", text(result))

    def test_comments_empty_lines_and_missing_final_newline(self) -> None:
        out = os.path.join(self.tmp, "out")
        result = self.crawl(self.pages("# comment\n\n1\t/ok\n\n2\t/ok2"), out)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertEqual(
            self.read(os.path.join(out, "status.tsv")), "1\t/ok\t200\n2\t/ok2\t200\n"
        )

    def test_crlf_line_endings(self) -> None:
        out = os.path.join(self.tmp, "out")
        pages = os.path.join(self.tmp, "crlf.tsv")
        with open(pages, "wb") as handle:
            handle.write(b"1\t/ok\r\n2\t/ok2\r\n")
        result = self.crawl(pages, out)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertEqual(
            self.read(os.path.join(out, "status.tsv")), "1\t/ok\t200\n2\t/ok2\t200\n"
        )

    def test_closed_port_records_000(self) -> None:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        out = os.path.join(self.tmp, "out")
        result = self.crawl(self.pages("1\t/ok\n"), out, base=f"http://127.0.0.1:{port}")
        self.assertEqual(result.returncode, 0, text(result))
        self.assertEqual(self.read(os.path.join(out, "status.tsv")), "1\t/ok\t000\n")
        self.assertTrue(os.path.isfile(os.path.join(out, ".complete")))

    def test_zero_valid_pages_fails(self) -> None:
        out = os.path.join(self.tmp, "out")
        result = self.crawl(self.pages("# only a comment\n\n"), out)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertFalse(os.path.exists(os.path.join(out, ".complete")))

    def test_zero_valid_pages_leaves_no_folder(self) -> None:
        out = os.path.join(self.tmp, "out")
        result = self.crawl(self.pages("# comment\nbad uid\t/ok\n5\tno-slash\n"), out)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertFalse(os.path.exists(out))

    @unittest.skipIf(not hasattr(os, "symlink"), "os.symlink is not available")
    def test_symlinked_outdir_fails(self) -> None:
        target = os.path.join(self.tmp, "target")
        os.makedirs(target)
        link = os.path.join(self.tmp, "link")
        try:
            os.symlink(target, link)
        except OSError as error:
            self.skipTest(f"cannot create symlink: {error}")
        pages = self.pages("1\t/ok\n")
        for flags in ((), ("--baseline",)):
            with self.subTest(flags=flags):
                result = self.crawl(pages, link, *flags)
                self.assertEqual(result.returncode, 2, text(result))
        self.assertEqual(os.listdir(target), [])

    def test_smoke_folder_with_foreign_file_fails(self) -> None:
        out = os.path.join(self.tmp, "out")
        self.write(os.path.join(out, ".smoke"), "")
        self.write(os.path.join(out, "1.html"), "old")
        notes = self.write(os.path.join(out, "notes.txt"), "keep")
        result = self.crawl(self.pages("1\t/ok\n"), out)
        self.assertEqual(result.returncode, 2, text(result))
        self.assertEqual(self.read(notes), "keep")
        self.assertEqual(self.read(os.path.join(out, "1.html")), "old")
        self.assertEqual(sorted(os.listdir(out)), [".smoke", "1.html", "notes.txt"])

    def test_baseline_against_closed_port_fails(self) -> None:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        out = os.path.join(self.tmp, "base")
        result = self.crawl(self.pages("1\t/ok\n"), out, "--baseline", base=f"http://127.0.0.1:{port}")
        self.assertEqual(result.returncode, 2, text(result))
        self.assertIn("not reachable", text(result))
        self.assertFalse(os.path.exists(os.path.join(out, ".complete")))

    def test_wrong_argument_count_fails(self) -> None:
        self.assertEqual(run_bash("crawl.sh").returncode, 2)
        self.assertEqual(run_bash("crawl.sh", self.pages("1\t/ok\n"), self.tmp).returncode, 2)

    def test_invalid_base_url_fails(self) -> None:
        out = os.path.join(self.tmp, "out")
        result = self.crawl(self.pages("1\t/ok\n"), out, base="ftp://x")
        self.assertEqual(result.returncode, 2, text(result))

    def test_missing_pages_file_fails(self) -> None:
        out = os.path.join(self.tmp, "out")
        result = self.crawl(os.path.join(self.tmp, "nope.tsv"), out)
        self.assertEqual(result.returncode, 2, text(result))

    def test_output_folder_with_space(self) -> None:
        out = os.path.join(self.tmp, "out dir", "with space")
        result = self.crawl(self.pages("1\t/ok\n"), out)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertTrue(os.path.isfile(os.path.join(out, "1.html")))


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class HtmlDiffTest(TempDirTestCase):
    """Tests for htmldiff.sh."""

    def normalize(
        self, content: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        path = self.write(os.path.join(self.tmp, "in.html"), content)
        return run_bash("htmldiff.sh", "--normalize", path, env=env)

    def diff(
        self, a: str, b: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        return run_bash("htmldiff.sh", a, b, env=env)

    def test_cache_buster_removed(self) -> None:
        result = self.normalize('<script src="a.js?1700000000"></script>\n')
        self.assertEqual(result.stdout.decode(), '<script src="a.js"></script>\n')

    def test_assets_hash_masked(self) -> None:
        result = self.normalize("x _assets/" + "a" * 32 + "/f.css\n")
        self.assertEqual(result.stdout.decode(), "x _assets/HASH/f.css\n")

    def test_generator_meta_masked(self) -> None:
        result = self.normalize('<meta name="generator" content="TYPO3 CMS">\n')
        self.assertEqual(result.stdout.decode(), "GEN\n")

    def test_processed_path_masked(self) -> None:
        result = self.normalize('<img src="/f/_processed_/a/b/csm_x.jpg" alt="x">\n')
        self.assertEqual(result.stdout.decode(), '<img src="/f/PROCESSED" alt="x">\n')

    def test_noise_lines_dropped(self) -> None:
        content = (
            "<p>keep</p>\n"
            '<input style="margin:0 0 0 -999em">\n'
            '<input name="tx[__state]" value="x">\n'
            "   \n"
            "\n"
            "<p>end</p>\n"
        )
        result = self.normalize(content)
        self.assertEqual(result.stdout.decode(), "<p>keep</p>\n<p>end</p>\n")

    def test_state_input_tag_removed_text_kept(self) -> None:
        result = self.normalize('<div>text</div><input name="x[__state]" value="1">\n')
        self.assertEqual(result.stdout.decode(), "<div>text</div>\n")

    def test_only_default_twitter_card_removed(self) -> None:
        result = self.normalize(
            '<meta content="summary" name="twitter:card">\n<meta name="twitter:card" content="summary_large_image">\n'
        )
        self.assertEqual(result.stdout.decode(), '<meta name="twitter:card" content="summary_large_image">\n')

    def test_all_lines_dropped_prints_nothing(self) -> None:
        result = self.normalize('\n<input name="tx[__state]">\n')
        self.assertEqual(result.returncode, 0, text(result))
        self.assertEqual(result.stdout, b"")

    def test_host_replaced_with_pair(self) -> None:
        env = {"OLD_HOST": OLD_HOST, "NEW_HOST": NEW_HOST}
        result = self.normalize(f"https://{OLD_HOST}/a\n", env=env)
        self.assertEqual(result.stdout.decode(), f"https://{NEW_HOST}/a\n")

    def test_only_one_host_variable_fails(self) -> None:
        self.assertEqual(self.normalize("x\n", env={"OLD_HOST": OLD_HOST}).returncode, 2)
        self.assertEqual(self.normalize("x\n", env={"NEW_HOST": NEW_HOST}).returncode, 2)

    def test_host_match_is_literal(self) -> None:
        result = self.normalize("axb a.b\n", env={"OLD_HOST": "a.b", "NEW_HOST": "c&d"})
        self.assertEqual(result.stdout.decode(), "axb c&d\n")

    def test_identical_crawls_pass(self) -> None:
        pages = {"1": "<p>a</p>\n", "2": "<p>b</p>\n"}
        a = self.make_crawl("dir a", pages)
        b = self.make_crawl("dir b", pages)
        result = self.diff(a, b)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertEqual(result.stdout, b"")

    def test_changed_line_reported(self) -> None:
        a = self.make_crawl("a", {"1": "<p>a</p>\n", "2": "<p>b</p>\n"})
        b = self.make_crawl("b", {"1": "<p>a</p>\n", "2": "<p>c</p>\n"})
        result = self.diff(a, b)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertEqual(result.stdout.decode().splitlines(), ["2 2"])

    def test_one_changed_line_counts_changes(self) -> None:
        a = self.make_crawl("a", {"7": "<p>a</p>\n"})
        b = self.make_crawl("b", {"7": "<p>a</p>\n<p>new</p>\n"})
        result = self.diff(a, b)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertEqual(result.stdout.decode().splitlines(), ["7 1"])

    def test_status_change_reported(self) -> None:
        pages = {"1": "<p>a</p>\n"}
        a = self.make_crawl("a", pages, {"1": "200"})
        b = self.make_crawl("b", pages, {"1": "404"})
        result = self.diff(a, b)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertIn("STATUS 1 200 404", result.stdout.decode())

    def test_status_line_order_does_not_matter(self) -> None:
        pages = {"1": "<p>a</p>\n", "2": "<p>b</p>\n"}
        a = self.make_crawl("a", pages, {"1": "200", "2": "404"})
        b = self.make_crawl("b", pages, {"1": "200", "2": "404"})
        self.write(os.path.join(b, "status.tsv"), "2\tslug-2\t404\n1\tslug-1\t200\n")
        result = self.diff(a, b)
        self.assertEqual(result.returncode, 0, text(result))
        self.assertEqual(result.stdout, b"")

    def test_uid_only_in_one_status_file(self) -> None:
        a = self.make_crawl("a", {"1": "<p>a</p>\n", "2": "<p>b</p>\n"})
        b = self.make_crawl("b", {"1": "<p>a</p>\n", "3": "<p>c</p>\n"})
        result = self.diff(a, b)
        self.assertEqual(result.returncode, 1, text(result))
        lines = result.stdout.decode().splitlines()
        self.assertIn("MISSING 2 B", lines)
        self.assertIn("MISSING 3 A", lines)

    def test_missing_html_reported(self) -> None:
        a = self.make_crawl("a", {"1": "<p>a</p>\n"})
        b = self.make_crawl("b", {}, listed=["1"])
        result = self.diff(a, b)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertIn("MISSING 1.html B", result.stdout.decode())

    def test_dirs_with_spaces(self) -> None:
        a = self.make_crawl("dir with space a", {"1": "<p>a</p>\n"})
        b = self.make_crawl("dir with space b", {"1": "<p>b</p>\n"})
        result = self.diff(a, b)
        self.assertEqual(result.returncode, 1, text(result))
        self.assertIn("1 2", result.stdout.decode())

    def test_missing_status_file_fails(self) -> None:
        a = self.make_crawl("a", {"1": "<p>a</p>\n"})
        b = self.make_crawl("b", {"1": "<p>a</p>\n"})
        os.remove(os.path.join(b, "status.tsv"))
        self.assertEqual(self.diff(a, b).returncode, 2)

    def test_wrong_argument_count_fails(self) -> None:
        self.assertEqual(run_bash("htmldiff.sh").returncode, 2)
        self.assertEqual(run_bash("htmldiff.sh", self.tmp).returncode, 2)


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class ShellSyntaxTest(unittest.TestCase):
    """Checks the Bash scripts with bash -n."""

    def test_syntax(self) -> None:
        for name in ("crawl.sh", "htmldiff.sh"):
            with self.subTest(script=name):
                result = subprocess.run(
                    ["bash", "-n", str(SCRIPTS / name)],
                    capture_output=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, text(result))


@unittest.skipUnless(shutil.which("php"), "needs php")
class PhpLintTest(unittest.TestCase):
    """Checks the PHP scripts with php -l."""

    def test_syntax(self) -> None:
        for name in ("ts-dump.php", "extension-scanner.php"):
            with self.subTest(script=name):
                result = subprocess.run(
                    ["php", "-l", str(SCRIPTS / name)],
                    capture_output=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, text(result))


if __name__ == "__main__":
    unittest.main()
