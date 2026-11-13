# Schema and wizards

Read this file for stage group C+D of every rung and for the rung exit in stage group E. It covers the schema gate, the upgrade wizards, extension configuration and the reference index. Binding rules live in `process.md` `## Hard gates`. This file adds the procedure.

Command classes follow `process.md` `## Command classes`. Dry-run and `--check` variants are check commands. Every other command here is a main session command with the snapshot `pre-<nn>-<stage>-<k>` before it (`process.md` `## Main session commands`; `<k>` is the attempt number from `## Stage groups`). The provider of each command (core or typo3-console) comes from the `typo3 list` result in `inventory.md` (`process.md` `## Command matrix`).

## Schema gate

Run these check commands before every schema change:
- `database:updateschema "*" --dry-run`
- `database:updateschema "*" --dry-run --raw`

Read the list. Then apply changes in this order, each a main session command:
1. `database:updateschema "*.add"`
2. Data migrations, if the step has any
3. `database:updateschema "*.change"`

Never run `*.prefix` or `*.drop` globally. Run drops one by one. Before each drop, count the rows that hold data with `SELECT COUNT(*) ... WHERE <field> <> ''` on a live copy. Report the counts, not the rows. Removal SQL from a local DB is only a template. Derive the go-live list from the dry-run on a live copy.

### Extension update drops a meaningful column
- Symptom: Records that editors deleted reappear after an extension update. The update drops a soft-delete column and the rows lose their flag.
- Detection: Compare the dry-run with the old and new `ext_tables.sql` of the extension. Look for a dropped column that marks state, such as a deleted flag.
- Fix: Delete the flagged rows before the drop. Main session command, snapshot before. Then run the single drop.
- Proof: The row count of the table matches the expected count after the drop. A crawl diff shows no reappeared content.
- Status: practice

### Schema gate not empty after the steps
- Symptom: `database:updateschema "*" --dry-run` still lists changes at the end of stage D.
- Detection: Run the dry-run and its `--raw` variant (check commands).
- Fix: Read each entry. Apply adds and changes as above. Handle each drop on its own with the count query. Do not loop. If an entry has no clear cause, set the outcome to `findings` or `blocked` (`process.md` `## Outcome`).
- Proof: The dry-run output is empty. Save it in the evidence folder.
- Status: practice

## Extension setup

Run `extension:setup` explicitly after the schema gate (main session command). It also writes missing default values of the extension configuration. The `post-autoload-dump` script does the same during Composer runs, which is why Composer runs with `--no-scripts` until then (`composer.md`).

## Upgrade wizards

Wizards belong to one rung. Since TYPO3 12, the core removes the wizards of older majors. So `upgrade:list` must be empty before the next rung starts.

Procedure:
1. Run `upgrade:list` (check command). Read the ids from its output.
2. Run `upgrade:run <id>` for each id, one per call (main session command, snapshot before).
3. Run `upgrade:list` again. The list must be empty.

Never hardcode a list of wizard ids in a step brief or a plan. Read it from `upgrade:list` each time.

Examples seen on TYPO3 12, not a list to follow:
- `sysFileMimeTypeMigration`
- `sysLogSerialization`
- `passwordPolicyForFrontendUsersUpdate`

### Wizard missing after a jump
- Symptom: A wizard that the old version listed no longer appears, and the data stays unmigrated.
- Detection: Compare the `upgrade:list` output of the old version, taken before the jump, with the new version.
- Fix: Run the wizards of the old major on the old version. Do not skip a rung. If the data is still unmigrated, stop with the outcome `blocked`.
- Proof: `upgrade:list` is empty on the new version and the affected content renders as in the baseline.
- Status: unverified

## Configuration

Change gitignored config files only with `configuration:set` and `configuration:remove` (main session commands, `process.md` `## Secrets`). `configuration:remove` without `--force` skips silently when no TTY exists. Verify every change with `configuration:show` on a path that holds no credentials. Never print values from credential paths.

### Silent skip of remove
- Symptom: `configuration:remove` ends with exit 0 and the key stays.
- Detection: Run `configuration:show` on the path after the command (check command).
- Fix: Run the command with `--force` after the user approved the removal. Main session command.
- Proof: `configuration:show` reports that the path no longer exists.
- Status: practice

## Reference index

The last action of every rung runs `referenceindex:update` (main session command). Then `referenceindex:update --check` (check command) must report a perfect index. Save its output in the evidence folder.
