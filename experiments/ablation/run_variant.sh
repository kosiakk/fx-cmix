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
# Keyed by mode as well: mode is a runtime flag, not a compile flag, so the
# binary would be identical -- but the two runs write enwik8.comp and
# progress.log into the same directory and would clobber each other.
BUILD="$BUILD_ROOT/$MODE/$ID"
# Results are keyed by mode: the dictionary is an ablation axis in its own
# right, not a setting to choose once. The same mechanism can earn a
# different amount depending on whether WRT already removed the redundancy
# it exploits, and that interaction is a result.
RESULTS="$REPO/experiments/ablation/results/$MODE"
SEED="${SEED:-923}"
UPDATE_LIMIT="${UPDATE_LIMIT:-3000}"
MARCH="${MARCH:-x86-64-v3}"

# Seed replicates are the same source built with a different RNG seed.
case "$ID" in
  seed1)    SEED=1 ;;
  seed7919) SEED=7919 ;;
esac

[ "$DEFINES" = "-" ] && DEFINES=""

mkdir -p "$RESULTS" "$BUILD_ROOT" "$BUILD_ROOT/$MODE"

# Take a lock before touching the build tree. Containers here get reclaimed
# without warning, so a stalled shard has to be safe to restart at any moment;
# without this, a restart would rm -rf a build tree that a live run is still
# using. mkdir is atomic, so it works as the lock.
LOCK="$BUILD_ROOT/$MODE-$ID.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  # Reclaim the lock if the process that held it is gone.
  OWNER=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  if [ -n "$OWNER" ] && kill -0 "$OWNER" 2>/dev/null; then
    echo "[$ID] already running as pid $OWNER, skipping"
    exit 0
  fi
  echo "[$ID] taking over a stale lock from pid ${OWNER:-unknown}"
  rm -rf "$LOCK"
  mkdir "$LOCK" 2>/dev/null || { echo "[$ID] lost the lock race, skipping"; exit 0; }
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT INT TERM

rm -rf "$BUILD"
mkdir -p "$BUILD"
# Isolated build tree: the makefile writes *.o and cmix into the working
# directory with fixed names, so concurrent variants would corrupt each other.
cp -a "$REPO/src" "$REPO/makefile" "$BUILD/"

echo "[$ID] building (SEED=$SEED MARCH=$MARCH ${DEFINES:-no ablation flags}${ABLATION_PGO:+ PGO})"
BUILD_LOG="$BUILD/build.log"
MAKE_ARGS=(MARCH="$MARCH" CFLAGS_DEFINES="-DSEED=$SEED -DUPDATE_LIMIT=$UPDATE_LIMIT $DEFINES")

if [ "${ABLATION_PGO:-0}" = "1" ]; then
  # Profile-guided build, worth roughly 20-30% on long runs. cmix's inner loop
  # is a bit-at-a-time mix over ~490 model outputs with many unpredictable
  # branches, which is exactly what profile data fixes.
  #
  # Measured effect on output: 12 bytes on 181 KB (0.007%), an order of
  # magnitude below the study's noise floor. So PGO buys speed and costs
  # nothing measurable in compression ratio -- but every variant in a
  # comparison must still be built the same way.
  PROFDATA="${LLVM_PROFDATA:-llvm-profdata-17}"
  {
    make -C "$BUILD" "${MAKE_ARGS[@]}" prof_gen -j"$(nproc)" &&
    "$BUILD/cmix" -c "$REPO/prof_input/input" "$BUILD/prof_comp" &&
    rm -f "$BUILD/prof_comp" &&
    "$PROFDATA" merge -output="$BUILD/pgo_data/default.profdata" "$BUILD"/pgo_data/*.profraw &&
    make -C "$BUILD" "${MAKE_ARGS[@]}" prof_use -j"$(nproc)"
  } > "$BUILD_LOG" 2>&1
  BUILD_RC=$?
else
  make -C "$BUILD" "${MAKE_ARGS[@]}" cmix > "$BUILD_LOG" 2>&1
  BUILD_RC=$?
fi

if [ $BUILD_RC -ne 0 ] || [ ! -x "$BUILD/cmix" ]; then
  echo "[$ID] BUILD FAILED, see $BUILD_LOG" >&2
  tail -20 "$BUILD_LOG" >&2
  exit 1
fi

QUICK=""
[ "${ABLATION_QUICK:-0}" = "1" ] && QUICK="--quick"
CORPORA=""
[ -n "${ABLATION_CORPORA:-}" ] && CORPORA="--corpora=${ABLATION_CORPORA}"

# --defines must use the = form: its value starts with "-", which argparse
# would otherwise parse as another flag.
python3 "$REPO/experiments/ablation/measure.py" \
  --id "$ID" --binary "$BUILD/cmix" --mode "$MODE" \
  --defines="${DEFINES:-none}" --seed "$SEED" --march "$MARCH" \
  --repo "$REPO" --out "$RESULTS/$ID.json" $QUICK $CORPORA
STATUS=$?

if [ $STATUS -eq 0 ] && [ "${ABLATION_PUSH:-0}" = "1" ]; then
  "$REPO/experiments/ablation/publish.sh" "$ID"
fi
exit $STATUS
