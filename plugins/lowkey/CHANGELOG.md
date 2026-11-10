# Changelog

All notable changes to the lowkey plugin are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the plugin uses [Semantic Versioning](https://semver.org/).

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
