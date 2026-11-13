#!/usr/bin/env bash
# Usage: htmldiff.sh <dirA> <dirB>
#        htmldiff.sh --normalize <file>
#
# Quick overview diff of two crawls made with crawl.sh.
# Prints one line per finding:
#   STATUS <uid> <codeA> <codeB>   HTTP status differs
#   MISSING <uid> <A|B>            uid is missing in that crawl's status.tsv
#   MISSING <uid>.html <A|B>       HTML file is missing in that crawl
#   <uid> <count>                  number of changed lines after normalization
#
# --normalize prints the normalized form of one file (for tests and manual checks).
# Normalization removes only the tags of honeypot fields, [__state] fields and the default
# twitter card (content="summary") and keeps
# the rest of the line. Lines that are blank afterwards disappear. It masks cache busters,
# _assets hashes, the generator meta tag and processed image paths.
#
# Env OLD_HOST and NEW_HOST: set both to replace the literal old host with the new
# host before comparing. Setting only one is an error.
#
# Exit codes: 0 no difference, 1 differences printed, 2 error.

set -uo pipefail

usage() {
  echo "usage: htmldiff.sh <dirA> <dirB> | htmldiff.sh --normalize <file>" >&2
}

old_host=${OLD_HOST:-}
new_host=${NEW_HOST:-}
if [[ -n "$old_host" && -z "$new_host" ]] || [[ -z "$old_host" && -n "$new_host" ]]; then
  echo "htmldiff: set both OLD_HOST and NEW_HOST or neither" >&2
  exit 2
fi

sed_args=(-e 's/<[^<>]*(margin:0 0 0 -999em|\[__state\])[^<>]*>//g')
# TYPO3 13 no longer always renders the default twitter card. Drop only the default tag, in both attribute orders.
sed_args+=(
  -e 's/<meta[^<>]*name="twitter:card"[^<>]*content="summary"[^<>]*>//g'
  -e 's/<meta[^<>]*content="summary"[^<>]*name="twitter:card"[^<>]*>//g'
)
if [[ -n "$old_host" ]]; then
  # Escape every ERE metacharacter, because the patterns below run with sed -E.
  old_esc=$(printf '%s' "$old_host" | sed 's/[][\.*^$/+?(){}|]/\\&/g')
  new_esc=$(printf '%s' "$new_host" | sed 's/[\/&]/\\&/g')
  sed_args+=(-e "s/$old_esc/$new_esc/g")
fi
sed_args+=(
  -e 's/\?[0-9]{9,11}//g'
  -e 's/_assets\/[0-9a-f]{32}/_assets\/HASH/g'
  -e 's/<meta name="generator"[^>]*>/GEN/'
  -e 's/_processed_\/[0-9a-f]\/[0-9a-f]\/[^"]*/PROCESSED/g'
)

# Print the normalized form of one file.
norm() {
  { grep -avE '^\s*$' "$1" || true; } | sed -E "${sed_args[@]}" | { grep -avE '^\s*$' || true; }
}

if [[ $# -ge 1 && "$1" == "--normalize" ]]; then
  if [[ $# -ne 2 ]]; then
    usage
    exit 2
  fi
  if [[ ! -f "$2" || ! -r "$2" ]]; then
    echo "htmldiff: not a readable file: $2" >&2
    exit 2
  fi
  norm "$2"
  exit 0
fi

if [[ $# -ne 2 ]]; then
  usage
  exit 2
fi

a=$1
b=$2
for dir in "$a" "$b"; do
  if [[ ! -d "$dir" ]]; then
    echo "htmldiff: not a directory: $dir" >&2
    exit 2
  fi
  if [[ ! -f "$dir/status.tsv" || ! -r "$dir/status.tsv" ]]; then
    echo "htmldiff: missing status.tsv in $dir" >&2
    exit 2
  fi
done

found=0

# Compare status codes by uid, not by line order.
status_lines=$(awk -F'\t' '
  NF == 0 { next }
  FILENAME == ARGV[1] { codeA[$1] = $3; orderA[++na] = $1; next }
  { codeB[$1] = $3; orderB[++nb] = $1 }
  END {
    for (i = 1; i <= na; i++) {
      u = orderA[i]
      if (u in doneA) continue
      doneA[u] = 1
      if (!(u in codeB)) print "MISSING " u " B"
      else if (codeA[u] != codeB[u]) print "STATUS " u " " codeA[u] " " codeB[u]
    }
    for (i = 1; i <= nb; i++) {
      u = orderB[i]
      if (u in doneB) continue
      doneB[u] = 1
      if (!(u in codeA)) print "MISSING " u " A"
    }
  }
' "$a/status.tsv" "$b/status.tsv")
if [[ $? -ne 0 ]]; then
  echo "htmldiff: cannot compare status files" >&2
  exit 2
fi
if [[ -n "$status_lines" ]]; then
  printf '%s\n' "$status_lines"
  found=1
fi

# Compare the HTML of every uid that both crawls list.
common=$(awk -F'\t' '
  NF == 0 { next }
  FILENAME == ARGV[1] { inA[$1] = 1; next }
  ($1 in inA) && !($1 in done) { done[$1] = 1; print $1 }
' "$a/status.tsv" "$b/status.tsv")
if [[ $? -ne 0 ]]; then
  echo "htmldiff: cannot compare status files" >&2
  exit 2
fi

while IFS= read -r uid; do
  uid=${uid%$'\r'}
  if [[ -z "$uid" ]]; then
    continue
  fi
  if [[ ! "$uid" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "htmldiff: invalid uid in status.tsv: $uid" >&2
    exit 2
  fi
  missing=0
  if [[ ! -f "$a/$uid.html" ]]; then
    echo "MISSING $uid.html A"
    missing=1
  fi
  if [[ ! -f "$b/$uid.html" ]]; then
    echo "MISSING $uid.html B"
    missing=1
  fi
  if [[ "$missing" -eq 1 ]]; then
    found=1
    continue
  fi
  count=$(diff <(norm "$a/$uid.html") <(norm "$b/$uid.html") | grep -c '^[<>]' || true)
  if [[ "${count:-0}" -gt 0 ]]; then
    echo "$uid $count"
    found=1
  fi
done <<< "$common"

if [[ "$found" -eq 1 ]]; then
  exit 1
fi
exit 0
