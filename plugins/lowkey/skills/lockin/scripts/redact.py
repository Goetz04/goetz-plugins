#!/usr/bin/env python3
"""Redact secrets from test output files in place and report remaining hits."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import re  # noqa: E402

REDACTED = "[REDACTED]"
SCHEMES = "bearer|basic|token|digest"

# The key suffix is bounded and the quoted value has no ambiguous alternative,
# so long lines cannot trigger quadratic backtracking.
KEY_VALUE = re.compile(
    r"""(?P<pre>(?:password|passwd|secret|token|api[_-]?key)[\w.-]{0,64}\s*\\?["']?\s*[:=]\s*)"""
    r"""(?:(?P<esc>\\?)(?P<q>["'])(?!\[REDACTED\](?P=esc)(?P=q))(?P<qv>(?:\\.|(?!(?P=q))[^\\])*?)(?P=esc)(?P=q)"""
    r"""|(?!\[REDACTED\]|\\["'])(?P<uv>[^\s"',;]+))""",
    re.IGNORECASE,
)
AUTHORIZATION = re.compile(
    r"""(?P<pre>authorization\s*["']?\s*[:=]\s*["']?)"""
    r"""(?:(?P<scheme>""" + SCHEMES + r""")\s+(?!\[REDACTED\])[^\s"',;]+"""
    r"""|(?!(?:""" + SCHEMES + r""")\s+\[REDACTED\])(?!\[REDACTED\])[^\s"',;]+)""",
    re.IGNORECASE,
)
BEARER = re.compile(r"\b(bearer\s+)(?!\[REDACTED\])([A-Za-z0-9._~+/=-]+)", re.IGNORECASE)
PRIVATE_KEY_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.IGNORECASE)
PRIVATE_KEY_LABEL = re.compile(r"-----BEGIN ([A-Z0-9 ]*)PRIVATE KEY-----", re.IGNORECASE)
ENV_LINE = re.compile(
    r"^(\s*(?:export\s+|declare -x\s+)?[A-Z][A-Z0-9_]*=)(?!\[REDACTED\]\r?\n?$)(\S.*?)(\r?\n)?$"
)
URL_CREDENTIALS = re.compile(
    r"(?<![a-zA-Z0-9+.-])(?P<pre>[a-zA-Z][a-zA-Z0-9+.-]*://[^/\s:@]+:)(?!\[REDACTED\]@)[^@\s/]+(?P<post>@)"
)
TOKEN_PREFIX = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)
COOKIE = re.compile(
    r"(?P<pre>\b(?:set-)?cookie\s*:(?!\s*\[REDACTED\]\s*$)\s*)(?P<v>[^\r\n]+)", re.IGNORECASE
)
EXIT_LINE = re.compile(r"^exit: \S+\r?\n?$")


def replace_key_value(match: re.Match[str]) -> str:
    """Keep key and quotes, replace the value."""
    if match.group("q"):
        quote = match.group("esc") + match.group("q")
        return f"{match.group('pre')}{quote}{REDACTED}{quote}"
    return f"{match.group('pre')}{REDACTED}"


def replace_authorization(match: re.Match[str]) -> str:
    """Keep the header name and the scheme, replace the credential."""
    scheme = match.group("scheme")
    if scheme:
        return f"{match.group('pre')}{scheme} {REDACTED}"
    return f"{match.group('pre')}{REDACTED}"


def replace_env(match: re.Match[str]) -> str:
    """Keep the variable name and the line ending, replace the value."""
    return f"{match.group(1)}{REDACTED}{match.group(3) or ''}"


