#!/usr/bin/env python3
"""Scoring agent: turn raw official + media records into contract-shaped results.

Run from anywhere:  python3 -I pipeline/score.py [--out data/scored.json]

Reads   data/official_results.json   (Official Results agent; required, may be empty)
        data/official_fetch_log.json  (per-state status; optional)
        data/media_results.json       (Media & Social agent; optional)
        data/scored.json              (previous run; optional, for changes + carry-forward)
        data/baselines.json           (2024/2022 baselines by jkey; optional, falls back to races.json)
        data/races.json               (race roster)
Writes  data/scored.json  { "results": { jkey: { race_id: result } }, "changes": [...], "agents": {...}, "meta": {...} }

Rules (CONTRACT.md + project decisions)
  * an official record for a jurisdiction/race overrides every media figure for it
  * official confidence = 40 + 0.6 x pct_reporting (100% -> 100), capped at 99 until certified
  * pct by party: D, R, O (= everything else), plus I when an independent is a major candidate
  * margin = R - D; swing_vs_2024 = margin - 2024 PRES margin; swing_vs_2022 = margin - 2022 same-office margin
  * called only when the official feed flags a winner, or pct_reporting >= 95 and the vote lead exceeds
    the outstanding share x 1.1 (lead > total / pct_reporting x (100 - pct_reporting) x 1.1); called_by = official_count
  * no official record: tier-1 media -> estimated 60-75 by agreement; tier-2 45-60; a single sourced tier-3 -> 30;
    sources disagreeing by > 2 points on a party -> contested with a range
  * changes: newly_official, race_called, flip, confidence_shift (>= 10), contested, majority_crossed
"""
import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
try:
    from orchestrate import senate_not_up, STATE_FIPS, FIPS_STATE, STATE_NAME  # noqa: E402
except Exception:  # pragma: no cover - orchestrate.py is part of the project; keep a fallback
    STATE_FIPS = {}; FIPS_STATE = {}; STATE_NAME = {}
    def senate_not_up(races):
        return {"D": 45, "R": 53, "I": 2}

MAJORITY = {'SEN': 51, 'HOU': 218}
CALL_MIN_REPORTING = 95.0
CALL_CUSHION = 1.1
CONTEST_SPREAD = 2.0
MAX_SOURCES = 5
TIER_BASE = {1: 60.0, 2: 45.0, 3: 30.0}
TIER_CAP = {1: 75.0, 2: 60.0, 3: 30.0}


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f'warning: could not read {path}: {e}', file=sys.stderr)
        return default


def r1(x):
    return None if x is None else round(float(x) + 1e-9, 1)


def party_bucket(p):
    return p if p in ('D', 'R', 'I') else 'O'


# ---------------------------------------------------------------- core maths (unit-tested)

def tally(votes, party_of, extra_parties=None):
    """votes {cand_id: n} -> (total, Counter by party code D/R/I/L/G/O, top-2 [(cand_id, n)])."""
    extra_parties = extra_parties or {}
    by = Counter(); total = 0
    for cid, n in (votes or {}).items():
        n = int(n or 0)
        p = party_of.get(cid) or extra_parties.get(cid) or 'O'
        by[p] += n; total += n
    ranked = sorted(((cid, int(n or 0)) for cid, n in (votes or {}).items()), key=lambda x: -x[1])
    return total, by, ranked


def pct_by_party(by, total, race_has_I, race_has_D, race_has_R):
    """-> dict with D, R, O and optionally I (one decimal; None when no votes)."""
    if total <= 0:
        out = {'D': None, 'R': None, 'O': None}
        if race_has_I and (not race_has_D or not race_has_R):
            out['I'] = None
        return out
    d = 100.0 * by.get('D', 0) / total
    r = 100.0 * by.get('R', 0) / total
    i = 100.0 * by.get('I', 0) / total
    show_i = race_has_I and (not race_has_D or not race_has_R or i >= 10.0)
    out = {'D': r1(d), 'R': r1(r)}
    if show_i:
        out['I'] = r1(i)
        out['O'] = r1(max(0.0, 100.0 - d - r - i))
    else:
        out['O'] = r1(max(0.0, 100.0 - d - r))
    return out


