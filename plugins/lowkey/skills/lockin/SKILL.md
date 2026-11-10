---
name: lockin
description: Run a gated five-phase workflow for a large or high-stakes coding task given as an issue number or task description. Understand the task, write a plan and let an Opus subagent challenge it, wait for explicit user approval, implement in self-contained work packages through a dedicated subagent, then review the full diff for correctness and risk.
argument-hint: [issue-number or task]
disable-model-invocation: true
---

# Lock in

Task input: `$ARGUMENTS`

This workflow trades speed and tokens for reliability. Use it for tasks where a wrong plan or a sloppy change costs more than the extra review. Follow the phases in order. Do not skip a phase, and do not merge phases, because each phase produces the input for the next one.

The workflow uses four subagents from this plugin:

| Subagent | Role |
|---|---|
| `lowkey:lockin-plan-challenger` | Challenges the plan before any code changes |
| `lowkey:lockin-implementer` | Implements exactly one work package |
| `lowkey:lockin-reviewer-correctness` | Reviews the diff for correctness, plan adherence, tests and conventions |
| `lowkey:lockin-reviewer-risk` | Reviews the diff for security, edge cases, performance and side effects |

Subagents never see this conversation. They only know what you write into their prompt. Every handoff must therefore carry all context the subagent needs: goal, relevant file paths, constraints, conventions and the expected output format.

## Phase 1 - Understand

Goal of this phase: a shared, written understanding of the task before anyone thinks about solutions.

### 1.1 Resolve the input

- If `$ARGUMENTS` is empty, ask the user for an issue number or a task description and stop until you get one.
- If `$ARGUMENTS` is an issue reference (a plain number like `13` or `#13`), fetch the issue:
  1. Check which CLI is available with `command -v gh` and `command -v glab`.
  2. If the git remote points to GitHub and `gh` exists, run `gh issue view <number> --comments`.
  3. If the git remote points to GitLab and `glab` exists, run `glab issue view <number> --comments`.
  4. If neither works (CLI missing, not authenticated, issue not found), tell the user what failed and ask them to paste the issue text or describe the task. Do not guess the content of an issue.
- Otherwise treat `$ARGUMENTS` as the task description.

Read the issue comments too. They often contain decisions or constraints that the issue body lacks.

### 1.2 Read the project context

- Read the project `CLAUDE.md` (root and any nested ones in affected directories). Its conventions bind every later phase, including the subagents, so extract the rules that matter for this task.
- Locate and read all files the task affects. Read callers and tests of the code you plan to change, not only the code itself. Changes break at the boundaries.
- Identify how the project runs tests, linters and static analysis. You need these commands for the work packages.

### 1.3 Write the task brief

Present a short brief to the user:

- **Goal**: what is true after the task is done, in one or two sentences.
- **Scope**: what you will change.
- **Non-goals**: what you deliberately leave untouched. Name tempting adjacent work explicitly, because it prevents scope creep later.
- **Open questions**: anything ambiguous. If an open question changes the plan, ask the user now instead of assuming.

## Phase 2 - Plan and challenge

Goal of this phase: a plan that survived an independent critical review.

### 2.1 Write the plan

Write the plan yourself in the main session. You hold the full context, so the plan belongs here and not in a subagent. The plan contains:

- Approach and the main design decisions with reasons
- Files to create, change or delete, with the intended change per file
- Data, API or schema changes and their migration path
- Test strategy: which tests to add or adapt, which commands prove the change works
- Risks you already see and how the plan handles them

### 2.2 Challenge the plan

Delegate to `lowkey:lockin-plan-challenger`. Its prompt must contain:

- The task brief from Phase 1 (goal, scope, non-goals)
- The complete plan
- Relevant `CLAUDE.md` rules
- Paths of the affected files, so it can read the code itself
- The current round number and, from round 2 on, the objections of earlier rounds with your decision on each

### 2.3 Process the objections

For each objection decide:

- **Accept**: revise the plan.
- **Reject**: write down a concrete reason. "Not relevant" is no reason. Explain why the risk does not apply or why the cost outweighs the benefit.

Keep a running list of rejected objections with reasons. The user sees this list in Phase 3.

### 2.4 Loop rules

- Run at most 3 challenge rounds. Diminishing returns set in fast, and each round costs an Opus call.
- Stop as soon as a round returns no critical objections.
- If critical objections remain after round 3, do not loop further. Carry them into Phase 3 and let the user decide.

## Phase 3 - Approval

Goal of this phase: explicit user consent before any code changes.

Show the user:

