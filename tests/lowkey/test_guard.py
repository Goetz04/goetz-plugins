"""Tests for the lowkey guard hook. Run with: python3 -m unittest discover tests"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD_SH = ROOT / "plugins" / "lowkey" / "hooks" / "guard.sh"

IMPLEMENTER = "lowkey:lockin-implementer"
REVIEWER = "lowkey:lockin-reviewer-risk"


def run_guard(payload: str, path_env: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if path_env is not None:
        env["PATH"] = path_env
    return subprocess.run(
        ["/bin/sh", str(GUARD_SH)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )


def call(
    tool: str, tool_input: dict, agent: str | None = IMPLEMENTER, cwd: str | None = "/repo"
) -> subprocess.CompletedProcess[str]:
    data: dict = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    if cwd is not None:
        data["cwd"] = cwd
    if agent is not None:
        data["agent_type"] = agent
    return run_guard(json.dumps(data))


class GuardTestCase(unittest.TestCase):
    def assertAllowed(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertBlocked(self, result: subprocess.CompletedProcess[str], fragment: str = "") -> None:
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("lowkey guard:", result.stderr)
        self.assertIn(fragment, result.stderr)


class ScopeTest(GuardTestCase):
    def test_main_session_is_never_blocked(self) -> None:
        self.assertAllowed(call("Bash", {"command": "git commit -m x && cat .env"}, agent=None))

    def test_foreign_agent_is_never_blocked(self) -> None:
        self.assertAllowed(call("Read", {"file_path": "/repo/.env"}, agent="Explore"))

    def test_plain_agent_name_is_not_guarded(self) -> None:
        # Plugin agents arrive namespaced. A user's own agent with a similar name stays untouched.
        self.assertAllowed(call("Read", {"file_path": "/repo/.env"}, agent="lockin-implementer"))

    def test_unknown_lowkey_agent_is_not_guarded(self) -> None:
        self.assertAllowed(call("Read", {"file_path": "/repo/.env"}, agent="lowkey:lockin-other"))

    def test_namespaced_agent_name_is_recognized(self) -> None:
        self.assertBlocked(call("Read", {"file_path": "/repo/.env"}, agent=REVIEWER))


class SecretTest(GuardTestCase):
    def test_read_env_is_blocked(self) -> None:
        self.assertBlocked(call("Read", {"file_path": "/repo/.env"}), "secret file")

    def test_read_env_local_is_blocked(self) -> None:
        self.assertBlocked(call("Read", {"file_path": "/repo/.env.local"}))

    def test_env_templates_are_allowed(self) -> None:
        for name in (".env.example", ".env.dist", ".env.sample"):
            with self.subTest(name=name):
                self.assertAllowed(call("Read", {"file_path": f"/repo/{name}"}))

    def test_key_material_is_blocked(self) -> None:
        for name in ("server.pem", "tls.key", "cert.p12", "cert.pfx", "id_rsa", "id_ed25519.pub"):
            with self.subTest(name=name):
                self.assertBlocked(call("Read", {"file_path": f"/home/u/{name}"}))

    def test_credential_files_are_blocked(self) -> None:
        for name in (".netrc", ".pgpass", "auth.json", "credentials", "credentials.json", "credentials.yml"):
            with self.subTest(name=name):
                self.assertBlocked(call("Read", {"file_path": f"/repo/{name}"}))

    def test_regular_files_are_allowed(self) -> None:
        for name in ("src/Service.php", "composer.json", "README.md", "environment.ts", "docs/credentials-howto.md", "credentials.md", "CredentialsProvider.php"):
            with self.subTest(name=name):
                self.assertAllowed(call("Read", {"file_path": f"/repo/{name}"}))

    def test_path_with_spaces_is_handled(self) -> None:
        self.assertBlocked(call("Read", {"file_path": "/repo/my app/.env"}))
        self.assertAllowed(call("Read", {"file_path": "/repo/my app/main.py"}))

    def test_write_env_is_blocked(self) -> None:
        self.assertBlocked(call("Write", {"file_path": "/repo/.env", "content": "X=1"}))

    def test_grep_on_secret_path_is_blocked(self) -> None:
        self.assertBlocked(call("Grep", {"pattern": "KEY", "path": "/repo/.env"}, agent=REVIEWER))

    def test_grep_with_secret_glob_is_blocked(self) -> None:
        self.assertBlocked(call("Grep", {"pattern": "KEY", "glob": "**/.env*"}, agent=REVIEWER))

    def test_grep_with_broad_or_code_glob_is_allowed(self) -> None:
        for pattern in ("*", "**/*", "*.php", "src/**/*.ts"):
            with self.subTest(glob=pattern):
                self.assertAllowed(call("Grep", {"pattern": "x", "glob": pattern}, agent=REVIEWER))

    def test_bash_cat_env_is_blocked(self) -> None:
        self.assertBlocked(call("Bash", {"command": "cat .env | grep DB"}))

    def test_bash_env_file_option_is_blocked(self) -> None:
        self.assertBlocked(call("Bash", {"command": "docker run --env-file=.env app"}))

    def test_bash_quoted_secret_is_blocked(self) -> None:
        for command in ('cat .e""nv', "cat .e\\nv", "cat '.env'", "cat config/id_r''sa"):
            with self.subTest(command=command):
                self.assertBlocked(call("Bash", {"command": command}), "secret")

    def test_bash_secret_glob_is_blocked(self) -> None:
        for command in ("cat .en?", "cat .e*", "cat config/*.pem", "ls ~/.ssh/id_*"):
            with self.subTest(command=command):
                self.assertBlocked(call("Bash", {"command": command}), "secret")

    def test_bash_code_globs_are_allowed(self) -> None:
        for command in ("ls *", "cat src/*.php", "grep -rn x tests/**/*.py"):
            with self.subTest(command=command):
                self.assertAllowed(call("Bash", {"command": command}))

    def test_glob_tool_with_secret_pattern_is_blocked(self) -> None:
        self.assertBlocked(call("Glob", {"pattern": "**/.env*"}, agent=REVIEWER), "Glob")

    def test_glob_tool_with_code_pattern_is_allowed(self) -> None:
        for pattern in ("**/*", "src/**/*.ts", "*.md"):
            with self.subTest(pattern=pattern):
                self.assertAllowed(call("Glob", {"pattern": pattern}, agent=REVIEWER))


class LockinStateTest(GuardTestCase):
    def test_read_own_package_is_allowed(self) -> None:
        self.assertAllowed(call("Read", {"file_path": "/repo/.lockin/s/packages/1.md"}))

    def test_edit_under_lockin_is_blocked(self) -> None:
        self.assertBlocked(call("Edit", {"file_path": "/repo/.lockin/s/state.md"}), ".lockin")

    def test_write_under_lockin_is_blocked(self) -> None:
        self.assertBlocked(call("Write", {"file_path": "/repo/.lockin/s/plan.md"}))

    def test_bash_touching_lockin_is_blocked(self) -> None:
        self.assertBlocked(call("Bash", {"command": "rm -rf .lockin/s"}))

    def test_bash_quoted_lockin_is_blocked(self) -> None:
        self.assertBlocked(call("Bash", {"command": 'cat .lock""in/s/state.md'}), ".lockin")

    def test_similar_names_are_allowed(self) -> None:
        self.assertAllowed(call("Edit", {"file_path": "/repo/src/lockin.py"}))


class WriteScopeTest(GuardTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.realpath(self._tmp.name)
        os.mkdir(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.repo, "src", "sub"))
        self.outside = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()
        self.outside.cleanup()

    def write(self, path: str, cwd: str | None = None, tool: str = "Write") -> subprocess.CompletedProcess[str]:
        return call(tool, {"file_path": path, "content": "x"}, cwd=cwd or self.repo)

    def test_write_inside_repo_is_allowed(self) -> None:
        self.assertAllowed(self.write(os.path.join(self.repo, "src", "a.py")))
        self.assertAllowed(self.write("src/b.py"))

    def test_write_from_subdirectory_cwd_is_allowed(self) -> None:
        self.assertAllowed(self.write(os.path.join(self.repo, "README.md"), cwd=os.path.join(self.repo, "src", "sub")))

    def test_write_outside_repo_is_blocked(self) -> None:
        for path in (os.path.join(self.outside.name, ".bashrc"), "/etc/hosts", "../escape.txt"):
            with self.subTest(path=path):
                self.assertBlocked(self.write(path), "outside the repository")

    def test_edit_outside_repo_is_blocked(self) -> None:
        self.assertBlocked(self.write("/etc/hosts", tool="Edit"), "outside the repository")

    def test_write_through_symlink_out_of_repo_is_blocked(self) -> None:
        os.symlink(self.outside.name, os.path.join(self.repo, "link"))
        self.assertBlocked(self.write(os.path.join(self.repo, "link", "x.txt")), "outside the repository")

    def test_write_under_git_dir_is_blocked(self) -> None:
        for path in (".git/hooks/pre-commit", os.path.join(self.repo, ".git", "config")):
            with self.subTest(path=path):
                self.assertBlocked(self.write(path), ".git/")

    def test_similar_git_names_are_allowed(self) -> None:
        self.assertAllowed(self.write(".gitignore"))
        self.assertAllowed(self.write(".github/workflows/ci.yml"))

    def test_missing_cwd_blocks_write(self) -> None:
        result = call("Write", {"file_path": "/repo/a.py", "content": "x"}, cwd=None)
        self.assertBlocked(result, "working directory")

    def test_main_session_may_write_anywhere(self) -> None:
        self.assertAllowed(call("Write", {"file_path": "/etc/hosts", "content": "x"}, agent=None))


class NestedShellTest(GuardTestCase):
    def test_shell_with_inline_code_is_blocked(self) -> None:
        for command in ('bash -c "git commit -m x"', "sh -c 'npm install foo'", "bash -lc 'make'", "zsh -ec true", "env bash -c ls", "find . | xargs sh -c 'echo'"):
            with self.subTest(command=command):
                self.assertBlocked(call("Bash", {"command": command}), "-c is not allowed")

    def test_eval_is_blocked(self) -> None:
        self.assertBlocked(call("Bash", {"command": "eval git push"}), "eval")

    def test_shell_running_a_script_is_allowed(self) -> None:
        for command in ("sh scripts/test.sh", "bash -e scripts/check.sh", "./run-tests.sh --ci"):
            with self.subTest(command=command):
                self.assertAllowed(call("Bash", {"command": command}))

    def test_reviewer_is_not_affected(self) -> None:
        self.assertAllowed(call("Bash", {"command": "bash -c ls"}, agent=REVIEWER))


class GitTest(GuardTestCase):
    def test_read_only_git_is_allowed(self) -> None:
        for command in ("git status --porcelain", "git diff HEAD -- src", "git -C sub log -1", "git -c core.quotePath=false ls-files"):
            with self.subTest(command=command):
                self.assertAllowed(call("Bash", {"command": command}))

    def test_git_writes_are_blocked(self) -> None:
        for command in ("git commit -m x", "git push", "git stash", "git reset --hard", "git checkout main", "git switch -c x", "git rebase main", "git merge x", "git restore .", "git clean -fd", "git add ."):
            with self.subTest(command=command):
                self.assertBlocked(call("Bash", {"command": command}), "git")

    def test_git_with_options_before_subcommand_is_blocked(self) -> None:
        self.assertBlocked(call("Bash", {"command": "git -C /repo commit -m x"}))

    def test_git_write_in_chain_is_blocked(self) -> None:
        self.assertBlocked(call("Bash", {"command": "vendor/bin/phpunit && git commit -am done"}))

    def test_git_write_in_subshell_is_blocked(self) -> None:
        self.assertBlocked(call("Bash", {"command": "echo $(git stash)"}))

    def test_git_write_behind_wrapper_is_blocked(self) -> None:
        self.assertBlocked(call("Bash", {"command": "GIT_AUTHOR_NAME=x env git commit -m x"}))

    def test_git_as_argument_is_allowed(self) -> None:
        self.assertAllowed(call("Bash", {"command": "grep -rn git docs/"}))

    def test_reviewer_git_rules_do_not_apply(self) -> None:
        # Reviewers have no Bash tool. The git rule is implementer-only by design.
        self.assertAllowed(call("Bash", {"command": "git commit -m x"}, agent=REVIEWER))


class InstallTest(GuardTestCase):
    def test_installs_are_blocked(self) -> None:
        for command in ("npm install", "npm i lodash", "npm ci", "pnpm add x", "yarn", "yarn add x", "composer require foo/bar", "composer update", "pip install x", "python3 -m pip install x", "uv add x", "uv pip install x", "sudo apt-get install jq", "brew install jq"):
            with self.subTest(command=command):
                self.assertBlocked(call("Bash", {"command": command}), "install")

    def test_options_before_subcommand_are_skipped(self) -> None:
        for command in ("npm --prefix x install foo", "npm --silent i", "python3 -m pip --quiet install foo", "python3.12 -m pip install x", "pip3.12 install x", "composer --no-interaction require a/b", "npm isntall x"):
            with self.subTest(command=command):
                self.assertBlocked(call("Bash", {"command": command}), "install")

    def test_more_package_managers_are_blocked(self) -> None:
        for command in ("cargo install ripgrep", "cargo add serde", "gem install rails", "bundle install", "bun add zod", "bun install", "go install x@latest", "go get x", "pipx run black", "poetry add requests", "pnpm dlx create-x", "yarn dlx x", "npx -y create-x", "npx --package=x y", "npm exec --yes x", "bunx -p x y", "apk add jq", "dnf install jq"):
            with self.subTest(command=command):
                self.assertBlocked(call("Bash", {"command": command}), "install")

    def test_local_binaries_via_npx_are_allowed(self) -> None:
        for command in ("npx vitest run", "npx --no-install eslint src", "bunx tsc --noEmit", "npm exec -- jest"):
            with self.subTest(command=command):
                self.assertAllowed(call("Bash", {"command": command}))

    def test_script_arguments_after_double_dash_are_ignored(self) -> None:
        self.assertAllowed(call("Bash", {"command": "npm run check -- install"}))

    def test_test_runners_are_allowed(self) -> None:
        for command in ("npm test", "npm run lint", "composer test", "vendor/bin/phpunit tests/Unit", "python3 -m pytest -q", "go test ./...", "cargo test", "bun test", "bundle exec rspec", "uv run pytest", "uv pip list"):
            with self.subTest(command=command):
                self.assertAllowed(call("Bash", {"command": command}))


class FailureModeTest(GuardTestCase):
    def test_broken_json_from_lockin_agent_is_blocked(self) -> None:
        self.assertBlocked(run_guard('{"agent_type": "lowkey:lockin-implementer", "tool_input": {'), "unreadable")

    def test_broken_json_from_other_agent_is_allowed(self) -> None:
        self.assertAllowed(run_guard('{"agent_type": "Explore", "tool_input": {'))

    def test_empty_input_is_allowed(self) -> None:
        self.assertAllowed(run_guard(""))

    def test_missing_python_blocks_lockin_agent(self) -> None:
        with tempfile.TemporaryDirectory() as bin_dir:
            for tool in ("cat", "grep", "dirname"):
                found = shutil.which(tool)
                self.assertIsNotNone(found, tool)
                os.symlink(found, os.path.join(bin_dir, tool))
            payload = json.dumps({"agent_type": IMPLEMENTER, "tool_name": "Read", "tool_input": {"file_path": "a.txt"}})
            result = run_guard(payload, path_env=bin_dir)
            self.assertBlocked(result, "python3 not found")
            other = run_guard(json.dumps({"agent_type": "Explore"}), path_env=bin_dir)
            self.assertAllowed(other)


if __name__ == "__main__":
    unittest.main()
