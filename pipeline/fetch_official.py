#!/usr/bin/env python3
"""Official Results agent: pull every verified state feed and emit raw records.

Run from anywhere:  python3 -I pipeline/fetch_official.py [--states CO,IA] [--workers 8]

Reads   data/official_sources.json   (feed directory; only states with a verified feed are fetched)
        data/races.json               (race roster; candidate ids are <race_id>:<lastname>)
        app/data/counties-10m.json    (county name -> FIPS table)
Writes  data/official_results.json    array of raw records per CONTRACT.md:
          { jkey, race_id, votes:{candidate_id:n}, pct_reporting, status, retrieved_at, url,
            state, level, winner:[candidate_id], extra_parties:{id:party}, precincts:[rep,total], platform }
        data/official_fetch_log.json  per-state ok/error/elapsed/record counts/unmatched names

Design rules
  * one parser per platform family; a state's failure never stops the others
  * 20 s timeout per request, 3 attempts with backoff, browser-like User-Agent
  * candidates are matched by last name against races.json (case/diacritic/suffix insensitive);
    names that do not match are logged, never guessed; their votes are kept under
    "<race_id>:~<slug>" so party percentages still add up
  * rows that are not from the 2026-11-03 general election are discarded and logged
  * status is always official_preliminary (certification is weeks away)
"""
import argparse
import csv
import datetime as dt
import html
import io
import json
import os
import re
import sys
import threading
import time
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELECTION_DATE = "2026-11-03"
ELECTION_DATE_US = ("11/03/2026", "11/3/2026")
STATUS = "official_preliminary"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0.0.0 Safari/537.36")
TIMEOUT = 20
RETRIES = 3
BACKOFF = (1.0, 2.5, 5.0)

STATE_FIPS = {
 'AL':'01','AK':'02','AZ':'04','AR':'05','CA':'06','CO':'08','CT':'09','DE':'10','DC':'11','FL':'12','GA':'13','HI':'15','ID':'16','IL':'17',
 'IN':'18','IA':'19','KS':'20','KY':'21','LA':'22','ME':'23','MD':'24','MA':'25','MI':'26','MN':'27','MS':'28','MO':'29','MT':'30','NE':'31',
 'NV':'32','NH':'33','NJ':'34','NM':'35','NY':'36','NC':'37','ND':'38','OH':'39','OK':'40','OR':'41','PA':'42','RI':'44','SC':'45','SD':'46',
 'TN':'47','TX':'48','UT':'49','VT':'50','VA':'51','WA':'53','WV':'54','WI':'55','WY':'56'}

ORDINALS = {'first':1,'second':2,'third':3,'fourth':4,'fifth':5,'sixth':6,'seventh':7,'eighth':8,'ninth':9,'tenth':10,
            'eleventh':11,'twelfth':12,'thirteenth':13,'fourteenth':14,'fifteenth':15,'sixteenth':16,'seventeenth':17,
            'eighteenth':18,'nineteenth':19,'twentieth':20}
ROMAN = {'i':1,'ii':2,'iii':3,'iv':4,'v':5,'vi':6,'vii':7,'viii':8,'ix':9,'x':10}
SUFFIXES = {'jr','sr','ii','iii','iv','v','esq','md','phd','w/i','wi','write-in','writein'}

# RI reports by city/town; map to its five counties.
RI_TOWN_COUNTY = {
 'barrington':'44001','bristol':'44001','warren':'44001',
 'coventry':'44003','east greenwich':'44003','warwick':'44003','west greenwich':'44003','west warwick':'44003',
 'jamestown':'44005','little compton':'44005','middletown':'44005','newport':'44005','portsmouth':'44005','tiverton':'44005',
 'burrillville':'44007','central falls':'44007','cranston':'44007','cumberland':'44007','east providence':'44007','foster':'44007',
 'glocester':'44007','johnston':'44007','lincoln':'44007','north providence':'44007','north smithfield':'44007','pawtucket':'44007',
 'providence':'44007','scituate':'44007','smithfield':'44007','woonsocket':'44007',
 'charlestown':'44009','exeter':'44009','hopkinton':'44009','narragansett':'44009','new shoreham':'44009','north kingstown':'44009',
 'richmond':'44009','south kingstown':'44009','westerly':'44009'}

# ---------------------------------------------------------------- utilities

def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def norm_text(s):
    s = html.unescape(s or '')
    s = strip_accents(s).lower()
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def to_int(v):
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(',', '').replace('="', '').replace('"', '')
    if not s or s.upper() in ('NR', 'N/A', '-'):
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def pct_of(reported, total):
    try:
        reported = float(reported); total = float(total)
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return None
    return round(min(100.0, 100.0 * reported / total), 1)


def parse_frac(s):
    """'0/1322', '="0/1322"', '(0 of 23,860)' -> (0, 1322)"""
    if s is None:
        return None
    m = re.search(r'(\d[\d,]*)\s*(?:/|of)\s*(\d[\d,]*)', str(s))
    if not m:
        return None
    return to_int(m.group(1)), to_int(m.group(2))


def norm_party(p):
    """Feed party label -> contract code D/R/I/L/G/O."""
    if not p:
        return 'O'
    s = norm_text(str(p)).strip('() ')
    if s in ('d', 'dem', 'democrat', 'democratic', 'democratic party', 'dem/prog', 'democratic-farmer-labor', 'dfl'):
        return 'D'
    if s in ('r', 'rep', 'republican', 'republican party', 'gop'):
        return 'R'
    if s in ('i', 'ind', 'independent', 'npa', 'nop', 'nopty', 'no party affiliation', 'no party', 'unaffiliated',
             'una', 'uaf', 'non', 'nonpartisan', 'non partisan', 'non-partisan', 'n', 'no', 'pet', 'petition', 'by petition'):
        return 'I'
    if s in ('l', 'lib', 'lbr', 'lpf', 'libertarian', 'libertarian party'):
        return 'L'
    if s in ('g', 'gre', 'grn', 'green', 'green party', 'pacific green'):
        return 'G'
    if s.startswith('democrat'):
        return 'D'
    if s.startswith('republican'):
        return 'R'
    if s.startswith('libertarian'):
        return 'L'
    if s.startswith('green'):
        return 'G'
    if s.startswith('independ') or s.startswith('unaffil') or s.startswith('no party'):
        return 'I'
    return 'O'


def name_tokens(name):
    """Tokens for matching: lowercased, de-accented, parentheticals/nicknames/suffixes removed,
    hyphenated parts split (and joined), apostrophes stripped. Returns a set."""
    s = html.unescape(name or '')
    s = strip_accents(s).lower()
    s = re.sub(r'\([^)]*\)', ' ', s)                       # (I) (Rep) (W/I) (Nick)
    s = re.sub(r'(?<!\w)"[^"]*"', ' ', s)                   # "Jim"
    s = re.sub(r"(?<!\w)'[^']*'(?!\w)", ' ', s)             # 'Brad'
    s = s.replace('&', ' and ')
    s = re.sub(r'[^a-z0-9\'\-\s/]', ' ', s)                 # drop commas, periods, quotes
    s = re.sub(r'\s+', ' ', s)
    raw = re.split(r'[\s/]+', s)
    toks = set()
    for t in raw:
        t = t.strip("'-")
        if not t or t in SUFFIXES or t == 'and':
            continue
        if len(t) == 1:          # initials
            continue
        toks.add(t)
        if "'" in t:
            toks.add(t.replace("'", ''))
        if '-' in t:
            parts = [p for p in t.split('-') if p]
            toks.update(parts)
            toks.add(''.join(parts))
    return toks


