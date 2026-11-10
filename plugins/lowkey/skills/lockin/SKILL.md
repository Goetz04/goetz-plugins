---
name: lockin
description: Run a gated five-phase workflow for a large or high-stakes coding task given as an issue number or task description. Understand the task, write a plan and let an Opus subagent challenge it, wait for explicit user approval, implement in self-contained work packages through a dedicated subagent, then review the full diff for correctness and risk.
argument-hint: "[--keep] [issue-number | task] | --resume [slug] [--keep]"
disable-model-invocation: true
---

# Lock in

Task input: `$ARGUMENTS`

This workflow trades speed and tokens for reliability. Use it for tasks where a wrong plan or a sloppy change costs more than the extra review. Follow the phases in order. Do not skip a phase, and do not merge phases, because each phase produces the input for the next one. The only exception is the analysis-only exit in 1.1.

The workflow uses four subagents from this plugin:

| Subagent | Role |
|---|---|
| `lowkey:lockin-plan-challenger` | Challenges the plan before any code changes |
| `lowkey:lockin-implementer` | Implements exactly one work package |
| `lowkey:lockin-reviewer-correctness` | Reviews the diff for correctness, plan adherence, tests and conventions |
| `lowkey:lockin-reviewer-risk` | Reviews the diff for security, edge cases, performance and side effects |

Subagents never see this conversation. They only know what you write into their prompt. Every handoff must therefore carry all context the subagent needs: goal, relevant file paths, constraints, conventions and the expected output format.

## State files

The workflow keeps its state in `<repo>/.lockin/<slug>/`, where `<repo>` is the output of `git rev-parse --show-toplevel`. The state survives context compaction and lets the user continue a run with `--resume`.

| File | Content |
|---|---|
| `state.md` | Task input, `keep_state`, brief, baseline, challenge log, approval record, work package list, review findings, `current_phase`, tree fingerprint |
| `plan.md` | The plan text, including the work package list |
| `packages/<n>.md` | The full text of work package `<n>` |
| `review/` | Diff, new file list and test output for the current review round. Transient, see 5.1 |

- Only the main session writes these files. Update `state.md` at the end of every phase, before you delegate a work package and after you verified it.
- `current_phase` is `1` to `5`, `wrap-up` or `done`. Each package in `state.md` has number, title, model and status: `pending`, `in_progress`, `done`, `failed` or `blocked`.
- After every write to `state.md`, record the tree fingerprint: a status snapshot as defined below. `<base>` is the base from Phase 4, or the baseline HEAD before that. For a repo without commits use the empty tree from `git hash-object -t tree /dev/null`.
- Store summaries, never raw output that contains credentials, tokens or environment dumps. The only exception is `review/`, under the rules in 5.1.
- `.lockin/` is the only exception to the rule that no project file changes before approval.
- The wrap-up deletes `.lockin/<slug>/` at the end of a finished run, unless `keep_state` is `true`. An interrupted or stopped run keeps its state for `--resume`.

Git rules for the whole workflow. Run all git commands from `<repo>`.

- A **status snapshot** consists of three parts:
  1. The output of `git -c core.quotePath=false status --porcelain -uall` without lines under `.lockin/`.
  2. The hash from `git diff <base> | git hash-object --stdin`. It catches changes to files that were already dirty.
  3. The hash from `git ls-files --others --exclude-standard -z -- ':(exclude).lockin' | xargs -0 -r git hash-object -- | git hash-object --stdin`. It catches content changes to untracked files, which the first two parts miss.
- Build path lists only from `git -c core.quotePath=false diff <ref> --name-only --no-renames` for changed files and `git -c core.quotePath=false ls-files --others --exclude-standard` for untracked files, never from porcelain lines. `--no-renames` lists both paths of a rename. Git still wraps a path in double quotes if it contains a quote or control character. Unquote such paths before you use them.
- Exclude a path from a diff with `':(exclude,literal)<path>'`, so spaces and characters like `[` or `*` match literally. Escape single quotes in a path for the shell. After you build the excludes, run the diff with `--name-only` and stop if a pre-existing path still appears.
- Always exclude `':(exclude).lockin'` from every diff you pass on.
- Files inside a git submodule are out of scope for a run in the parent repo. If the plan needs them, tell the user to start a separate run inside the submodule.

