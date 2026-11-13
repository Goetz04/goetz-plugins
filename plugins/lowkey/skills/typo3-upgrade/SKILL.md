---
name: typo3-upgrade
description: Plan a Composer-based TYPO3 major upgrade from 11.5, 12.4 or 13.4 to 12, 13 or 14, one rung at a time. Inventories the project read-only, writes a roadmap and one step brief per step, waits for approval and hands each step to /lowkey:lockin. Never changes project code, the database or Composer itself.
argument-hint: "[--to 12|13|14] [--lite] | --resume | --step <n>"
disable-model-invocation: true
---

# TYPO3 upgrade

Arguments: `$ARGUMENTS`

This skill plans a Composer-based TYPO3 major upgrade, one rung at a time (11 to 12, 12 to 13, 13 to 14). It inventories the project read-only, writes a roadmap and one step brief per step, waits for your approval and hands each step to `/lowkey:lockin`.

The skill never changes project code, never writes to the database and never runs Composer. All changes run through lockin.

The skill writes only `<state>` and `<work>`. After an explicit yes for each, it also writes the `info/exclude` file and `.lockin-guard.json`.

The skill cannot start lockin itself, because lockin has `disable-model-invocation: true`. The skill prints the command. The user runs it.

## Paths

- `<skill>` is `${CLAUDE_SKILL_DIR}`.
- `<refs>` is `<skill>/references`.
- `<scripts>` is `<skill>/scripts`.
- Project placeholders are `<repo>`, `<app>`, `<app-rel>`, `<composer-root>`, `<web-dir>`, `<state>` and `<work>`.
  - `<repo>` is the output of `git rev-parse --show-toplevel`.
  - `<composer-root>` comes from `composer_root` in `.ddev/config.yaml` (relative to the DDEV app root). Without it, `<repo>` if it holds `composer.json`. Otherwise ask the user.
  - `<app>` is the DDEV app root, the folder that holds `.ddev/`. Search `<repo>` and `<composer-root>`. If both hold one, ask the user. `<app>` must be `<repo>` or a folder inside it, otherwise stop with a note. Without `.ddev/`, `<app>` is `<composer-root>`.
  - `<app-rel>` is the path of `<app>` relative to `<repo>`.
  - `<web-dir>` comes from `extra.typo3/cms.web-dir` in `composer.json`, default `public`.
  - `<state>` is `<repo>/.lockin/upgrade`.
  - `<work>` is `<app>/.typo3-upgrade`.

Read `<refs>/process.md` before U1. Read `<refs>/roadmap-template.md` before U3.

Run scripts with `python3` or `bash`. Quote every path. Pass values from outside in single quotes and replace each `'` inside them with `'\''`.

## Rules

- Secrets. Follow `## Secrets` in `process.md`.
- Folders. Follow `## Folders` in `process.md`.
- Command classes. Follow `## Command classes` in `process.md`.
- Never access production. Use live logs only as copies the user provides. Use logs only as summaries.
- No private package name leaves the machine. Run lookups only for public packages.
- Claim no fact about TYPO3 without the MCP or the docs. Mark every other fact `unverified`.
- Ask before every command with side effects or network access.

## Arguments

Parse `$ARGUMENTS`.

- `--resume` or `--step <n>` (a positive integer). Read `resume.md` in the same directory as this file and follow it. These flags combine with no other flag.
- `--to 12|13|14` and `--lite`, in any order.
- Any other token that starts with `--`, or an invalid value. Show the argument hint and stop.

Free text after the flags counts as answers given in advance to the questions of this skill, for example "continue without the MCP" or "decline all network and ddev commands". Apply each answer when its question comes and say that you applied it.

The free-text answer "stop after the inventory" ends the run after U2 step 7, before U3.

An answer given in advance never counts as approval of the roadmap. The roadmap gate in U3 always waits for a reply in a later turn.

## U0 Version gate

Write nothing and ask nothing before the refusal check. One exception applies. Ask for `<composer-root>` only if you cannot determine it.

