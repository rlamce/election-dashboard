#!/usr/bin/env python3
"""Assemble data/races.json and data/poll_close.json for the 2026 general election."""
import json, re, unicodedata, datetime, sys
sys.path.insert(0, '/home/claude/election-dashboard/tools')

W = '/home/claude/dl/wiki/'
OUT = '/home/claude/election-dashboard/data/'

STATES = {  # postal -> (fips, name)
 'AL':('01','Alabama'),'AK':('02','Alaska'),'AZ':('04','Arizona'),'AR':('05','Arkansas'),'CA':('06','California'),
 'CO':('08','Colorado'),'CT':('09','Connecticut'),'DE':('10','Delaware'),'DC':('11','District of Columbia'),'FL':('12','Florida'),
 'GA':('13','Georgia'),'HI':('15','Hawaii'),'ID':('16','Idaho'),'IL':('17','Illinois'),'IN':('18','Indiana'),'IA':('19','Iowa'),
 'KS':('20','Kansas'),'KY':('21','Kentucky'),'LA':('22','Louisiana'),'ME':('23','Maine'),'MD':('24','Maryland'),'MA':('25','Massachusetts'),
 'MI':('26','Michigan'),'MN':('27','Minnesota'),'MS':('28','Mississippi'),'MO':('29','Missouri'),'MT':('30','Montana'),'NE':('31','Nebraska'),
 'NV':('32','Nevada'),'NH':('33','New Hampshire'),'NJ':('34','New Jersey'),'NM':('35','New Mexico'),'NY':('36','New York'),'NC':('37','North Carolina'),
 'ND':('38','North Dakota'),'OH':('39','Ohio'),'OK':('40','Oklahoma'),'OR':('41','Oregon'),'PA':('42','Pennsylvania'),'RI':('44','Rhode Island'),
 'SC':('45','South Carolina'),'SD':('46','South Dakota'),'TN':('47','Tennessee'),'TX':('48','Texas'),'UT':('49','Utah'),'VT':('50','Vermont'),
 'VA':('51','Virginia'),'WA':('53','Washington'),'WV':('54','West Virginia'),'WI':('55','Wisconsin'),'WY':('56','Wyoming'),
}
NAME2ST = {v[1]: k for k, v in STATES.items()}
NAME2ST['D.C.'] = 'DC'

HOUSE_SEATS = {'AL':7,'AK':1,'AZ':9,'AR':4,'CA':52,'CO':8,'CT':5,'DE':1,'FL':28,'GA':14,'HI':2,'ID':2,'IL':17,'IN':9,'IA':4,'KS':4,'KY':6,'LA':6,'ME':2,'MD':8,'MA':9,'MI':13,'MN':8,'MS':4,'MO':8,'MT':2,'NE':3,'NV':4,'NH':2,'NJ':12,'NM':3,'NY':26,'NC':14,'ND':1,'OH':15,'OK':5,'OR':6,'PA':17,'RI':2,'SC':7,'SD':1,'TN':9,'TX':38,'UT':4,'VT':1,'VA':11,'WA':10,'WV':2,'WI':8,'WY':1}
assert sum(HOUSE_SEATS.values()) == 435

