# goetz-plugins

A Claude Code plugin marketplace by [Goetz](https://github.com/Goetz04).

## Plugins

### lowkey

Lock in on big, important tasks. The `lockin` skill runs a gated workflow: understand the task, write a plan and let an independent subagent challenge it, wait for your approval, implement in small self-contained work packages and review the full diff with two dedicated reviewers.

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
/lowkey:lockin [--keep] <issue-number or task>
/lowkey:lockin --resume [slug] [--keep]
```

Examples:

```text
/lowkey:lockin 13
/lowkey:lockin "Add rate limiting to the public search API"
/lowkey:lockin --keep "Migrate the session store to Redis"
/lowkey:lockin --resume 2026-11-10-rate-limiting
```

With an issue number, the skill reads the issue through `gh` (GitHub) or `glab` (GitLab) if available. Otherwise it treats the argument as the task description. If the task only asks for an analysis, the skill delivers the analysis and asks whether to continue with a change. The skill requires a git repository.

The skill only runs when you invoke it explicitly. Claude does not start it on its own.

## Workflow

| Phase | What happens |
|---|---|
| 1. Understand | Reads the issue or task, the project `CLAUDE.md` and all affected files. Records a baseline: HEAD, working tree status and check-mode test results. States goal, scope and non-goals and creates the state folder with `state.md`. |
| 2. Plan and challenge | The main session writes the plan, including the list of work packages with files and model. `lockin-plan-challenger` challenges it, for up to 3 rounds or until no critical objections remain. |
| 3. Approval | Shows the final plan, the rejected objections with reasons and the work packages with their model. Waits for your explicit approval and records it with a hash of the plan, which covers the package list. No code changes before that. |
| 4. Implementation | Records the git base and blocks if your uncommitted changes overlap the planned files. Expands the approved package list into self-contained work packages. Their verification may only use test commands you confirmed. `lockin-implementer` implements them one by one. The main session verifies each result before the next package starts. |
| 5. Review | The main session writes the diff and the redacted test output to `.lockin/<slug>/review/`. `lockin-reviewer-correctness` and `lockin-reviewer-risk` read these files and review the full change. Every finding gets fixed or rejected with a reason. The review files get deleted at the end of the phase. |
| Wrap-up | Summary of implemented changes, open findings and test runs, plus a commit message, a PR description draft and the exact paths to stage. Deletes `.lockin/<slug>/` unless you passed `--keep`. No commit and no push unless you ask. |

## State files

The skill keeps its state in `.lockin/<slug>/` at the repository root: `state.md` (brief, baseline, challenge log, approval, package status, findings), `plan.md` with the work package list, one file per work package under `packages/` and, during the review only, the diff and test output under `review/`. This lets you continue a run after a context compaction or in a new session with `--resume`. A recorded approval is never enough on resume. The skill asks you again before it continues implementing.

The skill offers to add `.lockin/` to `.git/info/exclude`. It never edits your `.gitignore`. Do not commit `.lockin/`.

A finished run cleans up after itself. The skill deletes `review/` at the end of Phase 5, because it holds raw test output. Test output gets redacted for tokens, passwords and keys before the reviewers read it. After the wrap-up summary, the skill deletes `.lockin/<slug>/`. `.lockin/` is not versioned, so the delete is final. Pass `--keep` to keep the state of a run, for example to debug it. An interrupted run always keeps its state for `--resume`.

## Subagents

| Agent | Model | Tools | Focus |
|---|---|---|---|
| `lockin-plan-challenger` | Opus | Read, Grep, Glob | Gaps, risks, better alternatives, unclear assumptions |
| `lockin-implementer` | Haiku, Sonnet per package | Read, Edit, Write, Bash, Grep, Glob | Exactly one work package, no architecture decisions |
| `lockin-reviewer-correctness` | Sonnet | Read, Grep, Glob | Correctness, plan adherence, tests, `CLAUDE.md` conventions |
| `lockin-reviewer-risk` | Sonnet | Read, Grep, Glob | Security, edge cases, performance, side effects |

The reviewers have no Bash access, so they cannot change the code under review or run commands with side effects. The main session runs `git diff` and the test commands and writes the complete diff and test output to files that both reviewers read.

The implementer runs on Haiku by default. The main session switches to Sonnet for packages with logic across several files and for the second attempt on a failed package.

## Guard hook

The plugin ships a `PreToolUse` hook that enforces the hard rules of the subagents instead of trusting the prompt alone. It only acts on the four lockin agents. Other agents and the main session pass through unchanged.

| Rule | Agents | Blocks |
|---|---|---|
| No secrets | all four | Read, Edit, Write, Grep and Bash on `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`, `.netrc`, `.pgpass`, `auth.json`, `credentials` and `credentials.<ext>` except Markdown. `.env.example`, `.env.dist` and `.env.sample` stay readable. |
| State stays untouched | implementer | Edit, Write and Bash on `.lockin/`. Reading its own package file is allowed. |
| Read-only git | implementer | Every git subcommand except `diff`, `status`, `log`, `show`, `ls-files`, `rev-parse`, `blame` and `grep` |
| No installs | implementer | `npm`, `pnpm`, `yarn`, `composer`, `pip`, `uv`, `apt` and `brew` install commands |

The hook needs `python3` and `sh`. It fails closed for the lockin agents. If `python3` is missing or the hook itself fails, the lockin agents get blocked with a message that names the cause. The guard matches command patterns, so it is a second line of defense and no sandbox. Native Windows without a POSIX shell is not supported, use WSL.

## Development

```text
python3 -m unittest discover tests      # guard hook tests
python3 scripts/check_metadata.py       # marketplace.json and plugin.json agree
claude plugin validate . --strict       # marketplace manifest
claude plugin validate plugins/lowkey --strict
```

CI runs these checks on every push and pull request. The eval suite in `plugins/lowkey/evals/` runs real model calls and costs money, so it runs only on demand through the `Evals` workflow, which needs the repository secret `ANTHROPIC_API_KEY`. To run it locally, install `bubblewrap` and `socat` first, because the cases grant Bash and need the sandbox:

```text
cd plugins/lowkey
claude plugin eval . --tag smoke --scaffold --trust-plugin --no-publish --allow-tools Bash Edit Write Agent --max-cost-usd 2
```

## Cost

This workflow uses noticeably more tokens than a regular session. The plan challenger runs on Opus for up to three rounds, and every run starts several subagents for implementation and review. Use it for tasks where a wrong plan or an unreviewed change costs more than the extra tokens, not for small fixes.

## License

[MIT](LICENSE)