### Resume

If the task input starts with the word `--resume`, read `resume.md` in the same directory as this file and follow it. It replaces the rest of 1.1 for this run.

## Phase 1 - Understand

Goal of this phase: a shared, written understanding of the task before anyone thinks about solutions.

### 1.1 Resolve the input

- Run `git rev-parse --show-toplevel`. If it fails, tell the user that lockin needs a git repository, because base, diff, review and resume depend on it. Suggest `git init` with an initial commit and stop.
- If `$ARGUMENTS` is empty, ask the user for an issue number or a task description and stop until you get one.
- If `$ARGUMENTS` starts with `--resume`, follow "Resume" above and skip the rest of 1.1, including the analysis-only check.
- If `$ARGUMENTS` starts with `--keep`, remove the flag from the task input and set `keep_state: true` when you create `state.md` in 1.4. The run then keeps `.lockin/<slug>/` after the wrap-up. Without the flag, `keep_state` is `false`.
- If `$ARGUMENTS` is an issue reference (a plain number like `13` or `#13`), fetch the issue:
  1. Check which CLI is available with `command -v gh` and `command -v glab`.
  2. If the git remote points to GitHub and `gh` exists, run `gh issue view <number> --comments`.
  3. If the git remote points to GitLab and `glab` exists, run `glab issue view <number> --comments`.
  4. If neither works (CLI missing, not authenticated, issue not found), tell the user what failed and ask them to paste the issue text or describe the task. Do not guess the content of an issue.
- Otherwise treat `$ARGUMENTS` as the task description.

Read the issue comments too. They often contain decisions or constraints that the issue body lacks.

Then check whether the task asks for a change. If it only asks for analysis, explanation or evaluation, take the analysis-only exit: read the relevant files as in 1.2, deliver the analysis with a proposed scope and ask whether to continue with a change. If the user agrees, continue with 1.2 and use the agreed scope as the task. Otherwise end the workflow. This exit runs no baseline and creates no state.

### 1.2 Read the project context

- Never read `.env` files, credential files or private keys. This rule binds you and every subagent.
- Read the project `CLAUDE.md` (root and any nested ones in affected directories). Its conventions bind every later phase, including the subagents, so extract the rules that matter for this task.
- Locate and read all files the task affects. Read callers and tests of the code you plan to change, not only the code itself. Changes break at the boundaries.
- Identify how the project runs tests, linters and static analysis. You need these commands for the baseline and the work packages.

### 1.3 Record the baseline

The baseline separates problems the change causes from problems that existed before.

1. Record HEAD with `git rev-parse HEAD`, or `unborn` if the repo has no commit yet.
2. Record a status snapshot. If it lists changes, tell the user now. Phase 4 decides how to handle them.
3. Show the user the list of test, lint and static analysis commands you plan to run, and wait for an explicit confirmation. Run only the confirmed commands. Use check variants such as `--dry-run` or `--check` where they exist, never `--fix` and never snapshot updates. Mark every command that may touch a database, an external service or files outside the repo. If you are unsure, mark it.
4. Record command, exit status and a short failure summary per command. Pre-existing failures belong in the brief.
5. Record a second status snapshot. If tracked files or the diff hash changed, stop and tell the user which command changed which file. Do not revert anything. New untracked files from the run are fine, because the second snapshot covers them.
6. If the project has no automated tests, record that. The work packages then use manual verification.

### 1.4 Write the task brief

Present a short brief to the user:

- **Goal**: what is true after the task is done, in one or two sentences.
- **Scope**: what you will change.
- **Non-goals**: what you deliberately leave untouched. Name tempting adjacent work explicitly, because it prevents scope creep later.
- **Baseline**: pre-existing changes and failing checks, if any.
- **Open questions**: anything ambiguous. If an open question changes the plan, ask the user now instead of assuming.

