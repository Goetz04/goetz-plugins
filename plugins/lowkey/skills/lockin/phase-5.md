# Lock in - Phase 5 and wrap-up

This file continues `phase-4.md` in the same directory. The state rules and the git rules of `SKILL.md` apply here. Section references like 1.3 or 2.1 point to `SKILL.md`, 4.1 and 4.2 point to `phase-4.md`.

## Phase 5 - Review

Goal of this phase: an independent review of the complete change.

### 5.1 Collect diff and test output

The reviewers have no Bash access. They only read files, so a review cannot change the code under review or trigger side effects. You run the commands for them and write the results to `.lockin/<slug>/review/`. The reviewers read these files with the Read tool, so diff and output do not pass through your context or the prompts.

1. Create the review folder, the diff and the new file list with `python3 "<scripts>/collect_review.py" prepare --repo "<repo>" --out "<repo>/.lockin/<slug>/review" --base <base>`, plus `--exclude '<path>'` per pre-existing path. The script deletes an existing `review/` and creates it with mode 700, so each round starts from a fresh folder. It writes `diff.patch` with staged and unstaged changes, excluding `.lockin` and the pre-existing paths. It writes `new-files.txt` with the untracked paths that are not pre-existing, one per line. `git diff` does not show these files, and the reviewers read them with the Read tool. It also stores a snapshot for the checks in step 2. Exit 3 means a pre-existing path still appears in the diff: stop and tell the user. Exit 2 means an error: show stderr and stop.
2. Run every test, lint and static analysis command from the work packages and the project `CLAUDE.md` that the user confirmed in 1.3 or approved with the plan. Use check variants as in 1.3. Run each command in its own call: `python3 "<scripts>/collect_review.py" run --repo "<repo>" --out "<repo>/.lockin/<slug>/review" --index <n> --command '<command>'` (single quotes, with each `'` in the command replaced by `'\''`), and set the Bash `timeout` to 600000. The script writes the complete output to `review/test-<n>.txt`, with the command as the first line and `exit: <status>` as the last line, and stops a command after 540 seconds with `exit: timeout`. Exit 4 means the command changed files: stop and tell the user which ones, from the `changed` list. Exit 2 means an error: show stderr and stop. Report `warnings` to the user without stopping. Without automated tests, run the manual checks from the packages and write what you checked to `review/manual-checks.md`.
3. Redact the test files before any reviewer starts. Replace values after keys like `password`, `secret`, `token`, `api_key`, `authorization` and `bearer`, private key blocks and environment dumps with `[REDACTED]`. Run `python3 "<scripts>/redact.py"` with all `review/test-<n>.txt` files. It applies these rules in place. On exit 1 it lists `file:line: rule` for every hit left: redact these lines with Edit and run it again until it exits 0. Do not redact `diff.patch`. A secret in the diff is a finding for the risk reviewer, and it already sits in the working tree.

Keep the files unshortened. The reviewers cannot rerun anything, so every line you cut is a line they cannot check. If a test command fails, still keep the full output and do not fix anything before the review.

`review/` is the only place where the workflow stores raw output. It exists only during Phase 5. See 5.3 for its deletion.

### 5.2 Start the reviewers

In full mode, delegate to `lowkey:lockin-reviewer-correctness` and `lowkey:lockin-reviewer-risk` in parallel. In lite mode, delegate only to `lowkey:lockin-reviewer`. Every reviewer prompt contains:

- The task brief and the final approved plan
- The absolute paths of `review/diff.patch` and `review/new-files.txt`, with the instruction to read both completely
- The absolute paths of all `review/test-<n>.txt` files with their exit status, or the statement that the project has no automated tests with the path of `review/manual-checks.md`
- The baseline test results from Phase 1
- The list of pre-existing user changes, marked as user work that is not under review
- Relevant `CLAUDE.md` rules

### 5.3 Process the findings

Handle every finding:

- **Fix**: implement the fix directly or as a new work package through `lowkey:lockin-implementer`. Verify it like any other package. Write `active.json` before the delegation as in 4.2 and delete it after the verification.
- **Reject**: write down a concrete reason.

Do not drop findings silently. A rejected finding with a reason helps the user, a missing finding hides a risk. Record every finding with your decision in `state.md` and count it per reviewer in the run stats.

After substantial fixes, collect diff and test output again as in 5.1 and run the affected reviewer on the new state, in lite mode the combined reviewer. Limit this to one extra review round, then report remaining findings as open.