# Poll closing: last statewide close expressed in Eastern Time (EST, UTC-5, on 2026-11-03), plus notes.
# Source: Ballotpedia "State Poll Opening and Closing Times (2026)" converted to ET; AP/NYT convention for split-zone states.
POLL_CLOSE = {
 'AL': ('20:00', '7 p.m. CT statewide (20:00 ET); the few Eastern-time localities close 7 p.m. ET (19:00 ET).'),
 'AK': ('01:00', '8 p.m. local. Mainland Alaska (AKST) = 00:00 ET Nov 4; Aleutian precincts on Hawaii-Aleutian time = 01:00 ET Nov 4 (last close).'),
 'AZ': ('21:00', '7 p.m. MST (Arizona does not observe DST) = 21:00 ET.'),
 'AR': ('20:30', '7:30 p.m. CT.'),
 'CA': ('23:00', '8 p.m. PT. Largely vote-by-mail; ballots postmarked by election day count if received within 7 days.'),
 'CO': ('21:00', '7 p.m. MT. All-mail state.'),
 'CT': ('20:00', '8 p.m. ET.'),
 'DE': ('20:00', '8 p.m. ET.'),
 'DC': ('20:00', '8 p.m. ET. Largely vote-by-mail.'),
 'FL': ('20:00', '7 p.m. local: peninsula (ET) closes 19:00 ET; panhandle (CT) closes 20:00 ET (last close). Statewide results are typically withheld until 20:00 ET.'),
 'GA': ('19:00', '7 p.m. ET.'),
 'HI': ('00:00', '7 p.m. HST = 00:00 ET Nov 4. Largely vote-by-mail.'),
 'ID': ('23:00', '8 p.m. local: southern Idaho (MT) = 22:00 ET; northern panhandle (PT) = 23:00 ET (last close).'),
 'IL': ('20:00', '7 p.m. CT.'),
 'IN': ('19:00', '6 p.m. local: most of state (ET) = 18:00 ET; northwest/southwest counties (CT) = 19:00 ET (last close).'),
 'IA': ('21:00', '8 p.m. CT.'),
 'KS': ('21:00', '7 p.m. local: most of state (CT) = 20:00 ET; four western counties (MT) = 21:00 ET (last close). Counties may stay open until 8 p.m. CT.'),
 'KY': ('19:00', '6 p.m. local: eastern Kentucky (ET) = 18:00 ET; western Kentucky (CT) = 19:00 ET (last close).'),
 'LA': ('21:00', '8 p.m. CT.'),
 'ME': ('20:00', '8 p.m. ET. Ranked-choice voting used for federal general elections.'),
 'MD': ('20:00', '8 p.m. ET.'),
 'MA': ('20:00', '8 p.m. ET.'),
 'MI': ('21:00', '8 p.m. local: Lower Peninsula and most of Upper Peninsula (ET) = 20:00 ET; four western UP counties (CT) = 21:00 ET (last close).'),
 'MN': ('21:00', '8 p.m. CT.'),
 'MS': ('20:00', '7 p.m. CT.'),
 'MO': ('20:00', '7 p.m. CT.'),
 'MT': ('22:00', '8 p.m. MT.'),
 'NE': ('21:00', '8 p.m. CT / 7 p.m. MT = 21:00 ET statewide.'),
 'NV': ('22:00', '7 p.m. PT. Largely vote-by-mail.'),
 'NH': ('20:00', 'Set by municipality; no earlier than 7 p.m. ET. Most towns close 7 p.m.; largest cities 8 p.m. (last close 20:00 ET).'),
 'NJ': ('20:00', '8 p.m. ET.'),
 'NM': ('21:00', '7 p.m. MT.'),
 'NY': ('21:00', '9 p.m. ET.'),
 'NC': ('19:30', '7:30 p.m. ET.'),
 'ND': ('21:00', 'Counties set hours; polls close between 7 and 9 p.m. local. Most close 7 p.m. local (20:00 ET Central / 21:00 ET Mountain). Statutory latest possible close is 9 p.m. MT (23:00 ET).'),
 'OH': ('19:30', '7:30 p.m. ET.'),
 'OK': ('20:00', '7 p.m. CT.'),
 'OR': ('23:00', '8 p.m. local: most of state (PT) = 23:00 ET; Malheur County (MT) = 22:00 ET. All-mail state.'),
 'PA': ('20:00', '8 p.m. ET.'),
 'RI': ('20:00', '8 p.m. ET.'),
 'SC': ('19:00', '7 p.m. ET.'),
 'SD': ('21:00', '7 p.m. local: eastern SD (CT) = 20:00 ET; western SD (MT) = 21:00 ET (last close).'),
 'TN': ('20:00', '8 p.m. ET in East Tennessee / 7 p.m. CT in Middle and West Tennessee = 20:00 ET statewide.'),
 'TX': ('21:00', '7 p.m. local: most of state (CT) = 20:00 ET; El Paso and Hudspeth counties (MT) = 21:00 ET (last close).'),
 'UT': ('22:00', '8 p.m. MT. Largely vote-by-mail.'),
 'VT': ('19:00', '7 p.m. ET.'),
 'VA': ('19:00', '7 p.m. ET.'),
 'WA': ('23:00', '8 p.m. PT. All-mail state.'),
 'WV': ('19:30', '7:30 p.m. ET.'),
 'WI': ('21:00', '8 p.m. CT.'),
 'WY': ('21:00', '7 p.m. MT.'),
}

def close_utc(st):
    hhmm = POLL_CLOSE[st][0]
    h, m = map(int, hhmm.split(':'))
    # ET on Nov 3 2026 is EST (UTC-5). "00:00"/"01:00" are Nov 4 ET.
    day = 3 if h >= 12 else 4
    dt = datetime.datetime(2026, 11, day, h, m) + datetime.timedelta(hours=5)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

# ---------- name normalisation ----------
SUFFIXES = {'jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v'}
def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = s.lower().replace('"', ' ').replace("'", '').replace('.', ' ').replace('-', ' ').replace(',', ' ')
    s = re.sub(r'\(.*?\)', ' ', s)
    toks = [t for t in s.split() if t not in SUFFIXES]
    return toks

