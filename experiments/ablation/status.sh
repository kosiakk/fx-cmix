#!/bin/bash
# Live status of ablation variants running on this machine.
#
#   ./status.sh          once
#   ./status.sh -w [sec] repeat every N seconds (default 60)
#
# cmix writes "<percent> <output_bytes>" to ./progress.log in its working
# directory, which for this harness is the variant's build tree. That file is
# the only real progress signal -- the compressor's stderr is a carriage-return
# progress bar, and a multi-hour run otherwise looks identical to a hung one.
set -uo pipefail

BUILD_ROOT="${ABLATION_BUILD_ROOT:-/tmp/fx-cmix-ablation}"
WATCH=0
INTERVAL="${2:-60}"
[ "${1:-}" = "-w" ] && WATCH=1

show() {
  printf "%-14s %7s %10s %9s %8s %9s %s\n" \
    VARIANT PCT OUT_MB BPC_EST ELAPSED ETA RSS_GB
  local any=0
  for d in "$BUILD_ROOT"/*/; do
    [ -d "$d" ] || continue
    local name pct outb line pid rss el
    name=$(basename "$d")
    case "$name" in *.lock) continue ;; esac
    line=$(tail -c 4000 "$d/progress.log" 2>/dev/null | tr '\r' '\n' | grep -E '^[0-9]' | tail -1)
    [ -n "$line" ] || continue
    any=1
    pct=$(echo "$line" | awk '{print $1}')
    outb=$(echo "$line" | awk '{print $2}')

    # Match on the binary path in /proc rather than pgrep: the pattern contains
    # slashes and pgrep -f was silently matching nothing.
    pid=""
    for p in /proc/[0-9]*; do
      [ -r "$p/cmdline" ] || continue
      case "$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)" in
        *"$BUILD_ROOT/$name/cmix "*) pid=${p#/proc/}; break ;;
      esac
    done
    if [ -n "$pid" ]; then
      rss=$(awk '/VmRSS/{printf "%.1f", $2/1048576}' /proc/"$pid"/status 2>/dev/null)
      el=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')
    fi

    # bits/char extrapolated from the fraction done so far. Compression
    # improves as the model warms, so this reads pessimistic early on -- which
    # means BPC_EST is only comparable between variants at similar PCT. A
    # variant further along will look better than it is.
    awk -v n="$name" -v p="$pct" -v o="$outb" -v e="${el:-0}" -v r="${rss:-0}" 'BEGIN{
      mb = o/1048576
      bpc = (p > 0) ? (o/(p/100)) * 8 / 100000000 : 0
      eta = (p > 0 && e > 0) ? (e/(p/100) - e)/3600 : 0
      printf "%-14s %6.2f%% %9.1f %9.4f %7.1fh %8.1fh %6.1f\n", n, p, mb, bpc, e/3600, eta, r
    }'
  done
  [ "$any" = "1" ] || echo "(no variants with progress under $BUILD_ROOT)"
}

if [ "$WATCH" = "1" ]; then
  while :; do
    clear 2>/dev/null || true
    echo "== $(hostname) $(date -u +%FT%TZ) =="
    show
    sleep "$INTERVAL"
  done
else
  echo "== $(hostname) $(date -u +%FT%TZ) =="
  show
fi
