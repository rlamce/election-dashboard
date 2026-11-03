#!/usr/bin/env bash
# One refresh cycle: fetch official feeds -> score -> assemble app/data/dataset.json.
# Exit status is non-zero only when the orchestrator fails; fetch/score failures are
# logged and the orchestrator still runs with whatever data exists (stale flag in meta).
set -u
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
OUT="${1:-app/data}"
PY="${PYTHON:-python3}"

echo "== refresh $(date -u +%FT%TZ) root=$ROOT out=$OUT"

echo "-- fetch_official"
if ! "$PY" -I pipeline/fetch_official.py --quiet; then
  echo "fetch_official.py FAILED (continuing with previous data/official_results.json if any)" >&2
fi

echo "-- score"
if ! "$PY" -I pipeline/score.py; then
  echo "score.py FAILED (continuing with previous data/scored.json if any)" >&2
fi

echo "-- orchestrate"
"$PY" -I tools/orchestrate.py --out "$OUT"
rc=$?
if [ $rc -ne 0 ]; then
  echo "orchestrate.py FAILED (rc=$rc)" >&2
fi
exit $rc