NICK = {
 'chris': 'christopher', 'jim': 'james', 'jimmy': 'james', 'ed': 'edward', 'eddie': 'edward', 'ted': 'edward', 'dick': 'richard', 'rick': 'richard', 'rich': 'richard',
 'mike': 'michael', 'bill': 'william', 'will': 'william', 'billy': 'william', 'bob': 'robert', 'rob': 'robert', 'bobby': 'robert', 'robbie': 'robert',
 'tom': 'thomas', 'tommy': 'thomas', 'dan': 'daniel', 'danny': 'daniel', 'dave': 'david', 'steve': 'steven', 'joe': 'joseph', 'joey': 'joseph',
 'tony': 'anthony', 'andy': 'andrew', 'drew': 'andrew', 'pat': 'patrick', 'patty': 'patricia', 'pete': 'peter', 'ben': 'benjamin', 'benny': 'benjamin',
 'sam': 'samuel', 'nick': 'nicholas', 'matt': 'matthew', 'greg': 'gregory', 'gregg': 'gregory', 'jeff': 'jeffrey', 'ken': 'kenneth', 'kenny': 'kenneth',
 'ron': 'ronald', 'ronny': 'ronald', 'ronnie': 'ronald', 'don': 'donald', 'larry': 'lawrence', 'jerry': 'gerald', 'gerry': 'gerald', 'jack': 'john', 'johnny': 'john',
 'jon': 'jonathan', 'josh': 'joshua', 'zach': 'zachary', 'alex': 'alexander', 'al': 'albert', 'max': 'maxwell', 'fred': 'frederick', 'frank': 'francis',
 'hank': 'henry', 'harry': 'harold', 'ray': 'raymond', 'russ': 'russell', 'tim': 'timothy', 'terry': 'terence', 'vince': 'vincent', 'walt': 'walter',
 'liz': 'elizabeth', 'beth': 'elizabeth', 'betty': 'elizabeth', 'kathy': 'katherine', 'kate': 'katherine', 'katie': 'katherine', 'cathy': 'catherine',
 'debbie': 'deborah', 'deb': 'deborah', 'sue': 'susan', 'suzy': 'susan', 'peggy': 'margaret', 'maggie': 'margaret', 'meg': 'margaret',
 'becky': 'rebecca', 'jen': 'jennifer', 'jenny': 'jennifer', 'nancy': 'ann', 'cindy': 'cynthia', 'cyndi': 'cynthia', 'lori': 'lorraine',
 'abe': 'abraham', 'mitch': 'mitchell', 'lou': 'louis', 'jay': 'james', 'jb': 'jay', 'gus': 'august', 'augie': 'august', 'chuck': 'charles', 'charlie': 'charles',
 'rand': 'randal', 'randy': 'randall', 'lloyd': 'lloyd', 'teddy': 'theodore', 'mo': 'maurice', 'phil': 'philip', 'nate': 'nathaniel', 'nat': 'nathaniel',
 'gabe': 'gabriel', 'herb': 'herbert', 'marty': 'martin', 'doug': 'douglas', 'glenn': 'glenn', 'brad': 'bradley', 'wes': 'wesley', 'les': 'leslie',
 'vicky': 'victoria', 'vicki': 'victoria', 'trish': 'patricia', 'tricia': 'patricia', 'mary gay': 'mary', 'josh': 'joshua', 'jared': 'jared',
 'bernie': 'bernard', 'dusty': 'dustin', 'hal': 'harold', 'buddy': 'buddy', 'french': 'french', 'tj': 'thomas', 'rj': 'robert', 'jd': 'james',
}
NICK['gil'] = 'gilbert'; NICK['lou'] = 'louis'
EXTRA = {'louis': {'luis'}, 'jeffrey': {'jefferson'}, 'gregory': {'gregg'}}
def canon_first(tok):
    tok = tok.lower()
    return NICK.get(tok, tok)

def firsts_equal(a, b):
    # a, b: canonical first-name strings
    if a == b: return True
    if a in EXTRA and b in EXTRA[a]: return True
    if b in EXTRA and a in EXTRA[b]: return True
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)): return True
    return False

def first_tokens(name_tokens):
    """candidate first-name variants: first token (canonical) and, if present, first two tokens."""
    if not name_tokens: return set()
    out = {canon_first(name_tokens[0])}
    if len(name_tokens) >= 3: out.add(canon_first(name_tokens[0]) + ' ' + name_tokens[1])
    return out

def member_firsts(nm):
    outs = set()
    for f in filter(None, [nm.get('first'), nm.get('nickname')]):
        toks = norm(f)
        if toks: outs.add(canon_first(toks[0]))
    of = nm.get('official_full')
    if of:
        toks = norm(of)
        if toks: outs.add(canon_first(toks[0]))
        # members who go by a middle name: "J. French Hill", "H. Morgan Griffith", "W. Gregory Steube"
        if len(toks) >= 3 and len(toks[0]) == 1: outs.add(canon_first(toks[1]))
    if nm.get('middle') and nm.get('first') and len(norm(nm['first'])[0]) == 1:
        outs.add(canon_first(norm(nm['middle'])[0]))
    return outs