def split_lines(text: str) -> list[str]:
    """Split on newline only and keep the newline, so line numbers match editor lines."""
    lines = re.split(r"(?<=\n)", text)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def redact_key_blocks(text: str) -> str:
    """Replace terminated private key blocks. Stops at the first BEGIN without END.

    A plain regex with a lazy DOTALL body rescans to the end of the text for
    every unterminated BEGIN, which is quadratic on hostile output.
    """
    parts: list[str] = []
    position = 0
    while True:
        begin = PRIVATE_KEY_BEGIN.search(text, position)
        if not begin:
            break
        label = PRIVATE_KEY_LABEL.match(begin.group(0)).group(1)
        end_re = re.compile(r"-----END " + re.escape(label) + r"PRIVATE KEY-----", re.IGNORECASE)
        end = end_re.search(text, begin.end())
        if not end:
            break
        parts.append(text[position : begin.start()])
        parts.append("[REDACTED PRIVATE KEY]")
        position = end.end()
    parts.append(text[position:])
    return "".join(parts)


def redact_unterminated_key(text: str) -> str:
    """Replace an unterminated private key block up to the end, keep a final exit line."""
    match = PRIVATE_KEY_BEGIN.search(text)
    if not match:
        return text
    lines = split_lines(text[match.start() :])
    tail = lines[-1] if lines and EXIT_LINE.match(lines[-1]) else ""
    return text[: match.start()] + "[REDACTED PRIVATE KEY]\n" + tail


def redact_text(text: str) -> str:
    """Apply all rules and return the redacted text."""
    text = redact_key_blocks(text)
    text = redact_unterminated_key(text)
    result: list[str] = []
    for number, line in enumerate(split_lines(text)):
        line = KEY_VALUE.sub(replace_key_value, line)
        line = AUTHORIZATION.sub(replace_authorization, line)
        line = BEARER.sub(lambda m: f"{m.group(1)}{REDACTED}", line)
        line = URL_CREDENTIALS.sub(lambda m: f"{m.group('pre')}{REDACTED}{m.group('post')}", line)
        line = TOKEN_PREFIX.sub(REDACTED, line)
        line = COOKIE.sub(lambda m: f"{m.group('pre')}{REDACTED}", line)
        if number > 0:
            line = ENV_LINE.sub(replace_env, line)
        result.append(line)
    return "".join(result)


def find_hits(text: str) -> list[tuple[int, str]]:
    """Return (line number, rule name) for every unredacted secret left in the text."""
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(split_lines(text), start=1):
        if KEY_VALUE.search(line):
            hits.append((number, "key-value"))
        if AUTHORIZATION.search(line):
            hits.append((number, "authorization"))
        if BEARER.search(line):
            hits.append((number, "bearer"))
        if URL_CREDENTIALS.search(line):
            hits.append((number, "url-credentials"))
        if TOKEN_PREFIX.search(line):
            hits.append((number, "token-prefix"))
        if COOKIE.search(line):
            hits.append((number, "cookie"))
        if PRIVATE_KEY_BEGIN.search(line):
            hits.append((number, "private-key"))
        if number > 1 and ENV_LINE.search(line):
            hits.append((number, "env"))
    return hits


def process_file(path: str) -> int:
    """Redact one file in place and print remaining hits. Return the number of hits."""
    with open(path, "rb") as handle:
        original = handle.read().decode("utf-8", errors="surrogateescape")
    redacted = redact_text(original)
    if redacted != original:
        with open(path, "wb") as handle:
            handle.write(redacted.encode("utf-8", errors="surrogateescape"))
    hits = find_hits(redacted)
    for number, rule in hits:
        print(f"{path}:{number}: {rule}")
    return len(hits)


def main() -> int:
    """Parse arguments, redact all files and return the exit code."""
    parser = argparse.ArgumentParser(description="Redact secrets from files in place.")
    parser.add_argument("files", nargs="+", metavar="FILE")
    args = parser.parse_args()
    hit_count = 0
    io_error = False
    for path in args.files:
        try:
            hit_count += process_file(path)
        except OSError as error:
            print(f"redact.py: {error}", file=sys.stderr)
            io_error = True
    if io_error:
        return 2
    return 1 if hit_count else 0


if __name__ == "__main__":
    sys.exit(main())