def is_writein(name, party=None):
    n = norm_text(name)
    if party and re.search(r'write', str(party), re.I):
        return True
    return bool(re.search(r'write[\s-]*in|\(w/?i\)', n)) or n in ('other', 'others', 'scattering', 'blank', 'over votes', 'under votes', 'overvotes', 'undervotes', 'all others')


def slug(name):
    s = strip_accents(html.unescape(name or '')).lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or 'unknown'


# ---------------------------------------------------------------- HTTP

class Http:
    """requests wrapper: 20 s timeout, 3 attempts with backoff, browser-like UA."""
    def __init__(self, log):
        self.s = requests.Session()
        self.s.headers.update({'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9'})
        self.log = log
        self.count = 0

    def get(self, url, kind='text', ok_404=False, headers=None):
        last = None
        for attempt in range(RETRIES):
            try:
                self.count += 1
                r = self.s.get(url, timeout=TIMEOUT, headers=headers)
                if r.status_code == 404 and ok_404:
                    return None
                if r.status_code >= 400:
                    raise requests.HTTPError(f'HTTP {r.status_code} for {url}')
                if kind == 'bytes':
                    return r.content
                if kind == 'json':
                    try:
                        return r.json()
                    except ValueError:
                        txt = r.content.decode('utf-8-sig', 'replace').strip()
                        return json.loads(txt)
                # most feeds are UTF-8 even when the server says ISO-8859-1; try UTF-8 first
                try:
                    return r.content.decode('utf-8-sig')
                except UnicodeDecodeError:
                    return r.content.decode(r.encoding or 'cp1252', 'replace')
            except Exception as e:  # noqa: BLE001
                last = e
                if attempt < RETRIES - 1:
                    time.sleep(BACKOFF[attempt])
        raise RuntimeError(f'{type(last).__name__}: {last}')


# ---------------------------------------------------------------- roster and county index

class Roster:
    def __init__(self, path):
        with open(path) as f:
            raw = json.load(f)
        self.races = {k: v for k, v in raw.items() if not k.startswith('_')}
        self.by_key = {}
        for rid, r in self.races.items():
            key = (r['state'], r['office'])
            self.by_key.setdefault(key, []).append(r)
        self.cands = {}
        for rid, r in self.races.items():
            cl = []
            for c in r.get('candidates', []):
                key = c['id'].split(':', 1)[1]
                full = name_tokens(c['name'])
                last_tok = None
                parts = [p for p in re.split(r'\s+', strip_accents(c['name']).lower()) if p]
                parts = [p.strip('.,') for p in parts if p.strip('.,') not in SUFFIXES]
                if parts:
                    last_tok = re.sub(r"[^a-z\-']", '', parts[-1])
                keys = {key}
                if last_tok:
                    keys.add(last_tok)
                    keys.add(last_tok.replace("'", ''))
                    if '-' in last_tok:
                        keys.update(p for p in last_tok.split('-') if p)
                        keys.add(last_tok.replace('-', ''))
                cl.append({'id': c['id'], 'name': c['name'], 'party': c.get('party', 'O'), 'keys': keys, 'tokens': full,
                           'first': parts[0] if parts else ''})
            self.cands[rid] = cl

    def find_race(self, state, office, district=None, special=None):
        rs = self.by_key.get((state, office), [])
        if office == 'HOU':
            if district is None:
                return rs[0] if len(rs) == 1 else None
            d = f'{int(district):02d}'
            for r in rs:
                if r.get('district') == d:
                    return r
            return None
        if not rs:
            return None
        if len(rs) == 1:
            return rs[0]
        if special is not None:
            for r in rs:
                if bool(r.get('special')) == bool(special):
                    return r
        return None

    def match(self, rid, feed_name, feed_party=None):
        """-> (candidate_id or None, reason)."""
        toks = name_tokens(feed_name)
        if not toks:
            return None, 'empty'
        hits = [c for c in self.cands.get(rid, []) if c['keys'] & toks]
        if not hits:
            return None, 'no_match'
        if len(hits) == 1:
            return hits[0]['id'], 'last'
        fp = norm_party(feed_party) if feed_party else None
        if fp:
            ph = [c for c in hits if c['party'] == fp]
            if len(ph) == 1:
                return ph[0]['id'], 'last+party'
            if ph:
                hits = ph
        fh = [c for c in hits if c['first'] and c['first'] in toks]
        if len(fh) == 1:
            return fh[0]['id'], 'last+first'
        return None, 'ambiguous:' + ','.join(c['id'] for c in hits)


