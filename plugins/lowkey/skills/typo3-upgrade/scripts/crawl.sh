#!/usr/bin/env bash
# Usage: crawl.sh [--baseline] <pages.tsv> <outdir> <base-url>
#
# Fetches every page of a pages file from a local TYPO3 site and stores the HTML
# as <outdir>/<uid>.html plus the HTTP status codes in <outdir>/status.tsv.
#
# pages.tsv   Tab separated, one page per line: uid<TAB>slug. Extra columns are ignored.
#             Empty lines and lines starting with # are skipped.
# outdir      Output folder.
# base-url    Base URL such as http://127.0.0.1:8080 (http or https).
#
# --baseline  Writes a baseline crawl. The folder must not exist. It gets the marker
#             file .baseline and no later run overwrites it. If every page returns code
#             000 (site not reachable), the run ends with exit 2 and writes no .complete.
#             The folder with .baseline stays and the caller deletes it after asking the user.
# Without it  Smoke mode. The folder may be missing or empty. A folder with the marker
#             .smoke gets reused after the script deletes the files it owns (*.html,
#             status.tsv, .smoke, .complete) directly in the folder. If the folder holds
#             any other entry (files, subfolders, .baseline), the script refuses and
#             changes nothing. Any other folder is refused.
#
# The script checks the page list first. A list without a valid entry ends with exit 2
# before the script creates or changes any folder. A symlinked <outdir> is refused in both modes.
# The marker .complete appears as the last action of a finished crawl.
# Env CRAWL_INSECURE=1 passes -k to curl (self-signed certificates).
# curl runs with globoff (-g) and a connect timeout of 10 seconds.
# Redirects are not followed. HTTP errors are data and do not change the exit code,
# except the all-000 baseline described above.
# Exit codes: 0 done, 2 usage error or refusal.

set -uo pipefail

usage() {
  echo "usage: crawl.sh [--baseline] <pages.tsv> <outdir> <base-url>" >&2
}

