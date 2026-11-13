# Verification

Read this file for stage group A (crawl diff 0), stage group E (verification and report) and every step that needs proof of unchanged output. It covers crawls, diffs, TypoScript proof, the Extension Scanner, fixtures, backend checks and the evidence layout. Binding rules live in `process.md`. Read `## Baselines and crawls` and `## Expect file` there first. This file adds the usage details.

Command classes follow `process.md` `## Command classes`. Paths of the tools below are relative to `<work>/tools/`. Inside DDEV they read `php .typo3-upgrade/tools/<script>` (`process.md` `## Command classes`, command prefixes).

## Page lists

A page list is a TSV with `<uid>\t<slug>` per line. Empty lines and lines starting with `#` are skipped.
- The full list holds every page, including hidden pages. Fixtures unhide them inside a snapshot (see below).
- The smoke list is a small subset of the full list. It runs as a check command and fits into the time limit of lockin.
- Run the full list as a main session command.

## Crawl and diff

Usage of `crawl.sh`:
- `crawl.sh --baseline <pages.tsv> <outdir> <base-url>` writes a baseline. The folder must not exist. Main session command.
- `crawl.sh <pages.tsv> <outdir> <base-url>` is smoke mode. The folder may be missing, empty or hold its own `.smoke` marker. Check command when `<outdir>` is a fixed scratch folder. Smoke mode deletes only its own files (`*.html`, `status.tsv`, markers) and refuses a folder with any other entry.
- The script checks the page list first, before it touches any folder. It refuses a symlinked `<outdir>`.
- Markers: `.baseline` first, `.smoke` for smoke runs, `.complete` as the last action. Any other folder ends with exit 2.
- Redirects stay unfollowed. curl runs with `-g`. A failed request writes status `000`. HTTP errors do not change the exit code.
- A `--baseline` run where every page returned `000` ends with exit 2 and writes no `.complete`. The recovery rule is in `process.md` `## Baselines and crawls`.
- Set `CRAWL_INSECURE=1` for self-signed certificates, for example on `https://<project>.ddev.site`.

Usage of `htmldiff.sh` (overview):
- `htmldiff.sh <dirA> <dirB>` prints `STATUS`, `MISSING` and the count of changed lines per uid. Exit 0 equal, 1 differences, 2 error.
- `htmldiff.sh --normalize <file>` prints the normalized form of one file.
- The normalizer removes the honeypot tag, the `[__state]` tag and the default twitter card tag (`content="summary"`) only, not whole lines. It drops blank lines and masks cache busters, `_assets` hashes, the generator meta tag and processed image paths.

Usage of `residual.py` (gate):
- `residual.py [--limit N] [--expect <file> --expect-sha256 <hash>] [--pages <tsv> --pages-sha256 <hash>] <baseline-dir> <new-dir>`. Exit 0 no unmatched difference, 1 unmatched differences, 2 error.
- The baseline dir must hold `.baseline`, and both arguments must be different folders. A uid whose slug differs between both status files counts as unmatched (`SLUG`). A rule that matches 7 or more of 9 probe strings counts as catch-all and ends with exit 2.
- It compares only the uids listed in `<new-dir>/status.tsv`, so a smoke crawl works as a subset check.
- `--pages` and `--pages-sha256` come as a pair. They pin the page list. A uid of the list that `<new-dir>/status.tsv` lacks counts as unmatched.
- It exits 2 when `.complete` is missing on one side or when the new crawl lists no uid.
- It rejects expect patterns that match arbitrary probe text.
- `--expect` and `--expect-sha256` come as a pair. The hash must match the file. The format of the file is in `process.md` `## Expect file`.
- `--limit` caps the printed unmatched entries per uid. The default is 12. The counts stay complete.
- The normalizer covers the same noise as `htmldiff.sh` plus TYPO3 13 rendering effects. It drops the void tag slash, sorts tag attributes and trims whitespace. It removes noise at tag level only.
- The output lists `## unmatched`, then `## matched`, then a `RESULT <pass|fail> compared=<c> unmatched=<n> matched=<m>` line. With `--expect` it prints the SHA-256 it read.

