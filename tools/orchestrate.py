#!/usr/bin/env python3
"""Orchestrator: assemble dataset.json per CONTRACT.md from agent outputs.

Inputs (all under the project root):
  data/races.json            race roster (Race Roster agent)
  data/poll_close.json       poll-close times by state
  data/baselines.json        2024/2022 baselines by FIPS (optional until built)
  data/official_sources.json official results directory
  data/media_sources.json    vetted media list (optional)
  data/videos.json           video panel sources (optional)
  data/scored.json           election-night scored results (optional):
                             { "results": {jkey: {race_id: result}}, "changes": [...], "agents": {...} }
  app/data/cities.json       city list
  <out>/dataset.json         previous dataset (for delta + refresh id)

Usage: python3 -I tools/orchestrate.py [--out DIR] [--pretty]
"""
import json, os, sys, argparse, datetime as dt
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET_OFFSET = dt.timedelta(hours=-5)  # EST: DST ended Nov 1, 2026

STATE_FIPS = {
 'AL':'01','AK':'02','AZ':'04','AR':'05','CA':'06','CO':'08','CT':'09','DE':'10','DC':'11','FL':'12','GA':'13','HI':'15','ID':'16','IL':'17',
 'IN':'18','IA':'19','KS':'20','KY':'21','LA':'22','ME':'23','MD':'24','MA':'25','MI':'26','MN':'27','MS':'28','MO':'29','MT':'30','NE':'31',
 'NV':'32','NH':'33','NJ':'34','NM':'35','NY':'36','NC':'37','ND':'38','OH':'39','OK':'40','OR':'41','PA':'42','RI':'44','SC':'45','SD':'46',
 'TN':'47','TX':'48','UT':'49','VT':'50','VA':'51','WA':'53','WV':'54','WI':'55','WY':'56'}
STATE_NAME = {
 'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut','DE':'Delaware','DC':'District of Columbia',
 'FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine',
 'MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada',
 'NH':'New Hampshire','NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon',
 'PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia',
 'WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming'}
FIPS_STATE = {v:k for k,v in STATE_FIPS.items()}

# Governors not on the 2026 ballot (verified 2026-11-03 against Wikipedia's current-governors list)
GOV_NOT_UP = {'DE':'D','IN':'R','KY':'D','LA':'R','MS':'R','MO':'R','MT':'R','NJ':'D','NC':'D','ND':'R','UT':'R','WA':'D','WV':'R','VA':'D'}
PARTY_MAP = {'Democrat':'D','Republican':'R','Independent':'I'}

def load(path, default=None):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)

def iso(t): return t.replace(microsecond=0).isoformat().replace('+00:00','Z')
def et(t): return (t + ET_OFFSET).strftime('%-I:%M %p').replace('AM','a.m.').replace('PM','p.m.')

def pending():
    return {"status":"pending","confidence":0,"pct_reporting":None,"pct":None,"leader":None,"margin":None,
            "swing_vs_2024":None,"swing_vs_2022":None,"called":False,"called_by":None,"called_at":None,"range":None,
            "inherited_from":None,"updated_at":None}