baseline=0
if [[ $# -ge 1 && "$1" == "--baseline" ]]; then
  baseline=1
  shift
elif [[ $# -ge 1 && "$1" == -* ]]; then
  echo "crawl: unknown option: $1" >&2
  usage
  exit 2
fi

if [[ $# -ne 3 ]]; then
  usage
  exit 2
fi

pages=$1
out=$2
base=$3

if [[ ! -f "$pages" || ! -r "$pages" ]]; then
  echo "crawl: pages file is not a readable file: $pages" >&2
  exit 2
fi

if [[ ! "$base" =~ ^https?://[^/[:space:]]+(/.*)?$ ]]; then
  echo "crawl: invalid base url: $base" >&2
  exit 2
fi
while [[ "$base" == */ ]]; do
  base=${base%/}
done

valid_entries=0
while IFS=$'\t' read -r uid slug _ || [[ -n "${uid:-}" ]]; do
  uid=${uid%$'\r'}
  slug=${slug%$'\r'}
  if [[ -z "$uid" || "$uid" == \#* ]]; then
    continue
  fi
  if [[ "$uid" =~ ^[A-Za-z0-9_-]+$ && "$slug" == /* ]]; then
    valid_entries=$((valid_entries + 1))
  fi
done < "$pages"
if [[ "$valid_entries" -eq 0 ]]; then
  echo "crawl: no valid page in $pages" >&2
  exit 2
fi

if [[ -L "$out" ]]; then
  echo "crawl: refusing symlinked output path: $out" >&2
  exit 2
fi

if [[ "$baseline" -eq 1 ]]; then
  if [[ -e "$out" || -L "$out" ]]; then
    echo "crawl: refusing to overwrite existing path: $out" >&2
    exit 2
  fi
  if ! mkdir -p "$out"; then
    echo "crawl: cannot create folder: $out" >&2
    exit 2
  fi
  if ! : > "$out/.baseline"; then
    echo "crawl: cannot write marker: $out/.baseline" >&2
    exit 2
  fi
else
  if [[ -e "$out" || -L "$out" ]]; then
    if [[ ! -d "$out" ]]; then
      echo "crawl: output path is not a directory: $out" >&2
      exit 2
    fi
    if [[ -e "$out/.baseline" ]]; then
      echo "crawl: $out is a baseline, refusing to use it for a smoke crawl" >&2
      exit 2
    fi
    if [[ -e "$out/.smoke" ]]; then
      owned=()
      while IFS= read -r -d '' entry; do
        name=${entry##*/}
        if [[ -f "$entry" && ! -L "$entry" ]] \
          && [[ "$name" == *.html || "$name" == status.tsv || "$name" == .smoke || "$name" == .complete ]]; then
          owned+=("$entry")
        else
          echo "crawl: refusing to clear smoke folder with foreign entry: $entry" >&2
          exit 2
        fi
      done < <(find "$out" -mindepth 1 -maxdepth 1 -print0)
      if [[ ${#owned[@]} -gt 0 ]] && ! rm -f -- "${owned[@]}"; then
        echo "crawl: cannot clear smoke folder: $out" >&2
        exit 2
      fi
    else
      first=$(find "$out" -mindepth 1 -maxdepth 1 -print -quit)
      if [[ -n "$first" ]]; then
        echo "crawl: refusing to use non-empty folder without marker: $out" >&2
        exit 2
      fi
    fi
  else
    if ! mkdir -p "$out"; then
      echo "crawl: cannot create folder: $out" >&2
      exit 2
    fi
  fi
  if ! : > "$out/.smoke"; then
    echo "crawl: cannot write marker: $out/.smoke" >&2
    exit 2
  fi
fi

if ! : > "$out/status.tsv"; then
  echo "crawl: cannot write status file: $out/status.tsv" >&2
  exit 2
fi

insecure=()
if [[ "${CRAWL_INSECURE:-}" == "1" ]]; then
  insecure=(-k)
fi

seen=$'\n'
crawled=0
reachable=0

while IFS=$'\t' read -r uid slug _ || [[ -n "${uid:-}" ]]; do
  uid=${uid%$'\r'}
  slug=${slug%$'\r'}
  if [[ -z "$uid" || "$uid" == \#* ]]; then
    continue
  fi
  if [[ ! "$uid" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "crawl: skipping invalid uid: $uid" >&2
    continue
  fi
  if [[ "$slug" != /* ]]; then
    echo "crawl: skipping uid $uid: slug must start with /" >&2
    continue
  fi
  if [[ "$seen" == *$'\n'"$uid"$'\n'* ]]; then
    echo "crawl: skipping repeated uid: $uid" >&2
    continue
  fi
  seen+="$uid"$'\n'

  code=$(curl -s -o "$out/$uid.html" -w '%{http_code}' -g --connect-timeout 10 --max-time 20 \
    "${insecure[@]+"${insecure[@]}"}" "$base$slug" < /dev/null)
  if [[ ! "$code" =~ ^[0-9]{3}$ ]]; then
    code=000
  fi
  if [[ "$code" != "000" ]]; then
    reachable=$((reachable + 1))
  fi
  if ! printf '%s\t%s\t%s\n' "$uid" "$slug" "$code" >> "$out/status.tsv"; then
    echo "crawl: cannot write status file: $out/status.tsv" >&2
    exit 2
  fi
  crawled=$((crawled + 1))
done < "$pages"

if [[ "$crawled" -eq 0 ]]; then
  echo "crawl: no valid page in $pages" >&2
  exit 2
fi

if [[ "$baseline" -eq 1 && "$reachable" -eq 0 ]]; then
  echo "crawl: site not reachable, every page returned 000. Baseline is not complete: $out" >&2
  exit 2
fi

if ! : > "$out/.complete"; then
  echo "crawl: cannot write marker: $out/.complete" >&2
  exit 2
fi

cut -f3 "$out/status.tsv" | sort | uniq -c
exit 0
