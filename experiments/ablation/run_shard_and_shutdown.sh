#!/bin/bash
# Run a shard of enwik8 variants, publish results to GCS, then power the VM off.
#
#   ./run_shard_and_shutdown.sh <bucket> <variant,variant,...> [workers]
#
# Designed to be launched detached and left alone for many hours. Unlike the
# ephemeral containers this study started on, a GCE VM stays up, so a plain
# setsid/nohup process is the right tool -- no agent needs to babysit it.
#
# Results go to GCS rather than straight to git so that no credential with
# write access to the repository has to live on the VM. Each variant writes its
# own file, so shards never conflict; the git commit happens elsewhere.
#
# The VM shuts itself down when finished. That is the cost control: an idle
# c3-highmem-8 costs real money, and these runs take many hours with nobody
# watching the end of them.
set -uo pipefail

BUCKET="${1:?usage: $0 <gs://bucket> <variants> [workers]}"
VARIANTS="${2:?usage: $0 <gs://bucket> <variants> [workers]}"
WORKERS="${3:-2}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

HOSTNAME_TAG="$(hostname)"
LOG="$HERE/logs/shard_${HOSTNAME_TAG}.log"
mkdir -p "$HERE/logs" "$HERE/results"

RC_FILE="$HERE/logs/.shard_rc"
rm -f "$RC_FILE"

# The body is piped to tee, so it runs in a subshell -- an `exit` inside it
# would only leave the subshell and execution would fall through to the
# shutdown below. The exit status therefore travels via a file.
{
  echo "=== $(date -u +%FT%TZ) starting $VARIANTS on $HOSTNAME_TAG (workers=$WORKERS) ==="

  # PGO plus -march=native: this is the fastest build, and every variant in
  # this comparison is built the same way, which is what actually matters.
  ABLATION_PGO=1 MARCH=native \
    ./run_all.sh --only "$VARIANTS" --corpora enwik8 --workers "$WORKERS" --resume
  RC=$?
  echo "$RC" > "$RC_FILE"
  echo "=== $(date -u +%FT%TZ) run_all exited rc=$RC ==="

  if [ "$RC" -ne 4 ]; then
    # Upload whatever exists, even on failure -- a partial result is still
    # data, and a failed run is itself a finding worth keeping.
    for f in "$HERE"/results/e8_*.json; do
      [ -e "$f" ] || continue
      gcloud storage cp "$f" "$BUCKET/results/" && echo "uploaded $(basename "$f")"
    done
  fi
} 2>&1 | tee -a "$LOG"

gcloud storage cp "$LOG" "$BUCKET/logs/" 2>/dev/null || true

# rc=4 means no variant matched: a caller error, not a finished shard. Staying
# up costs money, but powering off a provisioned machine because of a typo
# costs more -- and that is exactly what happened once.
if [ "$(cat "$RC_FILE" 2>/dev/null || echo 1)" = "4" ]; then
  echo "NOT shutting down: no variants matched. Fix the ids and relaunch."
  exit 4
fi

echo "=== $(date -u +%FT%TZ) shutting down ==="
sudo shutdown -h +1
