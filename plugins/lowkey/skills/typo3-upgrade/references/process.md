# Upgrade process

These are the rules every step of a TYPO3 upgrade follows. `SKILL.md` and every step brief point to the headings of this file. Step briefs do not copy these sections. They name the sections that apply and point to the frozen copy `.lockin/upgrade/references/process.md`, which `steps_hash` protects. Each section stands alone and repeats what it needs.

Placeholders used in this file:
- `<repo>` is the git toplevel.
- `<app>` is the DDEV app root. It lies inside `<repo>`.
- `<app-rel>` is the path of `<app>` relative to `<repo>`.
- `<state>` is `<repo>/.lockin/upgrade`.
- `<work>` is `<app>/.typo3-upgrade`.
- `<nn>` is the two-digit step number, `<slug>` the step slug, `<stage>` the stage letter.

## Folders

The upgrade uses two folders. Both stay out of git.

`<state>` holds the plan side:
- `inventory.md` with the facts of the preflight
- `roadmap.md` with steps, status, outcomes and hashes
- `steps/` with one step brief per step (`<nn>-<slug>.md`)
- `references/` with a frozen copy of the skill references
- `tools/` with a frozen copy of the skill scripts

`<work>` holds the working side:
- `tools/` with the copy of the scripts that commands run
- `evidence/<nn>-<slug>/` with crawls, TypoScript dumps, dry-run output and log summaries

Why two folders. The guard blocks every implementer Bash command that contains `.lockin`. `ddev exec php` also needs the PHP tools inside the project mount. So commands run the tools from `<work>/tools/`, and the plan side stays in `<state>`.

Both folders must pass `git check-ignore -q`. If one fails, the skill and every step write nothing. Evidence holds crawled HTML and TypoScript constants, which often carry keys.

Evidence never holds SQL or DB dumps. `fe_users` and `be_users` contain personal data. Use DDEV snapshots for database state. Evidence keeps summaries and counts.

Loss warning. `git clean -fdX`, a fresh clone or a second developer loses both folders. Archive both folders at each rung exit. The E step of a rung mirrors the approved roadmap and the rung report into `docs/upgrade/`.

## Stage groups

Per rung (for example 11 to 12) the lockin runs follow these stage groups. One lockin run covers one group, never a whole rung.

- `A environment`: DB server version, PHP version on the old TYPO3 version. The crawl diff against the previous baseline is 0.
- `B forward-compatible code`: code changes that work on the old and the new version.
- `C+D Composer jump and schema`: C is the Composer jump with `--no-scripts`. D is the schema gate, the upgrade wizards, the removals one by one and `extension:setup`. C and D belong together because C leaves the site broken until D finishes.
- `E verification and report`: the report in `docs/upgrade/` in German or English, the Extension Scanner run and the rung exit gates.

Each stage has one cause. If two things change at once, a diff has two possible causes and the step splits.

Take the snapshot `pre-<nn>-<stage>-<k>` right before every DB write. `<k>` is the attempt number, starting at 1. Run `ddev snapshot --list` first and never reuse an existing name. A restore uses the newest snapshot of the first attempt that preceded the failed writes, chosen with the user.

A or B can be dropped when the inventory shows nothing to do. The roadmap records the reason.

## Command classes

lockin reruns the `Verification` commands of a package in its steps 4.2 and 5.1. So every command belongs to one of two classes.

Check commands may go into `Verification`. They are idempotent. They never write the DB, a snapshot or a baseline. Examples:
- `--dry-run` variants
- `upgrade:list`
- `referenceindex:update --check`
- `residual.py` against an existing baseline
- a smoke crawl with `crawl.sh` without `--baseline` into a fixed scratch folder
- `php -l`
- project tests

Main session commands are everything else:
- Composer (the guard blocks it for the implementer anyway)
- `ddev snapshot` and restores
- `upgrade:run`
- `database:updateschema` without `--dry-run`
- `extension:setup`
- migration commands
- fixture SQL
- `configuration:set` and `configuration:remove`
- the first bootstrap after a jump (v12 moves the config files)
- full crawls, baseline crawls and baseline dumps

Rules for `Verification` lines from lockin:
- No `.lockin` in the line. The guard blocks it.
- No `;`, `|`, `&` or parentheses inside quotes.
- No git after `cd` in the same line.

