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
from dataclasses import dataclass
from pathlib import PurePath
from typing import NamedTuple

# Plugin subagents arrive namespaced, verified with Claude Code 2.1.322.
AGENT_RE = re.compile(r"^lowkey:lockin-(?:implementer|plan-challenger|reviewer|reviewer-correctness|reviewer-risk)$")
RAW_AGENT_RE = re.compile(r'"agent_type"\s*:\s*"lowkey:lockin-')

IMPLEMENTER = "lowkey:lockin-implementer"

ENV_TEMPLATE_SUFFIXES = (".example", ".dist", ".sample")
SECRET_EXTENSIONS = (".pem", ".key", ".p12", ".pfx")
SECRET_PREFIXES = ("id_rsa", "id_ed25519")
# "credentials" or "credentials.<ext>", but not docs like credentials-howto.md.
CREDENTIALS_RE = re.compile(r"^credentials(?:\.[A-Za-z0-9]+)?$")
SECRET_NAMES = (".netrc", ".pgpass", "auth.json", ".npmrc", ".git-credentials", ".envrc")
# Probe names to decide whether a glob pattern can match a secret file.
SECRET_PROBES = (
    ".env", ".env.local", "x.pem", "x.key", "x.p12", "x.pfx",
    "id_rsa", "id_ed25519", "credentials.json", ".netrc", ".pgpass", "auth.json",
    ".npmrc", ".git-credentials", ".envrc",
)
# Optional file in the repository root with project-specific secret globs.
PROJECT_CONFIG = ".lockin-guard.json"

GIT_READ_ONLY = {"diff", "status", "log", "show", "ls-files", "rev-parse", "blame", "grep"}
GIT_GLOBAL_FLAGS = frozenset({"--no-pager", "-P", "--literal-pathspecs", "--no-optional-locks"})
SAFE_GIT_CONFIG_KEYS = frozenset({"core.quotepath", "color.ui"})
# Options of read-only subcommands that write files, run programs or read outside the repo.
# git accepts unique abbreviations of long options, so prefixes count too.
BLOCKED_GIT_OPTIONS = (
    "--output", "--open-files-in-pager", "--ext-diff", "--textconv", "--no-index",
    "--contents", "--untracked", "--no-exclude-standard", "--recurse-submodules",
)
GIT_PREFIX_EXCEPTIONS = frozenset({"--text"})
COMMAND_WRAPPERS = {"sudo", "env", "time", "nohup", "nice", "command", "exec", "xargs"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}

# Options of container wrappers, needed to find the wrapped command.
DDEV_EXEC_VALUE_OPTIONS = frozenset({"-s", "--service", "-d", "--dir"})
DDEV_EXEC_FLAGS = frozenset({"--raw", "-j", "--json-output"})
DOCKER_VALUE_OPTIONS = frozenset({"-H", "--host", "-c", "--context", "--config", "-l", "--log-level", "--tlscacert", "--tlscert", "--tlskey"})
DOCKER_FLAGS = frozenset({"-D", "--debug", "--tls", "--tlsverify"})
DOCKER_EXEC_VALUE_OPTIONS = frozenset({"-u", "--user", "-w", "--workdir", "-e", "--env", "--env-file", "--detach-keys"})
DOCKER_EXEC_FLAGS = frozenset({"-d", "--detach", "-i", "--interactive", "-t", "--tty", "--privileged"})
COMPOSE_VALUE_OPTIONS = frozenset({"-f", "--file", "-p", "--project-name", "--project-directory", "--profile", "--env-file", "--ansi", "--progress", "--parallel"})
COMPOSE_FLAGS = frozenset({"--dry-run", "--compatibility", "--all-resources"})
COMPOSE_EXEC_VALUE_OPTIONS = frozenset({"-u", "--user", "-w", "--workdir", "-e", "--env", "--index"})
COMPOSE_EXEC_FLAGS = frozenset({"-T", "--no-TTY", "-d", "--detach", "--privileged", "--dry-run"})
MAX_NESTING = 3
MAX_COMMAND_LENGTH = 16384
GLOB_CHARS = set("*?[")
# The workflow writes the Verification commands of the current package here.
ACTIVE_FILE = os.path.join(".lockin", "active.json")
DIRECTORY_CHANGERS = frozenset({"cd", "pushd", "popd"})

