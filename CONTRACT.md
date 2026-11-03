# Election Dashboard — Shared Data Contract v1.0

Every agent reads and writes against this contract. The Orchestrator assembles `dataset.json`; the dashboard consumes only `dataset.json` plus static geo files. Nothing displayed may come from anywhere else.

## Conventions
- Election: U.S. general election, Tuesday 2026-11-03 (midterm: Senate, House, governors; no presidential race).
- Party codes: `D`, `R`, `I` (independent), `L`, `G`, `O` (other/aggregate). Percentages are 0–100 with one decimal.
- `margin` always means **R% minus D%** (positive = Republican lead, negative = Democratic lead).
- Timestamps: ISO 8601 UTC.
- Jurisdiction keys (`jkey`):
  - `US` — national
  - two-digit state FIPS as string, e.g. `42` (PA)
  - five-digit county FIPS as string, e.g. `42101` (Philadelphia County)
  - city: `<countyFIPS>:<slug>`, e.g. `42101:philadelphia`
- State postal codes appear as `state` fields (`PA`); FIPS are used for keys so they join to TopoJSON ids.
- Race ids: `<STATE>-<OFFICE>-2026[-<DISTRICT>][-S]` — `PA-SEN-2026`, `PA-GOV-2026`, `PA-HOU-2026-07`, `OH-SEN-2026-S` (special).
- Offices: `SEN`, `GOV`, `HOU`.

## dataset.json

```jsonc
{
  "meta": {
    "schema_version": "1.0",
    "generated_at": "2026-11-03T23:05:00Z",
    "refresh_id": "r-0003",
    "previous_refresh_id": "r-0002",
    "election_date": "2026-11-03",
    "stale": false,                       // true if any agent failed and old data was carried forward
    "agents": {
      "official": { "ok": true, "ran_at": "…", "note": "" },
      "media":    { "ok": true, "ran_at": "…", "note": "" },
      "scoring":  { "ok": true, "ran_at": "…", "note": "" },
      "video":    { "ok": true, "ran_at": "…", "note": "" }
    }
  },

  "national": {
    "headline": "Polls have closed in 23 states. No Senate seats have been officially decided.",
    "overall_confidence": 0,              // 0–100, weighted by jurisdictions with data
    "states_with_official_data": 0,
    "chambers": {
      "SEN": { "not_up": { "D": 0, "R": 0, "I": 0 }, "called": { "D": 0, "R": 0, "I": 0 }, "undecided": 35, "majority": 51 },
      "HOU": { "called": { "D": 0, "R": 0 }, "undecided": 435, "majority": 218 },
      "GOV": { "not_up": { "D": 0, "R": 0 }, "called": { "D": 0, "R": 0 }, "undecided": 36 }
    }
  },

  "races": {
    "PA-SEN-2026": {
      "race_id": "PA-SEN-2026",
      "state": "PA", "state_fips": "42",
      "office": "SEN", "district": null, "special": false,
      "label": "Pennsylvania U.S. Senate",
      "candidates": [
        { "id": "PA-SEN-2026:lastname", "name": "Full Name", "party": "D", "incumbent": true }
      ],
      "poll_close_et": "20:00",            // first/last close in ET when a state splits: use last close
      "baseline": {
        "2024": { "office": "PRES", "D": 48.7, "R": 50.4, "margin": 1.7 },
        "2022": { "office": "SEN",  "D": 51.2, "R": 46.3, "margin": -4.9 }
      }
    }
  },

  "jurisdictions": {
    "42101": {
      "jkey": "42101", "level": "county",   // national | state | county | city
      "name": "Philadelphia", "state": "PA", "state_fips": "42",
      "parent": "42",                       // jkey of parent; cities point to their county
      "baseline": {
        "2024": { "PRES": { "D": 78.9, "R": 20.1, "margin": -58.8, "total_votes": 0 } },
        "2022": { "SEN": { "D": 0, "R": 0, "margin": 0 }, "GOV": { … } }
      },
      "results": {
        "PA-SEN-2026": {
          "status": "pending",              // official_certified | official_preliminary | estimated | contested | pending
          "confidence": 0,                  // 0–100
          "pct_reporting": null,            // precincts reporting, 0–100 or null
          "votes": { "PA-SEN-2026:lastname": 0 },
          "pct": { "D": null, "R": null, "O": null },
          "leader": null,                   // D | R | I | O | null
          "margin": null,                   // R − D on current pct
          "swing_vs_2024": null,            // margin − baseline.2024.margin
          "swing_vs_2022": null,
          "called": false, "called_by": null, "called_at": null,
          "range": null,                    // when contested: { "D": [lo, hi], "R": [lo, hi] }
          "inherited_from": null,           // city rows: county jkey when city has no own data
          "sources_used":     [ { "id": "src-…", "tier": "official", "url": "…", "ts": "…" } ],
          "sources_rejected": [ { "id": "src-…", "reason": "unsourced social post" } ],
          "updated_at": "…"
        }
      }
    }
  },

  "videos": [
    {
      "id": "vid-…",
      "platform": "youtube",
      "kind": "channel_live",               // channel_live (auto-resolves the channel's current live stream) | video
      "youtube_channel_id": "UC…", "youtube_video_id": null,
      "title": "PBS NewsHour election night live",
      "channel": "PBS NewsHour",
      "tier": "major_outlet",               // official | major_outlet | regional_outlet | unverified
      "live": null,                         // true | false | null (unknown until page checks)
      "started_at": null,
      "scope": { "level": "national", "jkey": "US" },   // or state/county/city jkey
      "location_confidence": "state",       // exact | city | state | inferred
      "embed_url": "https://www.youtube.com/embed/live_stream?channel=UC…&mute=1&autoplay=1",
      "link_url": "https://www.youtube.com/channel/UC…/live",
      "muted": true,
      "rank": 1
    }
  ],

  "changes": [
    {
      "ts": "…", "type": "race_called",     // race_called | flip | confidence_shift | newly_official | contested | majority_crossed | polls_closed
      "race_id": "PA-SEN-2026", "jkey": "42",
      "official": true, "important": true,  // voice may interrupt only when both are true
      "text": "Pennsylvania Senate: officially called for …"
    }
  ],

  "briefing": {
    "on_open": "Good evening. As of 7:05 PM Eastern, polls have closed in 23 states…",   // ≤ 15 s spoken
    "delta":   "Since your last look at 6:40 PM: …",                                       // what moved
    "alerts":  [ "…" ]                                                                      // official + important only
  },

  "sources": {
    "official": {
      "PA": { "name": "Pennsylvania Department of State", "url": "https://…", "feed": { "type": "json", "url": "…" } }
    },
    "media_tiers": {
      "1": ["AP", "Reuters", "NBC News", "ABC News", "CBS News", "CNN", "Fox News", "PBS"],
      "2": ["state and regional newspapers and TV stations"],
      "3": ["official or very-high-reach accounts on two or more platforms"]
    }
  }
}
```

