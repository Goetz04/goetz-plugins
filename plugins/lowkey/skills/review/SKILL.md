---
name: review
description: Review an existing change with the lockin reviewer subagents without changing any code. Takes a pull request number, a branch or a <base>..<head> range, or reviews the current branch against the default branch. Collects the diff, runs confirmed test commands, redacts their output and reports the findings of a correctness and a risk reviewer.
argument-hint: "[pr-number | branch | <base>..<head>]"
disable-model-invocation: true
---

# Review

Review target: `$ARGUMENTS`

This skill reviews a change that already exists. It never changes code, never comments on a pull request and never commits. The only files it writes are the transient review folder `<repo>/.lockin/review-<slug>/`, a temporary diff file next to it and, after a yes in R2, one line in `.git/info/exclude`. It deletes the review folder and the temporary file at the end.

The scripts live in `${CLAUDE_PLUGIN_ROOT}/skills/lockin/scripts`. This file calls that directory `<scripts>`. Run them with `python3` from `<repo>` and quote every path argument. They need Python 3.9 or newer.

Never read `.env` files, credential files or private keys. If the repository root holds a `.lockin-guard.json`, the files matching its `secret_globs` count as secret files too. This rule binds you and both reviewers.

## R1 Resolve the target

Run `git rev-parse --show-toplevel`. If it fails, tell the user that the skill needs a git repository and stop. The output is `<repo>`. Run all git commands from `<repo>`.

The **default branch** is the output of `git symbolic-ref --quiet --short refs/remotes/origin/HEAD`, for example `origin/main`. If that fails, use a local `main`, then a local `master`, each checked with `git rev-parse --verify --quiet refs/heads/<name>`. If none exists, ask the user.

Every ref that goes into a git command must not start with `-` and must pass `git rev-parse --verify --quiet '<ref>^{commit}'`. Otherwise tell the user and stop. Use the full SHA that this command prints in every later command instead of the ref name, so branch names never reach the shell again. A pull request number must consist of digits only after an optional leading `#`.

Resolve `$ARGUMENTS`:

- **Empty**: review the commits of the current branch. `<head>` is `HEAD`, `<base>` is `git merge-base <default> HEAD`. Uncommitted changes are not part of the review. Slug: `branch-<current branch>`, or `head-<short sha>` on a detached HEAD.
- **`<n>` or `#<n>`**: a pull request (GitHub) or merge request (GitLab). A branch with a numeric name needs the form `heads/<n>`. Check the remote with `git remote get-url origin` and the CLI with `command -v gh` or `command -v glab`. Without a working CLI for the remote, tell the user what failed and stop. Do not fetch anything. Read the metadata with `gh pr view <n> --json title,body,baseRefName,headRefName,headRefOid,url,files` or `glab mr view <n> --output json`. `<head>` is the head commit SHA from the metadata. Take it as a string and do not verify it locally, because the commit may not exist in the local repository. The diff comes from the CLI in R5. Slug: `pr-<n>`.
- **`<base>..<head>`**: review the diff between both refs as given. Refuse `<base>...<head>` and tell the user to pass the merge-base explicitly. Slug: `range-<base>-<head>`.
- **Anything else**: a branch. `<head>` is the branch, `<base>` is `git merge-base <default> <branch>`. Slug: `branch-<branch>`.

If `<base>` and `<head>` resolve to the same commit, tell the user that there is nothing to review and stop.

Build the slug in lower case. Replace every character outside `a-z`, `0-9` and `-` with `-`, collapse repeated `-` and cut it to 50 characters. The slug then holds only `a-z`, `0-9` and `-`. The review folder is `<repo>/.lockin/review-<slug>`. If it already exists, it stems from an aborted review. Ask the user before you delete it with `python3 "<scripts>/cleanup.py" --repo "<repo>" --slug review-<slug> --target run`.

## R2 Keep the folder out of git

Run `git check-ignore -q .lockin/`. If `.lockin/` is not ignored, ask once whether to append `/.lockin/` to the file that `git rev-parse --git-path info/exclude` names. That file is local and not versioned. Add a newline first if the file does not end with one. Run `git check-ignore -q .lockin/` again and warn if it still fails. Never edit `.gitignore`. If the user declines, warn that `.lockin/` must never be committed.

## R3 Read the context

