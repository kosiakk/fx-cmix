#!/bin/bash
# Run a shard of the ablation matrix with N concurrent workers.
#
#   ./run_all.sh [--shard I/N] [--workers K] [--push] [--only id,id,...]
#
# --shard I/N  run only variants whose index mod N == I-1 (1-based I)
# --workers K  concurrent variants (default 3; memory-bound, see below)
# --push       commit and push each result to main as it completes
# --only       explicit comma-separated variant ids, overrides --shard
#
# Concurrency is bounded by memory, not CPU. Each process reserves ~19 GB of
# address space (PPM 14.7 GB + fxcm hash tables ~4 GB + SSE ~450 MB), almost
# all of it lazily. Resident use on a 1 MB input is far smaller, but it is a
# measurement, not a guess -- run the baseline alone first and read peak_rss_kb
# out of its JSON before raising this.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

SHARD_I=1
SHARD_N=1
WORKERS=3
ONLY=""
export ABLATION_PUSH=0

while [ $# -gt 0 ]; do
  case "$1" in
    --shard)   SHARD_I="${2%%/*}"; SHARD_N="${2##*/}"; shift 2 ;;
    --workers) WORKERS="$2"; shift 2 ;;
    --only)    ONLY="$2"; shift 2 ;;
    --push)    export ABLATION_PUSH=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$HERE/results" "$HERE/logs"

mapfile -t ROWS < <(tail -n +2 "$HERE/variants.tsv" | grep -v '^[[:space:]]*$')

SELECTED=()
for i in "${!ROWS[@]}"; do
  IFS=$'\t' read -r id defines mode group desc <<< "${ROWS[$i]}"
  if [ -n "$ONLY" ]; then
    case ",$ONLY," in *",$id,"*) SELECTED+=("${ROWS[$i]}") ;; esac
  elif [ $(( i % SHARD_N )) -eq $(( SHARD_I - 1 )) ]; then
    SELECTED+=("${ROWS[$i]}")
  fi
done

echo "shard $SHARD_I/$SHARD_N: ${#SELECTED[@]} variants, $WORKERS concurrent"

FAILED=()
running=0
for row in "${SELECTED[@]}"; do
  IFS=$'\t' read -r id defines mode group desc <<< "$row"
  (
    if ! "$HERE/run_variant.sh" "$id" "$defines" "$mode" > "$HERE/logs/$id.log" 2>&1; then
      echo "FAILED $id" >> "$HERE/logs/failures"
      tail -5 "$HERE/logs/$id.log"
    fi
  ) &
  running=$((running + 1))
  if [ $running -ge $WORKERS ]; then
    wait -n
    running=$((running - 1))
  fi
done
wait

echo
if [ -s "$HERE/logs/failures" ]; then
  echo "failures:"; cat "$HERE/logs/failures"
fi
echo "results in $HERE/results:"
ls -1 "$HERE/results" 2>/dev/null | sed 's/^/  /'
