#!/usr/bin/env python3
"""Collect diff and test output for the review phase and check that tests leave the work tree alone."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lockin_common import (  # noqa: E402
    DIFF_FLAGS,
    GitError,
    UsageError,
    initial_base,
    pathspecs,
    repo_root,
    run_git,
    split_z,
    validate_slug,
)
from snapshot import printable, take_snapshot  # noqa: E402

import argparse  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402

REVIEW_PREFIX = "review-"


def check_not_symlink(path: str) -> None:
    """Raise UsageError if an existing path is a symlink or resolves to another location."""
    if os.path.lexists(path) and (os.path.islink(path) or os.path.realpath(path) != path):
        raise UsageError(f"refusing symlinked path: {path}")


def resolve_out(repo: str, out: str) -> tuple[str, bool]:
    """Validate the output folder and return (absolute path, is_review_form)."""
    abs_out = os.path.abspath(out)
    parts = os.path.relpath(abs_out, repo).split(os.sep)
    review_form = False
    if len(parts) == 3 and parts[0] == ".lockin" and parts[2] == "review":
        validate_slug(parts[1])
    elif (
        len(parts) == 2
        and parts[0] == ".lockin"
        and parts[1].startswith(REVIEW_PREFIX)
        and len(parts[1]) > len(REVIEW_PREFIX)
    ):
        validate_slug(parts[1])
        review_form = True
    else:
        raise UsageError(
            f"--out must be .lockin/<slug>/review or .lockin/review-<name> inside the repo: {out}"
        )
    lockin = os.path.join(repo, ".lockin")
    check_not_symlink(lockin)
    if not review_form:
        slug_dir = os.path.join(lockin, parts[1])
        check_not_symlink(slug_dir)
        if not os.path.isdir(slug_dir):
            raise UsageError(f"folder does not exist: {slug_dir}")
    check_not_symlink(abs_out)
    return abs_out, review_form


def write_new_files(repo: str, out_dir: str, excludes: list[str]) -> list[str]:
    """List untracked files into new-files.txt and return them."""
    new_files = split_z(
        run_git(repo, ["ls-files", "--others", "--exclude-standard", "-z", *pathspecs(excludes)])
    )
    lines: list[str] = []
    for path in new_files:
        if "\n" in path or "\r" in path:
            print(
                f"collect_review.py: path with a line break written as JSON: {json.dumps(path)}",
                file=sys.stderr,
            )
            lines.append(json.dumps(path))
        else:
            lines.append(path)
    with open(os.path.join(out_dir, "new-files.txt"), "wb") as handle:
        for line in lines:
            handle.write(line.encode("utf-8", "surrogateescape") + b"\n")
    return new_files


def prepare(args: argparse.Namespace) -> int:
    """Create the output folder, write diff.patch, new-files.txt and snapshot-before.json."""
    for ref in (args.base, args.head):
        if ref and ref.startswith("-"):
            raise UsageError(f'refs must not start with "-": {ref}')
    repo = repo_root(args.repo)
    base = args.base or initial_base(repo)
    excludes = args.exclude or []
    abs_out, review_form = resolve_out(repo, args.out)
    if review_form:
        lockin = os.path.join(repo, ".lockin")
        if not os.path.lexists(lockin):
            os.mkdir(lockin)
        resolve_out(repo, args.out)
    if os.path.lexists(abs_out):
        shutil.rmtree(abs_out)
    os.mkdir(abs_out, 0o700)
    os.chmod(abs_out, 0o700)

    diff_path = os.path.join(abs_out, "diff.patch")
    if args.diff_file:
        if not os.path.isfile(args.diff_file) or os.path.getsize(args.diff_file) == 0:
            print(
                f"collect_review.py: diff file is missing or empty: {args.diff_file}",
                file=sys.stderr,
            )
            return 5
        with open(args.diff_file, "rb") as source:
            diff_bytes = source.read()
    else:
        diff_args = ["diff", *DIFF_FLAGS, base]
        if args.head:
            diff_args.append(args.head)
        diff_bytes = run_git(repo, [*diff_args, *pathspecs(excludes)])
    with open(diff_path, "wb") as handle:
        handle.write(diff_bytes)

    if not args.diff_file:
        name_args = ["diff", *DIFF_FLAGS, "--name-only", "--no-renames", "-z", base]
        if args.head:
            name_args.append(args.head)
        names = set(split_z(run_git(repo, [*name_args, *pathspecs(excludes)])))
        hits = sorted(names.intersection(excludes))
        if hits:
            print(
                "collect_review.py: excluded paths appear in the diff: " + ", ".join(hits),
                file=sys.stderr,
            )
            return 3

    if args.head or args.diff_file:
        new_files: list[str] = []
        with open(os.path.join(abs_out, "new-files.txt"), "wb"):
            pass
    else:
        new_files = write_new_files(repo, abs_out, excludes)

    snapshot = take_snapshot(repo, base, [], False)
    snapshot_path = os.path.join(abs_out, "snapshot-before.json")
    with open(snapshot_path, "w", encoding="utf-8") as handle:
        json.dump(
            {"base": base, "snapshot": snapshot, "new_files": new_files, "excludes": excludes},
            handle,
        )
    result = {
        "out": abs_out,
        "diff": diff_path,
        "new_files": len(new_files),
        "snapshot": snapshot_path,
    }
    print(json.dumps(printable(result), ensure_ascii=False, indent=2))
    return 0


def kill_group(pid: int) -> None:
    """Send SIGKILL to the process group of a started command."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        # The process group already ended, nothing left to kill.
        pass