Then create the state:

1. Pick the slug `YYYY-MM-DD-<short-kebab-title>`, or `issue-<n>` for an issue. If `.lockin/<slug>/` already exists, ask whether to resume that run or start fresh with a numeric suffix such as `-2`.
2. Create `.lockin/<slug>/` and write `state.md` with task input, `keep_state`, brief and baseline.
3. Run `git check-ignore -q .lockin/`. If `.lockin/` is not ignored, ask once whether to append `/.lockin/` to the file that `git rev-parse --git-path info/exclude` names. That file is local and not versioned. Add a newline first if the file does not end with one, so you do not corrupt the last rule. Run `git check-ignore -q .lockin/` again and warn if it still fails. Never edit `.gitignore`. If the user declines, warn that `.lockin/` must never be committed.

## Phase 2 - Plan and challenge

Goal of this phase: a plan that survived an independent critical review.

### 2.1 Write the plan

Write the plan yourself in the main session. You hold the full context, so the plan belongs here and not in a subagent. Save it to `.lockin/<slug>/plan.md`. The plan contains:

- Approach and the main design decisions with reasons
- Files to create, change or delete, with the intended change per file
- Data, API or schema changes and their migration path
- Test strategy: which tests to add or adapt, which commands prove the change works. Without automated tests, name the manual checks.
- Risks you already see and how the plan handles them
- Work packages: a numbered list with title, files and model per package, ordered by dependency. Cut them by the rules in 4.1. The approval in Phase 3 covers this list, because it is part of `plan.md`.

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

Keep a running list of rejected objections with reasons. The user sees this list in Phase 3. After each round, record every objection with your decision in the challenge log in `state.md` and update `plan.md`.

### 2.4 Loop rules

- Run at most 3 challenge rounds. Diminishing returns set in fast, and each round costs an Opus call.
- Stop as soon as the verdict line of a round reads `NO CRITICAL OBJECTIONS`. Treat `CRITICAL OBJECTIONS: 0` the same way.
- If critical objections remain after round 3, do not loop further. Carry them into Phase 3 and let the user decide.

## Phase 3 - Approval

Goal of this phase: explicit user consent before any code changes.

Show the user:

1. The final plan
2. The rejected objections with your reasons
3. Unresolved critical objections, if any
4. The work package list from `plan.md` with the model per package (details follow in Phase 4)

Then stop and wait for explicit approval, such as "approved", "go" or "yes, implement it".

Do not change any project file before approval. The user owns architecture and scope decisions, and a change made before approval is a decision taken away from them. Silence, a follow-up question or a partial comment is not approval. If the user requests changes, revise the plan, update `plan.md` and show it again. Run another challenge round only if the changes are substantial.

After the approval, check that `plan.md` holds exactly the approved plan. Then write the approval record to `state.md`: the user's words, the date and the hash from `git hash-object .lockin/<slug>/plan.md`.

## Phase 4 - Implementation

Goal of this phase: the approved plan, implemented in small verified steps.

### 4.1 Expand the work packages

Expand each entry of the approved work package list in `plan.md` into a full package. Keep number, title, files and model as approved. If a package needs another file, another model or a different cut, this is a plan change. Handle it as described at the end of 4.2.

Rules for the cut, which 2.1 applies when it writes the list: each package leaves the project in a working state. Order them by dependency. Prefer more small packages over few large ones, because the implementer runs on Haiku by default and works best with narrow, explicit instructions.

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

### Verification
`<exact command, e.g. vendor/bin/phpunit tests/Unit/FooTest.php>`
or: No automated tests. Manual check: <exact steps>

