# TYPO3 upgrade - Resume and step

Continue an upgrade that `SKILL.md` planned. The task input reads `--resume` or `--step <n>`. Placeholders and paths are the same as in `SKILL.md`.

## Common start

1. Run the git and root checks of U0 in `SKILL.md`.
2. Read `<state>/roadmap.md`. If it is missing, say that there is nothing to resume and stop without writing.
3. If `roadmap.md` has no `## Approval`, continue at the approval of U3 in `SKILL.md`.
4. Compute `steps_hash` again with the frozen `python3 "<state>/tools/tree_hash.py" "<state>/steps" "<state>/references" "<state>/tools"`. Compare the result with `steps_hash` in `## Approval`. On a mismatch, show the step list, explain that approved files changed and ask for a new approval before anything else. Record the new approval in `## Approval`.
5. Read `<state>/references/process.md` before you continue.

## --step <n>

1. The step must exist in `roadmap.md`. If not, stop and say so.
2. If a dependency has no outcome `pass` or `findings`, warn and ask.
3. If the step already has the outcome `pass` or `findings`, ask whether to run it again. Before a rerun, keep the earlier outcome in `## Outcome log` as a rerun entry. Tell the user that the rerun uses new snapshot and baseline names (attempt suffix).
4. Do U4 of `SKILL.md` for this step.

## --resume

1. Find the steps with status `handed-off`. If none exists, show the status table and continue with U4 of `SKILL.md`. If several exist, list them and let the user pick one.
2. Find the lockin run. Search `.lockin/*/state.md` for the literal path `.lockin/upgrade/steps/<nn>-<slug>.md`. Skip `.lockin/upgrade/` and folders that start with `review-`. If several runs match, take the newest by modification time. If none matches, ask for the slug, or for the outcome and the evidence by hand.
3. If `current_phase` of lockin is not `done` or `wrap-up`, print `/lowkey:lockin --resume <slug>` and stop.
4. Read `## Upgrade commands` in that `state.md`. A `started` entry without a `done` entry blocks the outcome. Show it and let the user choose between restoring a `pre-<nn>-<stage>-<k>` snapshot and a manual check.
5. Check the gate integrity as in `## Gate integrity` in `process.md`. Run `diff -r "<state>/tools" "<work>/tools"`. Run `tree_hash.py` on every baseline. Compare baselines from earlier steps with `## Baseline hashes` of `roadmap.md`. Compare baselines of this run with the `baseline-hash` lines of lockin's `state.md`. Any difference stops the resume. Show it.
6. If the step used an expect file, show its entries and their SHA-256.
7. For an E step, show the commands of the rung exit gate with the DDEV prefix. These are `upgrade:list`, `database:updateschema "*" --dry-run`, `referenceindex:update --check` and a check for new lines in the error log, plus all check commands of the step. Run them after confirmation and summarize the result.
8. If the step left a `.baseline` folder without `.complete`, report it as incomplete. The outcome cannot be `pass`.
9. Propose an outcome by `## Outcome` in `process.md` and give the reasons. The user confirms or changes it. Then write to `roadmap.md` the step table columns `status`, `outcome`, `lockin slug` and `evidence`, the outcome log entry and the new baseline hashes.
   - The outcome log entry holds the date, the outcome, the lockin slug, the evidence path, the expect hash and the follow-ups.
   - Copy the `baseline-hash` lines of this run from lockin's `state.md` into `## Baseline hashes`.
   - Never write into step files.
10. For `findings`, map every follow-up to an existing step or propose a new step. A new step file changes `steps_hash` and needs approval before the next handoff. For `blocked`, stop and ask the user how to proceed. Never loop until green.
11. If all steps are done, print a summary of the whole upgrade. Remind the user of the go-live runbook and of the archive of both folders. Otherwise continue with U4 of `SKILL.md`.
