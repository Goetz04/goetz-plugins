---
name: lockin
description: Run a gated five-phase workflow for a large or high-stakes coding task given as an issue number or task description. Understand the task, write a plan and let an Opus subagent challenge it, wait for explicit user approval, implement in self-contained work packages through a dedicated subagent, then review the full diff for correctness and risk.
argument-hint: "[--keep] [--lite] [issue-number | task] | --resume [slug] [--keep]"
disable-model-invocation: true
---

# Lock in

Task input: `$ARGUMENTS`

This workflow trades speed and tokens for reliability. Use it for tasks where a wrong plan or a sloppy change costs more than the extra review. Follow the phases in order. Do not skip a phase, and do not merge phases, because each phase produces the input for the next one. The only exception is the analysis-only exit in 1.1.

The workflow uses these subagents from this plugin. A full run uses the two specialized reviewers, a lite run uses the combined reviewer instead:

| Subagent | Role |
|---|---|
| `lowkey:lockin-plan-challenger` | Challenges the plan before any code changes |
| `lowkey:lockin-implementer` | Implements exactly one work package |
| `lowkey:lockin-reviewer-correctness` | Reviews the diff for correctness, plan adherence, tests and conventions |
| `lowkey:lockin-reviewer-risk` | Reviews the diff for security, edge cases, performance and side effects |
| `lowkey:lockin-reviewer` | Reviews the diff for correctness and risk in one pass. Lite mode only |

Subagents never see this conversation. They only know what you write into their prompt. Every handoff must therefore carry all context the subagent needs: goal, relevant file paths, constraints, conventions and the expected output format.

A run has a mode. `full` is the default. `lite` runs one challenge round instead of three and the combined reviewer instead of the two specialized reviewers. Every gate stays in both modes: confirmation of the test commands, approval of the plan and the review.

The workflow spans three files in the directory of this file: this file holds the overview, the state files, the git rules and Phases 1 to 3. `phase-4.md` holds Phase 4. `phase-5.md` holds Phase 5 and the wrap-up.

## Scripts

The deterministic steps run as Python scripts in `${CLAUDE_SKILL_DIR}/scripts`. All workflow files call this directory `<scripts>`. Run every script with `python3` from `<repo>` and quote every path argument, for example `python3 "<scripts>/snapshot.py" --repo "<repo>" --exclude 'src/my file.php'`. Escape single quotes in paths for the shell. Pass every value that comes from outside, such as a test command, a ref or a commit subject, in single quotes and replace each `'` inside it with `'\''`. The scripts need Python 3.9 or newer, like the guard hook. Each script prints a JSON result on stdout.

| Script | Purpose | Exit codes |
|---|---|---|
| `snapshot.py [--base <ref>] [--exclude <path>]... [--paths]` | Status snapshot, see the git rules | 0 ok, 2 error |
| `collect_review.py prepare` and `run` | Review folder, diff, new files, one test command per call | 0 ok, 2 error, 3 pre-existing path still in the diff, 4 a command changed files, 5 diff file missing or empty |
| `redact.py <file>...` | Redacts test output in place | 0 clean, 1 hits left, 2 error |
| `cleanup.py --slug <slug> --target review\|run` | Deletes `review/` or the run folder after checking slug and path | 0 ok, 2 refused or failed |

On exit 2 of any script, show the stderr message to the user and stop the step. Do not retry with another command.

Before each step of Phase 4 or 5, make sure you have read the matching phase file in this session. After a context compaction, read it again. If `<scripts>` is no longer known, take it from `scripts_dir` in `state.md`.

## State files

The workflow keeps its state in `<repo>/.lockin/<slug>/`, where `<repo>` is the output of `git rev-parse --show-toplevel`. The state survives context compaction and lets the user continue a run with `--resume`.

| File | Content |
|---|---|
| `state.md` | Task input, `keep_state`, `mode`, `scripts_dir`, brief, baseline, challenge log, approval record, work package list, review findings, run stats, `issue`, `issue_cli`, `issue_comment`, `draft_pr`, `current_phase`, tree fingerprint |
| `plan.md` | The plan text, including the work package list |
| `packages/<n>.md` | The full text of work package `<n>` |
| `review/` | Diff, new file list and test output for the current review round. Transient, see 5.1 in `phase-5.md` |
| `../active.json` | `<repo>/.lockin/active.json`, outside the run folder: the Bash allowlist of the package that runs right now. One per repository, so run one lockin workflow per repository at a time. See 4.2 in `phase-4.md` |

- Only the main session writes these files. Update `state.md` at the end of every phase, before you delegate a work package and after you verified it.
- `current_phase` is `1` to `5`, `wrap-up` or `done`. Each package in `state.md` has number, title, model and status: `pending`, `in_progress`, `done`, `failed` or `blocked`.
- `mode` is `full` or `lite`. A `state.md` without `mode` counts as `full`.
- After every write to `state.md`, record the tree fingerprint: the `fingerprint` value of a status snapshot as defined below. `<base>` is the base from Phase 4, or the baseline HEAD before that. For a repo without commits use the empty tree from `git hash-object -t tree /dev/null`.
- Store summaries, never raw output that contains credentials, tokens or environment dumps. The only exception is `review/`, under the rules in 5.1 of `phase-5.md`.
- `.lockin/` is the only exception to the rule that no project file changes before approval.
- The wrap-up deletes `.lockin/<slug>/` at the end of a finished run, unless `keep_state` is `true`. An interrupted or stopped run keeps its state for `--resume`.

