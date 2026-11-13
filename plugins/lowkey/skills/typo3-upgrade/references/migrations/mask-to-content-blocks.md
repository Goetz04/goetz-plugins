# Mask to Content Blocks

Read this file for the blocker migration step of the roadmap. Binding rules (command classes, snapshots, folders, outcomes) live in `process.md`. This file adds the procedure.

Check the current release of `nhovratov/mask-to-content-blocks` and of Content Blocks before use. Do not trust a number. Status of the commands is `practice`. Check them against the installed versions with `--help`.

## When to run it

Run it on TYPO3 13, after the rung 12 to 13 has passed. Mask elements run on the old version until then. Content Blocks 2.x was the practice version (check the current release, do not trust this number).

## Preconditions

- The rung 12 to 13 has the outcome `pass` or `findings`, and `upgrade:list` is empty.
- A crawl baseline of all pages with Mask elements exists (`verification.md`).
- The inventory lists every Mask element, its fields and its child tables (counts only).
- A snapshot exists: `ddev snapshot --name pre-<nn>-<stage>-<k>` (main session command).
- Composer commands run with `--no-scripts` (`composer.md`).

## Procedure

1. Install `nhovratov/mask-to-content-blocks` and Content Blocks (Composer, main session command, snapshot before). Run the tool to generate the content blocks from the Mask definitions.
2. Keep every name. Use `typeName: mask_*` for content types, `prefixFields: false` for fields and `foreign_field: parentid` for child tables. The data stays in place, so no data migration runs.
3. Add `foreign_table_field: parenttable` to the child table definitions. The tool drops it.
4. Pin the Mask SQL column types in `ext_tables.sql`. Content Blocks emits no SQL for these fields, and the types that it derives from TCA are lossy (a nullable text column becomes an integer column).
5. Run the schema gate (`database:updateschema "*" --dry-run` and `--raw`, check commands). The gate allows no change and no create on `tx_mask_*` tables, except new indexes. Any other entry blocks the step.
6. Fix link fields. They are `TypolinkParameter` objects and always truthy. Test `{field.url}` in conditions.
7. Fix file fields with `maxitems: 1`. They stay a collection unless `relationship` is set. Adapt the template or set `relationship`.
8. Drop the fluid_styled_content frame. Mask rendered without it. Remove the `TYPO3/Appearance` basics from the content blocks, otherwise a frame wrapper changes the output.
9. Write an own `backend-preview.html` for elements that have child tables and no `header` field.
10. Run `content-blocks:lint` after every `config.yaml` change (check command).
11. Run the crawl diff against the baseline (`verification.md`). Approve expected diffs in the expect file.
12. Remove Mask afterwards. Remove the package with Composer (main session command, `--no-scripts`). Remove its static include from the site setup. Remove the `EXTENSIONS/mask` configuration with `configuration:remove` (main session command, with `--force` after approval, then check with `configuration:show`, see `schema-and-wizards.md`).

## Gates

- The schema dry-run shows no change or create on `tx_mask_*` tables, except new indexes.
- `content-blocks:lint` passes after the last `config.yaml` change.
- The crawl diff on all pages with Mask elements stays within the expected diffs.
- Link conditions use `{field.url}`, and a test with an empty link shows no output.
- The backend preview of every element with child tables shows a useful label.
- `upgrade:list` stays empty, and `referenceindex:update --check` reports a perfect index at the rung exit.

## Go-live order

1. `backend:lock`
2. `composer install --no-scripts`
3. Schema dry-run (check command), then `database:updateschema "*.add"` if the dry-run lists adds
4. `extension:setup`
5. Remove Mask and its configuration as in procedure step 12
6. `referenceindex:update`
7. `backend:unlock`

Take a snapshot or backup before step 2, and keep the restore command ready. Derive the final schema list from the dry-run on a live copy (`schema-and-wizards.md`).

## Proof

- The crawl diff shows equal output for every Mask element, or only approved diffs.
- The schema gate holds no entry for `tx_mask_*` besides new indexes.
- Mask no longer appears in `composer.lock`, and `configuration:show` finds no `EXTENSIONS/mask` path.
- The backend opens every element and its children, and saving them changes no stored column (open-and-save row diff, `verification.md`).
