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

## Usage

```text
/lowkey:lockin <issue-number or task>
```

Examples:

```text
/lowkey:lockin 13
/lowkey:lockin "Add rate limiting to the public search API"
```

With an issue number, the skill reads the issue through `gh` (GitHub) or `glab` (GitLab) if available. Otherwise it treats the argument as the task description.

The skill only runs when you invoke it explicitly. Claude does not start it on its own.

## Workflow

| Phase | What happens |
|---|---|
| 1. Understand | Reads the issue or task, the project `CLAUDE.md` and all affected files. States goal, scope and non-goals. |
| 2. Plan and challenge | The main session writes the plan. `lockin-plan-challenger` challenges it, for up to 3 rounds or until no critical objections remain. |
| 3. Approval | Shows the final plan and the rejected objections with reasons. Waits for your explicit approval. No code changes before that. |
| 4. Implementation | Splits the plan into self-contained work packages. `lockin-implementer` implements them one by one. The main session verifies each result before the next package starts. |
| 5. Review | The main session runs `git diff` and all test commands. `lockin-reviewer-correctness` and `lockin-reviewer-risk` review the full diff and test output. Every finding gets fixed or rejected with a reason. |
| Wrap-up | Summary of implemented changes, open findings and test runs. No commit and no push unless you ask. |

## Subagents

| Agent | Model | Tools | Focus |
|---|---|---|---|
| `lockin-plan-challenger` | Opus | Read, Grep, Glob | Gaps, risks, better alternatives, unclear assumptions |
| `lockin-implementer` | Haiku | Read, Edit, Write, Bash, Grep, Glob | Exactly one work package, no architecture decisions |
| `lockin-reviewer-correctness` | Sonnet | Read, Grep, Glob | Correctness, plan adherence, tests, `CLAUDE.md` conventions |
| `lockin-reviewer-risk` | Sonnet | Read, Grep, Glob | Security, edge cases, performance, side effects |

The reviewers have no Bash access, so they cannot change the code under review or run commands with side effects. The main session runs `git diff` and the test commands and passes the complete diff and test output to both reviewers.

## Cost

This workflow uses noticeably more tokens than a regular session. The plan challenger runs on Opus for up to three rounds, and every run starts several subagents for implementation and review. Use it for tasks where a wrong plan or an unreviewed change costs more than the extra tokens, not for small fixes.

## License

[MIT](LICENSE)
