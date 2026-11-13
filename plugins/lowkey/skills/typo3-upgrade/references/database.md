# Database

Read this file for stage group A (environment) of every rung and for stage group C+D when a schema change touches collations or column types. It covers the DB server version, the collation settings and the traps around schema changes. Binding rules (command classes, snapshots, folders) live in `process.md`. This file points to its headings.

Command classes follow `process.md` `## Command classes`. Every command below that writes carries the class main session. Take the snapshot `pre-<nn>-<stage>-<k>` before it, as `process.md` `## Main session commands` states. `<k>` is the attempt number from `## Stage groups`.

Evidence never holds SQL or DB dumps (`process.md` `## Folders`). Keep counts and summaries of DB facts instead.

### DB server version for TYPO3 12 and later
- Symptom: TYPO3 12 refuses to run, or schema diffs show noise, on MySQL 5.7 or on an old MariaDB.
- Detection: Read the DB type and version from `.ddev/config.yaml` or from the user. Check on the live system too, because it decides the go-live target environment.
- Fix: TYPO3 12 needs MySQL 8.0.17 or newer, or MariaDB 10.4.3 or newer. Switch DDEV in stage A, on the old TYPO3 version and before the core jump. Then later diffs have one cause less. Main session command: `ddev debug migrate-database mysql:8.0`, with the snapshot `pre-<nn>-A-<k>` before it.
- Proof: The crawl diff of stage A against the previous baseline is 0 (`verification.md`). The DDEV config shows the new DB version.
- Status: practice

### Snapshots from MySQL 5.7
- Symptom: `ddev snapshot restore` fails or breaks on MySQL 8.0 for a snapshot taken on 5.7.
- Detection: Compare the snapshot date with the date of the DB switch. Check `ddev snapshot --help` for the restore syntax.
- Fix: Take a fresh snapshot right after the DB switch. To restore an old snapshot, set a temporary 5.7 DDEV config, restore, then switch again. Both steps are main session commands.
- Proof: The restored DB answers a smoke crawl with the status codes of the baseline.
- Status: practice

### Default collation of MySQL 8
- Symptom: Schema diffs list many collation changes after the switch to MySQL 8. The new default is `utf8mb4_0900_ai_ci`.
- Detection: Run `database:updateschema "*" --dry-run` (check command, provider per `process.md` `## Command matrix`).
- Fix: Set `DB/Connections/Default/defaultTableOptions` with `charset` and `collation`. On TYPO3 12 the key is `tableoptions`. TYPO3 13 deprecates it. Write the setting with `configuration:set` only (main session command, `process.md` `## Secrets`). Verify with `configuration:show` on the non-credential path.
- Proof: The dry-run shows no collation changes.
- Status: practice

### DBAL 4 on TYPO3 13
- Symptom: TYPO3 13 compares the default charset of tables too. One schema run does not settle the diff.
- Detection: `database:updateschema "*" --dry-run` after the jump still lists changes after a first `*.change` run.
- Fix: Run `database:updateschema "*.change"` twice. The first run changes the tables, the second run changes the columns. Both are main session commands with a snapshot before.
- Proof: `database:updateschema "*.change" --dry-run` returns an empty list (check command).
- Status: practice

### ROW_FORMAT and unique columns on live
- Symptom: The schema change works locally and fails on the live copy. Typical causes are index length on an old row format and duplicate keys after a collation change.
- Detection: On a live copy, check `ROW_FORMAT=DYNAMIC` of the affected tables. Check unique columns such as `be_users.username` for values that become equal under the new collation. Report counts only.
- Fix: Convert the row format and resolve duplicates before the schema change. These writes are main session commands with a snapshot before.
- Proof: The dry-run on the live copy shows no failing statement. Duplicate counts are 0.
- Status: practice

### MariaDB 11 sandbox line in dumps
- Symptom: Importing a dump into MySQL fails at the first line. MariaDB 11 clients write `/*M!999999\- enable the sandbox mode */` at the top.
- Detection: `head -n 1` of the dump shows the line.
- Fix: Remove the line while importing. Main session command, snapshot before: `sed '1{/enable the sandbox mode/d}' dump.sql | ddev import-db`. Keep the dump outside the evidence folder.
- Proof: The import ends without error and a smoke crawl matches the live status codes.
- Status: practice

### sql_mode trap before a Gridelements migration
- Symptom: Hidden Gridelements children appear on pages after a schema change. `tt_content.colPos` became `INT UNSIGNED`, and non-strict `sql_mode` silently turned `-1` into `0`.
- Detection: Count rows with `colPos = -1` before the schema change and compare the counts per `colPos` afterwards (counts only, no dumps).
- Fix: Migrate first, change the schema after. See `migrations/gridelements-to-container.md` for the order. Run `*.change` for `tt_content` only after the migration reports no negative `colPos`.
- Proof: No row has a negative `colPos` before the change. The row counts per `colPos` match before and after.
- Status: practice