# Subcommands per package manager that install, add or remove packages.
INSTALL_VERBS = {
    "npm": {
        "install", "i", "in", "ins", "inst", "insta", "instal", "isnt", "isnta", "isntal", "isntall",
        "add", "ci", "update", "up", "upgrade", "udpate", "uninstall", "remove", "rm", "un", "unlink",
    },
    "pnpm": {"install", "i", "add", "update", "up", "remove", "dlx"},
    "yarn": {"install", "add", "upgrade", "remove", "dlx"},
    "bun": {"install", "i", "add", "update", "remove"},
    "composer": {"install", "i", "require", "update", "upgrade", "u", "remove"},
    "pip": {"install", "uninstall"},
    "pipx": {"install", "run", "inject", "upgrade"},
    "uv": {"add", "sync", "remove", "tool"},
    "poetry": {"add", "install", "update", "remove"},
    "cargo": {"install", "add", "update", "remove"},
    "gem": {"install", "update", "uninstall"},
    "bundle": {"install", "add", "update"},
    "go": {"install", "get"},
    "conda": {"install", "update", "remove"},
    "mamba": {"install", "update", "remove"},
    "apt": {"install", "reinstall", "upgrade", "remove", "purge"},
    "apt-get": {"install", "reinstall", "upgrade", "remove", "purge"},
    "dnf": {"install", "reinstall", "upgrade", "remove"},
    "yum": {"install", "reinstall", "upgrade", "remove"},
    "apk": {"add", "upgrade", "del"},
    "brew": {"install", "reinstall", "upgrade", "uninstall"},
}
# Options of npx, npm exec and bunx that fetch a package from the registry.
FETCH_OPTIONS = {"-y", "--yes", "-p", "--package"}
PIP_RE = re.compile(r"^pip(?:\d+(?:\.\d+)?)?$")
PYTHON_RE = re.compile(r"^python(?:\d+(?:\.\d+)?)?$")

SEGMENT_SPLIT_RE = re.compile(r"\|\||&&|[;|&\n()`]|\$\(")
# ":" splits <rev>:<path>, so "git show HEAD:.env" checks ".env".
TOKEN_SPLIT_RE = re.compile(r"[\s;&|<>()=`\"',:]+")


class Blocked(Exception):
    """A rule violation. The message names the rule."""


@dataclass(frozen=True)
class Context:
    """Per-call data the checks need. Empty strings mean "unknown"."""

    cwd: str
    root: str  # realpath of the repository root
    lexical_root: str  # same root without resolving symlinks
    secret_globs: tuple[str, ...]  # normalized, casefolded globs from .lockin-guard.json


def is_secret_name(name: str) -> bool:
    """Return True if a file basename looks like a secret file. Ignores case."""
    name = name.casefold()
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


def is_only_wildcards(name: str) -> bool:
    """Return True for empty names and names like `*` or `**` that match everything."""
    return not name or set(name) <= {"*", "?"}


def load_secret_globs(root: str) -> tuple[str, ...]:
    """Read the project secret globs from .lockin-guard.json in the repo root.

    A missing file means no project globs. A broken file blocks (fail-closed).
    """
    if not root:
        return ()
    path = os.path.join(root, PROJECT_CONFIG)
    if not os.path.lexists(path):
        return ()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Blocked(f"{PROJECT_CONFIG} is invalid: {error}.") from error
    if not isinstance(data, dict) or set(data) != {"secret_globs"}:
        raise Blocked(f'{PROJECT_CONFIG} is invalid: expected an object with exactly the key "secret_globs".')
    globs = data["secret_globs"]
    if not isinstance(globs, list):
        raise Blocked(f"{PROJECT_CONFIG} is invalid: secret_globs must be a list.")
    return tuple(normalize_secret_glob(glob) for glob in globs)


def normalize_secret_glob(glob: object) -> str:
    """Validate one project glob and bring it into the form the matchers expect."""
    if not isinstance(glob, str) or not glob.strip():
        raise Blocked(f"{PROJECT_CONFIG} is invalid: every glob must be a non-empty string.")
    text = glob.strip()
    while text.startswith("./"):
        text = text[2:]
    if not text or text.startswith("/") or ".." in PurePath(text).parts:
        raise Blocked(f"{PROJECT_CONFIG} is invalid: globs must be relative to the repository root: {glob}.")
    if text.endswith("/"):
        # A directory like "config/secrets/" covers everything below it.
        text = text.rstrip("/") + "/*"
    return text.casefold()


