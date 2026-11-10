#!/usr/bin/env python3
"""PreToolUse guard for the lowkey lockin subagents.

Reads the hook input JSON from stdin. Calls from other agents and from the
main session pass through unchanged (exit 0). Calls from a lockin subagent
that break a rule exit with code 2, which blocks the tool call. Any internal
error during a lockin call also blocks (fail-closed).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import PurePath

# Plugin subagents arrive namespaced, verified with Claude Code 2.1.322.
AGENT_RE = re.compile(r"^lowkey:lockin-(?:implementer|plan-challenger|reviewer-correctness|reviewer-risk)$")
RAW_AGENT_RE = re.compile(r'"agent_type"\s*:\s*"lowkey:lockin-')

IMPLEMENTER = "lowkey:lockin-implementer"

ENV_TEMPLATE_SUFFIXES = (".example", ".dist", ".sample")
SECRET_EXTENSIONS = (".pem", ".key", ".p12", ".pfx")
SECRET_PREFIXES = ("id_rsa", "id_ed25519")
# "credentials" or "credentials.<ext>", but not docs like credentials-howto.md.
CREDENTIALS_RE = re.compile(r"^credentials(?:\.[A-Za-z0-9]+)?$")
SECRET_NAMES = (".netrc", ".pgpass", "auth.json")
# Probe names to decide whether a glob pattern can match a secret file.
SECRET_PROBES = (
    ".env", ".env.local", "x.pem", "x.key", "x.p12", "x.pfx",
    "id_rsa", "id_ed25519", "credentials.json", ".netrc", ".pgpass", "auth.json",
)

GIT_READ_ONLY = {"diff", "status", "log", "show", "ls-files", "rev-parse", "blame", "grep"}
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
COMMAND_WRAPPERS = {"sudo", "env", "time", "nohup", "nice", "command", "exec", "xargs"}

SEGMENT_SPLIT_RE = re.compile(r"\|\||&&|[;|&\n()`]|\$\(")
TOKEN_SPLIT_RE = re.compile(r"[\s;&|<>()=`\"',]+")


class Blocked(Exception):
    """A rule violation. The message names the rule."""


def is_secret_name(name: str) -> bool:
    """Return True if a file basename looks like a secret file."""
    if name == ".env":
        return True
    if name.startswith(".env."):
        return not name.endswith(ENV_TEMPLATE_SUFFIXES)
    if name in SECRET_NAMES:
        return True
    if name.endswith(SECRET_EXTENSIONS):
        return True
    if CREDENTIALS_RE.match(name) and not name.endswith(".md"):
        return True
    return name.startswith(SECRET_PREFIXES)


def is_secret_path(path: str) -> bool:
    return is_secret_name(PurePath(path).name)


def glob_may_match_secret(pattern: str) -> bool:
    """Return True if a glob pattern can match a secret file.

    A pattern made only of wildcards (for example `*` or `**/*`) is not
    treated as a secret glob, otherwise every broad search would be blocked.
    """
    name = PurePath(pattern).name
    if not name or set(name) <= {"*", "?"}:
        return False
    return any(fnmatch.fnmatch(probe, name) for probe in SECRET_PROBES)


def is_lockin_path(path: str) -> bool:
    return ".lockin" in PurePath(path).parts


def tokenize(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def command_position(tokens: list[str]) -> list[str]:
    """Strip variable assignments and wrapper commands from the front."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token):
            index += 1
        elif PurePath(token).name in COMMAND_WRAPPERS:
            index += 1
        elif index > 0 and token.startswith("-") and PurePath(tokens[index - 1]).name in COMMAND_WRAPPERS:
            index += 1
        else:
            break
    return tokens[index:]


def check_git(args: list[str]) -> None:
    index = 0
    while index < len(args) and args[index].startswith("-"):
        option = args[index]
        index += 2 if option in GIT_OPTIONS_WITH_VALUE else 1
    if index >= len(args):
        return
    subcommand = args[index]
    if subcommand not in GIT_READ_ONLY:
        raise Blocked(
            f"git {subcommand} is not allowed. The implementer may only run read-only git "
            f"commands: {', '.join(sorted(GIT_READ_ONLY))}."
        )


def check_install(program: str, args: list[str]) -> None:
    first = args[0] if args else ""
    blocked = False
    if program in {"npm", "pnpm"}:
        blocked = first in {"install", "i", "add", "ci"}
    elif program == "yarn":
        blocked = first in {"", "install", "add"}
    elif program == "composer":
        blocked = first in {"install", "i", "require", "update"}
    elif program in {"pip", "pip3"}:
        blocked = first == "install"
    elif program in {"python", "python3"}:
        blocked = args[:3] == ["-m", "pip", "install"]
    elif program == "uv":
        blocked = first in {"add", "sync"} or args[:2] == ["pip", "install"]
    elif program in {"apt", "apt-get", "brew"}:
        blocked = first in {"install", "reinstall", "upgrade", "remove", "uninstall", "purge"}
    if blocked:
        raise Blocked(f"package installs are not allowed: {program} {first}".rstrip() + ".")


def check_bash(command: str, implementer: bool) -> None:
    for piece in TOKEN_SPLIT_RE.split(command):
        if piece and is_secret_path(piece):
            raise Blocked(f"the command touches a secret file: {piece}.")
    if not implementer:
        return
    if ".lockin" in command:
        raise Blocked("the command touches .lockin/, which belongs to the workflow.")
    for segment in SEGMENT_SPLIT_RE.split(command):
        tokens = command_position(tokenize(segment))
        if not tokens:
            continue
        program = PurePath(tokens[0]).name
        if program == "git":
            check_git(tokens[1:])
        check_install(program, tokens[1:])


def check(data: dict) -> None:
    agent = str(data.get("agent_type", ""))
    implementer = agent == IMPLEMENTER
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}

    if tool in {"Read", "Edit", "Write"}:
        path = str(tool_input.get("file_path", ""))
        if is_secret_path(path):
            raise Blocked(f"{tool} on a secret file is not allowed: {path}.")
        if tool in {"Edit", "Write"} and is_lockin_path(path):
            raise Blocked(f"{tool} under .lockin/ is not allowed: {path}.")
    elif tool == "Grep":
        path = str(tool_input.get("path", ""))
        pattern = str(tool_input.get("glob", ""))
        if path and is_secret_path(path):
            raise Blocked(f"Grep on a secret file is not allowed: {path}.")
        if pattern and glob_may_match_secret(pattern):
            raise Blocked(f"Grep with a glob that matches secret files is not allowed: {pattern}.")
    elif tool == "Bash":
        check_bash(str(tool_input.get("command", "")), implementer)


def block(reason: str) -> int:
    print(f"lowkey guard: {reason} Do not work around this block. Report it as BLOCKED.", file=sys.stderr)
    return 2


def main() -> int:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except ValueError:
        if RAW_AGENT_RE.search(raw):
            return block("unreadable hook input for a lockin agent.")
        return 0
    if not isinstance(data, dict) or not AGENT_RE.match(str(data.get("agent_type", ""))):
        return 0
    try:
        check(data)
    except Blocked as violation:
        return block(str(violation))
    except Exception as error:  # fail-closed: any bug blocks lockin agents only
        return block(f"internal error ({type(error).__name__}: {error}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
