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
/lowkey:lockin <issue-number or task>
/lowkey:lockin --resume [slug]
```

Examples:

```text
/lowkey:lockin 13
/lowkey:lockin "Add rate limiting to the public search API"
/lowkey:lockin --resume 2026-11-10-rate-limiting
```

With an issue number, the skill reads the issue through `gh` (GitHub) or `glab` (GitLab) if available. Otherwise it treats the argument as the task description. If the task only asks for an analysis, the skill delivers the analysis and asks whether to continue with a change. The skill requires a git repository.

The skill only runs when you invoke it explicitly. Claude does not start it on its own.

## Workflow

| Phase | What happens |
|---|---|
| 1. Understand | Reads the issue or task, the project `CLAUDE.md` and all affected files. Records a baseline: HEAD, working tree status and check-mode test results. States goal, scope and non-goals and creates the state folder with `state.md`. |
| 2. Plan and challenge | The main session writes the plan. `lockin-plan-challenger` challenges it, for up to 3 rounds or until no critical objections remain. |
| 3. Approval | Shows the final plan, the rejected objections with reasons and the work packages with their model. Waits for your explicit approval and records it with a hash of the plan. No code changes before that. |
| 4. Implementation | Records the git base and blocks if your uncommitted changes overlap the planned files. Splits the plan into self-contained work packages. `lockin-implementer` implements them one by one. The main session verifies each result before the next package starts. |
| 5. Review | The main session runs `git diff` and all test commands. `lockin-reviewer-correctness` and `lockin-reviewer-risk` review the full diff and test output. Every finding gets fixed or rejected with a reason. |
| Wrap-up | Summary of implemented changes, open findings and test runs, plus a commit message, a PR description draft and the exact paths to stage. No commit and no push unless you ask. |

## State files

The skill keeps its state in `.lockin/<slug>/` at the repository root: `state.md` (brief, baseline, challenge log, approval, package status, findings), `plan.md` and one file per work package under `packages/`. This lets you continue a run after a context compaction or in a new session with `--resume`. A recorded approval is never enough on resume. The skill asks you again before it continues implementing.

The skill offers to add `.lockin/` to `.git/info/exclude`. It never edits your `.gitignore`. Do not commit `.lockin/`. Delete the folder when the run is done.

## Subagents

| Agent | Model | Tools | Focus |
|---|---|---|---|
| `lockin-plan-challenger` | Opus | Read, Grep, Glob | Gaps, risks, better alternatives, unclear assumptions |
| `lockin-implementer` | Haiku, Sonnet per package | Read, Edit, Write, Bash, Grep, Glob | Exactly one work package, no architecture decisions |
| `lockin-reviewer-correctness` | Sonnet | Read, Grep, Glob | Correctness, plan adherence, tests, `CLAUDE.md` conventions |
| `lockin-reviewer-risk` | Sonnet | Read, Grep, Glob | Security, edge cases, performance, side effects |

The reviewers have no Bash access, so they cannot change the code under review or run commands with side effects. The main session runs `git diff` and the test commands and passes the complete diff and test output to both reviewers.

The implementer runs on Haiku by default. The main session switches to Sonnet for packages with logic across several files and for the second attempt on a failed package.

## Cost

This workflow uses noticeably more tokens than a regular session. The plan challenger runs on Opus for up to three rounds, and every run starts several subagents for implementation and review. Use it for tasks where a wrong plan or an unreviewed change costs more than the extra tokens, not for small fixes.

## License

[MIT](LICENSE)