def strip_any_depth(glob: str) -> str:
    """Remove a leading `**/` from a glob."""
    return glob[3:] if glob.startswith("**/") else glob


def glob_matches_relpath(glob: str, rel: str) -> bool:
    """Match a normalized project glob against a path relative to the repo root.

    `*` also matches `/`. A glob without `/` matches the basename anywhere.
    A leading `**/` matches at any depth, including the root.
    """
    rest = strip_any_depth(glob)
    if "/" not in rest:
        return fnmatch.fnmatchcase(PurePath(rel).name, rest)
    if glob.startswith("**/"):
        return fnmatch.fnmatchcase(rel, rest) or fnmatch.fnmatchcase(rel, "*/" + rest)
    return fnmatch.fnmatchcase(rel, glob)


def relative_inside(path: str, root: str) -> str | None:
    """Return path relative to root, casefolded with `/` separators, or None if it lies outside."""
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:
        return None
    return os.path.relpath(path, root).replace(os.sep, "/").casefold()


def path_candidates(path: str, ctx: Context, from_root: bool = False) -> list[str]:
    """Return the repo-relative forms of a path: lexical, resolved and, for Bash, from the root.

    The lexical form keeps symlinks, so a symlinked secret still matches its
    configured path. `git show HEAD:<path>` reads relative to the repo root,
    which `from_root` covers.
    """
    if not ctx.root:
        return []
    candidates = [
        relative_inside(os.path.normpath(os.path.join(ctx.cwd, path)), ctx.lexical_root),
        relative_inside(os.path.realpath(os.path.join(ctx.cwd, path)), ctx.root),
    ]
    if from_root and not os.path.isabs(path):
        candidates.append(relative_inside(os.path.normpath(os.path.join(ctx.lexical_root, path)), ctx.lexical_root))
    return [candidate for candidate in candidates if candidate is not None]


def is_project_secret(path: str, ctx: Context, bash: bool = False) -> bool:
    """Return True if a path matches a glob from .lockin-guard.json."""
    if not ctx.secret_globs:
        return False
    name = PurePath(path).name.casefold()
    candidates = path_candidates(path, ctx, from_root=bash)
    for glob in ctx.secret_globs:
        rest = strip_any_depth(glob)
        if any(glob_matches_relpath(glob, candidate) for candidate in candidates):
            return True
        if "/" not in rest and fnmatch.fnmatchcase(name, rest):
            return True
        # The shell may have changed directory, as in `cd typo3conf && cat LocalConfiguration.php`.
        basename = PurePath(rest).name
        if bash and not GLOB_CHARS & set(basename) and name == basename:
            return True
    return False


def pattern_may_match_project_secret(pattern: str, ctx: Context, bash: bool = False) -> bool:
    """Return True if a wildcard pattern can match a glob from .lockin-guard.json.

    Only two narrow cases count, so broad patterns like `*.php` stay allowed:
    the pattern names the secret basename literally, or its literal directory
    equals the directory of a literal project glob and its basename matches.
    """
    if not ctx.secret_globs:
        return False
    pattern = pattern.casefold()
    pattern_name = PurePath(pattern).name
    pattern_dir = os.path.normpath(str(PurePath(pattern).parent))
    if is_only_wildcards(pattern_name):
        return False
    pattern_dirs = {pattern_dir}
    if bash and ctx.cwd:
        resolved = relative_inside(os.path.normpath(os.path.join(ctx.cwd, pattern_dir)), ctx.lexical_root)
        if resolved is not None:
            pattern_dirs.add(os.path.normpath(resolved))
    for glob in ctx.secret_globs:
        rest = strip_any_depth(glob)
        glob_name = PurePath(rest).name
        literal_name = not GLOB_CHARS & set(glob_name)
        if literal_name and not GLOB_CHARS & set(pattern_name) and pattern_name == glob_name:
            return True
        literal_glob = not glob.startswith("**/") and not GLOB_CHARS & set(glob)
        if (
            literal_glob
            and not GLOB_CHARS & set(pattern_dir)
            and fnmatch.fnmatchcase(glob_name, pattern_name)
            and os.path.normpath(str(PurePath(glob).parent)) in pattern_dirs
        ):
            return True
    return False


def is_secret_path(path: str, ctx: Context, bash: bool = False) -> bool:
    return is_secret_name(PurePath(path).name) or is_project_secret(path, ctx, bash)


