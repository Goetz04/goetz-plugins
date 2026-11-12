#!/usr/bin/env python3
"""Shared helpers for the lockin scripts. Standard library only."""

from __future__ import annotations

import os
import subprocess

EMPTY_TREE_CMD = ["hash-object", "-t", "tree", "/dev/null"]
DIFF_FLAGS = ["--no-color", "--no-ext-diff", "--no-textconv"]


class GitError(Exception):
    """A git command failed. The message holds the command and git's stderr."""


class UsageError(Exception):
    """Invalid arguments or an unsafe target. The message names the problem."""


def run_git(repo: str, args: list[str], input_bytes: bytes | None = None) -> bytes:
    """Run `git -C <repo> <args>` and return stdout as bytes. Raise GitError on a non-zero exit."""
    result = subprocess.run(
        ["git", "-C", repo, *args],
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise GitError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return result.stdout


def repo_root(start: str | None = None) -> str:
    """Return the realpath of `git rev-parse --show-toplevel` run in `start` (default: cwd).

    Raise GitError outside a repository.
    """
    out = run_git(start if start is not None else os.getcwd(), ["rev-parse", "--show-toplevel"])
    return os.path.realpath(out.decode("utf-8", errors="surrogateescape").strip())


def empty_tree(repo: str) -> str:
    """Return the empty tree hash via `git hash-object -t tree /dev/null`."""
    return run_git(repo, EMPTY_TREE_CMD).decode("ascii").strip()


def initial_base(repo: str) -> str:
    """Return the HEAD commit hash or, in an unborn repo, the empty tree hash."""
    try:
        out = run_git(repo, ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"])
    except GitError:
        return empty_tree(repo)
    return out.decode("ascii").strip()


def pathspecs(excludes: list[str]) -> list[str]:
    """Return the pathspec list that skips the lockin state folder and all given excludes."""
    spec = ["--", ".", ":(exclude).lockin"]
    spec.extend(f":(exclude,literal){path}" for path in excludes)
    return spec


def validate_slug(slug: str) -> None:
    """Raise UsageError if slug is empty, ".", contains "/", "\\", ".." or a NUL character."""
    if slug in ("", "."):
        raise UsageError(f"invalid slug {slug!r}")
    for bad in ("/", "\\", "..", "\x00"):
        if bad in slug:
            raise UsageError(f"invalid slug {slug!r}: contains {bad!r}")


def lockin_dir(repo: str) -> str:
    """Return the path of the lockin state folder inside the repo."""
    return os.path.join(repo, ".lockin")


def hash_bytes(repo: str, data: bytes) -> str:
    """Return the output of `git hash-object --stdin` for data, stripped."""
    return run_git(repo, ["hash-object", "--stdin"], input_bytes=data).decode("ascii").strip()


def split_z(data: bytes) -> list[str]:
    """Split NUL-separated git output into paths, decoded as UTF-8 with surrogateescape."""
    return [
        part.decode("utf-8", errors="surrogateescape") for part in data.split(b"\x00") if part
    ]