def call_rule(ranked, total, pct_reporting, winner_flags=None):
    """The official-count call rule. -> (called: bool, reason: str)."""
    if winner_flags:
        return True, 'winner_flag'
    if pct_reporting is None or total <= 0 or len(ranked) < 1:
        return False, 'insufficient'
    if pct_reporting < CALL_MIN_REPORTING:
        return False, 'reporting_below_95'
    top = ranked[0][1]
    second = ranked[1][1] if len(ranked) > 1 else 0
    lead = top - second
    outstanding = total / pct_reporting * (100.0 - pct_reporting)
    if lead > outstanding * CALL_CUSHION and lead > 0:
        return True, 'lead_exceeds_outstanding'
    return False, 'lead_within_outstanding'


def official_confidence(pct_reporting, certified=False):
    if certified:
        return 100
    if pct_reporting is None:
        return 40
    return int(min(99, round(40 + 0.6 * float(pct_reporting))))


# ---------------------------------------------------------------- scorer

class Scorer:
    def __init__(self, races, baselines, prev, official, media, fetch_log, county_names, now=None):
        self.now = now or now_iso()
        self.races = races
        self.baselines = baselines or {}
        self.prev = (prev or {}).get('results', {}) or {}
        self.prev_meta = (prev or {}).get('meta', {}) or {}
        self.prev_changes = (prev or {}).get('changes', []) or []
        self.prev_agents = (prev or {}).get('agents', {}) or {}
        self.official = official or []
        self.media = media or []
        self.fetch_log = fetch_log or {}
        self.county_names = county_names or {}
        self.party_of = {}
        self.cand_name = {}
        self.race_parties = {}
        for rid, r in races.items():
            ps = set()
            for c in r.get('candidates', []):
                self.party_of[c['id']] = c.get('party', 'O')
                self.cand_name[c['id']] = c.get('name', c['id'])
                ps.add(c.get('party', 'O'))
            self.race_parties[rid] = ps
        self.results = defaultdict(dict)
        self.changes = []
        self.rejected_media = defaultdict(list)

    # ----- helpers
    def label(self, rid):
        return (self.races.get(rid) or {}).get('label') or rid

    def jname(self, jkey):
        if len(jkey) == 2:
            return STATE_NAME.get(FIPS_STATE.get(jkey, ''), jkey)
        st = FIPS_STATE.get(jkey[:2], '')
        return f"{self.county_names.get(jkey, jkey)}, {st}"

    def baseline_margins(self, jkey, rid):
        race = self.races.get(rid) or {}
        office = race.get('office')
        b = self.baselines.get(jkey) or {}
        m24 = ((b.get('2024') or {}).get('PRES') or {}).get('margin')
        b22 = (b.get('2022') or {})
        m22 = (b22.get(office) or b22.get(f"{office}-S") or {}).get('margin') if b22 else None
        if len(jkey) == 2:   # state level may also carry baselines on the race itself
            rb = race.get('baseline') or {}
            if m24 is None:
                m24 = (rb.get('2024') or {}).get('margin')
            if m22 is None and (rb.get('2022') or {}).get('office') == office:
                m22 = (rb.get('2022') or {}).get('margin')
        return m24, m22

    def base_result(self, rid, jkey):
        return {"status": "pending", "confidence": 0, "pct_reporting": None, "votes": {}, "pct": None, "leader": None,
                "margin": None, "swing_vs_2024": None, "swing_vs_2022": None, "called": False, "called_by": None,
                "called_at": None, "range": None, "inherited_from": None, "sources_used": [], "sources_rejected": [],
                "updated_at": None}

    def fill_derived(self, res, rid, jkey, votes, extra_parties, pct_reporting):
        total, by, ranked = tally(votes, self.party_of, extra_parties)
        ps = self.race_parties.get(rid, set())
        pct = pct_by_party(by, total, 'I' in ps, 'D' in ps, 'R' in ps)
        res['votes'] = {k: int(v or 0) for k, v in votes.items()}
        res['total_votes'] = total
        res['pct'] = pct
        res['pct_reporting'] = r1(pct_reporting) if pct_reporting is not None else None
        if total > 0:
            top = ranked[0][0]
            res['leader'] = party_bucket(self.party_of.get(top) or (extra_parties or {}).get(top) or 'O')
            res['leader_candidate'] = top
            res['margin'] = r1(pct['R'] - pct['D'])
        else:
            res['leader'] = None; res['leader_candidate'] = None; res['margin'] = None
        m24, m22 = self.baseline_margins(jkey, rid)
        res['swing_vs_2024'] = r1(res['margin'] - m24) if res['margin'] is not None and m24 is not None else None
        res['swing_vs_2022'] = r1(res['margin'] - m22) if res['margin'] is not None and m22 is not None else None
        return total, by, ranked

    # ----- official
    def score_official(self, rec, jkey, rid):
        res = self.base_result(rid, jkey)
        prev = (self.prev.get(jkey) or {}).get(rid) or {}
        res['status'] = rec.get('status') or 'official_preliminary'
        total, by, ranked = self.fill_derived(res, rid, jkey, rec.get('votes') or {}, rec.get('extra_parties'), rec.get('pct_reporting'))
        if total <= 0:
            # the feed is live but has not released any votes: stays pending (neutral on the map) with the
            # official source attached, so media figures may still fill the gap until real counts appear
            res['status'] = 'pending'; res['confidence'] = 0; res['feed_live'] = True
            res['sources_used'] = [{'id': f"official-{rec.get('state', jkey[:2])}", 'tier': 'official', 'url': rec.get('url'), 'ts': rec.get('retrieved_at')}]
            res['updated_at'] = rec.get('retrieved_at') or self.now
            return res
        res['confidence'] = official_confidence(res['pct_reporting'], certified=(res['status'] == 'official_certified'))
        if res['status'] == 'official_certified':
            res['confidence'] = 100
        called, why = (False, 'county')
        if len(jkey) == 2:
            called, why = call_rule(ranked, total, res['pct_reporting'], rec.get('winner'))
        res['called'] = bool(called)
        res['called_by'] = 'official_count' if called else None
        res['called_at'] = (prev.get('called_at') if prev.get('called') and prev.get('called_by') == 'official_count' else None) or (self.now if called else None)
        res['call_reason'] = why if called else None
        if rec.get('winner'):
            res['winner'] = rec['winner']
        res['range'] = None
        res['sources_used'] = [{'id': f"official-{rec.get('state', jkey[:2])}", 'tier': 'official', 'url': rec.get('url'), 'ts': rec.get('retrieved_at')}]
        res['sources_rejected'] = [{'id': m['id'], 'reason': 'official data available for this jurisdiction'} for m in self.media_for(jkey, rid)][:MAX_SOURCES]
        res['updated_at'] = rec.get('retrieved_at') or self.now
        if rec.get('note'):
            res['note'] = rec['note']
        return res

    # ----- media
    def media_for(self, jkey, rid):
        out = []
        for i, m in enumerate(self.media):
            if m.get('jkey') == jkey and m.get('race_id') == rid:
                mm = dict(m)
                mm['id'] = m.get('id') or f"media-{m.get('platform', 'web')}-{m.get('account') or m.get('claimed_source') or i}"
                out.append(mm)
        return out

    def media_pct(self, m, rid):
        """-> ({D,R,...} pct dict, pct_reporting|None) or (None, reason)."""
        figs = m.get('figures') or {}
        if not isinstance(figs, dict) or not figs:
            return None, 'malformed figures'
        keys = list(figs.keys())
        if any(':' in k for k in keys):
            votes = {k: int(float(v)) for k, v in figs.items() if v is not None and str(v).replace('.', '', 1).isdigit()}
            total, by, ranked = tally(votes, self.party_of)
            if total <= 0:
                return None, 'zero votes'
            ps = self.race_parties.get(rid, set())
            return pct_by_party(by, total, 'I' in ps, 'D' in ps, 'R' in ps), m.get('pct_reporting')
        pct = {}
        for k, v in figs.items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if 0 <= fv <= 100:
                pct[k.upper()] = r1(fv)
        if 'D' not in pct and 'R' not in pct:
            return None, 'malformed figures'
        pct.setdefault('D', 0.0); pct.setdefault('R', 0.0)
        others = sum(v for k, v in pct.items() if k not in ('D', 'R', 'O'))
        pct['O'] = r1(pct.get('O', max(0.0, 100.0 - pct['D'] - pct['R'] - others)))
        return pct, m.get('pct_reporting')

    def score_media(self, recs, jkey, rid):
        res = self.base_result(rid, jkey)
        accepted, rejected = [], []
        for m in recs:
            tier = int(m.get('tier') or 3)
            if tier not in (1, 2, 3):
                tier = 3
            pct, info = self.media_pct(m, rid)
            if pct is None:
                rejected.append({'id': m['id'], 'reason': info}); continue
            if tier == 3 and not m.get('claimed_source'):
                rejected.append({'id': m['id'], 'reason': 'unsourced social post'}); continue
            accepted.append({'m': m, 'tier': tier, 'pct': pct, 'pct_reporting': info, 'ts': m.get('posted_at') or m.get('retrieved_at') or ''})
        if not accepted:
            res['sources_rejected'] = rejected[:MAX_SOURCES]
            return res
        accepted.sort(key=lambda a: a['ts'], reverse=True)   # newest first ...
        accepted.sort(key=lambda a: a['tier'])                # ... within tier order (stable sort)
        best = accepted[0]['tier']
        if best < 3:
            keep = [a for a in accepted if a['tier'] <= 2]
            for a in accepted:
                if a['tier'] == 3:
                    rejected.append({'id': a['m']['id'], 'reason': 'tier-3 figure superseded by higher-tier sources'})
            accepted = keep
        top = [a for a in accepted if a['tier'] == best]
        # point estimate from the best tier; agreement measured across everything accepted
        pct = {}
        for k in ('D', 'R', 'I', 'O'):
            vals = [a['pct'][k] for a in top if a['pct'].get(k) is not None]
            if vals:
                pct[k] = r1(sum(vals) / len(vals))
        spread = {}
        for k in ('D', 'R'):
            vals = [a['pct'][k] for a in accepted if a['pct'].get(k) is not None]
            if len(vals) >= 2:
                spread[k] = (min(vals), max(vals))
        contested = any(hi - lo > CONTEST_SPREAD for lo, hi in spread.values())
        n_agree = len(accepted)
        conf = min(TIER_CAP[best], TIER_BASE[best] + 7.5 * (n_agree - 1))
        if contested:
            conf = max(20.0, TIER_BASE[best] - 15.0)
            res['status'] = 'contested'
            res['range'] = {k: [r1(lo), r1(hi)] for k, (lo, hi) in spread.items()}
        else:
            res['status'] = 'estimated'
        res['confidence'] = int(round(conf))
        res['pct'] = {'D': pct.get('D'), 'R': pct.get('R'), 'O': pct.get('O', r1(max(0.0, 100.0 - (pct.get('D') or 0) - (pct.get('R') or 0))))}
        if 'I' in pct:
            res['pct']['I'] = pct['I']
        prs = [a['pct_reporting'] for a in accepted if isinstance(a['pct_reporting'], (int, float))]
        res['pct_reporting'] = r1(max(prs)) if prs else None
        d, r = res['pct']['D'] or 0.0, res['pct']['R'] or 0.0
        i = res['pct'].get('I') or 0.0
        res['leader'] = max((('D', d), ('R', r), ('I', i)), key=lambda x: x[1])[0] if (d or r or i) else None
        res['margin'] = r1(r - d)
        m24, m22 = self.baseline_margins(jkey, rid)
        res['swing_vs_2024'] = r1(res['margin'] - m24) if m24 is not None else None
        res['swing_vs_2022'] = r1(res['margin'] - m22) if m22 is not None else None
        res['votes'] = {}
        res['called'] = False; res['called_by'] = None; res['called_at'] = None
        res['sources_used'] = [{'id': a['m']['id'], 'tier': f"media_t{a['tier']}", 'url': a['m'].get('url'), 'ts': a['ts'] or None,
                               'claimed_source': a['m'].get('claimed_source')} for a in accepted[:MAX_SOURCES]]
        res['sources_rejected'] = rejected[:MAX_SOURCES]
        res['updated_at'] = self.now
        return res

    # ----- driver
    def run(self):
        latest = {}
        for rec in self.official:
            key = (rec.get('jkey'), rec.get('race_id'))
            if not key[0] or key[1] not in self.races:
                continue
            cur = latest.get(key)
            if cur is None or (rec.get('retrieved_at', ''), sum(rec.get('votes', {}).values())) > (cur.get('retrieved_at', ''), sum(cur.get('votes', {}).values())):
                latest[key] = rec
        has_votes = set()
        for (jkey, rid), rec in latest.items():
            res = self.score_official(rec, jkey, rid)
            prev = (self.prev.get(jkey) or {}).get(rid) or {}
            if res['status'] == 'pending' and str(prev.get('status', '')).startswith('official'):
                # a feed that goes back to zero votes is a glitch, not a result: keep the last official figures
                res = dict(prev); res['carried_forward'] = True
            self.results[jkey][rid] = res
            if res['status'] != 'pending':
                has_votes.add((jkey, rid))
        media_keys = defaultdict(list)
        for m in self.media:
            if m.get('jkey') and m.get('race_id') in self.races:
                media_keys[(m['jkey'], m['race_id'])].append(m)
        for (jkey, rid), recs in media_keys.items():
            if (jkey, rid) in has_votes:
                continue
            prev = (self.prev.get(jkey) or {}).get(rid)
            if prev and str(prev.get('status', '')).startswith('official'):
                continue   # a previous official result is never replaced by media figures
            self.results[jkey][rid] = self.score_media(self.media_for(jkey, rid), jkey, rid)
        # carry forward official results that did not get a fresh record this run
        carried = 0
        for jkey, by_race in self.prev.items():
            for rid, prev in by_race.items():
                if rid in self.races and str(prev.get('status', '')).startswith('official') and rid not in self.results.get(jkey, {}):
                    p = dict(prev); p['carried_forward'] = True
                    self.results[jkey][rid] = p; carried += 1
        self.carried = carried
        self.make_changes()
        return self.output()

    # ----- changes
    def chamber_tallies(self):
        called = {'SEN': Counter(), 'HOU': Counter(), 'GOV': Counter()}
        for rid, race in self.races.items():
            res = (self.results.get(race.get('state_fips') or STATE_FIPS.get(race['state'], ''), {}) or {}).get(rid)
            if res and res.get('called') and res.get('leader') in ('D', 'R', 'I'):
                called[race['office']][res['leader']] += 1
        not_up = senate_not_up(self.races)
        if not_up.get('_note') or sum(int(not_up.get(p, 0)) for p in ('D', 'R', 'I')) >= 100:
            # orchestrate.py fell back to the full-chamber composition (legislators file missing):
            # without a real not-up count the Senate majority test would misfire, so skip it
            not_up = {'D': 0, 'R': 0, 'I': 0, '_unavailable': True}
        sen = {p: called['SEN'][p] + int(not_up.get(p, 0)) for p in ('D', 'R', 'I')}
        if not_up.get('_unavailable'):
            sen['_note'] = 'seats-not-up unavailable; Senate majority check disabled'
        hou = {p: called['HOU'][p] for p in ('D', 'R')}
        return {'SEN': sen, 'HOU': hou, 'called': {k: dict(v) for k, v in called.items()}}

    def make_changes(self):
        ch = []
        for jkey, by_race in self.results.items():
            for rid, res in by_race.items():
                if res.get('carried_forward'):
                    continue
                prev = (self.prev.get(jkey) or {}).get(rid) or {}
                official = str(res.get('status', '')).startswith('official')
                ts = res.get('updated_at') or self.now
                lab = self.label(rid)
                pr = res.get('pct_reporting')
                pr_txt = f"{pr:.0f}% of precincts reporting" if pr is not None else "precinct count not reported"
                if len(jkey) == 2:
                    if official and not str(prev.get('status', '')).startswith('official'):
                        ch.append(self.change(ts, 'newly_official', rid, jkey, True, False,
                                              f"{lab}: first official results posted ({pr_txt})."))
                    if res.get('called') and not prev.get('called'):
                        who = self.cand_name.get(res.get('leader_candidate'), res.get('leader'))
                        party = self.party_of.get(res.get('leader_candidate'), res.get('leader'))
                        pct = (res.get('pct') or {}).get(party_bucket(party))
                        ch.append(self.change(ts, 'race_called', rid, jkey, official, True,
                                              f"{lab}: officially decided for {who} ({party}), {pct if pct is not None else '?'}% with {pr_txt}."))
                    if prev.get('leader') and res.get('leader') and prev['leader'] != res['leader']:
                        who = self.cand_name.get(res.get('leader_candidate'), res.get('leader'))
                        ch.append(self.change(ts, 'flip', rid, jkey, official, bool(res.get('called')),
                                              f"{lab}: lead changes to {who} ({res['leader']}), margin {res.get('margin'):+.1f} with {pr_txt}."
                                              if res.get('margin') is not None else f"{lab}: lead changes to {res['leader']}."))
                    if prev and prev.get('status') != 'pending' and abs(int(res.get('confidence', 0)) - int(prev.get('confidence', 0))) >= 10:
                        ch.append(self.change(ts, 'confidence_shift', rid, jkey, official, False,
                                              f"{lab}: confidence {prev.get('confidence', 0)} to {res.get('confidence', 0)} ({pr_txt})."))
                    if res.get('status') == 'contested' and prev.get('status') != 'contested':
                        srcs = ', '.join(s.get('claimed_source') or s['id'] for s in res.get('sources_used', [])[:3])
                        ch.append(self.change(ts, 'contested', rid, jkey, False, False,
                                              f"{lab} marked contested: {srcs or 'sources'} differ by more than two points."))
                else:
                    if (prev.get('leader') and res.get('leader') and prev['leader'] != res['leader']
                            and pr is not None and pr >= 90):
                        ch.append(self.change(ts, 'flip', rid, jkey, official, False,
                                              f"{self.jname(jkey)} flips to {res['leader']} in the {lab} race ({pr_txt})."))
        # majority crossings
        tall = self.chamber_tallies()
        prev_t = self.prev_meta.get('chambers') or {}
        for chamber in ('SEN', 'HOU'):
            for party in ('D', 'R'):
                if tall[chamber].get('_note'):
                    continue
                new_n = tall[chamber].get(party, 0)
                old_n = ((prev_t.get(chamber) or {}).get(party)) if prev_t else None
                if new_n >= MAJORITY[chamber] and (old_n is None or old_n < MAJORITY[chamber]) and tall['called'][chamber]:
                    pname = {'D': 'Democrats', 'R': 'Republicans'}[party]
                    cname = {'SEN': 'Senate', 'HOU': 'House'}[chamber]
                    extra = ' (officially decided seats plus seats not up this year)' if chamber == 'SEN' else ' (officially decided seats)'
                    ch.append(self.change(self.now, 'majority_crossed', None, 'US', True, True,
                                          f"{pname} reach {new_n} {cname} seats, a majority{extra}."))
        self.chambers = tall
        ch.sort(key=lambda c: c['ts'] or '', reverse=True)
        self.changes = ch

    @staticmethod
    def change(ts, typ, rid, jkey, official, important, text):
        return {'ts': ts, 'type': typ, 'race_id': rid, 'jkey': jkey, 'official': bool(official), 'important': bool(important), 'text': text}

    # ----- agents + output
    def agents(self):
        fl = self.fetch_log or {}
        summ = fl.get('summary') or {}
        failed = summ.get('failed') or []
        attempted = summ.get('states_attempted') or []
        off_ok = bool(fl) and (len(failed) < max(1, len(attempted)))
        note = []
        if not fl:
            note.append('no official fetch log')
        if failed:
            note.append('fetch failed: ' + ', '.join(failed))
        if self.carried:
            note.append(f'{self.carried} results carried forward from the previous run')
        empty = [s for s in attempted if s not in (summ.get('states_with_records') or []) and s not in failed and s != 'DC']
        if empty:
            note.append('no rows yet: ' + ', '.join(empty))
        media_path = os.path.join(ROOT, 'data', 'media_results.json')
        if os.path.exists(media_path):
            ts = max([m.get('retrieved_at') or '' for m in self.media] or [''])
            media = {'ok': True, 'ran_at': ts or dt.datetime.fromtimestamp(os.path.getmtime(media_path), dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
                     'note': f'{len(self.media)} media records'}
        else:
            media = {'ok': True, 'ran_at': self.now, 'note': 'no media pull yet'}
        video = self.prev_agents.get('video')
        if not video:
            ds = load(os.path.join(ROOT, 'app', 'data', 'dataset.json'), {}) or {}
            video = ((ds.get('meta') or {}).get('agents') or {}).get('video')
        if not video:
            video = {'ok': True, 'ran_at': None, 'note': 'video agent not run yet; list carried as-is'}
        return {
            'official': {'ok': off_ok, 'ran_at': fl.get('generated_at') or self.now, 'note': '; '.join(note)},
            'media': media,
            'scoring': {'ok': True, 'ran_at': self.now, 'note': ''},
            'video': video,
        }

    def output(self):
        results = {jk: dict(v) for jk, v in self.results.items()}
        # keep the previous run's changes behind the new ones so a consumer that lost its history can rebuild it
        seen = {(c.get('ts'), c.get('type'), c.get('race_id'), c.get('jkey')) for c in self.changes}
        merged = list(self.changes)
        for c in self.prev_changes:
            k = (c.get('ts'), c.get('type'), c.get('race_id'), c.get('jkey'))
            if k not in seen:
                merged.append(c); seen.add(k)
        merged.sort(key=lambda c: c.get('ts') or '', reverse=True)
        n_state = sum(1 for jk in results if len(jk) == 2 for _ in results[jk])
        n_county = sum(1 for jk in results if len(jk) == 5 for _ in results[jk])
        statuses = Counter(r['status'] for jk in results for r in results[jk].values())
        return {
            'results': results,
            'changes': merged[:300],
            'agents': self.agents(),
            'meta': {'generated_at': self.now, 'counts': {'state_results': n_state, 'county_results': n_county, 'new_changes': len(self.changes),
                                                         'statuses': dict(statuses), 'carried_forward': self.carried},
                     'chambers': {'SEN': self.chambers['SEN'], 'HOU': self.chambers['HOU']},
                     'called': self.chambers['called']},
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=os.path.join(ROOT, 'data', 'scored.json'))
    ap.add_argument('--official', default=os.path.join(ROOT, 'data', 'official_results.json'))
    ap.add_argument('--media', default=os.path.join(ROOT, 'data', 'media_results.json'))
    ap.add_argument('--prev', default=None, help='previous scored.json (default: same as --out)')
    a = ap.parse_args()
    races_raw = load(os.path.join(ROOT, 'data', 'races.json'), {})
    races = {k: v for k, v in races_raw.items() if not k.startswith('_')}
    baselines = load(os.path.join(ROOT, 'data', 'baselines.json'), {}) or {}
    prev = load(a.prev or a.out, {}) or {}
    official = load(a.official, []) or []
    media = load(a.media, []) or []
    fetch_log = load(os.path.join(ROOT, 'data', 'official_fetch_log.json'), {}) or {}
    county_names = {}
    try:
        with open(os.path.join(ROOT, 'app', 'data', 'counties-10m.json')) as f:
            topo = json.load(f)
        county_names = {g['id']: (g.get('properties') or {}).get('name') for g in topo['objects']['counties']['geometries']}
    except Exception:  # noqa: BLE001
        pass
    sc = Scorer(races, baselines, prev, official, media, fetch_log, county_names)
    out = sc.run()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    os.replace(tmp, a.out)
    c = out['meta']['counts']
    print(f"scored {c['state_results']} state + {c['county_results']} county results ({c['statuses']}); "
          f"{c['new_changes']} new changes; official agent ok={out['agents']['official']['ok']} {out['agents']['official']['note']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