def glob_may_match_secret(pattern: str, ctx: Context, bash: bool = False) -> bool:
    """Return True if a glob pattern can match a secret file.

    A pattern made only of wildcards (for example `*` or `**/*`) is not
    treated as a secret glob, otherwise every broad search would be blocked.
    """
    name = PurePath(pattern).name.casefold()
    if is_only_wildcards(name):
        return False
    if any(fnmatch.fnmatchcase(probe, name) for probe in SECRET_PROBES):
        return True
    return pattern_may_match_project_secret(pattern, ctx, bash)


def piece_may_be_secret(piece: str, ctx: Context) -> bool:
    """Return True if a command word names a secret file or globs one."""
    if is_secret_path(piece, ctx, bash=True):
        return True
    return bool(GLOB_CHARS & set(piece)) and glob_may_match_secret(piece, ctx, bash=True)


def has_part(path: str, part: str) -> bool:
    """Return True if a path has the given component, ignoring case like macOS and NTFS do."""
    return any(item.casefold() == part for item in PurePath(path).parts)


def is_lockin_path(path: str) -> bool:
    return has_part(path, ".lockin")


def lexical_repo_root(cwd: str) -> str:
    """Return the nearest ancestor of cwd that holds .git, without resolving symlinks."""
    start = os.path.abspath(cwd)
    current = start
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return start
        current = parent


def repo_root(cwd: str) -> str:
    """Return the nearest ancestor of cwd that holds .git, or cwd itself."""
    current = os.path.realpath(cwd)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.realpath(cwd)
        current = parent


def check_write_scope(tool: str, path: str, ctx: Context) -> None:
    """Allow Edit and Write only inside the repository and outside .git/ and .lockin/."""
    if not ctx.cwd:
        raise Blocked(f"{tool} without a working directory in the hook input cannot be checked.")
    root = ctx.root
    target = os.path.realpath(os.path.join(ctx.cwd, path))
    if os.path.commonpath([root, target]) != root:
        raise Blocked(f"{tool} outside the repository is not allowed: {path}.")
    rel = os.path.relpath(target, root)
    if has_part(rel, ".git"):
        raise Blocked(f"{tool} under .git/ is not allowed: {path}.")
    if has_part(rel, ".lockin"):
        raise Blocked(f"{tool} under .lockin/ is not allowed: {path}.")