class Counties:
    """County name -> 5-digit FIPS, per state, from the dashboard's TopoJSON."""
    def __init__(self, path):
        self.names = {}        # fips -> name
        self.by_state = {}     # state_fips -> {norm name: [fips]}
        try:
            with open(path) as f:
                topo = json.load(f)
            for g in topo['objects']['counties']['geometries']:
                fid = g['id']; nm = (g.get('properties') or {}).get('name') or ''
                self.names[fid] = nm
                self.by_state.setdefault(fid[:2], {}).setdefault(self._norm(nm), []).append(fid)
        except Exception as e:  # noqa: BLE001
            print(f'warning: county table unavailable ({e})', file=sys.stderr)

    @staticmethod
    def _norm(name):
        s = norm_text(name)
        s = s.replace('saint ', 'st ').replace('ste. ', 'ste ').replace('st. ', 'st ')
        s = re.sub(r"[^a-z0-9 ]", '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def lookup(self, state_fips, name):
        table = self.by_state.get(state_fips, {})
        if not table:
            return None
        n = self._norm(name)
        if not n:
            return None
        hint_city = n.endswith(' city') or n.endswith(' cty')
        hint_county = n.endswith(' county') or n.endswith(' parish') or n.endswith(' borough') or n.endswith(' census area')
        cands = [n, re.sub(r' (county|parish|borough|census area|municipality|city and borough|city)$', '', n)]
        for c in cands:
            hits = table.get(c)
            if not hits:
                continue
            if len(hits) == 1:
                return hits[0]
            cities = [h for h in hits if int(h[2:]) >= 500]
            counties = [h for h in hits if int(h[2:]) < 500]
            if hint_city and len(cities) == 1:
                return cities[0]
            if hint_county and len(counties) == 1:
                return counties[0]
            if not hint_city and len(counties) == 1:
                return counties[0]
        return None


# ---------------------------------------------------------------- contest classification

def classify(title, state=None):
    """Contest title -> (office, district|None, special) or None if not SEN/GOV/HOU."""
    t = norm_text(title)
    t = re.sub(r'\(vote for \d+\)', ' ', t)
    t = t.replace('u. s.', 'us').replace('u.s.', 'us').replace('united states', 'us').replace('u s ', 'us ')
    t = re.sub(r'\s+', ' ', t).strip()
    special = bool(re.search(r'special|unexpired', t))
    if re.search(r'\bstate (senat|represent|house|assembl)', t) or 'general assembly' in t or 'legislat' in t or 'state senator' in t:
        return None
    if re.search(r'\b(nc|ga|va|sc|tx|fl|ca|ny|pa|oh|mi|il) (house|senate|senator)', t):   # state-legislature contests labelled with the state code
        return None
    if re.search(r'board of education|regent|school|judge|justice|commission|attorney general|treasurer|auditor|secretary of|'
                 r'comptroller|controller|superintendent|\bpsc\b|public service|sheriff|mayor|council|delegate|retain|'
                 r'amendment|question|proposition|measure|referend', t):
        return None
    if re.search(r'lieutenant governor|lt\.? governor|lt governor', t) and not re.match(r'^(for )?governor', t):
        return None
    if re.search(r'\bus senat|senator in congress|member, us senate|senate, us|us senate\b', t):
        return ('SEN', None, special)
    if re.match(r'^(for )?governor', t) or t.startswith('governor /') or 'governor and' in t or t == 'governor':
        return ('GOV', None, special)
    if re.search(r'us represent|representative in congress|representative to (the )?\d+(st|nd|rd|th) (us )?congress|us house|'
                 r'member, house of representatives|congressional district|representative to congress|rep in congress', t) \
            or ('house of representatives' in t and re.search(r'\bus\b', t)):
        d = None
        m = re.search(r'district\s*0*(\d+)', t) or re.search(r'\b(\d+)(st|nd|rd|th) (congressional )?district', t) or re.search(r'congressional district\s*0*(\d+)', t) or re.search(r'\bcd\s*0*(\d+)', t)
        if m:
            d = int(m.group(1))
        else:
            m = re.search(r'\bdist\.?\s+([ivx]+)\b', t)
            if m and m.group(1) in ROMAN:
                d = ROMAN[m.group(1)]
            else:
                m = re.search(r'\b(' + '|'.join(ORDINALS) + r') district', t)
                if m:
                    d = ORDINALS[m.group(1)]
                elif re.search(r'at[\s-]*large', t):
                    d = 0
        return ('HOU', d, special)
    return None


# ---------------------------------------------------------------- record builder

class StateRun:
    """Per-state context: HTTP, roster, counties, log collection, record emission."""
    def __init__(self, state, src, roster, counties):
        self.state = state
        self.fips = STATE_FIPS[state]
        self.src = src
        self.roster = roster
        self.counties = counties
        self.platform = src.get('platform') or (src.get('feed') or {}).get('type')
        self.records = []
        self.unmatched = []          # {race_id, name, party, votes, jkey}
        self.unmatched_seen = set()
        self.notes = []
        self.urls = []
        self.election_seen = None
        self.discarded = 0
        self.http = Http(self)
        self.retrieved_at = now_iso()

    def note(self, msg):
        self.notes.append(msg)

    def check_date(self, label, date_text):
        """Record what election the feed says it is; True if it is the 2026-11-03 general."""
        self.election_seen = f'{label}: {date_text}'
        s = str(date_text or '')
        ok = (ELECTION_DATE in s) or any(d in s for d in ELECTION_DATE_US) or bool(re.search(r'november\s+3,?\s+2026', s, re.I)) or bool(re.search(r'11032026|20261103', s))
        if not ok:
            self.note(f'DISCARDED: feed is not the 2026-11-03 general ({label}={date_text!r})')
        return ok

    def race_for(self, title):
        c = classify(title, self.state)
        if not c:
            return None
        office, district, special = c
        r = self.roster.find_race(self.state, office, district, special)
        if r is None and office == 'HOU' and district is None:
            return None
        return r

    def emit(self, race, jkey, cands, precincts=None, pct_reporting=None, url=None, note=None, level=None):
        """cands: list of (name, party, votes, is_winner). Returns the record or None."""
        rid = race['race_id']
        votes, extra, winners = {}, {}, []
        matched_any = False
        for name, party, v, win in cands:
            v = to_int(v)
            wi = is_writein(name, party) or norm_text(party or '') in ('wri', 'w/i', 'wi', 'write-in', 'write in')
            cid, why = (None, 'write-in')
            if not is_writein(name):                 # named write-in candidates still get a match attempt
                cid, why = self.roster.match(rid, name, party)
            if cid:
                matched_any = True
                votes[cid] = votes.get(cid, 0) + v
                if win:
                    winners.append(cid)
            elif wi:                                 # generic or unlisted write-in: fold into one bucket, no log noise
                key = f'{rid}:~write-in'
                votes[key] = votes.get(key, 0) + v
                extra[key] = 'O'
            else:
                key = f'{rid}:~{slug(name)}'
                votes[key] = votes.get(key, 0) + v
                extra[key] = norm_party(party)
                uk = (rid, norm_text(name))
                if uk not in self.unmatched_seen:
                    self.unmatched_seen.add(uk)
                    self.unmatched.append({'race_id': rid, 'name': name, 'party': party, 'reason': why,
                                           'votes': v, 'jkey': jkey})
        if not matched_any:
            if len(jkey) == 2:
                self.note(f'DISCARDED {rid} at {jkey}: no feed candidate matched the roster ({[c[0] for c in cands][:6]})')
            self.discarded += 1
            return None
        if pct_reporting is None and precincts:
            pct_reporting = pct_of(precincts[0], precincts[1])
        rec = {'jkey': jkey, 'race_id': rid, 'votes': votes, 'pct_reporting': pct_reporting, 'status': STATUS,
               'retrieved_at': self.retrieved_at, 'url': url or (self.src.get('feed') or {}).get('url') or self.src.get('url'),
               'state': self.state, 'level': level or ('state' if len(jkey) == 2 else 'county'),
               'winner': sorted(set(winners)), 'extra_parties': extra, 'platform': self.platform}
        if precincts:
            rec['precincts'] = [to_int(precincts[0]), to_int(precincts[1])]
        if note:
            rec['note'] = note
        self.records.append(rec)
        return rec

    def county_fips(self, name):
        f = self.counties.lookup(self.fips, name)
        if not f:
            key = ('county', norm_text(name))
            if key not in self.unmatched_seen:
                self.unmatched_seen.add(key)
                self.note(f'county not in FIPS table: {name!r}')
        return f


# ---------------------------------------------------------------- parsers (one per platform family)

def fetch_clarity(run):
    """Scytl/Clarity (CO, IA): summary.json for statewide + winner flags, detailxml.zip for counties."""
    base = run.src['feed']['url'].rsplit('/current_ver.txt', 1)[0]
    ver = run.http.get(f'{base}/current_ver.txt').strip()
    run.urls.append(f'{base}/{ver}/json/en/summary.json')
    summary = run.http.get(f'{base}/{ver}/json/en/summary.json', kind='json')
    # election identity from the detail XML (has ElectionName/ElectionDate); summary has none
    xml_ok = True
    try:
        zb = run.http.get(f'{base}/{ver}/reports/detailxml.zip', kind='bytes')
        xml = zipfile.ZipFile(io.BytesIO(zb)).read('detail.xml')
        root = ET.fromstring(xml)
    except Exception as e:  # noqa: BLE001
        run.note(f'detailxml.zip unavailable ({e}); county level skipped')
        xml_ok = False; root = None
    if xml_ok:
        ename = root.findtext('ElectionName'); edate = root.findtext('ElectionDate')
        if not run.check_date(ename, edate):
            return
    for c in summary:
        race = run.race_for(c.get('C', ''))
        if not race:
            continue
        names, parties, votes = c.get('CH') or [], c.get('P') or [], c.get('V') or []
        wins = c.get('W') or []
        cands = []
        for i, n in enumerate(names):
            cands.append((n, parties[i] if i < len(parties) else None, votes[i] if i < len(votes) else 0,
                          bool(wins[i]) if i < len(wins) else False))
        run.emit(race, run.fips, cands, precincts=(c.get('PR', 0), c.get('TP', 0)), url=f'{base}/{ver}/json/en/summary.json')
    if not xml_ok:
        return
    for contest in root.iter('Contest'):
        race = run.race_for(contest.get('text', ''))
        if not race or race['office'] == 'HOU':
            continue
        prec = {}
        for cty in contest.findall('./ParticipatingCounties/County'):
            prec[cty.get('name')] = (to_int(cty.get('precinctsReported')), to_int(cty.get('precinctsParticipating')))
        per_county = {}
        for ch in contest.findall('Choice'):
            vts = ch.findall('VoteType')
            totals = [v for v in vts if 'total' in (v.get('name') or '').lower()] or vts
            for vt in totals:
                for cty in vt.findall('County'):
                    per_county.setdefault(cty.get('name'), {})
                    key = (ch.get('text'), ch.get('party'))
                    per_county[cty.get('name')][key] = per_county[cty.get('name')].get(key, 0) + to_int(cty.get('votes'))
        for cname, cv in per_county.items():
            fips = run.county_fips(cname)
            if not fips:
                continue
            cands = [(n, p, v, False) for (n, p), v in cv.items()]
            run.emit(race, fips, cands, precincts=prec.get(cname), url=f'{base}/{ver}/reports/detailxml.zip')


def _ev_text(lst):
    if isinstance(lst, list):
        for x in lst:
            if x.get('languageId') == 'en':
                return x.get('text') or ''
        return lst[0].get('text', '') if lst else ''
    return lst or ''


def fetch_enhanced_voting(run):
    """Enhanced Voting public API (GA, ID, RI, UT, VA, WA)."""
    api = run.src['feed']['url'].rstrip('/')
    election = run.http.get(api, kind='json')
    ename = _ev_text(election.get('name')); edate = election.get('electionDate')
    if not run.check_date(ename, edate):
        return
    if election.get('isOfficialResults'):
        run.note('feed flags isOfficialResults=true')
    items, offset = [], 0
    while True:
        page = run.http.get(f'{api}/ballot-items?limit=500&offset={offset}', kind='json')
        data = page.get('data') or []
        items.extend(data)
        total = page.get('totalRecordCount') or len(items)
        offset += len(data)
        if not data or offset >= total:
            break
    run.urls.append(f'{api}/ballot-items')

    def opts_to_cands(opts):
        out = []
        for o in opts or []:
            party = (o.get('party') or {}).get('abbreviation') or _ev_text((o.get('party') or {}).get('name'))
            nm = _ev_text(o.get('name'))
            if o.get('isWriteIn'):
                nm = 'Write-in'
            out.append((nm, party, o.get('voteCount') or 0, bool(o.get('isWinner'))))
        return out

    wanted_county = []
    for it in items:
        if it.get('contestType') not in (None, 'Candidate'):
            continue
        race = run.race_for(_ev_text(it.get('name')))
        if not race:
            continue
        rs = it.get('reportingStatus') or {}
        prec = (rs.get('reportingUnits') or 0, rs.get('totalUnits') or 0)
        opts = (it.get('summaryResults') or {}).get('ballotOptions') or []
        rec = run.emit(race, run.fips, opts_to_cands(opts), precincts=prec, url=f'{api}/ballot-items')
        if rec and race['office'] != 'HOU' and it.get('hasBreakdownResults', True):
            wanted_county.append((it['id'], race))
    for bid, race in wanted_county:
        try:
            detail = run.http.get(f'{api}/ballot-items/{bid}', kind='json')
        except Exception as e:  # noqa: BLE001
            run.note(f'county breakdown failed for {race["race_id"]}: {e}')
            continue
        agg = {}   # fips -> {'cands': {(name,party): votes}, 'prec': [rep,total]}
        for br in detail.get('breakdownResults') or []:
            loc = br.get('locality') or {}
            lname = _ev_text(loc.get('name')); mfid = loc.get('mapFeatureId') or ''
            fips = None
            if run.state == 'VA' and re.fullmatch(r'\d{3}', mfid or ''):
                fips = run.fips + mfid
            elif run.state == 'UT' and re.fullmatch(r'\d{1,2}', mfid or ''):
                fips = f'{run.fips}{2 * int(mfid) - 1:03d}'
            elif run.state == 'RI':
                fips = RI_TOWN_COUNTY.get(norm_text(lname))
                if not fips:
                    run.note(f'RI locality not mapped to a county: {lname!r}')
                    continue
            else:
                fips = run.county_fips(lname or mfid)
            if not fips or fips not in run.counties.names:
                continue
            prs = br.get('precinctReportingStatus') or {}
            a = agg.setdefault(fips, {'cands': {}, 'prec': [0, 0]})
            a['prec'][0] += prs.get('reportingUnits') or 0
            a['prec'][1] += prs.get('totalUnits') or 0
            for nm, party, v, win in opts_to_cands(br.get('ballotOptions')):
                a['cands'][(nm, party)] = a['cands'].get((nm, party), 0) + to_int(v)
        for fips, a in agg.items():
            cands = [(nm, party, v, False) for (nm, party), v in a['cands'].items()]
            run.emit(race, fips, cands, precincts=a['prec'], url=f'{api}/ballot-items/{bid}')


def fetch_ess_csv(run):
    """ES&S ElectionResults resultsCSV.aspx (NE, NM, SD). Statewide only (county pages are HTML postbacks)."""
    feed = run.src['feed']['url']
    def with_type(t):
        return re.sub(r'type=[A-Za-z]+', f'type={t}', feed)
    # category codes per ResultsMedia.aspx: NE serves everything under type=All; NM splits FED/STATE; SD uses SWR
    urls = {'NE': [with_type('All')], 'NM': [with_type('FED'), with_type('STATE')], 'SD': [with_type('SWR')]}.get(run.state, [feed])
    seen_race = {}
    for url in urls:
        txt = run.http.get(url)
        run.urls.append(url)
        if '<html' in txt[:500].lower():
            run.note(f'{url} returned HTML, not CSV (feed not switched on yet?)')
            continue
        rows = list(csv.DictReader(io.StringIO(txt)))
        if not rows:
            run.note(f'{url}: header only, no rows')
            continue
        dts = {r.get('CurrentDateTime', '').split(' ')[0] for r in rows if r.get('CurrentDateTime')}
        if dts:
            if not run.check_date('CurrentDateTime', ','.join(sorted(dts))):
                continue
        else:
            run.election_seen = 'CSV carries no election date (NM); election verified from the site header on 2026-11-03'
        groups = {}
        for r in rows:
            rname = (r.get('RaceName') or '').strip()
            area = (r.get('AreaNum') or '').strip()
            c = classify(rname)
            if not c:
                continue
            office, district, special = c
            if office == 'HOU' and district is None:
                m = re.search(r'(\d+)', area)
                district = int(m.group(1)) if m else None
            race = run.roster.find_race(run.state, office, district, special)
            if not race:
                continue
            g = groups.setdefault(race['race_id'], {'race': race, 'cands': [], 'prec': None, 'url': url})
            name = re.sub(r'\s+', ' ', (r.get('CandidateName') or '')).strip()
            g['cands'].append((name, r.get('PartyCode'), r.get('CandidateVotes'), False))
            fr = parse_frac(r.get('PrecinctsReporting'))
            if fr:
                g['prec'] = fr
        for rid, g in groups.items():
            if rid in seen_race:
                continue
            seen_race[rid] = True
            run.emit(g['race'], run.fips, g['cands'], precincts=g['prec'], url=g['url'])


def fetch_nc(run):
    """NCSBE ENR: results_0.txt statewide; results_<n>.txt per county (n = alphabetical county index 1..100)."""
    base = run.src['feed']['url'].rsplit('/', 1)[0]
    data = run.http.get(f'{base}/results_0.txt', kind='json')
    run.urls.append(f'{base}/results_0.txt')
    run.election_seen = 'url path 20261103'
    if '20261103' not in base:
        run.note('feed URL is not the 2026-11-03 election path'); return

    def group(rows):
        groups = {}
        for r in rows:
            race = run.race_for(r.get('cnm', ''))
            if not race:
                continue
            g = groups.setdefault(race['race_id'], {'race': race, 'cands': [], 'prec': None})
            g['cands'].append((r.get('bnm', ''), r.get('pty'), r.get('vct'), False))
            g['prec'] = (to_int(r.get('prt')), to_int(r.get('ptl')))
        return groups

    for rid, g in group(data).items():
        run.emit(g['race'], run.fips, g['cands'], precincts=g['prec'], url=f'{base}/results_0.txt')
    names = sorted(((f, n) for f, n in run.counties.names.items() if f.startswith('37')), key=lambda x: x[1].lower())
    if len(names) != 100:
        run.note(f'expected 100 NC counties in FIPS table, found {len(names)}; county level skipped'); return

    def one(i):
        url = f'{base}/results_{i}.txt'
        try:
            rows = run.http.get(url, kind='json', ok_404=True)
        except Exception as e:  # noqa: BLE001
            return i, None, str(e)
        return i, rows, None
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, rows, err in ex.map(one, range(1, 101)):
            fips = names[i - 1][0]
            if err:
                run.note(f'county {names[i-1][1]} ({i}): {err}'); continue
            if not rows:
                continue
            for rid, g in group(rows).items():
                if g['race']['office'] == 'HOU':
                    continue
                run.emit(g['race'], fips, g['cands'], precincts=g['prec'], url=url_for(base, i))


def url_for(base, i):
    return f'{base}/results_{i}.txt'


def fetch_fl(run):
    """Florida Division of Elections tab-delimited election-night file (one row per candidate per county)."""
    url = run.src['feed']['url']
    txt = run.http.get(url)
    run.urls.append(url)
    rows = list(csv.DictReader(io.StringIO(txt), delimiter='\t'))
    if not rows:
        run.note('empty file'); return
    dates = {r.get('ElectionDate', '').strip() for r in rows}
    if not run.check_date('ElectionDate', ','.join(sorted(dates))):
        return
    rows = [r for r in rows if r.get('ElectionDate', '').strip() in ELECTION_DATE_US]
    code_map = {'USS': 'SEN', 'GOV': 'GOV', 'USR': 'HOU'}
    by_race = {}
    for r in rows:
        office = code_map.get((r.get('RaceCode') or '').strip())
        if not office:
            continue
        district = None
        if office == 'HOU':
            m = re.search(r'(\d+)', r.get('Juris1num') or '')
            district = int(m.group(1)) if m else None
        race = run.roster.find_race(run.state, office, district, None)
        if not race:
            continue
        name = ' '.join(x for x in [(r.get('CanNameFirst') or '').strip(), (r.get('CanNameMiddle') or '').strip(), (r.get('CanNameLast') or '').strip()] if x and x != '/')
        party = (r.get('PartyCode') or '').strip()      # WRI rows keep their name so listed write-in candidates can match
        cname = (r.get('CountyName') or '').strip()
        g = by_race.setdefault(race['race_id'], {'race': race, 'counties': {}})
        c = g['counties'].setdefault(cname, {'cands': {}, 'prec': (to_int(r.get('PrecinctsReporting')), to_int(r.get('Precincts')))})
        c['cands'][(name, party)] = c['cands'].get((name, party), 0) + to_int(r.get('CanVotes'))
    for rid, g in by_race.items():
        race = g['race']
        state_c, rep, tot = {}, 0, 0
        for cname, c in g['counties'].items():
            rep += c['prec'][0]; tot += c['prec'][1]
            for k, v in c['cands'].items():
                state_c[k] = state_c.get(k, 0) + v
            if race['office'] != 'HOU':
                fips = run.county_fips(cname)
                if fips:
                    run.emit(race, fips, [(n, p, v, False) for (n, p), v in c['cands'].items()], precincts=c['prec'], url=url)
        run.emit(race, run.fips, [(n, p, v, False) for (n, p), v in state_c.items()], precincts=(rep, tot), url=url)


def fetch_ca(run):
    """California SOS returns API: governor/county/all + us-rep/district/<n>."""
    api = 'https://api.sos.ca.gov/returns'
    seen_stale = False

    def parse_block(block):
        title = block.get('raceTitle', '')
        rep = parse_frac(block.get('Reporting', '')) or (0, 0)
        cands = [(c.get('Name', ''), c.get('Party'), c.get('Votes'), False) for c in block.get('candidates', [])]
        return title, rep, cands

    def report_time_ok(block):
        rt = block.get('ReportingTime', '')
        m = re.search(r'([A-Za-z]+)\s+(\d+),\s*(\d{4})', rt)
        if not m:
            return True
        try:
            d = dt.datetime.strptime(f'{m.group(1)} {m.group(2)} {m.group(3)}', '%B %d %Y').date()
        except ValueError:
            return True
        return d >= dt.date(2026, 11, 1)

    gov = run.http.get(f'{api}/governor/county/all', kind='json')
    run.urls.append(f'{api}/governor/county/all')
    race = run.roster.find_race('CA', 'GOV')
    if race and isinstance(gov, list):
        for block in gov:
            if not report_time_ok(block):
                seen_stale = True; continue
            title, rep, cands = parse_block(block)
            m = re.match(r'Governor - (.+?) County Results', title)
            if 'Statewide' in title:
                run.emit(race, run.fips, cands, precincts=rep, url=f'{api}/governor/county/all')
            elif m:
                fips = run.county_fips(m.group(1))
                if fips:
                    run.emit(race, fips, cands, precincts=rep, url=f'{api}/governor/county/all')
        run.election_seen = f'ReportingTime: {gov[0].get("ReportingTime") if gov else None}'
    house = [r for r in run.roster.by_key.get(('CA', 'HOU'), [])]
    def one(r):
        d = int(r['district'])
        try:
            return r, run.http.get(f'{api}/us-rep/district/{d}', kind='json'), None
        except Exception as e:  # noqa: BLE001
            return r, None, str(e)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r, block, err in ex.map(one, house):
            if err:
                run.note(f'{r["race_id"]}: {err}'); continue
            if not report_time_ok(block):
                seen_stale = True; continue
            title, rep, cands = parse_block(block)
            run.emit(r, run.fips, cands, precincts=rep, url=f'{api}/us-rep/district/{int(r["district"])}')
    if seen_stale:
        run.note('DISCARDED blocks whose ReportingTime predates 2026-11-01 (prior-election data still being served)')


def fetch_in(run):
    """Indiana ENR static JSON (US House only in 2026; no precinct counts exposed)."""
    base = 'https://enr.indianavoters.in.gov/site/data'
    settings = run.http.get(f'{base}/settings.json', kind='json')['Root']
    run.urls.append(f'{base}/settings.json')
    if not run.check_date('CurrentElection', f"{settings.get('CurrentElection')} type={settings.get('ElectionType')}"):
        return
    ver = settings.get('VersionType', 'B')
    cats = run.http.get(f'{base}/statewideElectionsC_{ver}.json', kind='json')['Root']
    cat_ids = []
    for grp in cats.get('List', []):
        for it in (grp.get('Items') or {}).get('Item', []):
            if classify(it.get('OFFICE_CATEGORY_NAME', '')):
                cat_ids.append(it['OFFICECATEGORYID'])
    if not cat_ids:
        run.note('no federal/governor office category in statewideElectionsC'); return
    for cid in cat_ids:
        url = f'{base}/OffCatC_{cid}_{ver}.json'
        data = run.http.get(url, kind='json')['Root']
        for race_block in (data.get('StatewideSummary') or {}).get('Race', []):
            race = run.race_for(race_block.get('OFFICE_TITLE', ''))
            if not race:
                continue
            cands = []
            for c in (race_block.get('Candidates') or {}).get('Candidate', []):
                cands.append((c.get('NAME_ON_BALLOT', ''), c.get('PARTY'), c.get('TOTAL'), c.get('isWinner') == 'T'))
            run.emit(race, run.fips, cands, pct_reporting=None, url=url, note='pct_reporting not exposed by IN ENR')


def fetch_la(run):
    """Louisiana SOS voterportal static JSON blobs."""
    base = 'https://voterportal.sos.la.gov/ElectionResults/ElectionResults/Data?blob='
    dates = run.http.get(f'{base}ElectionDates.htm', kind='json')
    if not run.check_date('DefaultElectionDate', (dates.get('Dates') or {}).get('DefaultElectionDate')):
        return
    folder = '20261103'
    rc = run.http.get(f'{base}{folder}/RacesCandidates_Multiparish.htm', kind='json')
    votes = run.http.get(f'{base}{folder}/Votes_Multiparish.htm', kind='json')
    run.urls.append(f'{base}{folder}/Votes_Multiparish.htm')
    choice_name = {}
    race_of = {}
    for r in (rc.get('Races') or {}).get('Race', []):
        race = run.race_for(r.get('SpecificTitle') or r.get('GeneralTitle') or '')
        if not race:
            continue
        race_of[r['ID']] = race
        for ch in r.get('Choice', []):
            desc = ch.get('Desc', '')
            m = re.search(r'\(([^)]*)\)\s*$', desc)
            party = m.group(1) if m else None
            name = re.sub(r'\([^)]*\)\s*$', '', desc).strip()
            choice_name[ch['ID']] = (name, party)
    def cands_from(choices):
        out = []
        for ch in choices or []:
            nm, p = choice_name.get(ch.get('ID'), (f'choice {ch.get("ID")}', None))
            out.append((nm, p, ch.get('VoteTotal'), False))
        return out
    for vr in (votes.get('Races') or {}).get('Race', []):
        race = race_of.get(vr.get('ID'))
        if not race:
            continue
        prec = (to_int(vr.get('PrecinctsReporting')), to_int(vr.get('PrecinctsExpected')))
        run.emit(race, run.fips, cands_from(vr.get('Choice')), precincts=prec, url=f'{base}{folder}/Votes_Multiparish.htm')
        if race['office'] == 'HOU':
            continue
        url = f'{base}{folder}/VotesRaceByParish/Votes_{vr["ID"]}.htm'
        try:
            pp = run.http.get(url, kind='json')
        except Exception as e:  # noqa: BLE001
            run.note(f'parish breakdown failed for {race["race_id"]}: {e}'); continue
        for p in (pp.get('Parishes') or {}).get('Parish', []):
            try:
                code = int(p.get('ParishValue'))
            except (TypeError, ValueError):
                continue
            fips = f'22{2 * code - 1:03d}'
            if fips not in run.counties.names:
                run.note(f'parish code {code} -> {fips} not in FIPS table'); continue
            prec = (to_int(p.get('PrecinctsReporting')), to_int(p.get('PrecinctsExpected')))
            run.emit(race, fips, cands_from(p.get('Choice')), precincts=prec, url=url)


def fetch_vt(run):
    """Vermont SOS static JSON (towns -> counties)."""
    base = 'https://static.electionresults.vermont.gov/'
    elections = run.http.get(f'{base}elections/elections.json', kind='json')
    gen = [e for e in elections if e.get('isGeneralElection') and e.get('isStateWideElection') and str(e.get('electionDate', '')).startswith(ELECTION_DATE)]
    if not gen:
        run.note('no statewide general election dated 2026-11-03 in elections.json')
        run.check_date('elections.json', [e.get('electionDateWithName') for e in elections[:3]])
        return
    guid = gen[0]['electionGuid']
    meta = run.http.get(f'{base}elections/{guid}.json', kind='json')
    ed = meta.get('electionDetails') or {}
    if not run.check_date(ed.get('electionName'), ed.get('electionDate')):
        return
    def path(key):
        p = (meta.get(key) or {}).get('path')
        return base + p.replace('\\', '/') if p else None
    # town -> county map (cached; the county file is ~1 MB)
    cache_path = os.path.join(ROOT, 'data', 'cache', 'vt_town_county.json')
    town_county = None
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                town_county = json.load(f)
        except Exception:  # noqa: BLE001
            town_county = None
    if not town_county:
        town_county = {}
        try:
            cty = run.http.get(path('county'), kind='json')
            for blk in cty.get('d', []):
                for office in blk.get('co', []):
                    cn = office.get('ctyn')
                    for cs in office.get('cs', []):
                        if cs.get('tn') and (cs.get('ctyn') or cn):
                            town_county[norm_text(cs['tn'])] = norm_text(cs.get('ctyn') or cn)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'w') as f:
                json.dump(town_county, f)
        except Exception as e:  # noqa: BLE001
            run.note(f'county file unavailable ({e}); county level skipped')
    for key in ('federal', 'stateWide'):
        url = path(key)
        if not url:
            continue
        data = run.http.get(url, kind='json')
        run.urls.append(url)
        for blk in data.get('d', []):
            for office in blk.get('o', []):
                race = run.race_for(office.get('on', ''))
                if not race:
                    continue
                state_c, srep, stot = {}, 0, 0
                by_county = {}
                seen_towns = set()
                for cs in office.get('cs', []):
                    tn = cs.get('tn') or ''
                    tid = cs.get('tid')
                    if tid in seen_towns:
                        continue
                    seen_towns.add(tid)
                    fr = parse_frac(cs.get('distReported')) or (0, 0)
                    srep += fr[0]; stot += fr[1]
                    cn = town_county.get(norm_text(tn)) if town_county else None
                    fips = run.county_fips(cn) if cn else None
                    bucket = by_county.setdefault(fips, {'cands': {}, 'prec': [0, 0]}) if fips else None
                    if bucket:
                        bucket['prec'][0] += fr[0]; bucket['prec'][1] += fr[1]
                    for c in (cs.get('rc') or []) + (cs.get('wc') or []):
                        nm = c.get('cn', ''); p = c.get('pn'); v = to_int(c.get('vc'))
                        if c.get('cid') == 0 or is_writein(nm):
                            nm = 'Write-in'
                        state_c[(nm, p)] = state_c.get((nm, p), 0) + v
                        if bucket:
                            bucket['cands'][(nm, p)] = bucket['cands'].get((nm, p), 0) + v
                run.emit(race, run.fips, [(n, p, v, False) for (n, p), v in state_c.items()], precincts=(srep, stot), url=url,
                         note='pct_reporting = towns reported')
                if race['office'] == 'HOU':
                    continue
                for fips, b in by_county.items():
                    run.emit(race, fips, [(n, p, v, False) for (n, p), v in b['cands'].items()], precincts=b['prec'], url=url)


