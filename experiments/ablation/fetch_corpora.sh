#!/bin/bash
# Fetch enwik8 and cut the prefixes the ablation study uses.
#
#   ./fetch_corpora.sh [5m|10m|full|all]
#
# enwik8 is 100 MB and is NOT committed -- each machine fetches its own copy
# into experiments/ablation/corpora/, which is gitignored.
#
# Why prefixes rather than the whole thing: at this build's measured ~1.7 KB/s,
# full enwik8 is roughly 17 hours per variant, longer than any container in
# this environment has stayed alive, and cmix has no checkpoint/resume. The
# 5 MB prefix crosses the mixer learning-rate schedule's 25M-step threshold
# (3.125 MB of input), which the 930 KB corpus never reaches.
set -uo pipefail

WHICH="${1:-5m}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$HERE/corpora"
URL="https://mattmahoney.net/dc/enwik8.zip"

mkdir -p "$DIR"

if [ ! -f "$DIR/enwik8" ]; then
  echo "fetching enwik8 (36 MB zipped, 100 MB raw)..."
  if [ -f /tmp/enwik8 ]; then
    cp /tmp/enwik8 "$DIR/enwik8"
  else
    curl -sS --max-time 900 -o "$DIR/enwik8.zip" "$URL" || {
      echo "download failed" >&2; exit 1; }
    ( cd "$DIR" && unzip -o -q enwik8.zip && rm -f enwik8.zip )
  fi
fi

[ -s "$DIR/enwik8" ] || { echo "enwik8 missing or empty" >&2; exit 1; }

cut() {  # name, bytes
  if [ ! -f "$DIR/$1" ]; then
    head -c "$2" "$DIR/enwik8" > "$DIR/$1"
    echo "cut $1 ($(wc -c < "$DIR/$1") bytes)"
  fi
}

case "$WHICH" in
  5m)   cut enwik8_5m  5000000 ;;
  10m)  cut enwik8_10m 10000000 ;;
  full) : ;;
  all)  cut enwik8_5m 5000000; cut enwik8_10m 10000000 ;;
  *) echo "usage: $0 [5m|10m|full|all]" >&2; exit 2 ;;
esac

ls -la "$DIR"
