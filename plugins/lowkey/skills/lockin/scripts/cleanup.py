#!/usr/bin/env python3
"""Delete the review folder or the whole run folder of a lockin run. Refuses symlinks."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lockin_common import GitError, UsageError, lockin_dir, repo_root, validate_slug  # noqa: E402

import argparse  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402


def print_json(data: dict) -> None:
    """Print data as JSON on stdout."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def is_unsafe(repo: str, expected: str) -> bool:
    """Return True when the target or its parent state folder resolves through a symlink."""
    state = lockin_dir(repo)
    return (
        os.path.islink(expected)
        or os.path.realpath(expected) != expected
        or os.path.realpath(state) != state
    )


def main() -> int:
    """Delete the requested folder and return the exit code."""
    parser = argparse.ArgumentParser(description="Delete a lockin review or run folder.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--target", required=True, choices=["review", "run"])
    parser.add_argument("--repo", help="repository directory (default: current directory)")
    args = parser.parse_args()
    try:
        validate_slug(args.slug)
        repo = repo_root(args.repo) if args.repo else repo_root()
    except (GitError, UsageError) as error:
        print(f"cleanup.py: {error}", file=sys.stderr)
        return 2

    expected = os.path.join(repo, ".lockin", args.slug)
    if args.target == "review":
        expected = os.path.join(expected, "review")
    if not os.path.lexists(expected):
        print_json({"deleted": None, "message": "nothing to delete"})
        return 0
    if is_unsafe(repo, expected):
        print(f"cleanup.py: refusing to delete {expected}: path involves a symlink", file=sys.stderr)
        return 2
    if not os.path.isdir(expected):
        print(f"cleanup.py: refusing to delete {expected}: not a directory", file=sys.stderr)
        return 2
    try:
        shutil.rmtree(expected)
    except OSError as error:
        print(f"cleanup.py: cannot delete {expected}: {error}", file=sys.stderr)
        return 2

    lockin_removed = False
    if args.target == "run":
        state = lockin_dir(repo)
        if os.path.isdir(state) and not os.listdir(state):
            try:
                os.rmdir(state)
            except OSError as error:
                print(f"cleanup.py: cannot delete {state}: {error}", file=sys.stderr)
                return 2
            lockin_removed = True
    print_json({"deleted": expected, "lockin_removed": lockin_removed})
    return 0


if __name__ == "__main__":
    sys.exit(main())
