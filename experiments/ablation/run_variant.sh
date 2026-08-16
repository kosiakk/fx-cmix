#!/bin/bash
# Build and measure one ablation variant.
#
#   ./run_variant.sh <id> <defines> <mode>
#
# <defines> is the -DABLATE_* string, or "-" for none.
# <mode> selects the CLI preprocessing level:
#   nodict  cmix -c IN OUT              text detection only (the baseline)
#   dict    cmix -c english.dic IN OUT  WRT dictionary transform + pretraining
#   noprep  cmix -n IN OUT              nothing
#
# Writes experiments/ablation/results/<id>.json and exits non-zero if the
# build fails or a round trip does not reproduce its input byte-for-byte.
set -uo pipefail

ID="$1"
DEFINES="$2"
MODE="$3"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_ROOT="${ABLATION_BUILD_ROOT:-/tmp/fx-cmix-ablation}"
BUILD="$BUILD_ROOT/$ID"
RESULTS="$REPO/experiments/ablation/results"
SEED="${SEED:-923}"
UPDATE_LIMIT="${UPDATE_LIMIT:-3000}"
MARCH="${MARCH:-x86-64-v3}"

# Seed replicates are the same source built with a different RNG seed.
case "$ID" in
  seed1)    SEED=1 ;;
  seed7919) SEED=7919 ;;
esac

[ "$DEFINES" = "-" ] && DEFINES=""

mkdir -p "$RESULTS" "$BUILD"
rm -rf "$BUILD"
mkdir -p "$BUILD"
# Isolated build tree: the makefile writes *.o and cmix into the working
# directory with fixed names, so concurrent variants would corrupt each other.
cp -a "$REPO/src" "$REPO/makefile" "$BUILD/"

echo "[$ID] building (SEED=$SEED MARCH=$MARCH ${DEFINES:-no ablation flags})"
BUILD_LOG="$BUILD/build.log"
if ! make -C "$BUILD" MARCH="$MARCH" \
      CFLAGS_DEFINES="-DSEED=$SEED -DUPDATE_LIMIT=$UPDATE_LIMIT $DEFINES" \
      cmix > "$BUILD_LOG" 2>&1; then
  echo "[$ID] BUILD FAILED, see $BUILD_LOG" >&2
  tail -20 "$BUILD_LOG" >&2
  exit 1
fi

# --defines must use the = form: its value starts with "-", which argparse
# would otherwise parse as another flag.
python3 "$REPO/experiments/ablation/measure.py" \
  --id "$ID" --binary "$BUILD/cmix" --mode "$MODE" \
  --defines="${DEFINES:-none}" --seed "$SEED" --march "$MARCH" \
  --repo "$REPO" --out "$RESULTS/$ID.json"
STATUS=$?

if [ $STATUS -eq 0 ] && [ "${ABLATION_PUSH:-0}" = "1" ]; then
  "$REPO/experiments/ablation/publish.sh" "$ID"
fi
exit $STATUS
