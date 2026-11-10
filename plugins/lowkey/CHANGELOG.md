# Changelog

All notable changes to the lowkey plugin are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the plugin uses [Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-11-10

### Added

- Automatic cleanup. The wrap-up deletes `.lockin/<slug>/` after the summary. `--keep` keeps the state of a run.
- `review/` folder for diff, new file list and redacted test output. The reviewers read these files instead of receiving them inline. The folder gets deleted at the end of Phase 5.
- The tree fingerprint hashes the content of untracked files, so resume detects changes to new files.
- Guard hook for the lockin subagents (`hooks/hooks.json`, `guard.sh`, `guard.py`). It blocks secret files for all four agents. For the implementer it also blocks writes to `.lockin/`, git commands other than read-only ones and package installs. The guard fails closed for lockin agents and never affects other agents or the main session. It needs `python3`.
- Eval suite in `evals/` with four cases for the gates of the workflow: empty arguments, analysis-only exit, resume without runs and no changes before approval.

### Changed

- `plan.md` contains the work package list with files and model. The approval hash covers it, and Phase 4 only expands the approved list.
- The `Verification` field of a work package may only contain user-confirmed commands. The implementer runs only these commands and read-only git.
- The implementer receives the path of its package file instead of the full text.
- The challenge loop also stops on `CRITICAL OBJECTIONS: 0`. The plan challenger uses this form only for one or more objections.
- The resume instructions moved to `skills/lockin/resume.md` and load only on `--resume`.

## [1.1.0] - 2026-11-10

### Added

- State files in `.lockin/<slug>/` and `--resume [slug]` to continue a run.
- Baseline in Phase 1: HEAD, working tree status and check-mode test results. The test commands run only after user confirmation.
- Git base and pre-existing change handling before Phase 4. Overlapping uncommitted changes block the run.
- Analysis-only exit for tasks without a change request.
- `Verification` field in work packages for projects without automated tests.
- Model choice per work package and a fixed retry ladder (planned model, then Sonnet, then main session or user).
- Commit message, PR description draft and staging path list in the wrap-up.

### Changed

- The skill requires a git repository.
- Reviewers receive the baseline test results and flag only new or changed failures.
- The plan challenger, the correctness reviewer and the main session never read secrets. The implementer and the risk reviewer already followed this rule.
- Agents never modify or review pre-existing user changes.
- The plan challenger verdict line is defined as the first line under `## Verdict`.
- The version lives only in `plugin.json`.

## [1.0.0] - 2026-11-10

### Added

- Initial release with the `lockin` skill and four subagents.