Command prefixes:
- Host commands use paths relative to `<repo>`.
- DDEV commands read `cd <app-rel> && ddev exec ...` when `<app-rel>` is not `.`, otherwise `ddev exec ...`.
- PHP tool paths inside `ddev exec` are relative to `<app>`, for example `php .typo3-upgrade/tools/ts-dump.php`.

## Main session commands

This section is an instruction that the step brief carries to lockin's main session. It is not built-in lockin behavior.

Put every main session command into lockin's `plan.md` as a numbered step between named packages. Give each one:
- the command `ddev snapshot --name pre-<nn>-<stage>-<k>` before it (`<k>` is the attempt number, starting at 1; run `ddev snapshot --list` first and never reuse an existing name)
- the restore command for that snapshot (the newest snapshot of the first attempt that preceded the failed writes, chosen with the user)

The Phase 3 approval covers these numbered steps. Right before each destructive command, ask the user a yes or no question.

Write two entries per command into lockin's `state.md` under `## Upgrade commands`:
- `started <time> <command>` before the command runs
- `done <time> exit <n>` after it ends

On a lockin resume, a `started` entry without a `done` entry means the command may have run halfway. Show the entry to the user and offer the restore of the matching `pre-<nn>-<stage>-<k>` snapshot. Never repeat the command automatically.

## Baselines and crawls

The page list is a TSV with `<uid>\t<slug>` per line. The smoke list is a small subset of that list. The full list holds every page, including hidden pages that fixtures unhide.

`crawl.sh` has two modes:
- `crawl.sh --baseline <pages.tsv> <outdir> <base-url>` writes a baseline. The folder must not exist. The script writes `.baseline` first and `.complete` as its last action. It refuses every existing folder.
- `crawl.sh <pages.tsv> <outdir> <base-url>` is smoke mode. It accepts a missing folder, an empty folder or a folder with its own `.smoke` marker. It writes `.smoke`, refills the folder and writes `.complete` last. Any other folder ends with exit 2.

So a rerun of the smoke check stays idempotent, and nothing overwrites a baseline.

`residual.py <baseline> <new>` compares only the uids listed in `<new>/status.tsv`. It exits 2 when `.complete` is missing on one side or when the new crawl lists no uid. `MISSING` means a uid is listed in `<new>/status.tsv` but its HTML file is absent on one side.

The main session writes the smoke page list with a main session command. Its SHA-256 goes into lockin's `plan.md`. The `Verification` line passes `--pages <smoke.tsv> --pages-sha256 <hash>` to `residual.py`. The page list belongs under "never modify".

After every baseline crawl, the main session reads the status summary. Codes other than 2xx or 3xx stop the step, unless the step brief expects them. `crawl.sh --baseline` exits 2 when every page returned `000`.

Recovery. A `--baseline` run that ended without `.complete` leaves a folder with `.baseline`. The main session deletes that folder only after the user said yes, then crawls again.

Rerun of a step whose baseline folder already exists. Use a new folder name with an attempt suffix. Never delete a complete baseline without the user's yes.

Right after every command that creates a baseline, the main session runs `tree_hash.py` on it and writes `baseline-hash <folder> <hash>` under `## Upgrade commands` in lockin's `state.md`.

The noise filter removes the honeypot tag, the `[__state]` tag and the default twitter card tag (`content="summary"`) only, not whole lines.

`htmldiff.sh` is the overview tool. `residual.py` is the gate tool.

Baselines exist before Phase 4 of a lockin run. They come from the previous step or from a main session command that creates them. Gate commands stay out of the lockin 1.3 baseline list. They go only into packages that follow the main session command which creates their inputs.

Run full crawls as main session commands. lockin stops a check after 540 seconds, and curl waits up to 20 seconds per page.

Set `CRAWL_INSECURE=1` for self-signed local certificates, for example on `https://<project>.ddev.site`.

Set `OLD_HOST` and `NEW_HOST` as a pair when the old and the new system run under different hosts. Setting only one is an error.

## Expect file

The expect file lists the approved differences of a step. One rule per line:
- `<uid or *>\t<regex>` approves changed lines that match the regex.
- `<uid>\tSTATUS <old> <new>` approves a status change.
- Lines starting with `#` are comments.

`residual.py` rejects the obvious catch-all forms and every pattern that matches arbitrary probe text. Anchor patterns and keep them narrow.