def fetch_de(run):
    """Delaware ENR JSON (statewide with precinct counts; county split from the by-county file)."""
    base = 'https://elections.delaware.gov/results/enr/'
    sw = run.http.get(f'{base}Election_StatewideResults_ID_GE2026.json', kind='json')
    run.urls.append(f'{base}Election_StatewideResults_ID_GE2026.json')
    if not sw:
        run.note('statewide file empty'); return
    dates = {r.get('Election Date') for r in sw}
    if not run.check_date(sw[0].get('Election Name'), ','.join(sorted(d for d in dates if d))):
        return
    groups = {}
    for r in sw:
        race = run.race_for(r.get('Contest Title', ''))
        if not race:
            continue
        g = groups.setdefault(race['race_id'], {'race': race, 'cands': [], 'prec': None})
        g['cands'].append((r.get('Candidate Name', ''), r.get('Party Name'), r.get('Total Votes'), False))
        g['prec'] = (to_int(r.get('Precincts Reported')), to_int(r.get('Total Precincts')))
    pct_state = {}
    for rid, g in groups.items():
        rec = run.emit(g['race'], run.fips, g['cands'], precincts=g['prec'], url=f'{base}Election_StatewideResults_ID_GE2026.json')
        if rec:
            pct_state[rid] = rec['pct_reporting']
    try:
        bc = run.http.get(f'{base}Election_ByCountyWithWilmington_ID_GE2026.json', kind='json')
    except Exception as e:  # noqa: BLE001
        run.note(f'by-county file unavailable: {e}'); return
    cg = {}
    for r in bc:
        race = run.race_for(r.get('Contest Title', ''))
        if not race or race['office'] == 'HOU':
            continue
        for cname in ('New Castle', 'Kent', 'Sussex'):
            fips = run.county_fips(cname)
            if not fips:
                continue
            cg.setdefault((race['race_id'], fips), {'race': race, 'cands': []})['cands'].append(
                (r.get('Candidate Name', ''), r.get('Party Name'), r.get(cname), False))
    for (rid, fips), g in cg.items():
        run.emit(g['race'], fips, g['cands'], pct_reporting=pct_state.get(rid), url=f'{base}Election_ByCountyWithWilmington_ID_GE2026.json',
                 note='pct_reporting is the statewide figure (county precinct counts not published)')


