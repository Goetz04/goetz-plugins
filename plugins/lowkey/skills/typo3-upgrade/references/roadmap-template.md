# Roadmap template

This file defines how the skill builds `roadmap.md` and the step briefs. Placeholders are the same as in `process.md`: `<repo>`, `<app>`, `<app-rel>`, `<state>` (`<repo>/.lockin/upgrade`), `<work>` (`<app>/.typo3-upgrade`), `<nn>`, `<slug>` and `<stage>`.

## Instantiation rules

- Number the steps `01`, `02`, ... in dependency order. Write the slug in kebab case.
- Include only the rungs between source and target.
- Create one step per stage group (A, B, C+D, E) of each rung. Drop A or B when the inventory shows nothing to do, and record the reason.
- Place each blocker migration on the version where the old and the new extension both run, or after the jump. Example: Gridelements to container runs on 11 before the jump. Mask to Content Blocks runs on 13. Record the decision and the reason in the roadmap, per blocker.
- Add a first step "set up DDEV" when `inventory.md` says `ddev: absent`.
- Add an early step "move credentials out and untrack" for each tracked config file.
- Add the forms step only when `typo3/cms-form` or a form extension is installed.
- Lockin mode: use `--lite` only for low-risk steps, and only when the user passed `--lite`. C+D steps, blocker migrations and the go-live runbook always run in full mode.
- Every step lists its dependencies.

## Blocks

The roadmap has seven blocks, in this order.

1. Log analysis and fixes on the source version. Evaluate the live error and deprecation logs. Run a local crawl with full backtraces and the Extension Scanner. Sync drift between live and repository, for example `.htaccess`, site configuration, form definitions and missing Composer packages. Map every deprecation to a later step. One legacy extension often causes most deprecations. Its migration then moves forward.
2. Blocker migrations. Run each on the version where the old and the new extension both work. Decide per blocker whether it runs before or after the jump.
3. The rungs. Each rung gets the four stage groups from `process.md`.
   - A environment. DB server and PHP version on the old version. The crawl diff is 0.
   - B forward-compatible code. The code works on the old and the new version.
   - C+D Composer jump with `--no-scripts`, schema gate, wizards, removals one by one, `extension:setup`.
   - E verification and the report in `docs/upgrade/`, in German or English.

   Acceptance per rung:
   - The site runs locally or on staging on the target LTS.
   - All wizards are done and `upgrade:list` is empty.
   - The schema analysis is empty.
   - Frontend and backend run without errors.
   - The Extension Scanner reports no critical hits in own code.
   - A list names the disabled or not yet compatible extensions for later steps.

   Extra acceptance for the target rung:
   - All active extensions are compatible with the target.
   - The deprecation log holds no entries from own code.
4. Forms. Every form fills and validates with clear messages. It sends the confirmation and notification mails. It looks as before. If the captcha has no release for the target, replace it.
5. Extension cleanup. Keep an inventory with the status updated, replaced or removed. Remove unused extensions. Replace unmaintained ones (the customer decides). Move features that the core now covers to the core.
6. Testing. Write a test list of central pages, functions and backend workflows with editor rights. Compare with live. The customer signs off on staging.
7. Go-live runbook. This block is a runbook only. lockin never runs against production. The runbook covers:
   - editorial freeze
   - fresh live DB and files
   - a rerun of every data migration (the wizards of every rung and the blocker migrations)
   - backups and a rollback plan
   - a smoke test
   - a log watch for some days
   - a target environment that meets the system requirements

## roadmap.md format

Header fields, one per line:
- `source`
- `target`
- `plugin version`
- `created`
- `mcp` (`available` or `declined`)
- `ddev` (`present` or `absent`)
- `tools` (`present` or `missing`)
- `composer root`
- `app root`
- `web dir`
- `default lockin mode`

Steps table with these columns:

| nn | step | rung and group | depends | lockin mode | status | outcome | lockin slug | evidence | notes |
|---|---|---|---|---|---|---|---|---|---|