When the last review round is processed, record the result per test command in `state.md`, plus the redacted excerpt of every failure. The wrap-up needs both. Then delete `.lockin/<slug>/review/` with `python3 "<scripts>/cleanup.py" --repo "<repo>" --slug <slug> --target review`, even if `keep_state` is `true`. The script checks that the slug is not empty and contains neither `/` nor `..`, that the target is exactly `<repo>/.lockin/<slug>/review` and that no symlink is involved.

## Wrap-up

Set `current_phase` to `wrap-up` in `state.md`. Then give the user a final summary:

- **Implemented**: what changed, per work package
- **Findings**: fixed findings, rejected findings with reasons, open findings
- **Tests**: which commands ran and their result, from `state.md`. Report failures with their recorded excerpt, never hide them.
- **Deviations**: any difference from the approved plan and why
- **Commit proposal**: a commit message in the style of `git log --oneline -10`, or in Conventional Commits style if the log is empty. Add a PR description draft with summary, changes per package, test results and open findings. List the exact paths to stage: the `changed` and `untracked` lists of `snapshot.py --base <base> --paths` with one `--exclude` per pre-existing path.
- **Stats**: a short block of at most 6 lines from the run stats in `state.md`: challenge rounds of the maximum, attempts per package with model, findings per reviewer as fixed, rejected and open.

### Draft pull request

Skip this section if `state.md` records no `issue`. Otherwise ask once whether to open a draft pull request (GitHub) or merge request (GitLab) for the issue, and set `draft_pr: pending` in `state.md` while the question is open. Without an explicit yes, record `draft_pr: declined` and continue with the cleanup. You never commit and never push. The user does both.

On yes, check the preconditions:

1. The current branch from `git rev-parse --abbrev-ref HEAD` is not the default branch from the git rules in `SKILL.md`.
2. `git rev-list --count <default>..HEAD` is greater than 0.
3. The branch has an upstream, so `git rev-parse --abbrev-ref --symbolic-full-name @{upstream}` succeeds, and `git rev-list --count @{upstream}..HEAD` is 0.
4. No path from the staging list of the commit proposal shows up in `changed` or `untracked` of `snapshot.py --base HEAD --paths` with one `--exclude` per pre-existing path.

If a precondition fails, name it and tell the user to commit and push. Then wait. When the user reports the push, check again. When the user wants to skip, print the PR description draft in the chat, record `draft_pr: skipped` and continue with the cleanup.

If all preconditions hold, write the PR description draft plus a last line `Closes #<issue>` to `.lockin/<slug>/pr-body.md`. Show the user the complete body and the exact command, and say that the pull request is visible to everyone who can read the repository. If the findings list holds open security findings, warn about them. Run the command only after an explicit yes to this text:

- GitHub: `gh pr create --draft --title '<commit subject>' --body-file "<repo>/.lockin/<slug>/pr-body.md"`
- GitLab: `glab mr create --draft --title '<commit subject>' --description "$(cat "<repo>/.lockin/<slug>/pr-body.md")" --yes`

Put the title in single quotes and replace each `'` in it with `'\''`. Never put the title in double quotes, because the shell expands `$`, backticks and backslashes there. Record `draft_pr: <url>` from the output, or `draft_pr: failed` with the error. On a failure, report the error and do not retry. Then continue with the cleanup, which also deletes `pr-body.md`.

Set `current_phase` to `done` in `state.md`. Then clean up:

- Delete `<repo>/.lockin/active.json` if it still exists, also when `keep_state` is `true`.
- If `keep_state` is `true`, keep `.lockin/<slug>/` and tell the user that they may delete it.
- Otherwise delete the run folder. Check first that the complete summary above stands in the chat. Then run `python3 "<scripts>/cleanup.py" --repo "<repo>" --slug <slug> --target run`. The script checks the slug and the exact target `<repo>/.lockin/<slug>`, refuses symlinks and removes `.lockin/` when it is empty afterwards. Tell the user that the state is gone, because `.lockin/` is not versioned and the delete cannot be undone.
- If the delete fails, report the error and the path. Do not retry with other commands.

Do not commit and do not push unless the user asks for it. The user reviews the change first and decides how it enters the history. If the user asks for a commit, show `git status` and `git diff --cached --name-only` first. If the index already holds paths outside the list, ask the user to unstage them or to confirm them. Stage only the listed paths.