_TD = re.compile(r'<td[^>]*>(.*?)</td>', re.S)
_TR = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S)


def _strip_tags(s):
    return html.unescape(re.sub(r'<[^>]+>', ' ', s or '')).replace('\xa0', ' ').strip()


def fetch_md(run):
    """Maryland SBE static HTML: governor (with county breakdown) and eight House districts."""
    base = 'https://elections.maryland.gov/elections/2026/general_results/'
    pages = [('gen_results_2026_1.html', 'GOV', None)] + [(f'gen_results_2026_4_{d}.html', 'HOU', d) for d in range(1, 9)]
    first = True
    for page, office, district in pages:
        race = run.roster.find_race('MD', office, district)
        if not race:
            continue
        url = base + page
        try:
            t = run.http.get(url)
        except Exception as e:  # noqa: BLE001
            run.note(f'{page}: {e}'); continue
        run.urls.append(url)
        if first:
            first = False
            m = re.search(r'(20\d\d)\s+(Gubernatorial|Presidential)?\s*General Election', t, re.I)
            label = m.group(0) if m else 'no election title found'
            # the page carries only the year + "General Election"; MD's 2026 general is Nov 3
            if not run.check_date('page title', f'{label} (2026-11-03)' if m and m.group(1) == '2026' else label):
                return
        prec = parse_frac(re.search(r'\((\d[\d,]* of \d[\d,]*) (election day )?precincts', t, re.I).group(1)) if re.search(r'\((\d[\d,]* of \d[\d,]*) (election day )?precincts', t, re.I) else None
        tbl = re.search(r'<table class="table-banded">(.*?)</table>', t, re.S)
        cands = []
        if tbl:
            for tr in _TR.findall(tbl.group(1)):
                tds = [_strip_tags(x) for x in _TD.findall(tr)]
                if len(tds) < 7 or tds[0].lower().startswith('totals'):
                    continue
                win = 'check.gif' in tr
                cands.append((tds[0], tds[1], tds[6], win))
        run.emit(race, run.fips, cands, precincts=prec, url=url)
        if office == 'GOV':
            durl = base + 'gen_detail_results_2026_1_1.html'
            try:
                d = run.http.get(durl)
            except Exception as e:  # noqa: BLE001
                run.note(f'governor county breakdown: {e}'); continue
            tbl = re.search(r'<table class="table-banded">(.*?)</table>', d, re.S)
            if not tbl:
                continue
            ths = re.findall(r'<th[^>]*>(.*?)</th>', tbl.group(1), re.S)
            heads = []
            for h in ths[1:]:
                parts = [p.strip() for p in re.split(r'<br\s*/?>', h) if _strip_tags(p)]
                heads.append((_strip_tags(parts[0]) if parts else '', _strip_tags(parts[1]) if len(parts) > 1 else ''))
            for tr in _TR.findall(tbl.group(1)):
                tds = [_strip_tags(x) for x in _TD.findall(tr)]
                if len(tds) < 2:
                    continue
                cname = tds[0]
                if cname.lower().startswith('total'):
                    continue
                fips = run.county_fips(cname)
                if not fips:
                    continue
                cc = [(heads[i][0], heads[i][1], tds[i + 1], False) for i in range(min(len(heads), len(tds) - 1))]
                run.emit(race, fips, cc, pct_reporting=None, url=durl, note='county precinct counts not published')


