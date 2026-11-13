# Changelog

All notable changes to the lowkey plugin are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the plugin uses [Semantic Versioning](https://semver.org/).

## [1.5.0] - 2026-11-13

### Added

- New skill `/lowkey:typo3-upgrade` for Composer-based TYPO3 major upgrades from 11.5, 12.4 or 13.4 to 12, 13 or 14, one rung at a time. It refuses older or non-LTS sources, inventories the project read-only, writes a roadmap and one step brief per step into `.lockin/upgrade/`, waits for approval and prints the lockin command for each step. It never changes code, the database or Composer itself. `--resume` records the outcome (`pass`, `findings`, `blocked`) and proposes the next step, `--step <n>` repeats a handoff.
- References for process and command classes, roadmap template, database, Composer, schema and wizards, verification, the rungs 11 to 12, 12 to 13 and 13 to 14, and the migrations Gridelements to container and Mask to Content Blocks. All 13 to 14 items are marked unverified.
- Scripts `crawl.sh`, `htmldiff.sh`, `residual.py`, `tree_hash.py`, `ts-dump.php` and `extension-scanner.php`, generalized from a real upgrade project, with tests in `tests/lowkey/test_typo3_upgrade.py`.
- Evals `upgrade-refuses-v10` and `upgrade-preflight-readonly` (smoke) and `upgrade-roadmap-gate` (gate).

### Changed

- `.gitattributes` keeps LF line endings for `*.php` too.

### Notes

- The skill recommends the MCP server TYPO3/dev-companion and stops once if it is missing. It works without it and then marks unconfirmed facts as unverified.
- Step briefs carry a command contract for lockin: only idempotent checks go into `Verification`, every command that writes the database, a snapshot or a baseline runs in lockin's main session after approval.
- The PHP scripts passed `php -l` only. They ran on TYPO3 12 and 13 in the source project, not in this repository.
- The three new evals pass in a local run. The `typo3-upgrade` cases need the extra grants `"Bash(cp:*)"` and `"Bash(mkdir:*)"`, see the README.
- `residual.py` pins the compared pages with `--pages` and `--pages-sha256`, and snapshot names carry an attempt number, so a rerun never overwrites the clean restore point.

## [1.4.0] - 2026-11-11

### Added

- Python scripts for the deterministic steps in `skills/lockin/scripts/`: `snapshot.py` (status snapshot and path lists), `collect_review.py` (`prepare` writes the review folder, diff and new file list, `run` runs one test command with a timeout and stops on file changes), `redact.py` (idempotent redaction of test output, exit 1 on remaining hits) and `cleanup.py` (checked delete of `review/` or the run folder). Tests in `tests/lowkey/test_scripts.py` use temporary git repositories with spaces, quotes and umlauts in paths. The scripts need Python 3.9 or newer.
- Run stats in `state.md`: challenge rounds, attempts per package with model and findings per reviewer with decision. The wrap-up prints them in a short block.
- `--lite` flag, combinable with `--keep`: one challenge round instead of three and the new combined reviewer `lockin-reviewer` instead of two. All gates stay. The mode stays in `state.md` and survives `--resume`.
- Issue backchannel for issue input, only after an explicit yes: the approved plan as an issue comment, and a draft pull request or merge request in the wrap-up once the user committed and pushed. The skill never commits or pushes.
- New skill `/lowkey:review` for a pull request, a branch, a `<base>..<head>` range or, without argument, the current branch against the merge-base of the default branch. It runs confirmed test commands, redacts their output, starts both reviewers in parallel and reports the findings without changing code.
- Evals `review-no-args` (smoke) and `plan-approval-gate` (gate). The gate case needs `--ablation none`, because the baseline arm cannot start plugin agents.

### Changed

- `SKILL.md` keeps the overview, state, git rules and Phases 1 to 3. Phase 4 moved to `phase-4.md`, Phase 5 and the wrap-up to `phase-5.md`. The rules for cutting work packages and picking models moved from 4.1 to 2.1, because the plan needs them before the approval.
- The tree fingerprint comes from `snapshot.py`. A resumed run from 1.3 or older shows a fingerprint mismatch once.
- The `diff` part of the status snapshot uses `--no-color --no-ext-diff --no-textconv`, so user diff settings cannot change it.
- The reviewer agents accept runs without plan or baseline.
- The guard covers the new agent `lowkey:lockin-reviewer`.
- CI runs the tests on Python 3.9 and 3.12. The job now reports one check per Python version, so a branch protection rule on the old check name `Guard tests and metadata` needs an update.
- `redact.py` also covers URL credentials, common token prefixes, cookie headers, escaped quotes and unterminated private key blocks, and runs in linear time on long lines.
- `collect_review.py run` kills the whole process group after the command, also on SIGINT and SIGTERM. The scripts refuse refs that start with `-`.
- The skill text passes test commands, refs and PR titles in single quotes. `/lowkey:review` uses full SHAs after resolving refs and warns before running tests of outside pull requests. Issue comment and draft PR show the exact text before the yes.

### Notes

- The grader syntax of the new evals (`input_match`, file targets for `regex`) and the `glab` flags come from the documentation and are not verified by a local run yet.
- Worktree isolation for the implementer is not implemented. Plugin agents accept `isolation: worktree`, but subagent worktrees branch from the default branch unless the user sets `worktree.baseRef: "head"`, which a plugin cannot set.

## [1.3.0] - 2026-11-11

### Added

- Bash allowlist for the implementer. The main session writes `.lockin/active.json` with the `Verification` commands before each delegation. The guard allows only these command segments plus strict read-only git. Without the file only read-only git runs, a broken file blocks every Bash call.
- Project secrets in an optional `.lockin-guard.json` in the repository root (`secret_globs`). A broken file blocks the lockin agents. The implementer cannot edit the file.
- Wrapper detection for `ddev`, `ddev exec`, `docker exec` and `docker compose exec`. Git, shell and install checks apply behind them. Unknown wrapper options block.
- `.npmrc`, `.git-credentials` and `.envrc` count as secret files.

### Changed

- Name checks ignore case, so `.LOCKIN/`, `.GIT/` and `.ENV` no longer pass on case-insensitive filesystems.
- Bash checks split `<rev>:<path>`, so `git show HEAD:.env` counts as secret access.
- Read-only git blocks options that write files, run programs or read outside the repository (`--output`, `--ext-diff`, `--textconv`, `--no-index`, `--contents`, `--untracked`, `--no-exclude-standard`, `--recurse-submodules`, `-O`), also abbreviated. Global options follow an allowlist. git in a directory with a planted `.git` or `HEAD` below the repository root blocks.
- Breaking: implementer Bash without `.lockin/active.json` allows only read-only git. A run resumed from 1.2 gets the file in step 4.2 before the next delegation.
- Read-only git blocks paths outside the repository, because `git diff <path> <path>` then acts as `--no-index`.
- Bash commands of lockin agents longer than 16384 characters get blocked, so the check cannot run into the hook timeout.
- The implementer needs a working directory in the hook input for Bash.
- SKILL.md writes and deletes `active.json` and documents the rules for `Verification` commands. The implementer edits files only with Edit and Write.

## [1.2.0] - 2026-11-10

### Added

- Automatic cleanup. The wrap-up deletes `.lockin/<slug>/` after the summary. `--keep` keeps the state of a run.
- `review/` folder for diff, new file list and redacted test output. The reviewers read these files instead of receiving them inline. The folder gets deleted at the end of Phase 5.
- The tree fingerprint hashes the content of untracked files, so resume detects changes to new files.
- Guard hook for the lockin subagents (`hooks/hooks.json`, `guard.sh`, `guard.py`). It blocks secret files for all four agents. For the implementer it also blocks writes to `.lockin/`, `.git/` and outside the repository, git commands other than read-only ones, nested shells (`sh -c`, `bash -c`, `eval`) and package installs across 20 package managers, also behind global options like `npm --prefix x install`. Bash checks see through quotes and globs, so `.e""nv` and `.en?` count as `.env`. The guard also covers the Glob tool. The guard fails closed for lockin agents and never affects other agents or the main session. It needs `python3`.
- Eval suite in `evals/` with four cases for the gates of the workflow: empty arguments, analysis-only exit, resume without runs and no changes before approval.

### Changed

- `plan.md` contains the work package list with files and model. The approval hash covers it, and Phase 4 only expands the approved list.
- The `Verification` field of a work package may only contain user-confirmed commands. The implementer runs only these commands and read-only git.
- The implementer receives the path of its package file instead of the full text.
- The challenge loop also stops on `CRITICAL OBJECTIONS: 0`. The plan challenger uses this form only for one or more objections.
- The resume instructions moved to `skills/lockin/resume.md` and load only on `--resume`.

## [1.1.0] - 2026-11-10

### Added

- State files in `.lockin/<slug>/` and `--resume [slug]` to continue a run.
- Baseline in Phase 1: HEAD, working tree status and check-mode test results. The test commands run only after user confirmation.
- Git base and pre-existing change handling before Phase 4. Overlapping uncommitted changes block the run.
- Analysis-only exit for tasks without a change request.
- `Verification` field in work packages for projects without automated tests.
- Model choice per work package and a fixed retry ladder (planned model, then Sonnet, then main session or user).
- Commit message, PR description draft and staging path list in the wrap-up.

### Changed

- The skill requires a git repository.
- Reviewers receive the baseline test results and flag only new or changed failures.
- The plan challenger, the correctness reviewer and the main session never read secrets. The implementer and the risk reviewer already followed this rule.
- Agents never modify or review pre-existing user changes.
- The plan challenger verdict line is defined as the first line under `## Verdict`.
- The version lives only in `plugin.json`.

## [1.0.0] - 2026-11-10

### Added

- Initial release with the `lockin` skill and four subagents.