lockin's `plan.md` holds the content of the file verbatim and its SHA-256. The Phase 3 approval covers both. No project file changes before approval. The first main session command after approval writes the file and checks it with `sha256sum`.

The `Verification` line passes `--expect <file> --expect-sha256 <hash>`. `residual.py` exits 2 when the hash differs and prints the SHA-256 it read.

Every package lists the expect file under "never modify".

## Gate integrity

The implementer can edit ignored folders. The review never sees them, because it reads only `diff.patch`. So the gates protect themselves with hashes.

`roadmap.md` records the `tree_hash.py` value of every baseline folder.

Before lockin's Phase 5 (before step 5.1), the main session runs:
- `diff -r .lockin/upgrade/tools <app-rel>/.typo3-upgrade/tools`
- `tree_hash.py` on every baseline folder. Compare baselines from earlier steps with `## Baseline hashes` in `roadmap.md`. Compare baselines created in this run with the `baseline-hash` lines in lockin's `state.md`.

Any difference stops the step. The main session reports it to the user and does not continue.

`--resume` of the upgrade skill repeats both checks before it records an outcome.

## Hard gates

Every step brief carries these gates.

- Snapshot. Run `ddev snapshot --list`, then `ddev snapshot --name pre-<nn>-<stage>-<k>` right before every DB write. `<k>` is the attempt number, starting at 1. Never reuse an existing name. When the step fails, restore the newest snapshot of the first attempt that preceded the failed writes, chosen with the user.
- Composer scripts. Run Composer only with `--no-scripts` until the schema gate. The `post-autoload-dump` script runs `extension:setup`, which writes schema changes. After the gate, run `extension:setup` explicitly. It also writes missing default values of the extension configuration.
- Release cooldown. `--no-blocking` is needed for TYPO3 advisories on Composer 2.9 and later. It also skips the release cooldown (unverified, check `composer update --help`). After such an update, read the `time` of every new or changed package in `composer.lock` and review very fresh releases.
- Schema gate. Run `database:updateschema "*" --dry-run` and the `--raw` variant before every schema change. Never run `*.prefix` or `*.drop` globally. Run drops one by one, after `SELECT COUNT(*) ... WHERE field <> ''` on the live copy. Removal SQL from a local DB is only a template. Derive the go-live list from the dry run on a live copy.
- Wizards. Wizards belong to one rung. Since 12, the core removes the wizards of older majors. `upgrade:list` must be empty before the next rung starts. Read the wizard ids from `upgrade:list` and never hardcode them.
- Crawl diff. Compare every crawl with the previous baseline. Every diff outside the expected-diff list of the step is a regression.
- Persistent evidence. Keep baselines and evidence in `<state>` or `<work>`, never in a session scratchpad. The session wipes it on restart.
- Ignored config files. Change gitignored config files only with `configuration:set` and `configuration:remove`. `configuration:remove` without `--force` skips silently when no TTY exists. Check the result with `configuration:show`.
- Rung exit. The last step of every rung runs `referenceindex:update`. Then `referenceindex:update --check` must report a perfect index.
- Command provider. The result of `typo3 list` in `inventory.md` decides which provider (core or typo3-console) supplies each command. See `## Command matrix`.

## Secrets

Never read `.env`, `auth.json`, `settings.php`, `additional.php`, `LocalConfiguration.php`, `AdditionalConfiguration.php` or any file that matches `secret_globs` in `.lockin-guard.json`. Never print values from these files. Compare key paths only.

Compare TypoScript dumps and other evidence that can hold keys by key path or counts. Never quote values in reports, findings, summaries or `docs/upgrade/`.

Read `.ddev/config*.yaml` only for the keys `name`, `type`, `docroot`, `php_version`, `database` and `composer_root`, for example with Grep. Never print `web_environment`. Never read `.ddev/.env*`.

`.lockin-guard.json` proposal. The skill proposes `secret_globs` for the four config files and merges them with existing globs. The file keeps exactly the key `secret_globs`, because the guard blocks every lockin agent on any other key. The skill validates the result with:

`python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert set(d)=={"secret_globs"}' .lockin-guard.json`

It writes the file only after a yes. `.lockin-guard.json` is a tracked project file.

Tracked config files reach the reviewers through `diff.patch`, and `redact.py` skips them. So the roadmap adds an early step that moves credentials out of the file and untracks it. Until then, every step brief tells lockin's main session to pass these paths as pre-existing excludes (`collect_review.py --exclude`) and to review their changes by key path only.