def fetch_tx(run):
    """Texas SOS static HTML results page (statewide only)."""
    url = run.src['feed']['url']
    t = run.http.get(url)
    run.urls.append(url)
    m = re.search(r'Election Results - ([A-Za-z]+, [A-Za-z]+ \d+, \d{4})', t)
    if not run.check_date('page title', m.group(1) if m else None):
        return
    blocks = re.findall(r'<div class="election">(.*?)</div>\s*<div class="polling">(.*?)</div>\s*<div>\s*<table class="election">(.*?)</table>', t, re.S)
    for title, polling, table in blocks:
        race = run.race_for(_strip_tags(title))
        if not race:
            continue
        pm = re.search(r'([\d.]+)\s*%', polling)
        pct = float(pm.group(1)) if pm else None
        cands = []
        for tr in _TR.findall(table):
            if 'class="header"' in tr:
                continue
            party = re.search(r'<td class="party">(.*?)</td>', tr, re.S)
            name = re.search(r'<td class="candidate">(.*?)</td>', tr, re.S)
            ballots = re.search(r'<td class="ballot"\s*>(.*?)</td>', tr, re.S)
            if not name:
                continue
            cands.append((_strip_tags(name.group(1)), _strip_tags(party.group(1)) if party else None,
                          _strip_tags(ballots.group(1)) if ballots else 0, False))
        run.emit(race, run.fips, cands, pct_reporting=pct, url=url, note='pct_reporting = polling locations reporting')