### Out of scope
<What the implementer must not touch.>
Pre-existing user changes, never modify: <paths or "none">
```

If a package needs a decision you have not made, make it now and write it into the package. The implementer is not allowed to make architecture decisions.

The `Verification` field may only contain commands that the user confirmed in 1.3 or approved with the plan. The implementer runs these commands with Bash, so an unconfirmed command there bypasses the confirmation. If a package needs a new command, ask the user first and record the confirmation in `state.md`.

Pick the model per package. The default is Haiku from the agent definition. Pass `model: "sonnet"` to the Agent tool when a package changes logic across more than one file or needs non-trivial algorithms or type reasoning. Do not use Opus for implementation.

### 4.2 Set the base and run the packages

Before the first package:

1. Record a fresh status snapshot, because the tree may have changed since Phase 1.
2. If a changed file is also a package file, stop. Explain that the change cannot be reviewed in isolation and ask the user to commit or stash that file. Never stash or commit yourself.
3. List all other changed and untracked files as pre-existing user changes. Build the list as described in the git rules above. Exclude these paths from every diff, for example `git diff <base> -- . ':(exclude).lockin' ':(exclude,literal)<path>'`.
4. Record the base with `git rev-parse HEAD`, or the empty tree from `git hash-object -t tree /dev/null` for a repo without commits. Write the base, the pre-existing list and this snapshot to `state.md` as the final baseline.
5. Fill the pre-existing list into every package and write each package to `.lockin/<slug>/packages/<n>.md`.

For each package:

1. Set its status to `in_progress` in `state.md`. Then delegate it to `lowkey:lockin-implementer` with the chosen model. The prompt names the absolute path of `.lockin/<slug>/packages/<n>.md` and tells the implementer to read it first. Do not repeat the package text in the prompt. Add only what the file lacks, such as the answer to an earlier `BLOCKED` question.
2. Check the result before you start the next package:
   - Read the report.
   - Inspect the actual change with `git diff <base>` on the affected files. Trust the diff, not the report.
   - Run the verification yourself if the report shows no clean run. Run only commands the user confirmed in 1.3 or approved with the plan. Take a status snapshot afterwards and stop if a command changed files.
   - Compare the change against the acceptance criteria.
3. If the result is correct, set the status to `done`.
4. If the result is wrong or incomplete, write a corrected package to `packages/<n>.md` that names the concrete problem and delegate again. Attempt 1 runs on the planned model, attempt 2 on Sonnet. After that, implement it yourself or ask the user. Set the status to `failed` if the user stops the package.
5. If the implementer reports `BLOCKED`, set the status to `blocked` and resolve the question. Ask the user when the answer changes scope or architecture. Then update `packages/<n>.md` and delegate again.

Run packages sequentially. Later packages build on earlier ones, and a defect caught early is cheaper than a defect spread across three packages.

If you discover during implementation that the approved plan does not work, stop. Explain the problem to the user and get approval for the changed plan before you continue. Then update `plan.md` and write the new approval with the new hash to `state.md`.

## Phase 5 - Review

Goal of this phase: an independent review of the complete change.

### 5.1 Collect diff and test output

The reviewers have no Bash access. They only read files, so a review cannot change the code under review or trigger side effects. You run the commands for them and write the results to `.lockin/<slug>/review/`. The reviewers read these files with the Read tool, so diff and output do not pass through your context or the prompts.

1. Delete `review/` if it exists, then create it with `mkdir -m 700 .lockin/<slug>/review`. Each review round starts from a fresh folder.
2. Write the diff to `review/diff.patch` with `git diff <base> -- . ':(exclude).lockin' > .lockin/<slug>/review/diff.patch`, plus one more `':(exclude,literal)<path>'` per pre-existing path. The diff contains staged and unstaged changes.
3. List the untracked files as described in the git rules. New files are the untracked paths missing from the pre-existing list of 4.2. `git diff` does not show them, so write their paths to `review/new-files.txt`, one per line. The reviewers read them with the Read tool.
4. Run every test, lint and static analysis command from the work packages and the project `CLAUDE.md` that the user confirmed in 1.3 or approved with the plan. Use check variants as in 1.3. Write the complete output of command `<n>` to `review/test-<n>.txt`, with the command as the first line and `exit: <status>` as the last line. Take a status snapshot afterwards and stop if a command changed files. Without automated tests, run the manual checks from the packages and write what you checked to `review/manual-checks.md`.
5. Redact the test files before any reviewer starts. Replace values after keys like `password`, `secret`, `token`, `api_key`, `authorization` and `bearer`, private key blocks and environment dumps with `[REDACTED]`. Then search the files for these patterns again with `grep -inE` and repeat until nothing is left. Do not redact `diff.patch`. A secret in the diff is a finding for the risk reviewer, and it already sits in the working tree.

Keep the files unshortened. The reviewers cannot rerun anything, so every line you cut is a line they cannot check. If a test command fails, still keep the full output and do not fix anything before the review.

`review/` is the only place where the workflow stores raw output. It exists only during Phase 5. See 5.3 for its deletion.

### 5.2 Start both reviewers

Delegate to `lowkey:lockin-reviewer-correctness` and `lowkey:lockin-reviewer-risk` in parallel. Both prompts contain:

- The task brief and the final approved plan
- The absolute paths of `review/diff.patch` and `review/new-files.txt`, with the instruction to read both completely
- The absolute paths of all `review/test-<n>.txt` files with their exit status, or the statement that the project has no automated tests with the path of `review/manual-checks.md`
- The baseline test results from Phase 1
- The list of pre-existing user changes, marked as user work that is not under review
- Relevant `CLAUDE.md` rules

### 5.3 Process the findings

Handle every finding:

- **Fix**: implement the fix directly or as a new work package through `lowkey:lockin-implementer`. Verify it like any other package.
- **Reject**: write down a concrete reason.

Do not drop findings silently. A rejected finding with a reason helps the user, a missing finding hides a risk. Record every finding with your decision in `state.md`.

After substantial fixes, collect diff and test output again as in 5.1 and run the affected reviewer on the new state. Limit this to one extra review round, then report remaining findings as open.

When the last review round is processed, delete `.lockin/<slug>/review/` with `rm -rf --`, even if `keep_state` is `true`. Before the delete, check that the slug is not empty and contains neither `/` nor `..`, and that the target is exactly `<repo>/.lockin/<slug>/review`. Before the delete, record the result per test command in `state.md`, plus the redacted excerpt of every failure. The wrap-up needs both.

## Wrap-up

Set `current_phase` to `wrap-up` in `state.md`. Then give the user a final summary:

- **Implemented**: what changed, per work package
- **Findings**: fixed findings, rejected findings with reasons, open findings
- **Tests**: which commands ran and their result, from `state.md`. Report failures with their recorded excerpt, never hide them.
- **Deviations**: any difference from the approved plan and why
- **Commit proposal**: a commit message in the style of `git log --oneline -10`, or in Conventional Commits style if the log is empty. Add a PR description draft with summary, changes per package, test results and open findings. List the exact paths to stage: the output of `git -c core.quotePath=false diff <base> --name-only --no-renames` with the same excludes as in 5.1, plus the new files, listed again as in step 3 of 5.1.

Set `current_phase` to `done` in `state.md`. Then clean up:

- If `keep_state` is `true`, keep `.lockin/<slug>/` and tell the user that they may delete it.
- Otherwise delete the run folder. Check first that the complete summary above stands in the chat, that the slug is not empty and contains neither `/` nor `..`, and that the target is exactly `<repo>/.lockin/<slug>`. Then run `rm -rf -- "<repo>/.lockin/<slug>"`. If `.lockin/` is empty afterwards, remove it with `rmdir`. Tell the user that the state is gone, because `.lockin/` is not versioned and the delete cannot be undone.
- If the delete fails, report the error and the path. Do not retry with other commands.

Do not commit and do not push unless the user asks for it. The user reviews the change first and decides how it enters the history. If the user asks for a commit, show `git status` and `git diff --cached --name-only` first. If the index already holds paths outside the list, ask the user to unstage them or to confirm them. Stage only the listed paths.
