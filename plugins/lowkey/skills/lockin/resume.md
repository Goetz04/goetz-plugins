# Lock in - Resume

Continue an earlier lockin run instead of starting a new one. The task input reads `--resume [slug] [--keep]`. The word after `--resume` is the slug, unless it is `--keep`.

- Without a slug, list the runs in `.lockin/*/state.md` with their `current_phase` and ask which one to continue.
- If the task input contains `--keep`, set `keep_state: true` in `state.md`.
- Read `state.md` and the `plan.md` and `packages/<n>.md` files that exist. Do not cut existing packages again. If the run stands in Phase 4 and `state.md` records no base, restart 4.2 at "Before the first package". If no package files exist, cut the packages as in 4.1.
- Compare HEAD and the tree fingerprint with the last recorded values. On a mismatch, show the difference and ask before you continue.
- If `git hash-object .lockin/<slug>/plan.md` differs from the hash in the approval record, go back to Phase 3.
- Without an approval record, continue at the recorded phase, but never past Phase 3 without a new approval.
- A recorded approval is information, not consent. If the run stands at or after Phase 4, show the plan, the open packages and any tree changes. Then wait for an explicit "continue" from the user in this session and record it in `state.md`.
- For a package in `in_progress`, show `git diff <base> -- <package files>` and `git status --porcelain -uall -- <package files>`, plus the content of new untracked package files. Then ask whether to keep it or redo it. Before a redo, name the paths that already exist. Verify a kept package as in 4.2. Never revert anything yourself. If the user wants a revert, the user does it.
- If the run stands in Phase 5 and `.lockin/<slug>/review/` exists, delete it and collect the review files again as in 5.1. The old files may no longer match the tree.
- If the run stands at `wrap-up`, repeat the wrap-up summary before the cleanup, because the user may not have seen it.