def fetch_hi(run):
    """Hawaii Office of Elections summary.txt (statewide); link discovered from the results page."""
    page_url = run.src['url']
    page = run.http.get(page_url)
    links = re.findall(r'href="([^"]*summary\.txt)"', page)
    cand = [html.unescape(l) for l in links if re.search(r'2026(\s|%20)*general', l, re.I)]
    if not cand:
        guess = 'https://elections.hawaii.gov/wp-content/results/2026%20General/summary.txt'
        run.note(f'no 2026 General summary.txt link on results page ({len(links)} summary links: {links[:3]}); trying {guess}')
        cand = [guess]
    url = cand[0].replace(' ', '%20')
    txt = run.http.get(url, ok_404=True)
    run.urls.append(url)
    if txt is None:
        run.note('summary.txt not published yet (404)'); run.election_seen = 'not published'; return
    if '#Contest' not in txt[:2000]:
        run.note(f'summary.txt is a placeholder: {txt.strip()[:120]!r}'); run.election_seen = 'placeholder'; return
    lines = [l for l in txt.splitlines() if l.strip()]
    hdr = next((l for l in lines if l.startswith('#Contest')), None)
    cols = [c.strip().lstrip('#') for c in hdr.split('\t')]
    run.election_seen = f'summary.txt from {url}'
    groups = {}
    for l in lines:
        if l.startswith('#'):
            continue
        vals = next(csv.reader([l], delimiter='\t', quotechar='"'))
        row = dict(zip(cols, vals))
        race = run.race_for(row.get('Contest Title', ''))
        if not race:
            continue
        g = groups.setdefault(race['race_id'], {'race': race, 'cands': [], 'prec': None})
        name = row.get('Candidate Name', '')
        if ',' in name:
            last, first = [x.strip() for x in name.split(',', 1)]
            name = f'{first} {last}'
        g['cands'].append((name, row.get('Candidate Party') or row.get('Contest Party'), row.get('Total Votes'), False))
        g['prec'] = (to_int(row.get('Counted Precincts')), to_int(row.get('Total Precincts')))
    for rid, g in groups.items():
        run.emit(g['race'], run.fips, g['cands'], precincts=g['prec'], url=url)