Old and new host. When the old and the new system run under different hosts, set `OLD_HOST` and `NEW_HOST` as a pair. Both tools replace the old host literally. Setting one of them is an error.

Every diff outside the expected-diff list of the step is a regression (`process.md` `## Hard gates`).

## TypoScript proof

Run `php .typo3-upgrade/tools/ts-dump.php [page-uid]` before and after the change, for example into two files in the evidence folder. The script sorts its output. The dumps hold values such as API keys, so never print a plain diff of them. Compare the key sets with `diff <(cut -d= -f1 before.txt) <(cut -d= -f1 after.txt)` and report changed values only as key paths or counts (`process.md` `## Secrets`). It defaults to page uid 1 and needs TYPO3 12 or newer. It documents 12 and 13. On 14 the result is unverified. It exits 2 on a missing autoloader or missing classes.

On TYPO3 11 the script does not work. There, crawl diffs are the only TypoScript proof.

The script runs as a check command when it only reads and writes to a fixed scratch file outside the baselines.

## Extension Scanner

Run `php .typo3-upgrade/tools/extension-scanner.php <extension-key>` once per own extension.
- Output lines read `<indicator> <relative path>:<line> <message>`, then `ERROR ...` lines for unparsable files, then `TOTAL strong=<n> weak=<n> errors=<n>`.
- Exit 0 means the scan covered every file and found no strong match. 1 means at least one strong match. 2 means an error, including a file that could not be parsed.
- The scanner knows only the matchers of the installed core. Run it again after each jump.
- Both the scanner and `ts-dump.php` bootstrap TYPO3 and may warm `var/cache`.

## Fixtures inside a snapshot

Fixtures make hidden or deleted content visible to a crawl.
1. Take the snapshot `pre-<nn>-<stage>-<k>` (main session command, `process.md` `## Stage groups`).
2. Unhide hidden pages and elements, restore deleted ones and add link variants with SQL. Run the same SQL before the old baseline and before the new crawl. Main session commands.
3. Crawl.
4. Restore the snapshot (main session command).

The fixture SQL stays in the plan. Evidence holds no dumps.

## Old and new side by side

Create a second DDEV project from a git worktree on the old version. Crawl both with `OLD_HOST` and `NEW_HOST` set. Remove the worktree and the DDEV project afterwards. These are main session commands. Use this setup when a step needs the old version running next to the new one, for example for a missing baseline, for screenshots or for open-and-save row diffs.

## Screenshots

Playwright is optional.
- Freeze animations, consent banners and carousels before the shot.
- Compare with a pixel diff.
- For a "before" shot without the old system, serve the saved old HTML under the same URL.
- Screenshots go into the evidence folder.

## Backend checks

Create a temporary admin inside a snapshot, check the backend workflows with it, then restore the snapshot. Main session commands. Never print passwords.

## Open-and-save row diffs

Open and save the same records under the old and the new version. Compare the rows that each version writes. Keep a summary of the changed columns in the evidence, no dumps. This shows silent changes of stored values, for example in FlexForms and RTE fields.

## CLI gates

Every rung exit checks these:
- `database:updateschema "*" --dry-run` is empty (check command)
- `upgrade:list` is empty (check command)
- The error log has no new lines
- The deprecation log differs from the baseline only by messages that the roadmap maps to a step
- A form submit stores its row and sends its mail, visible in Mailpit
- All asset and link URLs return 200
- `referenceindex:update --check` reports a perfect index (`schema-and-wizards.md`)

## Evidence layout

Save evidence under `<work>/evidence/<nn>-<slug>/`. No SQL dumps (`process.md` `## Folders`).

`roadmap.md` records the `tree_hash.py <baseline-dir>` value of every baseline folder. The main session compares these values before lockin's step 5.1 (`process.md` `## Gate integrity`). The `diff -r` check of the tools belongs to the same gate.
