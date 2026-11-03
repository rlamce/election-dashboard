# Election Night 2026 — Live Dashboard

Live site: **https://rlamce.github.io/election-dashboard/**

A command-center style map of the November 3, 2026 U.S. general election (Senate, House, governors) with
country → state → county → city drill-down, red/blue percentage shading, a 2024/2022 swing view,
muted live video panels, and a spoken briefing on open.

## How it works

```
official state feeds (21 states)  ──►  pipeline/fetch_official.py ──┐
media & social (Claude agent, on request) ─► data/media_results.json ─┼─► pipeline/score.py ─► data/scored.json
                                                                      │
race roster · baselines · sources · videos (data/*.json) ─────────────┴─► tools/orchestrate.py ─► app/data/dataset.json
                                                                                                       │
                                     GitHub Actions (.github/workflows/refresh.yml, every 5 min) ──────┘ commits it
                                                                                                       │
                                     app/index.html polls dataset.json every 5 min, caches the last copy locally
```

- `CONTRACT.md` — the data contract every component follows.
- `app/` — the dashboard (single HTML file + geo data). Opens instantly from the last cached dataset, then pulls the live one.
- `pipeline/` — election-night fetchers (one parser per state platform), the deterministic scorer, tests.
- `tools/orchestrate.py` — assembles `dataset.json`; `tools/deploy.sh` — mirrors this folder into the repo and pushes.
- `data/` — race roster (506 races), 2024/2022 baselines (3,113 counties), official & media source directories, 758 video sources.

## Rules the data follows
1. Official results override media and social for a jurisdiction; certified beats preliminary.
2. Confidence 0–100: official = 40 + 0.6 × precincts reporting; Tier-1 media 60–75; Tier-2 45–60; a lone unsourced social post ≤ 30.
3. A race is "called" only on an official winner flag, or at ≥95% reporting when the lead exceeds the outstanding vote.
4. Disagreement over 2 points → "contested" with a range, never a single number.
5. The page never computes or invents a percentage; it only displays dataset values.
6. Voice interrupts only for changes that are both official and important (race called, flip, majority crossed).

## Running a refresh by hand
```
pip install requests
bash pipeline/run_refresh.sh        # fetch → score → assemble app/data/dataset.json
python3 -I -m pytest pipeline/tests # 25 unit tests
```