def senate_not_up(races):
    legs = None
    for cand in ('/home/claude/dl/legislators/legislators-current.json', os.path.join(ROOT,'data','legislators-current.json')):
        if os.path.exists(cand):
            legs = json.load(open(cand)); break
    if not legs:
        return {"D":45,"R":53,"I":2,"_note":"fallback composition"}
    up = {(r['state'], 'special' if r.get('special') else 'regular') for r in races.values() if r['office']=='SEN'}
    up_states_regular = {s for s,k in up if k=='regular'}
    up_states_special = {s for s,k in up if k=='special'}
    c = Counter()
    for l in legs:
        t = l['terms'][-1]
        if t['type']!='sen': continue
        st, cls, party = t['state'], t.get('class'), PARTY_MAP.get(t['party'],'I')
        # 2026 specials (FL: Rubio seat, OH: Vance seat) are both Class 3 seats
        is_up = (cls==2 and st in up_states_regular) or (cls==3 and st in up_states_special)
        if not is_up:
            c[party]+=1
    return {"D":c['D'],"R":c['R'],"I":c['I']}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT,'app','data'))
    ap.add_argument('--pretty', action='store_true')
    ap.add_argument('--copy-to', action='append', default=[], help='extra output dirs')
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    races_raw = load('data/races.json', {})
    races = {k:v for k,v in races_raw.items() if not k.startswith('_')}
    poll_close = load('data/poll_close.json', {})
    baselines = load('data/baselines.json', {}) or {}
    official_sources = load('data/official_sources.json', {}) or {}
    media_sources = load('data/media_sources.json', {}) or {}
    videos = load('data/videos.json', []) or []
    cities = (load('app/data/cities.json', {}) or {}).get('cities', [])
    scored = load('data/scored.json', {}) or {}
    scored_results = scored.get('results', {})
    prev = None
    prev_path = os.path.join(a.out, 'dataset.json')
    if os.path.exists(prev_path):
        try: prev = json.load(open(prev_path))
        except Exception: prev = None

    # ---- refresh ids
    prev_id = prev['meta']['refresh_id'] if prev else None
    n = int(prev_id.split('-')[1])+1 if prev_id else 1
    refresh_id = f"r-{n:04d}"

    # ---- races: strip bulky fields, keep contract fields
    races_out = {}
    for rid, r in races.items():
        races_out[rid] = {
            "race_id": rid, "state": r['state'], "state_fips": r.get('state_fips') or STATE_FIPS[r['state']],
            "office": r['office'], "district": r.get('district'), "special": bool(r.get('special')),
            "label": r.get('label'), "candidates": [{"id":c['id'],"name":c['name'],"party":c['party'],"incumbent":bool(c.get('incumbent'))} for c in r.get('candidates',[])],
            "poll_close_et": r.get('poll_close_et') or (poll_close.get(r['state'],{}) or {}).get('close_et'),
            "baseline": r.get('baseline'),
            "notes": r.get('notes'), "source": r.get('source'),
        }
        if r.get('candidates_incomplete'): races_out[rid]['candidates_incomplete'] = True

    races_by_state = {}
    for rid, r in races_out.items():
        races_by_state.setdefault(r['state'], []).append(rid)

    # ---- jurisdictions
    J = {}
    J['US'] = {"jkey":"US","level":"national","name":"United States","state":None,"state_fips":None,"parent":None,"baseline":None,"results":{}}
    for st, fips in STATE_FIPS.items():
        J[fips] = {"jkey":fips,"level":"state","name":STATE_NAME[st],"state":st,"state_fips":fips,"parent":"US",
                   "baseline": baselines.get(fips), "results":{}}
        for rid in races_by_state.get(st, []):
            J[fips]['results'][rid] = scored_results.get(fips,{}).get(rid) or pending()
    county_names = {}
    try:
        topo = json.load(open(os.path.join(ROOT,'app','data','counties-10m.json')))
        for g in topo['objects']['counties']['geometries']:
            county_names[g['id']] = g.get('properties',{}).get('name')
    except Exception:
        pass
    county_keys = sorted(k for k in list(baselines.keys())+list(county_names.keys()) if isinstance(k,str) and len(k)==5 and k.isdigit())
    for fips in sorted(set(county_keys)):
        sfips = fips[:2]; st = FIPS_STATE.get(sfips)
        if not st: continue
        b = baselines.get(fips)
        J[fips] = {"jkey":fips,"level":"county","name":(b or {}).get('name') or county_names.get(fips) or fips,"state":st,"state_fips":sfips,"parent":sfips,
                   "baseline": {k:v for k,v in (b or {}).items() if k in ('2024','2022')} or None, "results":{}}
        for rid in races_by_state.get(st, []):
            if races_out[rid]['office']=='HOU': continue   # House is district-level; not mapped to counties in v1
            J[fips]['results'][rid] = scored_results.get(fips,{}).get(rid) or pending()
    for c in cities:
        cf = c.get('county_fips')
        if not cf or cf not in J: continue
        jk = f"{cf}:{c['slug']}"
        st = c['state']
        J[jk] = {"jkey":jk,"level":"city","name":c['name'],"state":st,"state_fips":c['state_fips'],"parent":cf,"pop":c.get('pop'),
                 "lat":c.get('lat'),"lon":c.get('lon'),"baseline": J[cf]['baseline'], "results":{}}
        for rid in races_by_state.get(st, []):
            if races_out[rid]['office']=='HOU': continue
            own = scored_results.get(jk,{}).get(rid)
            if own: J[jk]['results'][rid] = own
            else:
                inh = dict(J[cf]['results'].get(rid) or pending()); inh['inherited_from'] = cf
                J[jk]['results'][rid] = inh

    # ---- national summary
    def called_counts(office):
        c = Counter(); undecided = 0
        for rid, r in races_out.items():
            if r['office']!=office: continue
            res = J[r['state_fips']]['results'].get(rid) or {}
            if res.get('called') and res.get('leader') in ('D','R','I'):
                c[res['leader']] += 1
            else:
                undecided += 1
        return dict(c), undecided
    sen_called, sen_und = called_counts('SEN'); hou_called, hou_und = called_counts('HOU'); gov_called, gov_und = called_counts('GOV')
    gov_not_up = Counter(GOV_NOT_UP.values())
    chambers = {
        "SEN": {"not_up": senate_not_up(races), "called": {"D":sen_called.get('D',0),"R":sen_called.get('R',0),"I":sen_called.get('I',0)}, "undecided": sen_und, "majority": 51, "seats_up": sen_und + sum(sen_called.values())},
        "HOU": {"called": {"D":hou_called.get('D',0),"R":hou_called.get('R',0)}, "undecided": hou_und, "majority": 218},
        "GOV": {"not_up": {"D":gov_not_up['D'],"R":gov_not_up['R']}, "called": {"D":gov_called.get('D',0),"R":gov_called.get('R',0)}, "undecided": gov_und, "races_up": gov_und + sum(gov_called.values())},
    }
    closed = [st for st,p in poll_close.items() if p.get('close_utc') and dt.datetime.fromisoformat(p['close_utc'].replace('Z','+00:00')) <= now]
    conf_vals = [res['confidence'] for j in J.values() if j['level'] in ('state','county') for res in j['results'].values() if res.get('status')!='pending']
    overall_conf = round(sum(conf_vals)/len(conf_vals)) if conf_vals else 0
    states_official = len({j['state_fips'] for j in J.values() if j['level'] in ('state','county') for res in j['results'].values() if str(res.get('status','')).startswith('official')})
    total_called = sum(sen_called.values())+sum(gov_called.values())+sum(hou_called.values())
    if not closed:
        headline = "Polls are open. No results yet; all jurisdictions pending."
    else:
        headline = f"Polls have closed in {len(closed)} of 51 states and DC. "
        headline += (f"{sum(sen_called.values())} Senate, {sum(gov_called.values())} governor and {sum(hou_called.values())} House races officially decided." if total_called else "No races have been officially decided yet.")
    national = {"headline": headline, "overall_confidence": overall_conf, "states_with_official_data": states_official,
                "polls_closed_states": sorted(closed), "chambers": chambers}

    # ---- changes
    changes = list(scored.get('changes', []))
    prev_closed = set((prev or {}).get('national',{}).get('polls_closed_states',[]))
    for st in closed:
        if st not in prev_closed:
            changes.append({"ts": poll_close[st]['close_utc'], "type":"polls_closed", "race_id":None, "jkey":STATE_FIPS[st], "official":True, "important":False,
                            "text": f"Polls have closed in {STATE_NAME[st]}."})
    # carry forward previous changes not already present (cap 300)
    seen = {(c.get('ts'),c.get('type'),c.get('race_id'),c.get('jkey')) for c in changes}
    for c in (prev or {}).get('changes', []):
        k=(c.get('ts'),c.get('type'),c.get('race_id'),c.get('jkey'))
        if k not in seen: changes.append(c); seen.add(k)
    changes.sort(key=lambda c: c.get('ts') or '', reverse=True)
    changes = changes[:300]

    # ---- briefing
    t_et = et(now)
    sen = chambers['SEN']; gov = chambers['GOV']; hou = chambers['HOU']
    on_open = f"Good evening. It's {t_et} Eastern. "
    on_open += (f"Polls have closed in {len(closed)} of 51 states. " if closed else "Polls are still open everywhere. ")
    if total_called:
        on_open += f"Officially decided so far: Senate {sen['called']['D']} Democratic, {sen['called']['R']} Republican, {sen['undecided']} undecided; "
        on_open += f"governors {gov['called']['D']} to {gov['called']['R']}, {gov['undecided']} undecided; House {hou['called']['D']} to {hou['called']['R']}, {hou['undecided']} undecided. "
    else:
        on_open += f"No race has been officially decided. {sen['undecided']} Senate seats, {gov['undecided']} governorships and {hou['undecided']} House seats are on the board. "
    on_open += f"Overall data confidence is {overall_conf} out of 100. What would you like to look at?"
    prev_gen = (prev or {}).get('meta',{}).get('generated_at')
    new_changes = [c for c in changes if prev_gen and (c.get('ts') or '') > prev_gen]
    if prev_gen:
        prev_t = et(dt.datetime.fromisoformat(prev_gen.replace('Z','+00:00')))
        official_new = [c for c in new_changes if c.get('official') and c.get('type')!='polls_closed']
        closed_new = [c for c in new_changes if c.get('type')=='polls_closed']
        if official_new or closed_new:
            delta = f"Since your last look at {prev_t} Eastern: "
            if closed_new: delta += f"polls closed in {len(closed_new)} more state{'s' if len(closed_new)!=1 else ''}. "
            if official_new: delta += f"{len(official_new)} official update{'s' if len(official_new)!=1 else ''}: " + " ".join(c['text'] for c in official_new[:5]) + (" and more." if len(official_new)>5 else "")
        else:
            delta = f"Nothing official has changed since your last look at {prev_t} Eastern."
    else:
        delta = "This is your first briefing of the night."
    alerts = [c['text'] for c in new_changes if c.get('official') and c.get('important')]

    agents = scored.get('agents') or {
        "official": {"ok": True, "ran_at": iso(now), "note": "no election-night pull yet" if not scored_results else ""},
        "media":    {"ok": True, "ran_at": iso(now), "note": "no election-night pull yet" if not scored_results else ""},
        "scoring":  {"ok": True, "ran_at": iso(now), "note": ""},
        "video":    {"ok": bool(videos), "ran_at": iso(now), "note": "" if videos else "video list not yet built"},
    }
    dataset = {
        "meta": {"schema_version":"1.0","generated_at":iso(now),"refresh_id":refresh_id,"previous_refresh_id":prev_id,
                 "election_date":"2026-11-03","stale": not all(v.get('ok') for v in agents.values()),"agents":agents,
                 "counts": {"races":len(races_out),"states":51,"counties":sum(1 for j in J.values() if j['level']=='county'),"cities":sum(1 for j in J.values() if j['level']=='city'),"videos":len(videos)}},
        "national": national,
        "races": races_out,
        "jurisdictions": J,
        "videos": videos,
        "changes": changes,
        "briefing": {"on_open": on_open, "delta": delta, "alerts": alerts},
        "sources": {"official": {k:v for k,v in official_sources.items() if not k.startswith('_')},
                    "media_tiers": media_sources.get('tiers') or {"1":["AP","Reuters","NBC News","ABC News","CBS News","CNN","Fox News","PBS"],"2":["state and regional newspapers and TV"],"3":["official or very-high-reach accounts on two or more platforms"]},
                    "poll_close": poll_close},
    }
    outs = [a.out] + a.copy_to
    for d in outs:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d,'dataset.json'),'w') as f:
            json.dump(dataset, f, indent=(1 if a.pretty else None), separators=((',',': ') if a.pretty else (',',':')))
    size = os.path.getsize(os.path.join(a.out,'dataset.json'))
    print(f"{refresh_id} generated {iso(now)} — {len(races_out)} races, {dataset['meta']['counts']['counties']} counties, {dataset['meta']['counts']['cities']} cities, {len(videos)} videos, {len(changes)} changes; {size/1e6:.2f} MB -> {outs}")

if __name__ == '__main__':
    main()