def tokenize(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def skip_options(tokens: list[str], index: int, values: frozenset[str], flags: frozenset[str], wrapper: str) -> int:
    """Return the index of the first non-option token after `index`.

    Raises Blocked on an unknown option, because a wrong guess would shift
    the parser to the wrong command.
    """
    while index < len(tokens) and tokens[index].startswith("-") and tokens[index] != "-":
        token = tokens[index]
        if token.startswith("--"):
            name = token.split("=", 1)[0]
            if name in values:
                index += 1 if "=" in token else 2
            elif name in flags:
                index += 1
            else:
                raise Blocked(f"unknown {wrapper} option {token}, the guard cannot locate the command.")
            continue
        advance = 1
        for position, letter in enumerate(token[1:], start=2):
            option = f"-{letter}"
            if option in values:
                advance = 1 if position < len(token) else 2
                break
            if option not in flags:
                raise Blocked(f"unknown {wrapper} option {token}, the guard cannot locate the command.")
        index += advance
    return index


def unwrap_compose(tokens: list[str], index: int) -> int | None:
    """Return the index after `compose [options] exec [options] <service>`, or None if it is no exec."""
    index = skip_options(tokens, index, COMPOSE_VALUE_OPTIONS, COMPOSE_FLAGS, "docker compose")
    if index < len(tokens) and tokens[index] == "exec":
        return skip_options(tokens, index + 1, COMPOSE_EXEC_VALUE_OPTIONS, COMPOSE_EXEC_FLAGS, "docker compose exec") + 1
    return None


def unwrap_docker(tokens: list[str], index: int) -> int | None:
    """Return the index after `docker exec` or `docker compose exec` and its container, or None."""
    index = skip_options(tokens, index + 1, DOCKER_VALUE_OPTIONS, DOCKER_FLAGS, "docker")
    if index >= len(tokens):
        return None
    if tokens[index] == "exec":
        return skip_options(tokens, index + 1, DOCKER_EXEC_VALUE_OPTIONS, DOCKER_EXEC_FLAGS, "docker exec") + 1
    if tokens[index] == "compose":
        return unwrap_compose(tokens, index + 1)
    return None


class Unwrapped(NamedTuple):
    """The command after stripping wrappers. `nested` holds a shell line to check again."""

    tokens: list[str]
    nested: str | None


def unwrap(tokens: list[str]) -> Unwrapped:
    """Strip variable assignments, simple wrappers and container wrappers from the front."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        name = PurePath(token).name
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token):
            index += 1
        elif name in COMMAND_WRAPPERS:
            index += 1
            while index < len(tokens) and tokens[index].startswith("-"):
                index += 1
        elif name == "ddev":
            index += 1
            if index < len(tokens) and tokens[index].startswith("-"):
                raise Blocked(f"unknown ddev option {tokens[index]}, the guard cannot locate the command.")
            if index < len(tokens) and tokens[index] in {"exec", "."}:
                index = skip_options(tokens, index + 1, DDEV_EXEC_VALUE_OPTIONS, DDEV_EXEC_FLAGS, "ddev exec")
                # ddev runs the rest through `bash -c` in the container.
                return Unwrapped([], " ".join(tokens[index:]))
        elif name in {"docker", "docker-compose"}:
            after = unwrap_docker(tokens, index) if name == "docker" else unwrap_compose(tokens, index + 1)
            if after is None:
                return Unwrapped(tokens[index:], None)
            index = after
        else:
            break
    return Unwrapped(tokens[index:], None)


def is_inside_root(base: str, path: str, ctx: Context) -> bool:
    """Return True if path, resolved against base, lies inside the repository root."""
    real = os.path.realpath(os.path.join(base, path))
    try:
        return os.path.commonpath([ctx.root, real]) == ctx.root
    except ValueError:
        return False


def check_git_directory(effective: str, ctx: Context) -> None:
    """Block git in a directory outside the repo or below a planted git directory.

    git discovery starts at the effective directory and walks up. A `.git` or
    `HEAD` between there and the repo root can replace the real repository.
    """
    if not is_inside_root(effective, ".", ctx):
        raise Blocked("git outside the repository is not allowed.")
    real = os.path.realpath(effective)
    current = real
    while current != ctx.root:
        if os.path.exists(os.path.join(current, ".git")) or os.path.exists(os.path.join(current, "HEAD")):
            raise Blocked(f"git in {current} is not allowed, the directory may hold a planted git repository.")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def check_git(args: list[str], ctx: Context) -> None:
    """Allow only read-only git subcommands without options that write, run programs or leave the repo."""
    effective = ctx.cwd
    index = 0
    while index < len(args) and args[index].startswith("-"):
        token = args[index]
        if token == "-C":
            if index + 1 >= len(args):
                raise Blocked("git -C needs a directory.")
            value = args[index + 1]
            if value.startswith("~"):
                raise Blocked("git -C with ~ is not allowed, the shell expands it outside the repository.")
            effective = os.path.join(effective, value)
            index += 2
        elif token == "-c":
            if index + 1 >= len(args):
                raise Blocked("git -c needs a value.")
            key = args[index + 1].split("=", 1)[0].casefold()
            if key not in SAFE_GIT_CONFIG_KEYS:
                raise Blocked(f"git -c {key} is not allowed. Allowed keys: core.quotePath, color.ui.")
            index += 2
        elif token in GIT_GLOBAL_FLAGS:
            index += 1
        else:
            raise Blocked(f"git global option {token} is not allowed.")
    if index >= len(args):
        return
    subcommand = args[index]
    if subcommand not in GIT_READ_ONLY:
        raise Blocked(
            f"git {subcommand} is not allowed. The implementer may only run read-only git "
            f"commands: {', '.join(sorted(GIT_READ_ONLY))}."
        )
    rest = args[index + 1:]
    for arg in subcommand_args(rest):
        if arg.startswith("--"):
            name = arg.split("=", 1)[0]
            blocked = (
                len(name) >= 4
                and name not in GIT_PREFIX_EXCEPTIONS
                and any(option.startswith(name) for option in BLOCKED_GIT_OPTIONS)
            )
        else:
            # git grep clusters short options, so -lOsh means -l -O sh.
            blocked = arg.startswith("-") and len(arg) > 1 and "O" in arg[1:]
        if blocked:
            raise Blocked(
                f"git option {arg} is not allowed, it writes files, runs programs or reads outside the repository."
            )
    for arg in rest:
        # `git diff <path> <path>` with a path outside the work tree acts as --no-index.
        if (os.path.isabs(arg) or arg.startswith("..")) and not is_inside_root(effective, arg, ctx):
            raise Blocked(f"git argument {arg} points outside the repository.")
    check_git_directory(effective, ctx)


def subcommand_args(args: list[str]) -> list[str]:
    """Return the arguments before `--`. Later ones belong to the called script."""
    return args[: args.index("--")] if "--" in args else args


def check_install(program: str, args: list[str]) -> None:
    words = subcommand_args(args)
    name = "pip" if PIP_RE.match(program) else program
    blocked = False
    if name in {"npx", "bunx"} or (name == "npm" and "exec" in words):
        blocked = any(word.split("=", 1)[0] in FETCH_OPTIONS for word in words)
    elif name == "uv" and "pip" in words:
        blocked = bool(INSTALL_VERBS["pip"] & set(words[words.index("pip") + 1:]))
    elif name == "yarn" and not words:
        blocked = True
    elif name in INSTALL_VERBS:
        blocked = bool(INSTALL_VERBS[name] & set(words))
    elif PYTHON_RE.match(program) and "-m" in words:
        module_args = words[words.index("-m") + 1:]
        if module_args and PIP_RE.match(module_args[0]):
            blocked = bool(INSTALL_VERBS["pip"] & set(module_args[1:]))
    if blocked:
        raise Blocked(f"package installs are not allowed: {program} {' '.join(words)}".rstrip() + ".")


def check_shell(program: str, args: list[str]) -> None:
    """Block inline code for a nested shell, which would hide it from the guard."""
    if program == "eval":
        raise Blocked("eval is not allowed. Run the command directly.")
    if program in SHELLS and any(re.match(r"^-[A-Za-z]*c[A-Za-z]*$", arg) for arg in args):
        raise Blocked(f"{program} -c is not allowed. Run the command directly.")


def check_segments(command: str, ctx: Context, depth: int = 0) -> None:
    """Run the git, shell and install checks on every segment of a command line."""
    for segment in SEGMENT_SPLIT_RE.split(command):
        unwrapped = unwrap(tokenize(segment))
        if unwrapped.nested is not None:
            if depth >= MAX_NESTING:
                raise Blocked("ddev exec is nested too deeply to check.")
            check_segments(unwrapped.nested, ctx, depth + 1)
            continue
        tokens = unwrapped.tokens
        if not tokens:
            continue
        program = PurePath(tokens[0]).name
        if program == "git":
            check_git(tokens[1:], ctx)
        check_shell(program, tokens[1:])
        check_install(program, tokens[1:])


def unquoted_metachars(segment: str) -> tuple[str, ...]:
    """Return the shell metacharacters of a segment that the shell would interpret.

    Outside quotes a backslash quotes the next character. Inside single quotes
    nothing counts. Inside double quotes only `$` and backtick count. Outside
    quotes `$`, backtick, `*`, `?`, `[`, `{`, `>`, `<` and a word-initial `~` count.
    """
    found: list[str] = []
    state: str | None = None
    word_start = True
    index = 0
    while index < len(segment):
        char = segment[index]
        if state == "'":
            if char == "'":
                state = None
        elif state == '"':
            if char == "\\":
                index += 1
            elif char == '"':
                state = None
            elif char in "$`":
                found.append(char)
        else:
            if char == "\\":
                index += 1
            elif char in "'\"":
                state = char
            elif char in "$`*?[{><" or (char == "~" and word_start):
                found.append(char)
            word_start = char.isspace()
        index += 1
    return tuple(found)


Segment = tuple[tuple[str, ...], tuple[str, ...]]


def load_allowlist(ctx: Context) -> frozenset[Segment]:
    """Read the allowed command segments from .lockin/active.json.

    A missing file allows nothing (only read-only git). A broken file blocks.
    """
    path = os.path.join(ctx.root, ACTIVE_FILE)
    if not os.path.lexists(path):
        return frozenset()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Blocked(f".lockin/active.json is invalid: {error}.") from error
    if not isinstance(data, dict) or "commands" not in data:
        raise Blocked('.lockin/active.json is invalid: expected an object with the key "commands".')
    commands = data["commands"]
    if not isinstance(commands, list):
        raise Blocked(".lockin/active.json is invalid: commands must be a list.")
    allowed: set[Segment] = set()
    for command in commands:
        if not isinstance(command, str) or not command.strip():
            raise Blocked(".lockin/active.json is invalid: every command must be a non-empty string.")
        for segment in SEGMENT_SPLIT_RE.split(command):
            try:
                tokens = shlex.split(segment)
            except ValueError:
                # Such a segment never matches, because check_allowlist rejects it first.
                continue
            if tokens:
                allowed.add((tuple(tokens), unquoted_metachars(segment)))
    return frozenset(allowed)


def check_allowlist(command: str, ctx: Context) -> None:
    """Allow only segments from active.json and strict read-only git."""
    allowed = load_allowlist(ctx)
    parsed: list[tuple[str, list[str]]] = []
    for segment in SEGMENT_SPLIT_RE.split(command):
        # The split also cuts inside quotes. That always leaves an open quote in
        # the left part, so a clean parse proves that every split point lies outside quotes.
        try:
            tokens = shlex.split(segment)
        except ValueError as error:
            raise Blocked(
                f"the command cannot be parsed safely: {segment.strip()}. "
                "Do not put ;, |, & or parentheses inside quotes."
            ) from error
        if tokens:
            parsed.append((segment, tokens))
    changes_dir = any(tokens[0] in DIRECTORY_CHANGERS for _, tokens in parsed)
    for segment, tokens in parsed:
        if tokens[0] == "git" and changes_dir:
            raise Blocked("git after cd in one command is not allowed, run it separately.")
        metachars = unquoted_metachars(segment)
        if (tuple(tokens), metachars) in allowed:
            continue
        if tokens[0] == "git":
            if metachars:
                raise Blocked(
                    f"read-only git must not contain unquoted shell characters: {segment.strip()}. "
                    "Quote pathspecs like '*.py'."
                )
            check_git(tokens[1:], ctx)
            continue
        raise Blocked(
            f"the command is not on the allowlist of this work package: {segment.strip()}. "
            "Run only the Verification commands of the package and read-only git."
        )


def check_bash(command: str, ctx: Context, implementer: bool) -> None:
    # A hook timeout counts as non-blocking, so oversized input must block before the scan.
    if len(command) > MAX_COMMAND_LENGTH:
        raise Blocked(f"commands longer than {MAX_COMMAND_LENGTH} characters cannot be checked.")
    # The shell removes quotes and backslashes, so `.e""nv` reads `.env`.
    unquoted = " ".join(tokenize(command))
    for text in (command, unquoted):
        for piece in TOKEN_SPLIT_RE.split(text):
            if piece and piece_may_be_secret(piece, ctx):
                raise Blocked(f"the command touches a secret file: {piece}.")
    if not implementer:
        return
    if not ctx.cwd:
        raise Blocked("Bash without a working directory in the hook input cannot be checked.")
    if ".lockin" in command.casefold() or ".lockin" in unquoted.casefold():
        raise Blocked("the command touches .lockin/, which belongs to the workflow.")
    check_segments(command, ctx)
    check_allowlist(command, ctx)


def check(data: dict) -> None:
    agent = str(data.get("agent_type", ""))
    implementer = agent == IMPLEMENTER
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    cwd = str(data.get("cwd", ""))
    root = repo_root(cwd) if cwd else ""
    # A broken .lockin-guard.json raises Blocked here, before any tool check.
    ctx = Context(cwd, root, lexical_repo_root(cwd) if cwd else "", load_secret_globs(root))

    if tool in {"Read", "Edit", "Write"}:
        path = str(tool_input.get("file_path", ""))
        if is_secret_path(path, ctx):
            raise Blocked(f"{tool} on a secret file is not allowed: {path}.")
        if tool in {"Edit", "Write"}:
            if is_lockin_path(path):
                raise Blocked(f"{tool} under .lockin/ is not allowed: {path}.")
            if PurePath(path).name.casefold() == PROJECT_CONFIG:
                raise Blocked(f"{tool} on {PROJECT_CONFIG} is not allowed: {path}.")
            check_write_scope(tool, path, ctx)
    elif tool in {"Grep", "Glob"}:
        path = str(tool_input.get("path", ""))
        pattern = str(tool_input.get("glob" if tool == "Grep" else "pattern", ""))
        if path and is_secret_path(path, ctx):
            raise Blocked(f"{tool} on a secret file is not allowed: {path}.")
        if pattern and glob_may_match_secret(pattern, ctx):
            raise Blocked(f"{tool} with a glob that matches secret files is not allowed: {pattern}.")
    elif tool == "Bash":
        check_bash(str(tool_input.get("command", "")), ctx, implementer)


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
