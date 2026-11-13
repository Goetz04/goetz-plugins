#!/usr/bin/env python3
"""Compare two crawls of a TYPO3 site after removing known rendering noise.

Usage:
    residual.py [--limit N] [--expect FILE --expect-sha256 HEX]
                [--pages TSV --pages-sha256 HEX] <baseline-dir> <new-dir>

Each crawl dir holds one `<uid>.html` per page, a `status.tsv` (`uid<TAB>slug<TAB>code`)
and an empty marker file `.complete`. The baseline dir also holds `.baseline` (written by
`crawl.sh --baseline`). Both arguments must be different folders. Only uids listed in
`<new-dir>/status.tsv` are compared. A new crawl without any uid is an error. A uid whose
slug differs between both status files counts as unmatched (`SLUG <uid> <old> <new>`).

Normalization per line: removes only the noise tags (honeypot fields, form state and the
default twitter:card tag with content="summary") and keeps the rest of the line, replaces OLD_HOST with NEW_HOST
(both env vars set, literal match), removes cache busters, masks _assets hashes, generator
meta and _processed_ paths, drops the void tag slash, sorts tag attributes and trims
whitespace. A line that held only a noise tag disappears.

Expect file: one rule per line as `<uid or *><TAB><regex>` or `<uid><TAB>STATUS <old> <new>`.
Empty lines and lines starting with `#` are ignored. Its SHA-256 must match --expect-sha256.
Every remaining difference must match a rule, otherwise it counts as unmatched.
A line rule that matches 7 or more of 9 probe strings counts as catch-all and is refused.
Anchor rules and keep them narrow.

Pages file (optional): the page list of the crawl, pinned by --pages-sha256. Every uid in it
must appear in `<new-dir>/status.tsv`, otherwise it counts as unmatched (`MISSING <uid> new-status`).

The last line reads `RESULT <pass|fail> compared=<c> unmatched=<n> matched=<m>`.

Exit codes: 0 no unmatched differences, 1 unmatched differences, 2 usage or input error.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field

DEFAULT_LIMIT = 12
MAX_LINE_LENGTH = 230
NOISE_TAG_RE = re.compile(r'<[^<>]*(?:margin:0 0 0 -999em|\[__state\])[^<>]*>')
# TYPO3 13 no longer always renders the default twitter card. Only the default value counts as noise.
TWITTER_DEFAULT_RE = re.compile(r'<meta(?=[^<>]*name="twitter:card")(?=[^<>]*content="summary")[^<>]*>')
TAG_RE = re.compile(r"<(\w+)\s+([^<>]*?)>")
ATTR_RE = re.compile(
    r"""[^\s=<>"']+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'<>]+))?"""
)
STATUS_RULE_RE = re.compile(r"^STATUS (\S+) (\S+)$")
CATCH_ALL_PATTERNS = {"", ".*", ".+", "^.*$", "^.+$", "^.*", ".*$", "^", "$"}
CATCH_ALL_PROBES = (
    "x", "<p>", "Zq9", " ", "</div>", "a=b", '<div class="a">', "https://x.test/a", "Lorem ipsum",
)
# A rule that matches this many probes approves nearly any changed line.
CATCH_ALL_THRESHOLD = 7


class UsageError(Exception):
    """Invalid usage or input. `main` turns it into exit code 2."""


@dataclass
class Expectations:
    """Approved differences loaded from an expect file."""

    line_rules: list[tuple[str, re.Pattern[str]]]
    status_rules: set[tuple[str, str, str]]
    sha256: str


@dataclass
class Result:
    """Outcome of a comparison, grouped by uid."""

    unmatched: dict[str, list[str]] = field(default_factory=dict)
    matched: dict[str, int] = field(default_factory=dict)
    compared: int = 0

    def add_unmatched(self, uid: str, item: str) -> None:
        self.unmatched.setdefault(uid, []).append(item)

    def add_matched(self, uid: str) -> None:
        self.matched[uid] = self.matched.get(uid, 0) + 1


def sort_attributes(match: re.Match[str]) -> str:
    """Rebuild a start tag with its attributes in sorted order."""
    attributes = sorted(ATTR_RE.findall(match.group(2)))
    if not attributes:
        return "<" + match.group(1) + ">"
    return "<" + match.group(1) + " " + " ".join(attributes) + ">"


def normalize_line(line: str, host: tuple[str, str] | None) -> str | None:
    """Normalize one line. Return None when nothing is left after the noise tags are removed."""
    line = NOISE_TAG_RE.sub("", line)
    line = TWITTER_DEFAULT_RE.sub("", line)
    if host is not None:
        line = line.replace(host[0], host[1])
    line = re.sub(r"\?[0-9]{9,11}", "", line)
    line = re.sub(r"_assets/[0-9a-f]{32}", "_assets/HASH", line)
    line = re.sub(r'<meta name="generator"[^>]*>', "GEN", line)
    line = re.sub(r'_processed_/[0-9a-f]/[0-9a-f]/[^"]*', "PROCESSED", line)
    line = re.sub(r"\s*/>", ">", line)
    line = TAG_RE.sub(sort_attributes, line)
    line = line.strip()
    return line or None