## Agent output files (inputs to the Orchestrator)
| Agent | Writes | Shape |
|---|---|---|
| Race roster | `data/races.json` | `{ "<race_id>": race }` per the `races` block, baseline optional |
| Baselines | `data/baselines.json` | `{ "<jkey>": baseline }` per the `jurisdictions[*].baseline` block, plus `"_meta"` with sources |
| Official sources | `data/official_sources.json` | per the `sources.official` block |
| Video | `data/videos.json` | array per the `videos` block |
| Official results (election night) | `data/official_results.json` | array of raw records: `{ jkey, race_id, votes:{cand:n}, pct_reporting, status, retrieved_at, url }` |
| Media & social | `data/media_results.json` | array of raw records: `{ jkey, race_id, figures, claimed_source, platform, account, tier, posted_at, retrieved_at, url, type }` |
| Scoring | `data/scored.json` | `{ "<jkey>": { "<race_id>": result } }` per the `results` block, plus `changes` |

## Rules the dashboard enforces
1. Colors come only from `results[race].pct` for the selected race layer; `pending` renders neutral grey, `contested` renders hatched.
2. Swing view colors by `swing_vs_2024` (or `_2022` when chosen).
3. Cities with `inherited_from` display a "county-level" tag.
4. Voice interrupts fire only for `changes` where `official && important` and `ts` is newer than the last spoken change.
5. The page never computes or invents a percentage; it only displays values present in the dataset.