1. Run `git rev-parse --show-toplevel`. If it fails, say that the skill needs a git repository and stop.
2. Determine `<composer-root>` as in `## Paths`.
3. Read `typo3/cms-core` from `<composer-root>/composer.lock`. Search `packages` and `packages-dev`. Strip a leading `v` from the version.
4. Refuse and stop with a short note, and write no file, in these cases.
   - `composer.lock` or `typo3/cms-core` is missing. The skill needs Composer mode.
   - The version is below 11.5.
   - The source is not an LTS line. Supported sources are 11.5, 12.4 and 13.4. For 12.1, say to update to 12.4 first.
   - `--to` is not above the source major, or above 14.
5. Without `--to`, propose 14. The user confirms the target with the roadmap.
6. If `<state>/roadmap.md` exists, say that a roadmap exists, point to `--resume` and `--step <n>` and stop. Never overwrite it. To start fresh, the user moves the folder. Also stop when `<state>/steps/`, `<state>/references/` or `<state>/tools/` exists without `roadmap.md`. That is a partial earlier run. Tell the user to move or delete `<state>` and start again.

## U1 MCP check

Check whether tools of TYPO3/dev-companion are available, for example a tool whose name ends in `typo3_changelog_lookup`.

If yes, record `mcp: available`.

If not, stop once and show the install hint from `## MCP` in `process.md`. The hint below matches that section.
- Clone the project and run `composer install`.
- Run `bin/typo3-dev-companion install` in the project root, then restart the session.
- `install` writes the `typo3-dev-companion` entry into `.mcp.json` and skills into `.agents/skills`. The option `--agent=<id>` selects other skill locations (unverified).
- Commit these files on purpose, or add `.mcp.json` and `.agents/` to `info/exclude`.
- The MCP covers 12.4, 13.4 and 14.3, not 11.5.

Ask whether to install first or continue without.
- Install first. Stop. The user runs the skill again after the restart.
- Continue without. Record `mcp: declined`.

Never install the MCP and never edit `.mcp.json`.

## U2 Preflight

The preflight is read-only, except for `<state>`, `<work>` and the two files that need a yes. Work in this order.

1. Ignore check. Run `git check-ignore -q` for `.lockin/` and `<app-rel>/.typo3-upgrade/`. If one fails, ask once to append `/.lockin/` and `/<app-rel>/.typo3-upgrade/` (or `/.typo3-upgrade/` when `<app-rel>` is `.`) to the file from `git rev-parse --git-path info/exclude`. Add a newline first if the file does not end with one. Never use `.gitignore`. Check again. If a path is still not ignored, or the user declined, explain why (`## Folders` in `process.md`) and stop without writing anything.
2. Roots and environment. Determine `<app>`, `<app-rel>` and `<web-dir>`. Check for DDEV (`.ddev/config.yaml`) and read the PHP version and the DB type and version from it. Read only the keys named in `## Secrets` in `process.md` from `.ddev/config*.yaml`. Read the PHP constraint from `config.platform.php` and `require.php` in `composer.json`. Without DDEV, record `ddev: absent`.
3. Extensions from `composer.lock`. List every package of type `typo3-cms-extension` and every `typo3/cms-*` system extension in use. Per package record:
   - the name and the extension key from `extra.typo3/cms.extension-key`
   - the installed version
   - the source class. `public` when `notification-url` is `https://packagist.org/downloads/`. Otherwise `path`, `vcs` or `private`, taken from `dist` and `source`.
   - the raw `typo3/cms-core` constraint

   Blockers are Gridelements, Mask, content_defender, typo3-console without a release for a rung, extensions without a release for a target major, captcha extensions without a release (forms) and extensions in the web dir without Composer.
