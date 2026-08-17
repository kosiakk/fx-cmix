#!/bin/bash
# Run variants in both preprocessing arms, two at a time.
#
#   ./run_pairs.sh <corpus> <id,id,...>
#
# Bypasses run_all's machine-wide runner lock on purpose: this is meant to run
# alongside a long shard, using cores that shard leaves idle. Each variant
# still takes its own per-variant lock.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$HERE"
CORPUS="$1"; IDS="$2"; N=0
for id in ${IDS//,/ }; do
  D=$(awk -F'\t' -v v="$id" '$1==v{print $2}' variants.tsv)
  [ -n "$D" ] || { echo "unknown variant: $id" >&2; continue; }
  for mode in dict nodict; do
    ( MARCH=native ABLATION_PGO=1 ABLATION_CORPORA="$CORPUS" \
        ./run_variant.sh "$id" "$D" "$mode" > "logs/${id}_${mode}.log" 2>&1
      tail -1 "logs/${id}_${mode}.log" ) &
    N=$((N+1)); [ $((N % 2)) -eq 0 ] && wait
  done
done
wait
