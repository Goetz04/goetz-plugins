#!/usr/bin/env python3
"""Check that marketplace.json and each plugin.json agree on shared metadata.

Exits with 1 and lists every mismatch, so CI fails on drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
SHARED_FIELDS = ("description", "author", "license", "homepage", "repository", "keywords")


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    marketplace = load(MARKETPLACE)
    errors: list[str] = []
    for entry in marketplace.get("plugins", []):
        name = entry.get("name", "<unnamed>")
        manifest_path = (MARKETPLACE.parent.parent / entry["source"] / ".claude-plugin" / "plugin.json").resolve()
        if not manifest_path.is_file():
            errors.append(f"{name}: plugin.json not found at {manifest_path}")
            continue
        manifest = load(manifest_path)
        if manifest.get("name") != name:
            errors.append(f"{name}: name differs from plugin.json ({manifest.get('name')!r})")
        for field in SHARED_FIELDS:
            if entry.get(field) != manifest.get(field):
                errors.append(
                    f"{name}: {field} differs\n  marketplace.json: {entry.get(field)!r}\n  plugin.json:      {manifest.get(field)!r}"
                )
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print(f"Metadata consistent for {len(marketplace.get('plugins', []))} plugin(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