### Run stats

`state.md` keeps a `## Run stats` section in this form:

```
challenge_rounds: <n> of <max>
attempts:
- package <n>: <model> x<k>[, sonnet x<k>][, main session]
findings:
- <reviewer>: fixed <a>, rejected <b>, open <c>
```

- 2.3 increments `challenge_rounds` after each round. `<max>` is 3 in full mode and 1 in lite mode.
- 4.2 counts every delegation of a package with its model before it starts, and adds `main session` when you implement a package yourself. A fix package from 5.3 gets its own line.
- 5.3 counts every finding per reviewer agent with its final decision. A finding still open at the end counts as `open`.

Git rules for the whole workflow. Run all git commands from `<repo>`.

- A **status snapshot** consists of three parts:
  1. The output of `git -c core.quotePath=false status --porcelain -uall` without lines under `.lockin/`.
  2. The hash from `git diff --no-color --no-ext-diff --no-textconv <base> | git hash-object --stdin`. It catches changes to files that were already dirty.
  3. The hash from `git ls-files --others --exclude-standard -z -- ':(exclude).lockin' | xargs -0 -r git hash-object -- | git hash-object --stdin`. It catches content changes to untracked files, which the first two parts miss.

  Take a snapshot with `python3 "<scripts>/snapshot.py" --repo "<repo>" --base <base>`. Its `status`, `diff_hash` and `untracked_hash` are the three parts. Store `fingerprint` and the `status` lines in `state.md`.
- Get path lists from `snapshot.py --paths`. Its `changed` and `untracked` lists hold the paths unquoted. The script builds them only from `git -c core.quotePath=false diff <ref> --name-only --no-renames` for changed files and `git -c core.quotePath=false ls-files --others --exclude-standard` for untracked files, never from porcelain lines. `--no-renames` lists both paths of a rename. Git still wraps a path in double quotes if it contains a quote or control character. Unquote such paths before you use them.
- Exclude a path from a diff with `':(exclude,literal)<path>'`, so spaces and characters like `[` or `*` match literally. Escape single quotes in a path for the shell. After you build the excludes, run the diff with `--name-only` and stop if a pre-existing path still appears. `snapshot.py` and `collect_review.py` take each pre-existing path as `--exclude '<path>'`, build the literal pathspec and run the check themselves. `collect_review.py prepare` exits with 3 if a pre-existing path still appears.
- Always exclude `':(exclude).lockin'` from every diff you pass on.
- The **default branch** is the output of `git symbolic-ref --quiet --short refs/remotes/origin/HEAD`, for example `origin/main`. If that fails, use a local `main`, then a local `master`, each checked with `git rev-parse --verify --quiet refs/heads/<name>`. If none exists, ask the user.
- Files inside a git submodule are out of scope for a run in the parent repo. If the plan needs them, tell the user to start a separate run inside the submodule.

### Resume

If the task input starts with the word `--resume`, read `resume.md` in the same directory as this file and follow it. It replaces the rest of 1.1 for this run.

## Phase 1 - Understand

Goal of this phase: a shared, written understanding of the task before anyone thinks about solutions.

### 1.1 Resolve the input

- Run `git rev-parse --show-toplevel`. If it fails, tell the user that lockin needs a git repository, because base, diff, review and resume depend on it. Suggest `git init` with an initial commit and stop.
- If `$ARGUMENTS` is empty, ask the user for an issue number or a task description and stop until you get one.
- If `$ARGUMENTS` starts with `--resume`, follow "Resume" above and skip the rest of 1.1, including the analysis-only check.
- If `$ARGUMENTS` starts with flags, remove them from the task input. `--keep` and `--lite` may appear in any order before the task. `--keep` sets `keep_state: true` when you create `state.md` in 1.4, and the run then keeps `.lockin/<slug>/` after the wrap-up. Without the flag, `keep_state` is `false`. `--lite` sets `mode: lite` in `state.md`. Without the flag, `mode` is `full`.
- If `$ARGUMENTS` is an issue reference (a plain number like `13` or `#13`), fetch the issue:
  1. Check which CLI is available with `command -v gh` and `command -v glab`.
  2. If the git remote points to GitHub and `gh` exists, run `gh issue view <number> --comments`.
  3. If the git remote points to GitLab and `glab` exists, run `glab issue view <number> --comments`.
  4. If neither works (CLI missing, not authenticated, issue not found), tell the user what failed and ask them to paste the issue text or describe the task. Do not guess the content of an issue.

  If the fetch worked, record `issue: <number>` and `issue_cli: gh` or `glab` in `state.md` when you create it in 1.4. Only runs with these fields get the issue comment offer in Phase 3 and the draft PR offer in the wrap-up.