- Read the project `CLAUDE.md` (root and nested ones in affected directories) and extract the rules that matter for the change.
- For a pull request, take title, description and changed files from the metadata. Otherwise read `git log --oneline <base>..<head>` and `git diff --name-only <base> <head>`.
- Record the reviewed head SHA, the SHA of `HEAD` and whether the working tree has uncommitted changes (`git status --porcelain`).

## R4 Test commands

Run tests only if the reviewed head SHA equals the SHA of `HEAD`. Otherwise the working tree holds other code, so skip the tests and tell the user why. They can check out the branch and run the skill again.

The tests execute the code under review, including test fixtures and build scripts of the change. For a pull request from an outside contributor, say so before the confirmation and recommend a container or sandbox.

If the SHAs match, identify the test, lint and static analysis commands of the project. Show them to the user and wait for an explicit confirmation. Use check variants such as `--dry-run` or `--check` where they exist, never `--fix` and never snapshot updates. Mark every command that may touch a database, an external service or files outside the repo. If the working tree has uncommitted changes, warn that the tests run against them too. If the user declines, review without tests.

## R5 Collect diff and test output

1. For a pull request, first create the folder with `mkdir -p "<repo>/.lockin"`. Then write the diff with `gh pr diff <n> > "<repo>/.lockin/review-<slug>.diff"` or `glab mr diff <n> > "<repo>/.lockin/review-<slug>.diff"`. If the command fails, report the error, delete the file and stop.
2. Prepare the review folder:
   - Pull request: `python3 "<scripts>/collect_review.py" prepare --repo "<repo>" --out "<repo>/.lockin/review-<slug>" --diff-file "<repo>/.lockin/review-<slug>.diff"`, then delete the temporary diff file.
   - Otherwise: `python3 "<scripts>/collect_review.py" prepare --repo "<repo>" --out "<repo>/.lockin/review-<slug>" --base '<base sha>' --head '<head sha>'`.
   Exit 5 means the diff is empty: tell the user and go to R8. Exit 2 means an error: show stderr and go to R8.
3. Run each confirmed command in its own call: `python3 "<scripts>/collect_review.py" run --repo "<repo>" --out "<repo>/.lockin/review-<slug>" --index <n> --command '<command>'`, with the Bash `timeout` set to 600000. Replace each `'` in the command with `'\''`. Exit 4 means the command changed files: stop, tell the user which ones from the `changed` list and go to R8. Exit 2 means an error: show stderr and go to R8. Report `warnings` without stopping.
4. Redact the test files with `python3 "<scripts>/redact.py"` and all `test-<n>.txt` files. On exit 1, redact the listed lines with Edit and run it again until it exits 0. Do not redact `diff.patch`. A secret in the diff is a finding for the risk reviewer.

Keep the files unshortened. The reviewers cannot run anything themselves.

## R6 Start both reviewers

Delegate to `lowkey:lockin-reviewer-correctness` and `lowkey:lockin-reviewer-risk` in parallel. Both prompts contain:

- The review target, and the pull request title and description or the commit list from R3
- The statement that no approved plan exists, so plan adherence gets checked against the pull request description or the commit messages
- The statement that no baseline exists, so test failures stay unclassified
- The absolute paths of `diff.patch` and `new-files.txt` in the review folder, with the instruction to read both completely. `new-files.txt` is empty in this skill, because the diff already holds new files.
- The absolute paths of all `test-<n>.txt` files with their exit status, or `Tests were not run: <reason>`
- The reviewed head SHA, the SHA of `HEAD` and whether the working tree is dirty. If the SHAs differ or the tree is dirty, `diff.patch` is the only authoritative source, and findings that rest on surrounding code must be marked as unverified.
- Pre-existing user changes: none
- Relevant `CLAUDE.md` rules

## R7 Report

Merge the findings of both reviewers into one report. Remove duplicates, sort by severity with critical first, and name reviewer, file and line per finding. Add the test results per command. Do not fix anything, do not edit files and do not post anything to the pull request. The user decides what to do with the findings.

## R8 Clean up

Delete the review folder with `python3 "<scripts>/cleanup.py" --repo "<repo>" --slug review-<slug> --target run`, also when the review stopped early. The script refuses symlinks and removes `.lockin/` when it is empty afterwards. Delete a leftover temporary diff file `<repo>/.lockin/review-<slug>.diff` before that. If the delete fails, report the error and the path and do not retry.