def fetch_dc(run):
    """DC BOE: no in-scope race (no Senate/Governor/voting House seat); check that the election is published."""
    url = run.src['feed']['url']
    lst = run.http.get(url, kind='json')
    run.urls.append(url)
    gen = [e for e in lst if str(e.get('ElectionDate', '')).startswith(ELECTION_DATE)]
    if gen:
        e = gen[0]
        run.election_seen = f"{e.get('ElectionName')} {e.get('ElectionDate')} live={e.get('IsLive')} published={e.get('IsPublished')} id={e.get('ElectionResultsId')}"
    else:
        run.election_seen = f'2026-11-03 general not listed (latest: {lst[0].get("ElectionName")} {lst[0].get("ElectionDate")})' if lst else 'empty list'
    run.note('DC has no Senate/Governor/House race in races.json; feed checked for liveness only')


PARSERS = {
    'CO': fetch_clarity, 'IA': fetch_clarity,
    'GA': fetch_enhanced_voting, 'ID': fetch_enhanced_voting, 'RI': fetch_enhanced_voting,
    'UT': fetch_enhanced_voting, 'VA': fetch_enhanced_voting, 'WA': fetch_enhanced_voting,
    'NE': fetch_ess_csv, 'NM': fetch_ess_csv, 'SD': fetch_ess_csv,
    'NC': fetch_nc, 'FL': fetch_fl, 'CA': fetch_ca, 'IN': fetch_in, 'LA': fetch_la, 'VT': fetch_vt,
    'DE': fetch_de, 'MD': fetch_md, 'TX': fetch_tx, 'HI': fetch_hi, 'DC': fetch_dc,
}


# ---------------------------------------------------------------- driver

def run_state(state, src, roster, counties):
    run = StateRun(state, src, roster, counties)
    t0 = time.time()
    err = None
    try:
        PARSERS[state](run)
    except Exception as e:  # noqa: BLE001
        err = f'{type(e).__name__}: {e}'
    elapsed = round(time.time() - t0, 2)
    states_recs = sum(1 for r in run.records if r['level'] == 'state')
    county_recs = len(run.records) - states_recs
    races = sorted({r['race_id'] for r in run.records if r['level'] == 'state'})
    log = {'ok': err is None, 'error': err, 'elapsed_s': elapsed, 'requests': run.http.count,
           'records': len(run.records), 'state_records': states_recs, 'county_records': county_recs,
           'races': races, 'election_seen': run.election_seen, 'platform': run.platform,
           'unmatched': run.unmatched, 'discarded_records': run.discarded, 'notes': run.notes, 'urls': run.urls[:10],
           'retrieved_at': run.retrieved_at}
    return run.records, log


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--states', help='comma-separated subset, e.g. CO,IA')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--out', default=os.path.join(ROOT, 'data'))
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    with open(os.path.join(ROOT, 'data', 'official_sources.json')) as f:
        sources = json.load(f)
    meta = sources.get('_meta', {})
    states = list(meta.get('states_with_feed') or [s for s, v in sources.items() if not s.startswith('_') and (v.get('feed') or {}).get('type') not in (None, 'none')])
    # states with a parser but no verified URL yet (HI publishes its txt files only after the first release)
    states += [s for s in PARSERS if s in sources and s not in states]
    if a.states:
        states = [s.strip().upper() for s in a.states.split(',') if s.strip()]
    states = [s for s in states if s in PARSERS and s in sources]
    roster = Roster(os.path.join(ROOT, 'data', 'races.json'))
    counties = Counties(os.path.join(ROOT, 'app', 'data', 'counties-10m.json'))

    t0 = time.time()
    all_records, logs = [], {}
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_state, s, sources[s], roster, counties): s for s in states}
        for f in as_completed(futs):
            s = futs[f]
            try:
                recs, log = f.result()
            except Exception as e:  # noqa: BLE001
                recs, log = [], {'ok': False, 'error': f'driver: {e}', 'records': 0, 'notes': []}
            all_records.extend(recs)
            logs[s] = log
            if not a.quiet:
                flag = 'ok ' if log['ok'] else 'ERR'
                print(f"[{flag}] {s:2s} {log.get('elapsed_s', 0):6.1f}s recs={log.get('records', 0):5d} "
                      f"(state {log.get('state_records', 0)}, county {log.get('county_records', 0)}) "
                      f"unmatched={len(log.get('unmatched') or [])} {log.get('error') or ''}")
                for n in (log.get('notes') or [])[:4]:
                    print(f'       - {n[:200]}')
    all_records.sort(key=lambda r: (r['state'], r['race_id'], r['jkey']))
    failed = sorted(s for s, l in logs.items() if not l['ok'])
    out_log = {
        'generated_at': now_iso(), 'election_date': ELECTION_DATE, 'elapsed_s': round(time.time() - t0, 1),
        'summary': {'states_attempted': states, 'ok': sorted(s for s in logs if logs[s]['ok']), 'failed': failed,
                    'total_records': len(all_records),
                    'state_records': sum(1 for r in all_records if r['level'] == 'state'),
                    'county_records': sum(1 for r in all_records if r['level'] == 'county'),
                    'unmatched_total': sum(len(l.get('unmatched') or []) for l in logs.values()),
                    'states_with_records': sorted({r['state'] for r in all_records})},
        'states': {s: logs[s] for s in sorted(logs)},
    }
    os.makedirs(a.out, exist_ok=True)
    tmp = os.path.join(a.out, 'official_results.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(all_records, f, separators=(',', ':'))
    os.replace(tmp, os.path.join(a.out, 'official_results.json'))
    with open(os.path.join(a.out, 'official_fetch_log.json'), 'w') as f:
        json.dump(out_log, f, indent=1)
    print(f"done in {out_log['elapsed_s']}s: {len(all_records)} records from {len(out_log['summary']['states_with_records'])} states; "
          f"failed: {failed or 'none'}; unmatched names: {out_log['summary']['unmatched_total']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
