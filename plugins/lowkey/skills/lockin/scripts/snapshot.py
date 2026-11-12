#!/usr/bin/env python3
"""Take a fingerprint of the working tree state: status, tracked diff and untracked file contents."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lockin_common import (  # noqa: E402
    DIFF_FLAGS,
    GitError,
    UsageError,
    hash_bytes,
    initial_base,
    pathspecs,
    repo_root,
    run_git,
    split_z,
)

import argparse  # noqa: E402
import json  # noqa: E402

CHUNK_SIZE = 200


def hash_untracked(repo: str, paths: list[str]) -> dict[str, str]:
    """Return a map of untracked path to blob hash. Hash in chunks to keep argv short."""
    files: dict[str, str] = {}
    for start in range(0, len(paths), CHUNK_SIZE):
        chunk = paths[start : start + CHUNK_SIZE]
        out = run_git(repo, ["hash-object", "--", *chunk]).decode("ascii")
        hashes = out.split()
        if len(hashes) != len(chunk):
            raise GitError("git hash-object returned an unexpected number of hashes")
        files.update(zip(chunk, hashes))
    return files


def take_snapshot(repo: str, base: str, excludes: list[str], with_paths: bool) -> dict:
    """Return the snapshot hashes and, with with_paths, the changed and untracked paths."""
    spec = pathspecs(excludes)
    status_raw = run_git(repo, ["-c", "core.quotePath=false", "status", "--porcelain", "-uall", *spec])
    status = [
        line for line in status_raw.decode("utf-8", errors="surrogateescape").split("\n") if line
    ]
    diff_hash = hash_bytes(repo, run_git(repo, ["diff", *DIFF_FLAGS, base, *spec]))
    untracked = split_z(
        run_git(repo, ["ls-files", "--others", "--exclude-standard", "-z", *spec])
    )
    untracked_files = hash_untracked(repo, untracked)
    untracked_hash = hash_bytes(
        repo, b"".join(untracked_files[path].encode() + b"\n" for path in untracked)
    )
    fingerprint = hash_bytes(
        repo,
        ("status:\n" + "\n".join(status) + "\ndiff:" + diff_hash + "\nuntracked:" + untracked_hash + "\n").encode(
            "utf-8", "surrogateescape"
        ),
    )
    result: dict = {
        "base": base,
        "status": status,
        "diff_hash": diff_hash,
        "untracked_hash": untracked_hash,
        "untracked_files": untracked_files,
        "fingerprint": fingerprint,
    }
    if with_paths:
        result["changed"] = split_z(
            run_git(repo, ["diff", "--name-only", "--no-renames", "-z", base, *spec])
        )
        result["untracked"] = untracked
    return result


def printable(value: object) -> object:
    """Replace invalid UTF-8 bytes in paths with U+FFFD so json.dumps never fails."""
    if isinstance(value, str):
        return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    if isinstance(value, list):
        return [printable(item) for item in value]
    if isinstance(value, dict):
        return {printable(key): printable(item) for key, item in value.items()}
    return value


def main() -> int:
    """Parse arguments, print the snapshot as JSON and return the exit code."""
    parser = argparse.ArgumentParser(description="Fingerprint the working tree state.")
    parser.add_argument("--repo", help="repository directory (default: current directory)")
    parser.add_argument("--base", help="base ref for the tracked diff (default: HEAD or empty tree)")
    parser.add_argument(
        "--exclude", action="append", default=[], help="path relative to the repo root to skip"
    )
    parser.add_argument("--paths", action="store_true", help="also list changed and untracked paths")
    args = parser.parse_args()
    if args.base and args.base.startswith("-"):
        print(f'snapshot.py: refs must not start with "-": {args.base}', file=sys.stderr)
        return 2
    try:
        repo = repo_root(args.repo) if args.repo else repo_root()
        base = args.base if args.base else initial_base(repo)
        snapshot = take_snapshot(repo, base, args.exclude, args.paths)
    except (GitError, UsageError) as error:
        print(f"snapshot.py: {error}", file=sys.stderr)
        return 2
    print(json.dumps(printable(snapshot), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