def normalize_file(path: str, host: tuple[str, str] | None) -> list[str]:
    """Return all normalized, non-empty lines of a file."""
    lines: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            normalized = normalize_line(raw, host)
            if normalized is not None:
                lines.append(normalized)
    return lines


def read_status(directory: str) -> dict[str, str]:
    """Read status.tsv of a crawl dir as uid -> code, in file order."""
    return {uid: code for uid, (_slug, code) in read_status_rows(directory).items()}


def read_status_rows(directory: str) -> dict[str, tuple[str, str]]:
    """Read status.tsv of a crawl dir as uid -> (slug, code), in file order."""
    path = os.path.join(directory, "status.tsv")
    status: dict[str, tuple[str, str]] = {}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            fields = line.split("\t")
            if len(fields) < 3:
                raise UsageError(f"{path}: line {number} is malformed, expected uid<TAB>slug<TAB>code")
            status[fields[0]] = (fields[1], fields[2])
    return status


def load_expect(path: str, expected_sha256: str) -> Expectations:
    """Load an expect file after checking its SHA-256."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as error:
        raise UsageError(f"cannot read expect file {path}: {error}") from error
    actual = hashlib.sha256(raw).hexdigest()
    if actual.lower() != expected_sha256.strip().lower():
        raise UsageError(
            f"expect file hash mismatch, expected {expected_sha256.strip().lower()} but found {actual}"
        )
    line_rules: list[tuple[str, re.Pattern[str]]] = []
    status_rules: set[tuple[str, str, str]] = set()
    text = raw.decode("utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        if "\t" not in line:
            raise UsageError(f"expect file line {number} has no TAB between key and pattern")
        key, pattern = line.split("\t", 1)
        key = key.strip()
        status_match = STATUS_RULE_RE.match(pattern)
        if status_match:
            if key == "*":
                raise UsageError(f"expect file line {number}: STATUS rules need a uid, not *")
            status_rules.add((key, status_match.group(1), status_match.group(2)))
            continue
        if pattern.strip() in CATCH_ALL_PATTERNS:
            raise UsageError(f"expect file line {number}: catch-all pattern is not allowed")
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            raise UsageError(f"expect file line {number}: invalid regex ({error})") from error
        if sum(1 for probe in CATCH_ALL_PROBES if compiled.search(probe)) >= CATCH_ALL_THRESHOLD:
            raise UsageError(f"expect file line {number}: catch-all pattern is not allowed")
        line_rules.append((key, compiled))
    return Expectations(line_rules=line_rules, status_rules=status_rules, sha256=actual)


def changed_lines(old_lines: list[str], new_lines: list[str]) -> list[str]:
    """Return the added and removed lines of a zero-context unified diff."""
    diff = difflib.unified_diff(old_lines, new_lines, lineterm="", n=0)
    return [
        line
        for line in diff
        if line[:1] in ("+", "-") and not line.startswith("+++") and not line.startswith("---")
    ]


def compare(
    baseline: str,
    new: str,
    expect: Expectations | None,
    host: tuple[str, str] | None,
    page_uids: list[str] | None = None,
) -> Result:
    """Compare all uids listed in the new status file against the baseline.

    Every uid in page_uids must appear in the new status file.
    """
    result = Result()
    baseline_rows = read_status_rows(baseline)
    new_rows = read_status_rows(new)
    baseline_status = {uid: code for uid, (_slug, code) in baseline_rows.items()}
    new_status = {uid: code for uid, (_slug, code) in new_rows.items()}
    if not new_status:
        raise UsageError("new crawl lists no uid")
    result.compared = len(new_status)
    for uid in page_uids or []:
        if uid not in new_status:
            result.add_unmatched(uid, f"MISSING {uid} new-status")
    status_rules = expect.status_rules if expect else set()
    line_rules = expect.line_rules if expect else []
    for uid in sorted(new_status, key=lambda value: (len(value), value)):
        if uid not in baseline_status:
            result.add_unmatched(uid, f"MISSING {uid} baseline-status")
        elif baseline_rows[uid][0] != new_rows[uid][0]:
            result.add_unmatched(uid, f"SLUG {uid} {baseline_rows[uid][0]} {new_rows[uid][0]}")
        elif baseline_status[uid] != new_status[uid]:
            old_code, new_code = baseline_status[uid], new_status[uid]
            if (uid, old_code, new_code) in status_rules:
                result.add_matched(uid)
            else:
                result.add_unmatched(uid, f"STATUS {uid} {old_code} {new_code}")
        baseline_file = os.path.join(baseline, uid + ".html")
        new_file = os.path.join(new, uid + ".html")
        missing = False
        if not os.path.isfile(baseline_file):
            result.add_unmatched(uid, f"MISSING {uid} baseline")
            missing = True
        if not os.path.isfile(new_file):
            result.add_unmatched(uid, f"MISSING {uid} new")
            missing = True
        if missing:
            continue
        diff = changed_lines(normalize_file(baseline_file, host), normalize_file(new_file, host))
        for line in diff:
            content = line[1:]
            if any(key in (uid, "*") and pattern.search(content) for key, pattern in line_rules):
                result.add_matched(uid)
            else:
                result.add_unmatched(uid, line)
    return result


def load_pages(path: str, expected_sha256: str) -> tuple[list[str], str]:
    """Load the uids of a page list after checking its SHA-256. Return (uids, sha256)."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as error:
        raise UsageError(f"cannot read pages file {path}: {error}") from error
    actual = hashlib.sha256(raw).hexdigest()
    if actual.lower() != expected_sha256.strip().lower():
        raise UsageError(
            f"pages file hash mismatch, expected {expected_sha256.strip().lower()} but found {actual}"
        )
    uids: list[str] = []
    for line in raw.decode("utf-8", errors="replace").split("\n"):
        line = line.rstrip("\r")
        if not line.strip() or line.startswith("#"):
            continue
        uid = line.split("\t", 1)[0]
        if uid and uid not in uids:
            uids.append(uid)
    return uids, actual