def member_lasts(nm):
    outs = set()
    l = norm(nm.get('last', ''))
    if l: outs.add(' '.join(l)); outs.add(l[-1])
    of = nm.get('official_full')
    if of:
        toks = norm(of)
        if len(toks) >= 2: outs.add(toks[-1]); outs.add(' '.join(toks[-2:]))
    return outs

def cand_lasts(toks):
    outs = set()
    if toks:
        outs.add(toks[-1])
        if len(toks) >= 3: outs.add(' '.join(toks[-2:]))
    return outs

def slug(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s

def ordinal(n):
    return "%d%s" % (n, "tsnrhtdd"[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10::4])

def last_slug(name):
    n = norm(name)
    return slug(n[-1]) if n else slug(name)

# ---------- load inputs ----------
legis = json.load(open('/home/claude/dl/legislators/legislators-current.json'))
reps = {}; sens = {}; all_members = []
for p in legis:
    t = p['terms'][-1]
    nm = p['name']
    full = nm.get('official_full') or ' '.join(filter(None, [nm.get('first'), nm.get('middle'), nm.get('last'), nm.get('suffix')]))
    party = {'Republican': 'R', 'Democrat': 'D', 'Independent': 'I'}.get(t['party'], 'O')
    rec = {'name': full, 'party': party, 'party_label': t['party'], 'bioguide': p['id']['bioguide'],
           'firsts': member_firsts(nm), 'lasts': member_lasts(nm),
           'type': t['type'], 'state': t['state'], 'district': t.get('district'), 'class': t.get('class'), 'start': t['start']}
    all_members.append(rec)
    if t['type'] == 'rep': reps[(t['state'], t['district'])] = rec
    else: sens[(t['state'], t['class'])] = rec

def match_member(name, pool):
    toks = norm(name)
    cf, cl = first_tokens(toks), cand_lasts(toks)
    hits = [m for m in pool if (m['lasts'] & cl) and any(firsts_equal(a, b) for a in m['firsts'] for b in cf)]
    uniq = {m.get('bioguide') or m['name']: m for m in hits}
    return list(uniq.values())

sen_w = json.load(open(W + 'sen_parsed.json'))
gov_w = json.load(open(W + 'gov_parsed.json'))
hou_w = json.load(open(W + 'hou_parsed.json'))
pres24 = json.load(open(W + 'pres24_parsed.json'))
res22 = json.load(open(W + 'res22_parsed.json'))

# Florida / Ohio special rows parsed separately (table in the "Special elections" section)
import parse_wiki as pw
sen_text = open(W + 'sen_raw.txt', encoding='utf-8').read()
sen_sp = pw.parse_summary_table(sen_text, '=== Special elections during the preceding Congress ===')
# fix label (strip "(Class 3)") and mark special
for r in sen_sp:
    r['label'] = r['label'].replace('<br />(Class 3)', '').strip()
    r['special'] = True
    if not r['incumbent']:
        m = re.search(r'\n\|\s*\[\[([^\]|]*)\]\]', r['raw_head'])
    # incumbents known: FL Ashley Moody, OH Jon Husted
sen_sp_by_state = {NAME2ST[r['label'].split('<br')[0].strip()]: r for r in sen_sp}
assert set(sen_sp_by_state) == {'FL', 'OH'}, sen_sp_by_state.keys()

# ---------- baselines ----------
def pres_baseline(st):
    name = STATES[st][1] if st != 'DC' else 'D.C.'
    v = pres24[name]
    return {'office': 'PRES', 'year': 2024, 'D': round(v['D'], 1), 'R': round(v['R'], 1), 'margin': round(v['R'] - v['D'], 1)}

def top_pct(cands, party):
    xs = [c['pct'] for c in cands if c['party'] == party]
    return max(xs) if xs else None

def b22_from(cands, office, note=None):
    d, r = top_pct(cands, 'D'), top_pct(cands, 'R')
    out = {'office': office, 'year': 2022, 'D': d, 'R': r, 'margin': round(r - d, 1) if (d is not None and r is not None) else None}
    if note: out['note'] = note
    return out

# manual overrides / fallbacks for the 2022 slot
MANUAL_22 = {
 ('GA', 'SEN'): {'office': 'SEN', 'year': 2022, 'D': 49.4, 'R': 48.5, 'margin': -0.9, 'note': 'November 2022 general (first round). December runoff: Warnock (D) 51.4, Walker (R) 48.6.'},
 ('AK', 'SEN'): {'office': 'SEN', 'year': 2022, 'D': 10.4, 'R': 43.4, 'margin': 33.0, 'note': 'Top-four RCV first round: Murkowski (R) 43.4, Tshibaka (R) 42.6, Chesbro (D) 10.4; final round Murkowski 53.7 vs Tshibaka 46.3 (R vs R). D/R margin is not comparable to a two-party race.'},
 ('LA', 'SEN'): {'office': 'SEN', 'year': 2022, 'D': 17.9, 'R': 61.6, 'margin': 43.7, 'note': 'Jungle primary: Kennedy (R) 61.6; top Democrat Chambers 17.9 (all Democrats combined approx. 34.9); Louisiana now uses closed party primaries for Senate.'},
 ('DE', 'SEN'): {'office': 'HOU-AL', 'year': 2022, 'D': 55.5, 'R': 43.0, 'margin': -12.5, 'note': 'No Senate or governor race in Delaware in 2022; using 2022 U.S. House at-large (statewide) result: Blunt Rochester (D) 55.5, Murphy (R) 43.0.'},
 ('MS', 'SEN'): {'office': 'GOV', 'year': 2023, 'D': 47.7, 'R': 50.9, 'margin': 3.2, 'note': 'No statewide partisan race in Mississippi in 2022; using 2023 governor result: Reeves (R) 50.9, Presley (D) 47.7.'},
 ('MT', 'SEN'): {'office': 'SEN', 'year': 2024, 'D': 45.5, 'R': 52.6, 'margin': 7.1, 'note': 'No statewide partisan race in Montana in 2022; using 2024 U.S. Senate result: Sheehy (R) 52.6, Tester (D) 45.5.'},
 ('NJ', 'SEN'): {'office': 'GOV', 'year': 2021, 'D': 51.2, 'R': 48.0, 'margin': -3.2, 'note': 'No statewide race in New Jersey in 2022; using 2021 governor result: Murphy (D) 51.2, Ciattarelli (R) 48.0.'},
 ('VA', 'SEN'): {'office': 'GOV', 'year': 2021, 'D': 48.6, 'R': 50.6, 'margin': 2.0, 'note': 'No statewide race in Virginia in 2022; using 2021 governor result: Youngkin (R) 50.6, McAuliffe (D) 48.6.'},
 ('WV', 'SEN'): {'office': 'SEN', 'year': 2024, 'D': 27.8, 'R': 68.8, 'margin': 41.0, 'note': 'No statewide partisan race in West Virginia in 2022; using 2024 U.S. Senate result: Justice (R) 68.8, Elliott (D) 27.8.'},
}

def baseline_2022(st, office):
    key = (st, office)
    if key in MANUAL_22: return MANUAL_22[key]
    name = STATES[st][1]
    if office == 'SEN':
        if name in res22['SEN']: return b22_from(res22['SEN'][name], 'SEN')
        if name in res22['GOV']: return b22_from(res22['GOV'][name], 'GOV', note='No Senate race in this state in 2022; using 2022 governor result.')
        raise SystemExit('no 2022 baseline for ' + st)
    else:
        if name in res22['GOV']: return b22_from(res22['GOV'][name], 'GOV')
        raise SystemExit('no 2022 gov baseline for ' + st)

# ---------- build candidates ----------
def build_cands(race_id, wiki_cands, incumbent_pool):
    out = []
    used = {}
    for c in wiki_cands:
        base = last_slug(c['name'])
        if base in used or any(last_slug(o['name']) == base for o in wiki_cands if o is not c):
            cid = f"{race_id}:{slug(c['name'])}"
        else:
            cid = f"{race_id}:{base}"
        used[base] = True
        rec = {'id': cid, 'name': c['name'], 'party': c['party'], 'incumbent': False}
        if c['party_label'] and c['party_label'].lower() not in ('republican', 'democratic', 'independent', 'libertarian', 'green'):
            rec['party_label'] = c['party_label']
        if c.get('note'): rec['note'] = c['note']
        hits = match_member(c['name'], incumbent_pool)
        if hits:
            rec['incumbent'] = True
            rec['bioguide'] = hits[0]['bioguide']
            rec['_member'] = hits[0]['name']
        out.append(rec)
    # ambiguity: two candidates matched to the same member -> apply manual override or clear
    by_member = {}
    for rec in out:
        if rec['incumbent']: by_member.setdefault(rec.get('bioguide') or rec['_member'], []).append(rec)
    for mid, recs in by_member.items():
        if len(recs) > 1:
            keep = INCUMBENT_OVERRIDE.get(race_id)
            for rec in recs:
                if rec['name'] != keep:
                    rec['incumbent'] = False; rec.pop('bioguide', None)
            if not keep: WARN.append(f"ambiguous incumbent match in {race_id}: {[r['name'] for r in recs]}")
    for rec in out: rec.pop('_member', None)
    return out

INCUMBENT_OVERRIDE = {'AK-SEN-2026': 'Dan S. Sullivan'}
WARN = []

races = {}
sources = []

# ---------- Senate ----------
sen_count = 0
for r in sen_w + sen_sp:
    st = NAME2ST[r['label'].split('<br')[0].strip()]
    special = bool(r.get('special'))
    race_id = f"{st}-SEN-2026" + ('-S' if special else '')
    seat_class = 3 if special else 2
    inc = sens.get((st, seat_class))
    pool = [inc] if inc else []
    cands = build_cands(race_id, r['candidates'], pool)
    rec = {
        'race_id': race_id, 'state': st, 'state_fips': STATES[st][0], 'office': 'SEN', 'district': None, 'special': special,
        'label': f"{STATES[st][1]} U.S. Senate" + (' (special)' if special else ''),
        'seat_class': seat_class,
        'incumbent': {'name': inc['name'], 'party': inc['party'], 'bioguide': inc['bioguide'], 'running': any(c['incumbent'] for c in cands)} if inc else None,
        'candidates': cands,
        'poll_close_et': POLL_CLOSE[st][0],
        'baseline': {'2024': pres_baseline(st), '2022': baseline_2022(st, 'SEN')},
        'notes': (r.get('status') or '').replace('<br />', ' ').strip(),
        'source': f"https://en.wikipedia.org/wiki/{r['page'].replace(' ', '_')}",
    }
    if st == 'AK': rec['notes'] += ' Top-four primary; general election uses ranked-choice voting among the four listed candidates.'
    if st == 'ME': rec['notes'] += ' Ranked-choice voting.'
    if st == 'GA': rec['notes'] += ' Runoff on December 1, 2026 if no candidate exceeds 50%.'
    if st == 'LA': rec['notes'] += ' First Louisiana Senate election under closed party primaries (no jungle primary).'
    races[race_id] = rec
    sen_count += 1

# ---------- Governors ----------
gov_count = 0
GOV_INC_FIX = {'SD': ('Larry Rhoden', 'R'), 'MN': ('Tim Walz', 'D')}
for r in gov_w:
    st = NAME2ST[r['label']]
    race_id = f"{st}-GOV-2026"
    inc_name, inc_party = r['incumbent'], {'Republican': 'R', 'Democratic': 'D', 'DFL': 'D'}.get(r['incumbent_party'] or '', None)
    if st in GOV_INC_FIX: inc_name, inc_party = GOV_INC_FIX[st]
    assert inc_name and inc_party, (st, r)
    _t = norm(inc_name)
    pool = [{'name': inc_name, 'party': inc_party, 'bioguide': None, 'firsts': first_tokens(_t), 'lasts': cand_lasts(_t)}]
    cands = build_cands(race_id, r['candidates'], pool)
    for c in cands: c.pop('bioguide', None)
    status = (r.get('status') or '').replace('nowrap', '').strip()
    rec = {
        'race_id': race_id, 'state': st, 'state_fips': STATES[st][0], 'office': 'GOV', 'district': None, 'special': False,
        'label': f"{STATES[st][1]} Governor",
        'incumbent': {'name': inc_name, 'party': inc_party, 'running': any(c['incumbent'] for c in cands)},
        'candidates': cands,
        'poll_close_et': POLL_CLOSE[st][0],
        'baseline': {'2024': pres_baseline(st), '2022': baseline_2022(st, 'GOV')},
        'notes': status,
        'source': f"https://en.wikipedia.org/wiki/{r['page'].replace(' ', '_')}",
    }
    if st == 'AK': rec['notes'] += ' Top-four primary; general election uses ranked-choice voting among the four listed candidates.'
    if st == 'ME': rec['notes'] += ' Ranked-choice voting is NOT used for the general election for governor (state offices use plurality).'
    if st == 'GA': rec['notes'] += ' Runoff on December 1, 2026 if no candidate exceeds 50%.'
    if st == 'VT': rec['notes'] += ' Two-year term.'
    if st == 'NH': rec['notes'] += ' Two-year term.'
    races[race_id] = rec
    gov_count += 1

# ---------- House ----------
REDISTRICTED = {'AL', 'CA', 'FL', 'LA', 'NC', 'OH', 'TN', 'TX', 'UT'}
NEW_SEATS = {'AL-01', 'CA-38', 'FL-22', 'TX-09', 'TX-30', 'TX-32', 'TX-35', 'UT-01'}
house_full = house_inc_only = 0
rep_pool = [m for m in all_members if m['type'] == 'rep']
for st, n in HOUSE_SEATS.items():
    for d in (range(1, n + 1) if n > 1 else [0]):
        race_id = f"{st}-HOU-2026-{d:02d}"
        key = f"{st}-{d:02d}"
        inc = reps.get((st, d))
        w = hou_w.get(key, {})
        cands = build_cands(race_id, w.get('candidates', []), [m for m in rep_pool if m['state'] == st])
        # incumbent flag semantics: candidate currently serves in the House (any district); note if from another district
        for c in cands:
            if c['incumbent']:
                m = next(x for x in rep_pool if x['bioguide'] == c['bioguide'])
                if (m['state'], m['district']) != (st, d):
                    c['incumbent_of'] = f"{m['state']}-{m['district']:02d}"
        complete = bool(cands)
        label = f"{STATES[st][1]} " + (f"{ordinal(d)} Congressional District" if d else "At-Large Congressional District")
        rec = {
            'race_id': race_id, 'state': st, 'state_fips': STATES[st][0], 'office': 'HOU', 'district': f"{d:02d}", 'special': False,
            'label': label,
            'incumbent': {'name': inc['name'], 'party': inc['party'], 'bioguide': inc['bioguide'], 'running': any(c.get('incumbent') and c.get('bioguide') == inc['bioguide'] for c in cands)} if inc else None,
            'candidates': cands,
            'candidates_incomplete': not complete,
            'poll_close_et': POLL_CLOSE[st][0],
            'notes': '',
            'source': f"https://en.wikipedia.org/wiki/2026_United_States_House_of_Representatives_elections#{STATES[st][1].replace(' ', '_')}",
        }
        if inc is None: rec['notes'] = 'Seat vacant at time of roster build (no incumbent in legislators-current).'
        if st in REDISTRICTED: rec['redistricted_2026'] = True
        if key in NEW_SEATS: rec['notes'] = (rec['notes'] + ' New district with no incumbent under the 2026 map.').strip()
        if st in REDISTRICTED and w.get('wiki_incumbents'):
            wi = [x for x in w['wiki_incumbents'] if not re.match(r'^\d{4}', x)]
            if wi: rec['wiki_incumbent_2026_map'] = wi
        if st == 'AK': rec['notes'] = (rec['notes'] + ' Top-four primary; ranked-choice general election.').strip()
        if st == 'ME': rec['notes'] = (rec['notes'] + ' Ranked-choice voting.').strip()
        if st == 'LA': rec['notes'] = (rec['notes'] + ' Closed party primaries used for the first time for U.S. House in 2026.').strip()
        if st == 'CA' or st == 'WA': rec['notes'] = (rec['notes'] + ' Top-two primary; both general-election candidates may share a party.').strip()
        races[race_id] = rec
        if complete: house_full += 1
        else: house_inc_only += 1


now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
meta = {
    'schema_version': '1.0', 'generated_at': now, 'election_date': '2026-11-03',
    'counts': {'SEN': sen_count, 'SEN_special': sum(1 for r in races.values() if r['office'] == 'SEN' and r['special']),
               'GOV': gov_count, 'HOU': house_full + house_inc_only, 'HOU_with_candidates': house_full, 'HOU_incumbent_only': house_inc_only},
    'conventions': {
        'margin': 'R minus D (positive = Republican lead).',
        'incumbent_flag': 'Candidate currently holds the office being contested (Senate/governor) or currently serves in the U.S. House in any district (House; see incumbent_of when the member was redistricted into a different district number).',
        'house_incumbent_field': 'House race.incumbent is the member currently representing that district NUMBER per unitedstates/congress-legislators (pre-2026-map numbering). In redistricted states (redistricted_2026=true) the 2026 district boundaries differ; wiki_incumbent_2026_map lists the member(s) Wikipedia treats as incumbent under the new map.',
        'poll_close_et': 'Last statewide poll close in U.S. Eastern Time (EST, UTC-5). 00:00 and 01:00 mean Nov 4 ET (Hawaii, Alaska). See poll_close.json for notes and UTC.',
        'baseline_2022': 'Same office in 2022 when available; otherwise another statewide race, with office/year/note set explicitly (DE: 2022 House at-large; MS: 2023 GOV; MT: 2024 SEN; NJ/VA: 2021 GOV; WV: 2024 SEN).',
    },
    'sources': [
        {'id': 'legislators-current', 'url': 'https://unitedstates.github.io/congress-legislators/legislators-current.json', 'used_for': 'Current House/Senate incumbents, parties, bioguide IDs', 'retrieved_at': now},
        {'id': 'wiki-sen-2026', 'url': 'https://en.wikipedia.org/wiki/2026_United_States_Senate_elections', 'used_for': 'Senate seat list, incumbents, general-election candidates', 'retrieved_at': now},
        {'id': 'wiki-gov-2026', 'url': 'https://en.wikipedia.org/wiki/2026_United_States_gubernatorial_elections', 'used_for': 'Governor race list, incumbents, general-election candidates', 'retrieved_at': now},
        {'id': 'wiki-hou-2026', 'url': 'https://en.wikipedia.org/wiki/2026_United_States_House_of_Representatives_elections', 'used_for': 'House general-election candidates for all 435 districts; mid-decade redistricting status', 'retrieved_at': now},
        {'id': 'bp-sen-2026', 'url': 'https://ballotpedia.org/United_States_Senate_elections,_2026', 'used_for': 'Cross-check of the 35-seat Senate list (33 regular + FL, OH specials)', 'retrieved_at': now},
        {'id': 'bp-gov-2026', 'url': 'https://ballotpedia.org/Gubernatorial_elections,_2026', 'used_for': 'Cross-check of the 36-state governor list', 'retrieved_at': now},
        {'id': 'bp-hou-pa-2026', 'url': 'https://ballotpedia.org/United_States_House_of_Representatives_elections_in_Pennsylvania,_2026', 'used_for': 'Spot-check of House candidate lists (all 17 PA districts matched)', 'retrieved_at': now},
        {'id': 'bp-poll-times-2026', 'url': 'https://ballotpedia.org/State_Poll_Opening_and_Closing_Times_(2026)', 'used_for': 'Poll closing times (local), converted to ET', 'retrieved_at': now},
        {'id': 'wiki-pres-2024', 'url': 'https://en.wikipedia.org/wiki/2024_United_States_presidential_election#Results_by_state', 'used_for': 'baseline.2024 statewide presidential D%/R% (certified totals)', 'retrieved_at': now},
        {'id': 'wiki-sen-2022', 'url': 'https://en.wikipedia.org/wiki/2022_United_States_Senate_elections', 'used_for': 'baseline.2022 Senate results', 'retrieved_at': now},
        {'id': 'wiki-gov-2022', 'url': 'https://en.wikipedia.org/wiki/2022_United_States_gubernatorial_elections', 'used_for': 'baseline.2022 governor results', 'retrieved_at': now},
        {'id': 'wiki-de-hou-2022', 'url': 'https://en.wikipedia.org/wiki/2022_United_States_House_of_Representatives_election_in_Delaware', 'used_for': 'DE 2022-slot fallback baseline', 'retrieved_at': now},
        {'id': 'wiki-ms-gov-2023', 'url': 'https://en.wikipedia.org/wiki/2023_Mississippi_gubernatorial_election', 'used_for': 'MS 2022-slot fallback baseline', 'retrieved_at': now},
        {'id': 'wiki-mt-sen-2024', 'url': 'https://en.wikipedia.org/wiki/2024_United_States_Senate_election_in_Montana', 'used_for': 'MT 2022-slot fallback baseline', 'retrieved_at': now},
        {'id': 'wiki-nj-gov-2021', 'url': 'https://en.wikipedia.org/wiki/2021_New_Jersey_gubernatorial_election', 'used_for': 'NJ 2022-slot fallback baseline', 'retrieved_at': now},
        {'id': 'wiki-va-gov-2021', 'url': 'https://en.wikipedia.org/wiki/2021_Virginia_gubernatorial_election', 'used_for': 'VA 2022-slot fallback baseline', 'retrieved_at': now},
        {'id': 'wiki-wv-sen-2024', 'url': 'https://en.wikipedia.org/wiki/2024_United_States_Senate_election_in_West_Virginia', 'used_for': 'WV 2022-slot fallback baseline', 'retrieved_at': now},
        {'id': 'wiki-mi-gov-2026', 'url': 'https://en.wikipedia.org/wiki/2026_Michigan_gubernatorial_election', 'used_for': 'Confirmed Mike Duggan (I) withdrew', 'retrieved_at': now},
        {'id': 'news-sc-sen', 'url': 'https://www.wtoc.com/2026/08/26/graham-andrews-face-off-november-senate-election/', 'used_for': 'Confirmed SC Senate general: Darline Graham (R, appointed) vs Annie Andrews (D)', 'retrieved_at': now},
    ],
    'redistricted_states_2026': sorted(REDISTRICTED),
    'vacant_house_seats_at_build': [k for k in [f"{s}-{d:02d}" for s, n in HOUSE_SEATS.items() for d in (range(1, n+1) if n > 1 else [0])] if (k[:2], int(k[3:])) not in reps],
}

out = {'_meta': meta}
out.update(dict(sorted(races.items())))
json.dump(out, open(OUT + 'races.json', 'w'), indent=1, ensure_ascii=False)

pc = {'_meta': {'generated_at': now, 'election_date': '2026-11-03', 'timezone_note': 'close_et is U.S. Eastern Standard Time (UTC-5). Values 00:00/01:00 fall on Nov 4 ET. close_utc is unambiguous.',
                'sources': ['https://ballotpedia.org/State_Poll_Opening_and_Closing_Times_(2026)']}}
for st in sorted(POLL_CLOSE):
    pc[st] = {'close_et': POLL_CLOSE[st][0], 'close_utc': close_utc(st), 'notes': POLL_CLOSE[st][1]}
json.dump(pc, open(OUT + 'poll_close.json', 'w'), indent=1, ensure_ascii=False)

print(json.dumps(meta['counts']))
for w_ in WARN: print('WARN', w_)
print('vacant:', meta['vacant_house_seats_at_build'])
