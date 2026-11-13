#!/usr/bin/env python3
"""Compute one stable SHA-256 over the contents of one or more folders.

Usage:
    tree_hash.py <dir> [<dir>...]

Each regular file contributes the line `<label>/<relative path>\\0<sha256 of content>\\n`.
The label is the basename of the folder. Lines are sorted by bytes, so the result does
not depend on locale or creation order. Symlinks (also as root argument), entries that are
neither regular files nor folders (pipes, sockets, devices) and duplicate labels are errors.
The result changes on any edit, rename, addition or removal of a file.

Exit codes: 0 success (hash on stdout), 2 usage or input error.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys

CHUNK_SIZE = 1024 * 1024


class UsageError(Exception):
    """Invalid usage or input. `main` turns it into exit code 2."""


def file_digest(path: str) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def label_of(directory: str) -> str:
    """Return the basename of a directory without trailing separators."""
    return os.path.basename(os.path.abspath(directory).rstrip(os.sep))


def raise_walk_error(error: OSError) -> None:
    """Stop on unreadable folders instead of skipping them, so the hash covers every file."""
    raise UsageError(f"cannot read folder: {error}")


def collect_entries(directory: str, label: str) -> list[tuple[bytes, str]]:
    """Return (entry path bytes, file path) for every regular file below a directory."""
    entries: list[tuple[bytes, str]] = []
    for current, dirnames, filenames in os.walk(directory, onerror=raise_walk_error, followlinks=False):
        for name in dirnames + filenames:
            full = os.path.join(current, name)
            if os.path.islink(full):
                raise UsageError(f"symlink not allowed: {full}")
            mode = os.lstat(full).st_mode
            if not stat.S_ISREG(mode) and not stat.S_ISDIR(mode):
                raise UsageError(f"not a regular file or directory: {full}")
        for name in filenames:
            full = os.path.join(current, name)
            relative = os.path.relpath(full, directory).replace(os.sep, "/")
            entries.append((os.fsencode(f"{label}/{relative}"), full))
    return entries


def tree_hash(directories: list[str]) -> str:
    """Return the combined hash of all given directories."""
    labels: set[str] = set()
    entries: list[tuple[bytes, str]] = []
    for directory in directories:
        if os.path.islink(directory):
            raise UsageError(f"symlink not allowed: {directory}")
        if not os.path.isdir(directory):
            raise UsageError(f"not a directory: {directory}")
        label = label_of(directory)
        if label in labels:
            raise UsageError(f"duplicate label: {label}")
        labels.add(label)
        entries.extend(collect_entries(directory, label))
    entries.sort(key=lambda entry: entry[0])
    lines = [
        entry_path + b"\0" + file_digest(full).encode("ascii") + b"\n"
        for entry_path, full in entries
    ]
    return hashlib.sha256(b"".join(lines)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Entry point. Return the process exit code."""
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if not arguments:
            raise UsageError("usage: tree_hash.py <dir> [<dir>...]")
        print(tree_hash(arguments))
    except (UsageError, OSError) as error:
        print(f"tree_hash: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