def check_crawl_dir(directory: str, baseline: bool = False) -> None:
    """Check that a crawl dir exists and holds .complete and status.tsv, plus .baseline for a baseline."""
    if not os.path.isdir(directory):
        raise UsageError(f"not a directory: {directory}")
    names = (".complete", "status.tsv", ".baseline") if baseline else (".complete", "status.tsv")
    for name in names:
        if not os.path.isfile(os.path.join(directory, name)):
            raise UsageError(f"{directory} has no {name}")


def host_from_env() -> tuple[str, str] | None:
    """Read the OLD_HOST/NEW_HOST pair from the environment."""
    old_host = os.environ.get("OLD_HOST", "")
    new_host = os.environ.get("NEW_HOST", "")
    if old_host and new_host:
        return (old_host, new_host)
    if old_host or new_host:
        raise UsageError("set both OLD_HOST and NEW_HOST or neither")
    return None


def non_negative_int(value: str) -> int:
    """Argparse type for an integer >= 0."""
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not an integer: {value}") from error
    if number < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return number


def build_parser() -> argparse.ArgumentParser:
    """Create the command line parser."""
    parser = argparse.ArgumentParser(
        prog="residual.py",
        description="Compare two TYPO3 crawls after removing known rendering noise.",
    )
    parser.add_argument("--limit", type=non_negative_int, default=DEFAULT_LIMIT,
                        help="entries printed per uid (default 12)")
    parser.add_argument("--expect", help="expect file with approved differences")
    parser.add_argument("--expect-sha256", help="SHA-256 of the expect file")
    parser.add_argument("--pages", help="page list (TSV) that the new crawl must cover")
    parser.add_argument("--pages-sha256", help="SHA-256 of the page list")
    parser.add_argument("baseline", help="baseline crawl dir")
    parser.add_argument("new", help="new crawl dir")
    return parser


def run(args: argparse.Namespace) -> int:
    """Run the comparison and print the report."""
    if (args.expect is None) != (args.expect_sha256 is None):
        raise UsageError("--expect and --expect-sha256 must be given together")
    if (args.pages is None) != (args.pages_sha256 is None):
        raise UsageError("--pages and --pages-sha256 must be given together")
    check_crawl_dir(args.baseline, baseline=True)
    check_crawl_dir(args.new)
    if os.path.realpath(args.baseline) == os.path.realpath(args.new):
        raise UsageError("baseline and new crawl are the same folder")
    host = host_from_env()
    expect = load_expect(args.expect, args.expect_sha256) if args.expect else None
    page_uids: list[str] | None = None
    if args.pages is not None:
        page_uids, pages_sha = load_pages(args.pages, args.pages_sha256)
    result = compare(args.baseline, args.new, expect, host, page_uids)
    if expect is not None:
        print(f"expect sha256: {expect.sha256}")
    if page_uids is not None:
        print(f"pages sha256: {pages_sha}")
    print("## unmatched")
    for uid, items in result.unmatched.items():
        print(f"=== {uid} ({len(items)})")
        for item in items[: args.limit]:
            print(item[:MAX_LINE_LENGTH])
    print("## matched")
    for uid, count in result.matched.items():
        print(f"{uid} {count}")
    unmatched_total = sum(len(items) for items in result.unmatched.values())
    matched_total = sum(result.matched.values())
    verdict = "pass" if unmatched_total == 0 else "fail"
    print(f"RESULT {verdict} compared={result.compared} unmatched={unmatched_total} matched={matched_total}")
    return 0 if unmatched_total == 0 else 1


def main(argv: list[str] | None = None) -> int:
    """Entry point. Return the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except UsageError as error:
        print(f"residual: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