Edits to config files are main session commands. Use `configuration:set` and `configuration:remove`.

## MCP

The recommended MCP is TYPO3/dev-companion. Its tools:
- `typo3_project_describe` for project facts
- `typo3_ter_lookup` with the extension key (from `extra.typo3/cms.extension-key` in `composer.lock`, not the Composer name) for the availability per target major
- `typo3_changelog_lookup` for breaking changes and deprecations

The skill `typo3-extension-upgrade` of the same project covers code work per package.

The status `available` or `declined` lives in `roadmap.md`. Step briefs point there and never carry the status.

Only lockin's main session calls MCP tools and skills. lockin's agents have no MCP or Skill tool. The main session writes the facts it found into the package text.

Install hint when the MCP is missing:
- Clone TYPO3/dev-companion and run `composer install`.
- Run `bin/typo3-dev-companion install` in the project root, then restart the session.
- `install` writes the `typo3-dev-companion` entry into `.mcp.json` and skills into `.agents/skills`. The option `--agent=<id>` selects other skill locations (unverified).
- Commit these files on purpose, or add `.mcp.json` and `.agents/` to `info/exclude`.
- The MCP covers 12.4, 13.4 and 14.3, not 11.5.

Without the MCP, use the TYPO3 changelog on docs.typo3.org and mark every fact `unverified`.

## Outcome

Every step ends with one outcome:
- `pass` means all gates are green.
- `findings` means the gates are green and documented follow-ups exist. Each follow-up maps to a roadmap step.
- `blocked` means stop and ask the user.

Never loop until green. Return remaining causes to the roadmap.

A step is ready when every dependency has the outcome `pass` or `findings`.

## Command matrix

Status values:
- `practice` means used in a real upgrade from 11 to 14.
- `unverified` means not confirmed. Check the command with its `--help` before use.

No entry has the status `verified`, because no entry has a named source.

| Command | Provider | Versions | Status | Note |
|---|---|---|---|---|
| `upgrade:list` | unverified | 12 to 14 | practice | Lists open wizards. Must be empty before the next rung. |
| `upgrade:run <id>` | unverified | 12 to 14 | practice | One wizard per call. Read the id from `upgrade:list`. |
| `database:updateschema "*" --dry-run` and `--raw` | core or typo3-console, depends on the major | all | unverified | Provider per major unverified. Read `typo3 list`. |
| `database:updateschema "*.add"` and `"*.change"` | core or typo3-console, depends on the major | all | unverified | Run `*.add` before and `*.change` after a data migration. |
| `extension:setup` | unverified | 12 to 14 | practice | Run explicitly after the schema gate. |
| `configuration:set`, `remove`, `show` | unverified per major | all | unverified | `remove` without `--force` skips silently without TTY. |
| `referenceindex:update` and `--check` | unverified | all | practice | `--check` ends every rung. |
| `backend:lock` and `backend:unlock` | unverified | all | practice | Used around go-live migrations. |
| `container:sorting` and `container:integrity` | EXT:container | all | practice | `container:sorting` verbose first, then `--apply`. |
| `content-blocks:lint` | EXT:content-blocks | 13 | practice | Run after every `config.yaml` change. |
| `composer ... --no-scripts` | Composer | all | practice | Mandatory until the schema gate. |
| `composer ... --no-blocking` | Composer | Composer 2.9 and later | unverified | Check `composer update --help`. The flag also skips the release cooldown (unverified). |
| `ddev snapshot --name <name>` | DDEV | all | practice | Before every DB write. |
| `ddev snapshot --list` | DDEV | all | unverified | Check `ddev snapshot --help`. |
| `ddev snapshot restore <name>` | DDEV | all | practice | Check `ddev snapshot --help` for the exact syntax. |
| `ddev debug migrate-database mysql:8.0` | DDEV | before the jump to 12 | practice | Snapshots from MySQL 5.7 do not restore on 8.0 without a temporary 5.7 config. |

The provider in step briefs comes from the `typo3 list` result in `inventory.md`.

## Guard limits

The lowkey guard limits lockin agents in this context.

The implementer:
- cannot run Composer install, update, require or remove
- cannot use `.lockin` in a Bash command
- can run only allowlisted commands

The reviewers have no Bash. They see only the git diff. Ignored folders and the database stay invisible to them.
