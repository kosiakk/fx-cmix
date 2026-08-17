#!/bin/bash
# Publish one variant's result straight to main.
#
# Every worker writes a distinct results/<id>.json, so concurrent workers never
# conflict on content -- only on the ref. Pull --rebase then push, and retry the
# race a few times.
set -uo pipefail

ID="$1"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILE="$(cd "$REPO" && find experiments/ablation/results -name "$ID.json" | head -1)"

cd "$REPO" || exit 1

git config user.email >/dev/null 2>&1 || git config user.email "ablation@fx-cmix.local"
git config user.name  >/dev/null 2>&1 || git config user.name  "fx-cmix ablation worker"

git add "$FILE" || exit 1
if git diff --cached --quiet; then
  echo "[$ID] nothing to publish"
  exit 0
fi
git commit -q -m "Ablation result: $ID" || exit 1

for attempt in 1 2 3 4 5; do
  if git pull --rebase -q origin main && git push -q origin main; then
    echo "[$ID] published"
    exit 0
  fi
  delay=$((attempt * 3))
  echo "[$ID] push race, retry in ${delay}s (attempt $attempt)" >&2
  sleep $delay
done

echo "[$ID] PUBLISH FAILED, result is committed locally but not pushed" >&2
exit 1
