#!/bin/sh
# Wrapper for guard.py. Fails closed for lockin subagents when python3 is
# missing or guard.py exits with a code other than 0 or 2. Claude Code treats
# such codes as non-blocking, which would silently disable the guard.

input=$(cat)
dir=$(dirname "$0")
lockin_pattern='"agent_type"[[:space:]]*:[[:space:]]*"lowkey:lockin-'

is_lockin() {
    printf '%s' "$input" | grep -Eq "$lockin_pattern"
}

if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$input" | python3 "$dir/guard.py"
    status=$?
    if [ "$status" -eq 0 ] || [ "$status" -eq 2 ]; then
        exit "$status"
    fi
    if is_lockin; then
        echo "lowkey guard: guard.py failed with exit code $status, blocking the lockin agent call." >&2
        exit 2
    fi
    exit 0
fi

if is_lockin; then
    echo "lowkey guard: python3 not found. Install python3 or disable the lowkey plugin." >&2
    exit 2
fi
exit 0