4. Logs. Summarize `var/log/typo3_*.log` and the deprecation logs with counts, top messages and origin extension. Never copy raw lines.
5. Secrets. Check which of the four config files git tracks. Make the `.lockin-guard.json` proposal from `## Secrets` in `process.md`. Write the file only after a yes, merge with existing globs and validate the result.
6. Command confirmation. List the commands with side effects or network access and wait for an explicit confirmation, like lockin 1.3. Mark commands that bootstrap TYPO3, because they may warm `var/cache`. Candidates:
   - one lookup per public package. With `mcp: available`, call `typo3_ter_lookup` with the extension key. An `empty` answer falls back to Packagist. Otherwise run `curl -s https://packagist.org/packages/<vendor>/<name>.json`.
   - `mkdir -p` and `cp -R "<scripts>/." "<work>/tools/"`
   - `typo3 list --format=json` with the DDEV prefix. Record the provider (core or typo3-console) per command.
   - the Extension Scanner per own extension (`path` packages), with `ddev exec php .typo3-upgrade/tools/extension-scanner.php <key>` and the DDEV prefix. On 11 the capability probe may refuse. Then the backend scanner is the way.
   - with the MCP, also `typo3_project_describe`

   Run only confirmed commands. Declined commands leave their fields `unchecked`.
7. Write `<state>/inventory.md` with:
   - the header fields source, target proposal, `<repo>`, `<app>`, `<app-rel>`, `<composer-root>`, `<web-dir>`, PHP, DB, `ddev`, `mcp`, command providers, tracked config files and guard file status
   - the extension table with package, key, installed version, source class, constraint, availability per target major (`yes`, `no` or `unchecked`) and note
   - the blockers with a proposed placement
   - the log summary
   - the scanner summary, with the note that the scanner only knows the matchers of the installed core
   - the list of `unchecked` items

   Write no secrets and no raw logs.

Then continue with U3.

## U3 Roadmap

Read `<refs>/roadmap-template.md` and `<refs>/process.md`.

1. Run `mkdir -p "<state>/references" "<state>/tools"`, then `cp -R "<refs>/." "<state>/references/"` and `cp -R "<scripts>/." "<state>/tools/"`. These are frozen copies, so a plugin update cannot change the rules or the hash algorithm mid-upgrade. Do not copy into `<work>/tools/` here. If a copy fails, stop before you write `roadmap.md` or step files, show the error and say how to fix it. Without the frozen copies, `steps_hash` does not protect the rules. Read the plugin version from `<skill>/../../.claude-plugin/plugin.json` and record it.
2. Build `<state>/roadmap.md` and `<state>/steps/<nn>-<slug>.md` by the template. Point each brief to the `process.md` sections that apply, as the template says. Never copy the sections into a brief. The frozen copy and `steps_hash` protect them, and copies make every brief large and slow to write.
3. Compute `steps_hash` with `python3 "<state>/tools/tree_hash.py" "<state>/steps" "<state>/references" "<state>/tools"`.
4. Show the roadmap as a table with step, rung and group, depends and lockin mode. Add the blocker decisions and the `unchecked` items. Wait for explicit approval. Silence, a question or a partial comment is no approval.
5. On change requests, update the step files, compute the hash again and show the roadmap again.
6. After approval, record the words of the user, the date and `steps_hash` in `## Approval` of `roadmap.md`.

   If `<work>/tools/` is missing and the user did not decline the copy in U2 or in an answer given in advance, ask once whether to copy the approved scripts there now (`mkdir -p` and `cp -R "<state>/tools/." "<work>/tools/"`). The source is the frozen copy, so `<work>/tools/` matches the approved hash. Never copy without a yes. Without the copy, record `tools: missing` in `roadmap.md` and say that step briefs cannot run the tools until the copy exists.
7. Offer the optional ticket texts. Ask for German or English. Print them only and never post them.

## U4 Handoff

Pick the first step with status `planned` whose dependencies all have the outcome `pass` or `findings`.

If no step is ready, show the status table and say which dependency blocks.

Print its title, its goal and its dependencies. Print the exact command:

`/lowkey:lockin --keep [--lite] Implement the step brief in .lockin/upgrade/steps/<nn>-<slug>.md`

Add `--lite` only when the lockin mode of the step is `lite`.

Explain that `--keep` keeps the state of lockin for `--resume`. After lockin finishes, the user runs `/lowkey:typo3-upgrade --resume`.

Set the status of the step to `handed-off` with the date in `roadmap.md`. Stop. Never start lockin yourself. Never continue with the next step in the same turn.