Status values: `planned`, `handed-off`, `pass`, `findings`, `blocked`. These values stand only in this template. `roadmap.md` holds no legend line with status values.

Status and outcome live only in `roadmap.md`, never in step files.

Section `## Baseline hashes`. One line per baseline folder, as `<folder> <tree_hash>`. The hash comes from the frozen `tree_hash.py`.

Section `## Approval`. It holds:
- the words of the user
- the date
- `steps_hash`, from `tree_hash.py` over `<state>/steps`, `<state>/references` and `<state>/tools`

Section `## Outcome log`. One entry per step with:
- the date
- the outcome
- the lockin slug
- the evidence path
- the hash of the expect file
- the follow-ups, each mapped to a step

## Step brief template

Every step brief starts with this line for lockin:

`This is a step brief of /lowkey:typo3-upgrade. Treat it as the task description. Read .lockin/upgrade/references/process.md completely before Phase 2. The sections named under Gates and Command classes bind this step.`

Then the brief follows this template. The text after each section name tells the skill what to write.

```
# Step <nn>: <title>
- Roadmap: .lockin/upgrade/roadmap.md (status and outcome live there)
- Rung and stage group: <11->12 A | B | C+D | E | none>
- Depends on: <step numbers | none>
- lockin mode: full | lite
- MCP typo3-dev-companion: see roadmap.md
- Composer root, web dir, app root: <values>
- Command prefixes: host `<repo-relative paths>`, DDEV `<cd <app-rel> && ddev exec | ddev exec>`
## Goal
## Acceptance criteria
## Project context
## Stages
## Gates
## Command classes
## Check commands
## Main session commands
## Baselines
## Expected diffs
## Never modify
## Evidence
## References
```

Instructions per section. Never copy `process.md` sections into a brief. Name them by heading. The frozen copy in `.lockin/upgrade/references/process.md` holds the text, and `steps_hash` covers it.
- `Goal`. One or two sentences.
- `Acceptance criteria`. User story lines plus checkable criteria.
- `Project context`. Facts from `inventory.md` that matter for this step. Add the provider of each command from the `typo3 list` result.
- `Stages`. One cause per stage. Name the snapshot `pre-<nn>-<stage>-<k>` before each DB write.
- `Gates`. A list of the binding `process.md` sections by heading: `Folders`, `Hard gates`, `Secrets`, `Gate integrity`, `MCP`, `Outcome` and `Command matrix`. Add only what is specific to this step, for example which hard gates apply to which stage.
- `Command classes`. A list of these `process.md` sections by heading: `Command classes`, `Main session commands`, `Baselines and crawls` and `Expect file`. Add only the step-specific consequences, for example which commands of this step are main session commands.
- `Check commands`. Candidates for the `Verification` of lockin packages. Only check-class commands.
- `Main session commands`. Numbered. Each entry names its snapshot, its restore command and the `started` and `done` entries for `## Upgrade commands`.
- `Baselines`. The existing baselines from earlier steps, or the main session command that creates them.
- `Expected diffs`. What the expect file must cover, plus the schema and TypoScript expectations. The content and its SHA-256 go into the lockin plan. The main session writes the file after approval.
- `Never modify`. The expect file, the baselines, the tools and the tracked config files.
- `Evidence`. The folder `.typo3-upgrade/evidence/<nn>-<slug>/` and the files to produce. No SQL dumps.
- `References`. Repo-relative links to the frozen copies in `.lockin/upgrade/references/<file>.md`. Always include `.lockin/upgrade/references/process.md`. lockin's agents may read `.lockin/` with Read.

## Ticket text template

The skill prints ticket texts only when the user asks. It never posts them. The user picks German or English.

```
Title: <step title>
Goal: <one or two sentences>
Acceptance criteria:
- <checkable criterion>
Dependencies: <ticket titles or none>
```

The text holds no hosts and no internal paths.
