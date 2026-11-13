# Gridelements to container

Read this file for the blocker migration step of the roadmap. Binding rules (command classes, snapshots, folders, outcomes) live in `process.md`. The `sql_mode` trap lives in `database.md` (`### sql_mode trap before a Gridelements migration`). This file adds the procedure.

Status of the container commands (`container:sorting`, `container:integrity`) is `practice`. Check their names, options and provider against the installed version with `typo3 list` and `--help` before use. Check the current release of EXT:container, do not trust a number.

## When to run it

Run the migration on the source version where both extensions work. In the common case that is TYPO3 11, in the stage group that `roadmap.md` names for the blocker step. It runs before the jump of its rung, because Gridelements has no release for the target.

Run it again on every live copy and at go-live (see the go-live order below).

## Preconditions

- Both extensions (Gridelements and container) are installed and active on the source version.
- A snapshot exists: `ddev snapshot --name pre-<nn>-<stage>-<k>` (main session command).
- The inventory lists every grid layout in use, with its columns and the count of elements per layout (counts only).
- The `tt_content.colPos` column has not changed its type yet. Do not run the schema change for `tt_content` before this migration is done.
- A crawl baseline of all pages that use grid elements exists (`verification.md`).

## Procedure

1. Map each grid layout to one container CType, one to one. Write the mapping into the step notes.
2. Map each grid column to a `colPos` of the container. Keep the column order.
3. Register the container CTypes in the project code with the mapped columns (code change, stage B or the step's own package).
4. Keep the Gridelements FlexForm in `pi_flexform` unchanged, so no data is lost and the migration stays reversible.
5. Write an own migration command. It must meet these rules:
   - It is idempotent. A second run changes nothing.
   - It has a `--dry-run` option that writes nothing and reports the planned changes as counts.
   - It runs in one transaction.
   - It rolls back and exits non-zero if any negative `colPos` remains after the run.
6. Run `<migration command> --dry-run` (check command). Read the counts against the inventory.
7. Take the snapshot `pre-<nn>-<stage>-<k>`. Run the migration command (main session command).
8. Handle children in unknown columns. Gridelements skips them silently, and container reports them. Move them to the first column of their container and hide them. Report the count of moved elements.
9. Run `container:sorting` in verbose mode first (main session command, read the output). Container needs children sorted after their parent. Then run `container:sorting --apply` (main session command).
10. Run `container:integrity` (check command).
11. Run the crawl diff against the baseline (`verification.md`). Approve expected diffs in the expect file.

Run `database:updateschema "*.change"` for `tt_content` only after the migration reports no negative `colPos` (`database.md`).

## Gates

- The migration dry-run reports counts that match the inventory.
- No row has a negative `colPos` after the migration. Count with a query on the live copy (counts only).
- `container:integrity` reports no problem.
- The row counts per `colPos` match before and after the later schema change.
- The crawl diff shows no change beyond the expected diffs. Hidden children do not appear on pages.
- `referenceindex:update --check` reports a perfect index at the rung exit (`schema-and-wizards.md`).

## Go-live order

Run in this order on the live copy and at go-live. Every command is a main session command, except the check commands named in the procedure.

1. `backend:lock`
2. `composer install --no-scripts`
3. `database:updateschema "*.add"`
4. Migration command with `--dry-run`
5. Migration command
6. `database:updateschema "*.change"`
7. `extension:setup`
8. `container:sorting --apply`
9. `referenceindex:update`
10. `container:integrity`
11. `backend:unlock`

Take a snapshot or backup before step 3, and keep the restore command ready.

## Proof

- The migration output lists the converted element counts per layout, and they match the inventory.
- No negative `colPos` remains.
- `container:integrity` reports a clean state.
- The crawl diff on all pages with grid elements stays within the expected diffs.
- The backend shows each container with its children in the right columns.
