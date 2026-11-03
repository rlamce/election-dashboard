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

# Gate: pulls run only when data/refresh_control.json says enabled and now is inside its window
# (FORCE=1 bypasses, used for manual runs).
if [ "${FORCE:-0}" != "1" ] && [ -f data/refresh_control.json ]; then
  if ! "$PY" -I - <<'EOF'
import json, sys, datetime as dt
c = json.load(open('data/refresh_control.json'))
now = dt.datetime.now(dt.timezone.utc)
p = lambda s: dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
ok = bool(c.get('enabled')) and (not c.get('window_start_utc') or p(c['window_start_utc']) <= now) and (not c.get('window_end_utc') or now <= p(c['window_end_utc']))
print(f"refresh_control: enabled={c.get('enabled')} window={c.get('window_start_utc')}..{c.get('window_end_utc')} now={now.isoformat()} -> {'RUN' if ok else 'SKIP'}")
sys.exit(0 if ok else 3)
EOF
  then echo "skipping: outside refresh window or disabled"; exit 0; fi
fi

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