def tracked_lines(status: list[str]) -> list[str]:
    """Return the status lines of tracked files."""
    return [line for line in status if not line.startswith("??")]


def compare_snapshots(before: dict, after_snap: dict, protected: list[str]) -> tuple[list[str], list[str]]:
    """Return (fatal differences, warnings) between two snapshots."""
    fatal: list[str] = []
    warnings: list[str] = []
    if tracked_lines(before["snapshot"]["status"]) != tracked_lines(after_snap["status"]):
        fatal.append("tracked file status changed")
    if before["snapshot"]["diff_hash"] != after_snap["diff_hash"]:
        fatal.append("tracked diff changed")
    old = before["snapshot"]["untracked_files"]
    new = after_snap["untracked_files"]
    for path in protected:
        if path not in old:
            continue
        if path not in new:
            fatal.append(f"protected untracked file removed: {path}")
        elif new[path] != old[path]:
            fatal.append(f"protected untracked file changed: {path}")
    for path in sorted(new):
        if path not in old:
            warnings.append(f"untracked file added: {path}")
        elif new[path] != old[path] and path not in protected:
            warnings.append(f"untracked file changed: {path}")
    for path in sorted(old):
        if path not in new and path not in protected:
            warnings.append(f"untracked file removed: {path}")
    return fatal, warnings


def run_command(args: argparse.Namespace) -> int:
    """Run a test command, record its output and check that it left the work tree unchanged."""
    repo = repo_root(args.repo)
    abs_out, _ = resolve_out(repo, args.out)
    before_path = os.path.join(abs_out, "snapshot-before.json")
    if not os.path.isfile(before_path):
        print("collect_review.py: run prepare first", file=sys.stderr)
        return 2
    with open(before_path, "r", encoding="utf-8") as handle:
        before = json.load(handle)

    command = args.command
    out_file = os.path.join(abs_out, f"test-{args.index}.txt")
    with open(out_file, "wb") as handle:
        handle.write(command.encode("utf-8", "surrogateescape") + b"\n")
        handle.flush()
        proc = subprocess.Popen(
            command,
            shell=True,
            executable=shutil.which("bash") or "/bin/sh",
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        def handle_signal(signum: int, frame: object) -> None:
            """Kill the command's process group, then stop like the signal asks."""
            kill_group(proc.pid)
            if signum == signal.SIGINT:
                raise KeyboardInterrupt
            raise SystemExit(143)

        previous = {
            signum: signal.signal(signum, handle_signal) for signum in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            try:
                proc.wait(timeout=args.timeout)
                status = str(proc.returncode)
            except subprocess.TimeoutExpired:
                kill_group(proc.pid)
                proc.wait()
                status = "timeout"
            finally:
                # Background children must not write after the exit line.
                kill_group(proc.pid)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)

    with open(out_file, "rb+") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() > 0:
            handle.seek(-1, os.SEEK_END)
            last_byte = handle.read(1)
            handle.seek(0, os.SEEK_END)
            if last_byte != b"\n":
                handle.write(b"\n")
        handle.write(f"exit: {status}\n".encode("utf-8"))

    after = take_snapshot(repo, before["base"], [], False)
    protected = list(before["new_files"]) + list(before["excludes"])
    fatal, warnings = compare_snapshots(before, after, protected)
    result = {
        "file": out_file,
        "command": command,
        "exit": status,
        "warnings": warnings,
        "changed": fatal,
    }
    print(json.dumps(printable(result), ensure_ascii=False, indent=2))
    return 4 if fatal else 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with the prepare and run subcommands."""
    parser = argparse.ArgumentParser(description="Collect review input.")
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", help="write diff.patch, new-files.txt and snapshot-before.json")
    prep.add_argument("--out", required=True, help="output folder inside .lockin")
    prep.add_argument("--repo", help="repository directory (default: current directory)")
    prep.add_argument("--base", help="base ref (default: HEAD or empty tree)")
    group = prep.add_mutually_exclusive_group()
    group.add_argument("--head", help="head ref for a commit range diff")
    group.add_argument("--diff-file", help="use this patch file instead of running git diff")
    prep.add_argument(
        "--exclude", action="append", default=[], help="path relative to the repo root to skip"
    )
    prep.set_defaults(func=prepare)

    run = sub.add_parser("run", help="run a test command and record its output")
    run.add_argument("--out", required=True, help="output folder inside .lockin")
    run.add_argument("--index", type=int, required=True, help="test run number, at least 1")
    run.add_argument("--command", dest="test_command", required=True, help="shell command to run")
    run.add_argument("--repo", help="repository directory (default: current directory)")
    run.add_argument("--timeout", type=float, default=540, help="seconds before the command is killed")
    run.set_defaults(func=run_command)
    return parser


def main() -> int:
    """Parse arguments, run the subcommand and return the exit code."""
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run":
        if args.index < 1:
            parser.error("--index must be at least 1")
        args.command = args.test_command
    try:
        return args.func(args)
    except (GitError, UsageError) as error:
        print(f"collect_review.py: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"collect_review.py: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"collect_review.py: unexpected error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
