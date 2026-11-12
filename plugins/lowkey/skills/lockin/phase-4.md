# Lock in - Phase 4

This file continues `SKILL.md` in the same directory. The state rules, the git rules and the work package rules in 2.1 of `SKILL.md` apply here. Section references like 1.3 or 2.1 point to `SKILL.md`.

## Phase 4 - Implementation

Goal of this phase: the approved plan, implemented in small verified steps.

### 4.1 Expand the work packages

Expand each entry of the approved work package list in `plan.md` into a full package. Keep number, title, files and model as approved. If a package needs another file, another model or a different cut, this is a plan change. Handle it as described at the end of 4.2.

Cut and model rules: see "Work package rules" in 2.1 of SKILL.md.

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
`<exact command, e.g. vendor/bin/phpunit tests/Unit/FooTest.php>`, one command line per line
or: No automated tests. Manual check: <exact steps>

### Out of scope
<What the implementer must not touch.>
Pre-existing user changes, never modify: <paths or "none">
```

If a package needs a decision you have not made, make it now and write it into the package. The implementer is not allowed to make architecture decisions.

### 4.2 Set the base and run the packages

Before the first package:

1. Record a fresh status snapshot with `snapshot.py --paths`, because the tree may have changed since Phase 1.
2. If a changed file is also a package file, stop. Explain that the change cannot be reviewed in isolation and ask the user to commit or stash that file. Never stash or commit yourself.
3. List all other changed and untracked files as pre-existing user changes. Take it from the `changed` and `untracked` lists of that snapshot. Exclude these paths from every diff, for example `git diff <base> -- . ':(exclude).lockin' ':(exclude,literal)<path>'`.
4. Record the base with `git rev-parse HEAD`, or the empty tree from `git hash-object -t tree /dev/null` for a repo without commits. Write the base, the pre-existing list and this snapshot to `state.md` as the final baseline. The `base` field of `snapshot.py` without `--base` holds the same value.
5. Fill the pre-existing list into every package and write each package to `.lockin/<slug>/packages/<n>.md`.

For each package:

1. Set its status to `in_progress` in `state.md`. Count the attempt with its model in the run stats. Write `<repo>/.lockin/active.json` as `{"slug": "<slug>", "package": <n>, "commands": [<each Verification command verbatim>]}`, with `"commands": []` for manual checks. Rewrite it before every delegation, including retries (step 4) and after a newly confirmed command (step 5), together with `packages/<n>.md`. The guard allows the implementer with Bash only these commands plus read-only git. Without the file it allows only read-only git, and a broken file blocks every Bash call of the implementer. Then delegate it to `lowkey:lockin-implementer` with the chosen model. The prompt names the absolute path of `.lockin/<slug>/packages/<n>.md` and tells the implementer to read it first. Do not repeat the package text in the prompt. Add only what the file lacks, such as the answer to an earlier `BLOCKED` question.
2. Check the result before you start the next package:
   - Read the report.
   - Inspect the actual change with `git diff <base>` on the affected files. Trust the diff, not the report.
   - Run the verification yourself if the report shows no clean run. Run only commands the user confirmed in 1.3 or approved with the plan. Take a status snapshot with `snapshot.py` before and after the run. Stop if a `status` line without `??`, `diff_hash` or the `untracked_files` entry of a package file changed.
   - Compare the change against the acceptance criteria.
3. If the result is correct, set the status to `done`.
4. If the result is wrong or incomplete, write a corrected package to `packages/<n>.md` that names the concrete problem and delegate again. Attempt 1 runs on the planned model, attempt 2 on Sonnet. After that, implement it yourself or ask the user. If you implement it yourself, add `main session` to its line in the run stats. Set the status to `failed` if the user stops the package.
5. If the implementer reports `BLOCKED`, set the status to `blocked` and resolve the question. Ask the user when the answer changes scope or architecture. Then update `packages/<n>.md` and delegate again.
6. If the report or a tool error contains `lowkey guard:`, the plugin's guard hook blocked a call. Treat it like `BLOCKED`. Show the user the blocked call and the reason. Never rephrase the command to get past the guard, and never tell the implementer to do so. If the package truly needs the call, the user decides, and you run it yourself after their approval. The guard also blocks every command outside `active.json` and read-only git. Add a command to the package only after the user confirmed it, then rewrite `active.json`.

Run packages sequentially. Later packages build on earlier ones, and a defect caught early is cheaper than a defect spread across three packages.

After the last package, and whenever the user stops a package or the run, delete `<repo>/.lockin/active.json`. A stale allowlist must not apply to a later run.

If you discover during implementation that the approved plan does not work, stop. Explain the problem to the user and get approval for the changed plan before you continue. Then update `plan.md` and write the new approval with the new hash to `state.md`.

When the last package is done, read `phase-5.md` in the same directory as this file and follow it.
