# Composer

Read this file for stage group C+D of every rung and for any step that changes packages. It covers the Composer flags of the jump, the installer change on TYPO3 12, private repositories and path packages. Binding rules live in `process.md`. This file points to its headings.

Every Composer command is a main session command. The guard blocks Composer install, update, require and remove for the implementer (`process.md` `## Guard limits`). Take the snapshot `pre-<nn>-<stage>-<k>` before each one (`process.md` `## Main session commands`; `<k>` is the attempt number from `## Stage groups`).

### Scripts until the schema gate
- Symptom: A Composer run writes schema changes before the schema gate. The site breaks halfway or a later diff has two causes.
- Detection: The `post-autoload-dump` script runs `extension:setup`, which writes schema add and change statements. Look for it in `composer.json` and in the output of the run.
- Fix: Run every Composer command with `--no-scripts` until the schema gate has passed (`schema-and-wizards.md`). Then run `extension:setup` explicitly. It also writes missing default values of the extension configuration. Both are main session commands.
- Proof: `database:updateschema "*" --dry-run` (check command) lists the pending changes after the jump instead of an empty list.
- Status: practice

### No-blocking flag and package age
- Symptom: Composer 2.9 and later blocks the update because of TYPO3 security advisories. The flag that lets the update pass may also skip the release cooldown.
- Detection: Read `composer update --help` for the exact flag before use. After the update, read the `time` of every new or changed package in `composer.lock`.
- Fix: Use `--no-blocking` only when the advisories block the update and the step brief names them. Review every very fresh release by hand. Main session command.
- Proof: The step notes list each reviewed package with its `time` value.
- Status: unverified (the flag and its effect on the cooldown are not confirmed, see `process.md` `## Command matrix`)

### Installers v5 on TYPO3 12
- Symptom: Assets and extension files disappear from the old paths after the jump. Pages lose CSS, JS or images.
- Detection: Extensions now live in `vendor/`. Public resources land in `<web-dir>/_assets/`. Grep stored content for old paths, for example `tt_content.bodytext` for `typo3conf/ext` (report counts only). Grep templates and TypoScript for the same string.
- Fix: Reference every file through `EXT:` paths or `f:uri.resource`. Replace `typo3conf/ext` paths in stored content with a data migration. That is a main session command with a snapshot before.
- Proof: A crawl diff shows no change in asset URLs beyond the expected diffs. Every asset and link URL returns 200 (`verification.md`).
- Status: practice

### Second install after the first update
- Symptom: After the first `composer update`, the installed files do not match the new installer. The old installer stayed in memory during that run.
- Detection: Extensions or resources appear in the old locations, or `<web-dir>/_assets/` is incomplete.
- Fix: Run `composer install --no-scripts` once more (main session command).
- Proof: A second `composer install --no-scripts` reports nothing to change. The resources exist in `<web-dir>/_assets/`.
- Status: practice

### Private repositories
- Symptom: Composer asks for credentials or fails to reach a private repository.
- Detection: The repository entry in `composer.json` points to a private source.
- Fix: Keep the credentials in an `auth.json` outside the repository. Never read it and never print it (`process.md` `## Secrets`). Ask the user to run or fix the command that needs it.
- Proof: The Composer run reaches the repository without a prompt.
- Status: practice

### Path packages
- Symptom: A path package breaks `dev-*` constraints after someone adds a `version` key to its `composer.json`.
- Detection: Look for a `version` key in the `composer.json` of each path package.
- Fix: Do not add a `version` key. Refresh only its lock entry with `composer update <pkg> --no-scripts` (main session command).
- Proof: `composer.lock` shows the path package with the expected reference and the update touched no other package.
- Status: practice

### Lookups for public packages
- Symptom: A lookup sends a private package name to a public service.
- Detection: The `composer.lock` entry of a public package carries the `notification-url` `https://packagist.org/downloads/`.
- Fix: Look up only packages with that URL. Path, VCS and private packages stay `unchecked`.
- Proof: The inventory records the raw `typo3/cms-core` constraint next to each verdict and lists no private package name in a lookup.
- Status: practice