- Otherwise treat `$ARGUMENTS` as the task description.

Read the issue comments too. They often contain decisions or constraints that the issue body lacks.

Then check whether the task asks for a change. If it only asks for analysis, explanation or evaluation, take the analysis-only exit: read the relevant files as in 1.2, deliver the analysis with a proposed scope and ask whether to continue with a change. If the user agrees, continue with 1.2 and use the agreed scope as the task. Otherwise end the workflow. This exit runs no baseline and creates no state.

### 1.2 Read the project context

- Never read `.env` files, credential files or private keys. This rule binds you and every subagent. If the repository root holds a `.lockin-guard.json`, the files matching its `secret_globs` count as secret files too.
- Read the project `CLAUDE.md` (root and any nested ones in affected directories). Its conventions bind every later phase, including the subagents, so extract the rules that matter for this task.
- Locate and read all files the task affects. Read callers and tests of the code you plan to change, not only the code itself. Changes break at the boundaries.
- Identify how the project runs tests, linters and static analysis. You need these commands for the baseline and the work packages.

### 1.3 Record the baseline

The baseline separates problems the change causes from problems that existed before.

1. Record HEAD with `git rev-parse HEAD`, or `unborn` if the repo has no commit yet.
2. Record a status snapshot with `snapshot.py`. If it lists changes, tell the user now. Phase 4 decides how to handle them.
3. Show the user the list of test, lint and static analysis commands you plan to run, and wait for an explicit confirmation. Run only the confirmed commands. Use check variants such as `--dry-run` or `--check` where they exist, never `--fix` and never snapshot updates. Mark every command that may touch a database, an external service or files outside the repo. If you are unsure, mark it.
4. Record command, exit status and a short failure summary per command. Pre-existing failures belong in the brief.
5. Record a second status snapshot. Compare the `status` lines that do not start with `??` and `diff_hash` with the first snapshot. If they changed, stop and tell the user which command changed which file. Do not revert anything. New untracked files from the run are fine, because the second snapshot covers them.
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
2. Create `.lockin/<slug>/` and write `state.md` with task input, `keep_state`, `mode`, `scripts_dir` (the absolute path of `<scripts>`), an empty run stats section, brief and baseline.
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
- Work packages: a numbered list with title, files and model per package, ordered by dependency. Cut them by the work package rules below. The approval in Phase 3 covers this list, because it is part of `plan.md`.

#### Work package rules

Each package leaves the project in a working state. Order them by dependency. Prefer more small packages over few large ones, because the implementer runs on Haiku by default and works best with narrow, explicit instructions.

The `Verification` field may only contain commands that the user confirmed in 1.3 or approved with the plan. The implementer runs these commands with Bash, so an unconfirmed command there bypasses the confirmation. If a package needs a new command, ask the user first and record the confirmation in `state.md`.

Write every `Verification` command as the exact command line the implementer runs. The guard compares each segment between `&&`, `||`, `;`, `|` and `&` with the allowlist, after shell-style tokenizing. Do not put `;`, `|`, `&` or parentheses inside quotes, because the guard blocks such commands. Write `ddev exec vendor/bin/phpunit && ddev exec vendor/bin/phpstan`, not `ddev exec "vendor/bin/phpunit && vendor/bin/phpstan"`. Do not combine `cd` and git in one command line.

Pick the model per package. The default is Haiku from the agent definition. Pass `model: "sonnet"` to the Agent tool when a package changes logic across more than one file or needs non-trivial algorithms or type reasoning. Do not use Opus for implementation.

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

Keep a running list of rejected objections with reasons. The user sees this list in Phase 3. After each round, record every objection with your decision in the challenge log in `state.md` and update `plan.md`. Then increment `challenge_rounds` in the run stats.

### 2.4 Loop rules

- Run at most 3 challenge rounds, or 1 in lite mode. Diminishing returns set in fast, and each round costs an Opus call.
- Stop as soon as the verdict line of a round reads `NO CRITICAL OBJECTIONS`. Treat `CRITICAL OBJECTIONS: 0` the same way.
- If critical objections remain after the last allowed round, do not loop further. Carry them into Phase 3 and let the user decide.

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

If `state.md` records `issue`, ask once whether to post the approved plan as a comment on the issue. Say that the comment is visible to everyone who can read the issue, show the exact text from `plan.md` that you would post and the exact command:

- GitHub: `gh issue comment <issue> --body-file "<repo>/.lockin/<slug>/plan.md"`
- GitLab: `glab issue note <issue> --message "$(cat "<repo>/.lockin/<slug>/plan.md")"`

Run it only after an explicit yes. Record `issue_comment: posted`, `declined` or `failed` in `state.md`. On a failure, report the error and do not retry. Wait for the answer before you start Phase 4. Without `issue`, skip this offer.

Then read `phase-4.md` in the same directory as this file and follow it.
