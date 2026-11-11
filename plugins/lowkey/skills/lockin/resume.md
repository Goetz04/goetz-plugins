# Lock in - Resume

Continue an earlier lockin run instead of starting a new one. The task input reads `--resume [slug] [--keep]`. The word after `--resume` is the slug, unless it starts with `--`.

- Without a slug, list the runs in `.lockin/*/state.md` with their `current_phase` and ask which one to continue.
- If the task input contains `--keep`, set `keep_state: true` in `state.md`.
- The mode comes from `mode` in `state.md`, and `full` if the field is missing. A `--lite` in the task input does not change the mode of an existing run. Tell the user so if they passed it.
- Set `scripts_dir` in `state.md` to the absolute path of `<scripts>` from `SKILL.md`. Older runs lack the field. A fingerprint recorded by lockin 1.3 or older differs from the `snapshot.py` value, so the comparison below shows a mismatch once. Explain that to the user when you ask.
- Read `state.md` and the `plan.md` and `packages/<n>.md` files that exist. Do not cut existing packages again. If the run stands in Phase 4 and `state.md` records no base, restart 4.2 of `phase-4.md` at "Before the first package". If no package files exist, cut the packages as in 4.1 of `phase-4.md`.
- Compare HEAD and the `fingerprint` of a fresh `snapshot.py` call with the last recorded values. On a mismatch, show the difference and ask before you continue.
- If `git hash-object .lockin/<slug>/plan.md` differs from the hash in the approval record, go back to Phase 3.
- Without an approval record, continue at the recorded phase, but never past Phase 3 without a new approval.
- A recorded approval is information, not consent. If the run stands at or after Phase 4, show the plan, the open packages and any tree changes. Then wait for an explicit "continue" from the user in this session and record it in `state.md`.
- For a package in `in_progress`, show `git diff <base> -- <package files>` and `git status --porcelain -uall -- <package files>`, plus the content of new untracked package files. Then ask whether to keep it or redo it. Before a redo, name the paths that already exist. Verify a kept package as in 4.2 of `phase-4.md`. Never revert anything yourself. If the user wants a revert, the user does it.
- If the run stands in Phase 5 and `.lockin/<slug>/review/` exists, delete it with `cleanup.py --target review` and collect the review files again as in 5.1 of `phase-5.md`. The old files may no longer match the tree.
- If the run stands at `wrap-up`, repeat the wrap-up summary before the cleanup, because the user may not have seen it. If `draft_pr` is `pending`, run the draft pull request section of the wrap-up again, including the precondition check.
- Before you continue, load the phase text. If `current_phase` is `4`, read `phase-4.md`. If it is `5`, `wrap-up` or `done`, read `phase-5.md`. Both files lie in the same directory as this file. Phases 1 to 3 stand in `SKILL.md`.