1. The final plan
2. The rejected objections with your reasons
3. Unresolved critical objections, if any
4. The planned work packages as a short list (details follow in Phase 4)

Then stop and wait for explicit approval, such as "approved", "go" or "yes, implement it".

Do not change any project file before approval. The user owns architecture and scope decisions, and a change made before approval is a decision taken away from them. Silence, a follow-up question or a partial comment is not approval. If the user requests changes, revise the plan and show it again. Run another challenge round only if the changes are substantial.

## Phase 4 - Implementation

Goal of this phase: the approved plan, implemented in small verified steps.

### 4.1 Split the plan into work packages

Cut the plan into packages that each leave the project in a working state. Order them by dependency. Prefer more small packages over few large ones, because the implementer runs on a small model and works best with narrow, explicit instructions.

Every package must be fully self-contained. The implementer does not see the conversation, the plan discussion or other packages. Use this template:

```markdown
## Work package <n>/<total>: <short title>

### Context
<Why this change exists and how it fits into the overall goal. 2-5 sentences.>

### Files
- `<path>`: <create | modify | delete>

### Exact change
<Precise description per file: functions, signatures, behavior, error handling.
Include code snippets or exact names wherever ambiguity is possible.>

### Conventions
<Relevant CLAUDE.md rules and patterns from neighboring code, e.g. naming,
typing, error handling, test structure.>

### Acceptance criteria
- <Verifiable criterion>
- <Verifiable criterion>

### Test command
`<exact command, e.g. vendor/bin/phpunit tests/Unit/FooTest.php>`

### Out of scope
<What the implementer must not touch.>
```

If a package needs a decision you have not made, make it now and write it into the package. The implementer is not allowed to make architecture decisions.

### 4.2 Run the packages one by one

For each package:

1. Delegate it to `lowkey:lockin-implementer`.
2. Check the result before you start the next package:
   - Read the report.
   - Inspect the actual change with `git diff` on the affected files. Trust the diff, not the report.
   - Run the test command yourself if the report shows no clean run.
   - Compare the change against the acceptance criteria.
3. If the result is wrong or incomplete, write a corrected package that names the concrete problem and delegate again. After two failed attempts on the same package, implement it yourself or ask the user.
4. If the implementer reports `BLOCKED`, resolve the question. Ask the user when the answer changes scope or architecture. Then update the package and delegate again.

Run packages sequentially. Later packages build on earlier ones, and a defect caught early is cheaper than a defect spread across three packages.

If you discover during implementation that the approved plan does not work, stop. Explain the problem to the user and get approval for the changed plan before you continue.

## Phase 5 - Review

Goal of this phase: an independent review of the complete change.

### 5.1 Collect diff and test output

The reviewers have no Bash access. They only read files, so a review cannot change the code under review or trigger side effects. You run the commands for them:

1. Run `git diff <base>` against the state before Phase 4. Use plain `git diff` if all changes are uncommitted in the working tree.
2. Run `git status --porcelain` and collect new untracked files. `git diff` does not show them, so list their paths separately. The reviewers read them with the Read tool.
3. Run every test, lint and static analysis command from the work packages and the project `CLAUDE.md`. Capture the complete output, including the exit status of each command.

Pass diff and test output unshortened. The reviewers cannot rerun anything, so every line you cut is a line they cannot check. If a test command fails, still pass the full output and do not fix anything before the review.

### 5.2 Start both reviewers

Delegate to `lowkey:lockin-reviewer-correctness` and `lowkey:lockin-reviewer-risk` in parallel. Both prompts contain:

- The task brief and the final approved plan
- The complete diff
- Paths of new untracked files
- Each test command with its exit status and complete output
- Relevant `CLAUDE.md` rules

### 5.3 Process the findings

Handle every finding:

- **Fix**: implement the fix directly or as a new work package through `lowkey:lockin-implementer`. Verify it like any other package.
- **Reject**: write down a concrete reason.

Do not drop findings silently. A rejected finding with a reason helps the user, a missing finding hides a risk.

After substantial fixes, collect diff and test output again as in 5.1 and run the affected reviewer on the new state. Limit this to one extra review round, then report remaining findings as open.

## Wrap-up

Give the user a final summary:

- **Implemented**: what changed, per work package
- **Findings**: fixed findings, rejected findings with reasons, open findings
- **Tests**: which commands ran and their result. Report failures with output, never hide them.
- **Deviations**: any difference from the approved plan and why

Do not commit and do not push unless the user asks for it. The user reviews the change first and decides how it enters the history.
