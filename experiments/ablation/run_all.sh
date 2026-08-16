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
RESUME=0
export ABLATION_PUSH=0
export ABLATION_QUICK=0
export ABLATION_CORPORA=""
export ABLATION_PGO=0

while [ $# -gt 0 ]; do
  case "$1" in
    --shard)   SHARD_I="${2%%/*}"; SHARD_N="${2##*/}"; shift 2 ;;
    --workers) WORKERS="$2"; shift 2 ;;
    --only)    ONLY="$2"; shift 2 ;;
    --push)    export ABLATION_PUSH=1; shift ;;
    --quick)   export ABLATION_QUICK=1; shift ;;
    --corpora) export ABLATION_CORPORA="$2"; shift 2 ;;
    --pgo)     export ABLATION_PGO=1; shift ;;
    --resume)  RESUME=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# A variant counts as done if it has a result that did not fail and that covers
# the corpora this invocation asks for. Runs get interrupted -- this machine's
# container has been restarted mid-matrix -- so resuming must be cheap and must
# never silently accept a partial result.
is_done() {
  python3 - "$HERE/results/$1.json" "$ABLATION_QUICK" "$ABLATION_CORPORA" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
if d.get("failed"):
    sys.exit(1)
if sys.argv[2] == "1":
    need = ["input"]
elif len(sys.argv) > 3 and sys.argv[3]:
    need = [c.strip() for c in sys.argv[3].split(",") if c.strip()]
else:
    need = ["input", "input2"]
sys.exit(0 if all(c in d.get("corpora", {}) for c in need) else 1)
PY
}

mkdir -p "$HERE/results" "$HERE/logs"

# One runner per machine. --workers bounds concurrency within a runner, so two
# overlapping runners silently double it -- which on this box meant 4 concurrent
# variants, 15 GB exhausted, and an OOM-killed baseline. Refuse rather than
# oversubscribe.
BUILD_ROOT_LOCK="${ABLATION_BUILD_ROOT:-/tmp/fx-cmix-ablation}"
mkdir -p "$BUILD_ROOT_LOCK"
RUNNER_LOCK="$BUILD_ROOT_LOCK/runner.lock"
if ! mkdir "$RUNNER_LOCK" 2>/dev/null; then
  OWNER=$(cat "$RUNNER_LOCK/pid" 2>/dev/null || echo "")
  if [ -n "$OWNER" ] && kill -0 "$OWNER" 2>/dev/null; then
    echo "another runner is already active on this machine (pid $OWNER)." >&2
    echo "wait for it, or stop it before starting another." >&2
    exit 3
  fi
  rm -rf "$RUNNER_LOCK"; mkdir "$RUNNER_LOCK" 2>/dev/null || exit 3
fi
echo $$ > "$RUNNER_LOCK/pid"
trap 'rm -rf "$RUNNER_LOCK"' EXIT INT TERM

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

# Selecting nothing is a mistake in the caller, not a finished run. Say so and
# fail, so a self-terminating runner does not power the machine off having
# done no work.
if [ ${#SELECTED[@]} -eq 0 ]; then
  echo "no variants matched -- check the ids against variants.tsv" >&2
  exit 4
fi

FAILED=()
running=0
for row in "${SELECTED[@]}"; do
  IFS=$'\t' read -r id defines mode group desc <<< "$row"
  if [ $RESUME -eq 1 ] && is_done "$id"; then
    echo "[$id] already done, skipping"
    continue
  fi
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
if [ -s "$HERE/logs/failures" ]; then
  nfail=$(wc -l < "$HERE/logs/failures")
  if [ "$nfail" -ge "${#SELECTED[@]}" ]; then
    echo "every selected variant failed -- not a completed shard" >&2
    echo "results in $HERE/results:"
    ls -1 "$HERE/results" 2>/dev/null | sed 's/^/  /'
    exit 5
  fi
fi

echo "results in $HERE/results:"
ls -1 "$HERE/results" 2>/dev/null | sed 's/^/  /'
