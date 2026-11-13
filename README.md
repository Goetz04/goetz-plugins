# goetz-plugins

A Claude Code plugin marketplace by [Goetz](https://github.com/Goetz04).

## Plugins

### lowkey

Lock in on big, important tasks. The `lockin` skill runs a gated workflow: understand the task, write a plan and let an independent subagent challenge it, wait for your approval, implement in small self-contained work packages and review the full diff with two dedicated reviewers. The `review` skill reviews an existing branch or pull request with the same reviewers, without changing code. The `typo3-upgrade` skill plans a TYPO3 major upgrade and hands each step to `lockin`.

## Installation

```text
/plugin marketplace add Goetz04/goetz-plugins
/plugin install lowkey@goetz
```

## Updates

Auto-update is off by default for third-party marketplaces. Turn it on in `/plugin` → Marketplaces → goetz → Enable auto-update. To update manually, run:

```text
/plugin marketplace update goetz
/reload-plugins
```

Every release bumps the version in `plugin.json`. See the [changelog](plugins/lowkey/CHANGELOG.md) for what changed.

## Usage

```text
/lowkey:lockin [--keep] [--lite] <issue-number or task>
/lowkey:lockin --resume [slug] [--keep]
/lowkey:review [pr-number | branch | <base>..<head>]
/lowkey:typo3-upgrade [--to 12|13|14] [--lite]
/lowkey:typo3-upgrade --resume | --step <n>
```

Examples:

```text
/lowkey:lockin 13
/lowkey:lockin "Add rate limiting to the public search API"
/lowkey:lockin --keep "Migrate the session store to Redis"
/lowkey:lockin --lite "Add a CSV export to the report page"
/lowkey:lockin --resume 2026-11-10-rate-limiting
/lowkey:typo3-upgrade --to 13
```

With an issue number, the skill reads the issue through `gh` (GitHub) or `glab` (GitLab) if available. Otherwise it treats the argument as the task description. If the task only asks for an analysis, the skill delivers the analysis and asks whether to continue with a change. The skill requires a git repository.

`--lite` runs one challenge round instead of three and one combined reviewer instead of two. All gates stay. With issue input, the skill offers to post the approved plan as an issue comment and to open a draft pull request in the wrap-up. Both need your explicit yes. Commit and push stay with you.

The skill only runs when you invoke it explicitly. Claude does not start it on its own.

## Workflow

| Phase | What happens |
|---|---|
| 1. Understand | Reads the issue or task, the project `CLAUDE.md` and all affected files. Records a baseline: HEAD, working tree status and check-mode test results. States goal, scope and non-goals and creates the state folder with `state.md`. |
| 2. Plan and challenge | The main session writes the plan, including the list of work packages with files and model. `lockin-plan-challenger` challenges it, for up to 3 rounds or until no critical objections remain. In lite mode it runs one round. |
| 3. Approval | Shows the final plan, the rejected objections with reasons and the work packages with their model. Waits for your explicit approval and records it with a hash of the plan, which covers the package list. No code changes before that. With issue input, it offers to post the plan as an issue comment. |
| 4. Implementation | Records the git base and blocks if your uncommitted changes overlap the planned files. Expands the approved package list into self-contained work packages. Their verification may only use test commands you confirmed. `lockin-implementer` implements them one by one. The main session verifies each result before the next package starts. |
| 5. Review | The main session writes the diff and the redacted test output to `.lockin/<slug>/review/`. `lockin-reviewer-correctness` and `lockin-reviewer-risk` read these files and review the full change. Every finding gets fixed or rejected with a reason. The review files get deleted at the end of the phase. In lite mode the combined `lockin-reviewer` reviews instead. |
| Wrap-up | Summary of implemented changes, open findings and test runs, plus a commit message, a PR description draft and the exact paths to stage. Deletes `.lockin/<slug>/` unless you passed `--keep`. No commit and no push unless you ask. Prints the run stats. With issue input, it offers a draft pull request once you committed and pushed. |

The skill text lives in `SKILL.md` (Phases 1 to 3), `phase-4.md` and `phase-5.md`. Deterministic steps such as snapshots, diff collection, redaction and cleanup run as Python scripts in `skills/lockin/scripts/`.

## Review skill

`/lowkey:review` reviews a change that already exists. It never changes code and never comments on a pull request.

| Argument | Reviewed diff |
|---|---|
| none | Commits of the current branch since the merge-base with the default branch. Uncommitted changes are not part of it. |
| `<n>` or `#<n>` | Pull request via `gh pr diff` or merge request via `glab mr diff`. Needs the CLI, otherwise the skill stops. |
| `<branch>` | Commits of the branch since the merge-base with the default branch. |
| `<base>..<head>` | The diff between both refs. |

The skill runs test commands only after your confirmation and only if the reviewed head is the checked-out `HEAD`. It redacts the test output, starts `lockin-reviewer-correctness` and `lockin-reviewer-risk` in parallel and reports the merged findings. The diff and test output live in `.lockin/review-<slug>/` during the review and get deleted at the end.

## TYPO3 upgrade skill

`/lowkey:typo3-upgrade` plans a Composer-based TYPO3 major upgrade. It orchestrates `lockin`: it writes the roadmap and hands each step to `lockin`, which implements and reviews it. The skill never changes project code, the database or Composer itself.

The skill accepts 11.5, 12.4 and 13.4 as source and 12, 13 or 14 as target. It refuses other sources. It runs one rung at a time and never skips a major version. Local intermediate versions never go live.

| Phase | What happens |
|---|---|
| Version gate | Reads `typo3/cms-core` from `composer.lock`. Refuses unsupported sources and invalid targets. Writes nothing. |
| MCP check | Looks for TYPO3/dev-companion. Stops once if it is missing and offers to install it or continue without it. |
| Preflight | Inventories extensions, blockers and logs read-only. Asks before each command with side effects or network access. |
| Roadmap | Writes the roadmap and one step brief per step. Waits for your explicit approval. |
| Handoff | Prints the `lockin` command for the next step. You run it. |
| Resume | After a `lockin` run, `--resume` records the outcome and proposes the next step. `--step <n>` repeats a handoff. |

The skill uses two folders. Both must be ignored by git, so add them to `.git/info/exclude`.

- `.lockin/upgrade/` holds the state, frozen copies of the references and the tools.
- `.typo3-upgrade/` in the DDEV app root holds the tools and the evidence.

The evidence never holds SQL dumps, because user tables contain personal data. Use DDEV snapshots for database state. Archive both folders at each rung exit, because `git clean -fdX` or a fresh clone deletes them.

The skill prints the handoff command for the next step, for example `/lowkey:lockin --keep Implement the step brief in .lockin/upgrade/steps/<nn>-<slug>.md`. Add `--lite` when the step uses lite mode. You run the command yourself, because `lockin` sets `disable-model-invocation`, so the skill cannot start it. Run `/lowkey:typo3-upgrade --resume` after `lockin` finishes.

Check commands are idempotent and may go into the `Verification` of a step. Commands that write the database, a snapshot or a baseline run in the main session of `lockin`, after your approval. See [`process.md`](plugins/lowkey/skills/typo3-upgrade/references/process.md) for the full rules.

The skill recommends the MCP server [TYPO3/dev-companion](https://github.com/TYPO3/dev-companion). Without it, the skill marks unconfirmed facts as `unverified`. The install writes `.mcp.json` and `.agents/skills` into the project.

The item format of the fix packs and the idea of per-object approval for destructive schema changes come from [dirnbauer/typo3-skills](https://github.com/dirnbauer/typo3-skills). All text in this plugin is original.

## State files

The skill keeps its state in `.lockin/<slug>/` at the repository root: `state.md` (brief, baseline, challenge log, approval, package status, findings), `plan.md` with the work package list, one file per work package under `packages/` and, during the review only, the diff and test output under `review/`. This lets you continue a run after a context compaction or in a new session with `--resume`. A recorded approval is never enough on resume. The skill asks you again before it continues implementing. `state.md` also records the mode and the run stats.

The skill offers to add `.lockin/` to `.git/info/exclude`. It never edits your `.gitignore`. Do not commit `.lockin/`.

A finished run cleans up after itself. The skill deletes `review/` at the end of Phase 5, because it holds raw test output. Test output gets redacted for tokens, passwords and keys before the reviewers read it. After the wrap-up summary, the skill deletes `.lockin/<slug>/`. `.lockin/` is not versioned, so the delete is final. Pass `--keep` to keep the state of a run, for example to debug it. An interrupted run always keeps its state for `--resume`.

## Subagents

| Agent | Model | Tools | Focus |
|---|---|---|---|
| `lockin-plan-challenger` | Opus | Read, Grep, Glob | Gaps, risks, better alternatives, unclear assumptions |
| `lockin-implementer` | Haiku, Sonnet per package | Read, Edit, Write, Bash, Grep, Glob | Exactly one work package, no architecture decisions |
| `lockin-reviewer-correctness` | Sonnet | Read, Grep, Glob | Correctness, plan adherence, tests, `CLAUDE.md` conventions |
| `lockin-reviewer-risk` | Sonnet | Read, Grep, Glob | Security, edge cases, performance, side effects |
| `lockin-reviewer` | Sonnet | Read, Grep, Glob | Correctness and risk in one pass, lite mode only |

The three reviewers have no Bash access, so they cannot change the code under review or run commands with side effects. The main session runs `git diff` and the test commands and writes the complete diff and test output to files that both reviewers read.

The implementer runs on Haiku by default. The main session switches to Sonnet for packages with logic across several files and for the second attempt on a failed package.

## Guard hook

The plugin ships a `PreToolUse` hook that enforces the hard rules of the subagents instead of trusting the prompt alone. It only acts on the five lockin agents. Other agents and the main session pass through unchanged.

| Rule | Agents | Blocks |
|---|---|---|
| No secrets | all five | Read, Edit, Write, Grep, Glob and Bash on `.env`, `.env.*`, `.envrc`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`, `.netrc`, `.pgpass`, `.npmrc`, `.git-credentials`, `auth.json`, `credentials` and `credentials.<ext>` except Markdown, plus the globs from `.lockin-guard.json`. Names match case-insensitively. `.env.example`, `.env.dist` and `.env.sample` stay readable. Bash checks also catch quoted names like `.e""nv`, globs like `.en?` and `<rev>:<path>` like `git show HEAD:.env`. |
| State stays untouched | implementer | Edit, Write and Bash on `.lockin/` and Edit and Write on `.lockin-guard.json`, in any letter case. Reading its own package file is allowed. |
| Writes stay in the repo | implementer | Edit and Write outside the repository root and under `.git/`. Symlinks get resolved first. |
| Allowlist | implementer | Every Bash command segment that is neither listed in `.lockin/active.json` nor strict read-only git. The main session writes the file before each delegation with the `Verification` commands of the package. Without the file only read-only git runs. A broken file blocks every Bash call. |
| No nested shells | implementer | `sh`, `bash`, `zsh`, `dash`, `ksh` and `fish` with `-c`, plus `eval`. Running a script file stays allowed. |
| Read-only git | implementer | Every git subcommand except `diff`, `status`, `log`, `show`, `ls-files`, `rev-parse`, `blame` and `grep`. Options that write, run programs or read outside the repository: `--output`, `--ext-diff`, `--textconv`, `--no-index`, `--contents`, `--untracked`, `--no-exclude-standard`, `--recurse-submodules` and `-O`, also abbreviated. Global options except `-C` inside the repository, `-c core.quotePath`, `-c color.ui`, `--no-pager`, `-P`, `--literal-pathspecs` and `--no-optional-locks`. Paths outside the repository, because `git diff <path> <path>` then acts as `--no-index`. The guard also blocks git in a directory that holds a planted `.git` or `HEAD` below the repository root. |
| No installs | implementer | Install, update and remove commands of `npm`, `pnpm`, `yarn`, `bun`, `composer`, `pip`, `pipx`, `uv`, `poetry`, `cargo`, `gem`, `bundle`, `go`, `conda`, `mamba`, `apt`, `dnf`, `yum`, `apk` and `brew`, also behind global options. `npx`, `npm exec` and `bunx` only with `--yes` or `--package`, plus `pnpm dlx` and `yarn dlx`. |
| Wrappers | implementer | The git, shell and install checks also apply behind `sudo`, `env`, `ddev`, `ddev exec`, `docker exec <container>`, `docker compose exec <service>` and `docker-compose exec <service>`. Unknown options of these wrappers block, because the guard cannot locate the command. |

### Allowlist rules

The guard splits a Bash command at `&&`, `||`, `;`, `|`, `&`, newlines, parentheses and command substitutions. Each segment must match a segment of an `active.json` entry, compared after shell-style tokenizing and with the same unquoted shell characters (`$`, backtick, `*`, `?`, `[`, `{`, `>`, `<`, leading `~`). Otherwise it must be strict read-only git: it starts with `git` itself and contains none of these characters unquoted. Write `Verification` commands as plain command lines:

- No `;`, `|`, `&` or parentheses inside quotes. Write `ddev exec vendor/bin/phpunit && ddev exec vendor/bin/phpstan` instead of `ddev exec "vendor/bin/phpunit && vendor/bin/phpstan"`.
- No git after `cd` in the same command line.
- Quote globs in git pathspecs: `git diff -- '*.py'`.

Allowed commands still pass all other checks, so an allowlisted `ddev exec composer require x` stays blocked. `active.json` lives at `.lockin/active.json`, outside the run folder, so run one lockin workflow per repository at a time.

### Project secrets

Add a `.lockin-guard.json` to the repository root to protect project-specific files:

```json
{
  "secret_globs": [
    "config/system/additional.php",
    "typo3conf/LocalConfiguration.php",
    "config/secrets/"
  ]
}
```

The file needs exactly the key `secret_globs` with a list of non-empty relative globs. A missing file means only the fixed list applies. A broken file blocks every call of the lockin agents until you fix it. Globs match the path relative to the repository root with `fnmatch`, so `*` also matches `/`. A glob without `/` matches the file name anywhere. A trailing `/` covers the whole directory, and a leading `**/` matches at any depth, including the root. Matching ignores case. The guard checks the path as written and the resolved path, so a symlinked secret stays protected.

### Limits

The hook and the scripts need `python3` 3.9 or newer, the hook also `sh`. It fails closed for the lockin agents. If `python3` is missing or the hook itself fails, the lockin agents get blocked with a message that names the cause. Bash commands longer than 16384 characters get blocked before the scan, so a slow check cannot run into the hook timeout. The guard matches command patterns, so it is a second line of defense and no sandbox. Known gaps:

- Allowlisted commands run code from the working tree. A test the implementer wrote can copy files or start processes. The diff check in Phase 4 and the review in Phase 5 remain the real barrier.
- Committed secret files stay readable through read-only git that does not name them, such as `git log -p`, `git show <commit>` or `git grep <pattern> <rev>`.
- Project globs with a wildcard in the file name miss `cd <dir> && cat <file>`. Brace expansion like `.{e,x}nv` hides a secret name.
- The wrapper detection covers `ddev` and `docker exec` or `docker compose exec`, not `docker run`, `docker compose run`, `podman`, `kubectl exec` or `ddev ssh`. The allowlist still blocks them unless they are listed.
- `npx` without `--yes` may fetch a missing package when it is allowlisted.

Native Windows without a POSIX shell is not supported, use WSL.

## Development

```text
python3 -m unittest discover tests      # guard hook and script tests
python3 scripts/check_metadata.py       # marketplace.json and plugin.json agree
claude plugin validate . --strict       # marketplace manifest
claude plugin validate plugins/lowkey --strict
```

CI runs the unit tests on Python 3.9 and 3.12, plus the metadata check and both validations, on every push and pull request. The eval suite in `plugins/lowkey/evals/` runs locally only, before a release. Every case makes real model calls against your Claude login, so it counts against your plan usage. Install `bubblewrap` and `socat` first, because the cases grant Bash and need the sandbox.

```text
cd plugins/lowkey
claude plugin eval . --tag smoke --scaffold --trust-plugin --no-publish --allow-tools Bash Edit Write Agent "Bash(cp:*)" "Bash(mkdir:*)" --max-cost-usd 2
```

The `typo3-upgrade` cases copy files with `cp` and `mkdir`, which the eval sandbox denies unless the two `Bash(...)` grants allow them. The `gate` tag holds the more expensive cases `gates-before-changes`, `plan-approval-gate` and `upgrade-roadmap-gate`. The first two start plugin agents, which the no-plugin baseline arm cannot run, so turn the baseline off:

```text
claude plugin eval . --tag gate --ablation none --scaffold --trust-plugin --no-publish --allow-tools Bash Edit Write Agent "Bash(cp:*)" "Bash(mkdir:*)" --max-cost-usd 10
```

## Cost

This workflow uses noticeably more tokens than a regular session. The plan challenger runs on Opus for up to three rounds, and every run starts several subagents for implementation and review. Use it for tasks where a wrong plan or an unreviewed change costs more than the extra tokens, not for small fixes. `--lite` saves two Opus rounds and one Sonnet reviewer per review round. `/lowkey:review` costs two Sonnet reviewer runs per call. `/lowkey:typo3-upgrade` itself runs no subagents. Every step costs one lockin run.

## License

[MIT](LICENSE)
