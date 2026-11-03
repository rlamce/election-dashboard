#!/usr/bin/env python3
"""Unit tests for the election-night pipeline (candidate matcher, contest classifier, call rule, scorer).

Run:  python3 -I pipeline/tests/test_pipeline.py
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import fetch_official as fo  # noqa: E402
import score as sc  # noqa: E402

RACES = {
    "FL-GOV-2026": {"race_id": "FL-GOV-2026", "state": "FL", "state_fips": "12", "office": "GOV", "district": None, "special": False,
                    "label": "Florida Governor",
                    "candidates": [{"id": "FL-GOV-2026:donalds", "name": "Byron Donalds", "party": "R"},
                                   {"id": "FL-GOV-2026:jolly", "name": "David Jolly", "party": "D"},
                                   {"id": "FL-GOV-2026:jewett", "name": "Jason Jewett", "party": "L"}],
                    "baseline": {"2024": {"office": "PRES", "margin": 13.1}, "2022": {"office": "GOV", "margin": 19.4}}},
    "FL-HOU-2026-26": {"race_id": "FL-HOU-2026-26", "state": "FL", "state_fips": "12", "office": "HOU", "district": "26", "special": False,
                       "label": "Florida 26th Congressional District",
                       "candidates": [{"id": "FL-HOU-2026-26:balart", "name": "Mario Díaz-Balart", "party": "R"},
                                      {"id": "FL-HOU-2026-26:locklin", "name": "Nicole Locklin", "party": "D"}]},
    "FL-SEN-2026-S": {"race_id": "FL-SEN-2026-S", "state": "FL", "state_fips": "12", "office": "SEN", "district": None, "special": True,
                      "label": "Florida U.S. Senate (special)",
                      "candidates": [{"id": "FL-SEN-2026-S:moody", "name": "Ashley Moody", "party": "R"},
                                     {"id": "FL-SEN-2026-S:nixon", "name": "Angie Nixon", "party": "D"},
                                     {"id": "FL-SEN-2026-S:gillespie", "name": "Neil Gillespie", "party": "I"}]},
    "NM-SEN-2026": {"race_id": "NM-SEN-2026", "state": "NM", "state_fips": "35", "office": "SEN", "district": None, "special": False,
                    "label": "New Mexico U.S. Senate",
                    "candidates": [{"id": "NM-SEN-2026:lujan", "name": "Ben Ray Luján", "party": "D"},
                                   {"id": "NM-SEN-2026:marker", "name": "Larry Marker", "party": "R"}]},
    "TN-HOU-2026-05": {"race_id": "TN-HOU-2026-05", "state": "TN", "state_fips": "47", "office": "HOU", "district": "05", "special": False,
                       "label": "Tennessee 5th Congressional District",
                       "candidates": [{"id": "TN-HOU-2026-05:ogles", "name": "Andy Ogles", "party": "R"},
                                      {"id": "TN-HOU-2026-05:oleary", "name": "Micheál O'Leary", "party": "I"},
                                      {"id": "TN-HOU-2026-05:smith", "name": "Pat Smith", "party": "D"},
                                      {"id": "TN-HOU-2026-05:smith2", "name": "Jo Smith", "party": "I"}]},
    "GA-HOU-2026-02": {"race_id": "GA-HOU-2026-02", "state": "GA", "state_fips": "13", "office": "HOU", "district": "02", "special": False,
                       "label": "Georgia 2nd Congressional District",
                       "candidates": [{"id": "GA-HOU-2026-02:bishop", "name": "Sanford Bishop", "party": "D"},
                                      {"id": "GA-HOU-2026-02:day", "name": "Matt Day", "party": "R"}]},
    "NE-SEN-2026": {"race_id": "NE-SEN-2026", "state": "NE", "state_fips": "31", "office": "SEN", "district": None, "special": False,
                    "label": "Nebraska U.S. Senate",
                    "candidates": [{"id": "NE-SEN-2026:ricketts", "name": "Pete Ricketts", "party": "R"},
                                   {"id": "NE-SEN-2026:osborn", "name": "Dan Osborn", "party": "I"}]},
}


def make_roster():
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(RACES, f)
    return fo.Roster(f.name)


class MatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = make_roster()

    def m(self, rid, name, party=None):
        return self.r.match(rid, name, party)[0]

    def test_plain_last_name_case_insensitive(self):
        self.assertEqual(self.m('FL-GOV-2026', 'BYRON DONALDS', 'REP'), 'FL-GOV-2026:donalds')
        self.assertEqual(self.m('FL-GOV-2026', 'david jolly'), 'FL-GOV-2026:jolly')

    def test_ticket_formats(self):
        # FL file puts the governor's last name in the first-name column: "Donalds Avila"
        self.assertEqual(self.m('FL-GOV-2026', 'Donalds Avila', 'REP'), 'FL-GOV-2026:donalds')
        self.assertEqual(self.m('FL-GOV-2026', 'Byron Donalds / Jay Collins'), 'FL-GOV-2026:donalds')
        self.assertEqual(self.m('FL-GOV-2026', 'David Jolly and Someone Else'), 'FL-GOV-2026:jolly')

    def test_suffixes_and_parentheticals(self):
        self.assertEqual(self.m('GA-HOU-2026-02', 'Sanford Bishop Jr. (I) (Dem)', 'Dem'), 'GA-HOU-2026-02:bishop')
        self.assertEqual(self.m('GA-HOU-2026-02', 'Sanford D. Bishop, Jr.'), 'GA-HOU-2026-02:bishop')
        self.assertEqual(self.m('GA-HOU-2026-02', 'Matt "Matty" Day III (Rep)'), 'GA-HOU-2026-02:day')

    def test_hyphen_and_diacritics(self):
        self.assertEqual(self.m('FL-HOU-2026-26', 'Diaz-Balart, Mario', 'REP'), 'FL-HOU-2026-26:balart')
        self.assertEqual(self.m('FL-HOU-2026-26', 'MARIO DIAZ BALART'), 'FL-HOU-2026-26:balart')
        self.assertEqual(self.m('FL-HOU-2026-26', 'Mario Díaz-Balart'), 'FL-HOU-2026-26:balart')
        self.assertEqual(self.m('NM-SEN-2026', 'BEN R LUJAN', 'DEM'), 'NM-SEN-2026:lujan')
        self.assertEqual(self.m('NM-SEN-2026', 'Ben Ray Luján'), 'NM-SEN-2026:lujan')
        self.assertEqual(self.m('TN-HOU-2026-05', "Micheal O'Leary"), 'TN-HOU-2026-05:oleary')
        self.assertEqual(self.m('TN-HOU-2026-05', 'Micheál OLeary'), 'TN-HOU-2026-05:oleary')

    def test_ambiguous_names_are_not_guessed(self):
        self.assertIsNone(self.m('TN-HOU-2026-05', 'Smith'))                 # two Smiths, no party
        self.assertEqual(self.m('TN-HOU-2026-05', 'Pat Smith', 'DEM'), 'TN-HOU-2026-05:smith')   # party resolves
        self.assertEqual(self.m('TN-HOU-2026-05', 'Jo Smith'), 'TN-HOU-2026-05:smith2')          # first name resolves
        cid, why = self.r.match('TN-HOU-2026-05', 'Smith', None)
        self.assertIsNone(cid); self.assertTrue(why.startswith('ambiguous'))

    def test_unknown_name_is_logged_not_guessed(self):
        cid, why = self.r.match('FL-GOV-2026', 'Some Newcomer', 'DEM')
        self.assertIsNone(cid); self.assertEqual(why, 'no_match')

    def test_writein_detection(self):
        self.assertTrue(fo.is_writein('Write-in'))
        self.assertTrue(fo.is_writein('Other Write-Ins'))
        self.assertTrue(fo.is_writein('OTHER WRITE-IN'))
        self.assertTrue(fo.is_writein('David E. Bokash (W/I)'))
        self.assertTrue(fo.is_writein('AVERY AYERS', 'WRITE-IN'))
        self.assertFalse(fo.is_writein('Byron Donalds', 'REP'))

    def test_party_normalisation(self):
        for raw, exp in [('REP', 'R'), ('Rep', 'R'), ('Republican Party', 'R'), ('DEM', 'D'), ('Democratic', 'D'), ('DEM/PROG', 'D'),
                         ('NPA', 'I'), ('Ind', 'I'), ('Unaffiliated', 'I'), ('LIB', 'L'), ('LPF', 'L'), ('GRE', 'G'), ('PET', 'I'),
                         ('FWD', 'O'), ('', 'O'), (None, 'O'), ('WRITE-IN', 'O')]:
            self.assertEqual(fo.norm_party(raw), exp, raw)


class ClassifierTests(unittest.TestCase):
    def test_senate(self):
        for t in ['United States Senator', 'US Senate', 'Member, United States Senate', 'Senator in Congress', 'US SENATE (VOTE FOR 1)',
                  'For United States Senator - 6  Year Term', 'U. S. Senator', 'U.S. Senator', 'U. S. SENATOR', 'UNITED STATES SENATOR']:
            self.assertEqual(fo.classify(t)[0], 'SEN', t)
        for t in ['State Senator District 1', 'State Senate - District 1', 'Senator in General Assembly District 1',
                  'Legislative District 6 - State Senator', 'NC SENATE DISTRICT 01 (VOTE FOR 1)']:
            self.assertIsNone(fo.classify(t), t)

    def test_governor(self):
        for t in ['Governor', 'Governor / Lieutenant Governor', 'Governor and Lt. Governor', 'For Governor and Lt. Governor', 'GOVERNOR',
                  'Governor / Lt. Governor', 'Governor and Lieutenant Governor']:
            self.assertEqual(fo.classify(t)[0], 'GOV', t)
        for t in ['Lieutenant Governor', 'LIEUTENANT GOVERNOR', 'Lt. Governor']:
            self.assertIsNone(fo.classify(t), t)

    def test_house_with_district(self):
        cases = {'Representative to the 120th United States Congress - District 1': 1,
                 'United States Representative District 4': 4,
                 'US House of Representatives - District 14': 14,
                 'Member, House of Representatives (11th District)': 11,
                 'Representative in Congress District 2': 2,
                 'U.S. House District 3': 3,
                 'Congressional District 10 - U.S. Representative': 10,
                 'US HOUSE OF REPRESENTATIVES DISTRICT 02 (VOTE FOR 1)': 2,
                 'United States Representative, First District': 1,
                 'U. S. Representative -- 6th Congressional District': 6,
                 'U. S. REPRESENTATIVE DISTRICT 37': 37,
                 'U.S. Representative, Dist II': 2,
                 'Representative In Congress': None,
                 'REPRESENTATIVE TO CONGRESS': None,
                 'United States Representative': None}
        for t, d in cases.items():
            c = fo.classify(t)
            self.assertIsNotNone(c, t); self.assertEqual(c[0], 'HOU', t); self.assertEqual(c[1], d, t)
        for t in ['NC HOUSE OF REPRESENTATIVES DISTRICT 001 (VOTE FOR 1)', 'State Representative District 1 Seat A',
                  'State Board of Education Member - Congressional District 1', 'Regent of the University of Colorado - Congressional District 2',
                  'Legislative District 1 - State Representative Pos. 1', 'House of Delegates', 'State House District 1 (Multi-County)']:
            self.assertIsNone(fo.classify(t), t)

    def test_find_race(self):
        r = make_roster()
        self.assertEqual(r.find_race('FL', 'SEN')['race_id'], 'FL-SEN-2026-S')      # only one Senate race in the state
        self.assertEqual(r.find_race('FL', 'HOU', 26)['race_id'], 'FL-HOU-2026-26')
        self.assertIsNone(r.find_race('FL', 'HOU', 99))
        self.assertEqual(r.find_race('NM', 'HOU', None), None)                      # NM has no HOU race in the fixture
        self.assertEqual(r.find_race('GA', 'HOU', None)['race_id'], 'GA-HOU-2026-02')  # single-district fixture -> at-large rule


class CountyLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'app', 'data', 'counties-10m.json')
        cls.c = fo.Counties(path)

    def test_lookup(self):
        c = self.c
        if not c.names:
            self.skipTest('county table not available')
        self.assertEqual(c.lookup('12', 'Miami-Dade'), '12086')
        self.assertEqual(c.lookup('12', 'St. Lucie'), '12111')
        self.assertEqual(c.lookup('12', 'DeSoto'), '12027')
        self.assertEqual(c.lookup('24', 'Baltimore City'), '24510')
        self.assertEqual(c.lookup('24', 'Baltimore County'), '24005')
        self.assertEqual(c.lookup('24', "Saint Mary's"), '24037')
        self.assertEqual(c.lookup('24', "Prince George's"), '24033')
        self.assertEqual(c.lookup('13', 'APPLING COUNTY'), '13001')
        self.assertEqual(c.lookup('19', "O'Brien"), '19141')
        self.assertEqual(c.lookup('22', 'East Baton Rouge Parish'), '22033')
        self.assertEqual(c.lookup('51', 'FAIRFAX CITY'), '51600')
        self.assertEqual(c.lookup('51', 'FAIRFAX COUNTY'), '51059')
        self.assertEqual(c.lookup('51', 'CHARLES CITY COUNTY'), '51036')
        self.assertIsNone(c.lookup('12', 'Nowhere'))


class CallRuleTests(unittest.TestCase):
    def test_winner_flag_calls(self):
        self.assertTrue(sc.call_rule([('a', 10), ('b', 5)], 15, 3.0, ['a'])[0])

    def test_below_95_never_calls(self):
        self.assertFalse(sc.call_rule([('a', 900000), ('b', 100000)], 1000000, 94.9)[0])

    def test_lead_vs_outstanding(self):
        # 96% reporting, 960k counted -> 40k outstanding; need lead > 44k
        self.assertFalse(sc.call_rule([('a', 500000), ('b', 460000)], 960000, 96.0)[0])    # lead 40k
        self.assertFalse(sc.call_rule([('a', 502000), ('b', 458000)], 960000, 96.0)[0])    # lead 44k (not > 44k)
        self.assertTrue(sc.call_rule([('a', 502100), ('b', 457900)], 960000, 96.0)[0])     # lead 44.2k
        self.assertTrue(sc.call_rule([('a', 51), ('b', 49)], 100, 100.0)[0])               # 100% in: any lead
        self.assertFalse(sc.call_rule([('a', 50), ('b', 50)], 100, 100.0)[0])              # tie
        self.assertFalse(sc.call_rule([], 0, 100.0)[0])
        self.assertFalse(sc.call_rule([('a', 1)], 1, None)[0])

    def test_confidence(self):
        self.assertEqual(sc.official_confidence(0), 40)
        self.assertEqual(sc.official_confidence(50), 70)
        self.assertEqual(sc.official_confidence(100), 99)
        self.assertEqual(sc.official_confidence(100, certified=True), 100)
        self.assertEqual(sc.official_confidence(None), 40)

    def test_pct_by_party(self):
        from collections import Counter
        pct = sc.pct_by_party(Counter({'D': 48, 'R': 50, 'L': 2}), 100, False, True, True)
        self.assertEqual(pct, {'D': 48.0, 'R': 50.0, 'O': 2.0})
        pct = sc.pct_by_party(Counter({'R': 55, 'I': 45}), 100, True, False, True)
        self.assertEqual(pct['I'], 45.0); self.assertEqual(pct['O'], 0.0)
        pct = sc.pct_by_party(Counter({'D': 47, 'R': 49, 'I': 4}), 100, True, True, True)
        self.assertNotIn('I', pct); self.assertEqual(pct['O'], 4.0)
        pct = sc.pct_by_party(Counter({'D': 40, 'R': 45, 'I': 15}), 100, True, True, True)
        self.assertEqual(pct['I'], 15.0)


class ScorerTests(unittest.TestCase):
    def rec(self, jkey, rid, votes, pr, winner=None, ts='2026-11-04T02:00:00Z'):
        return {'jkey': jkey, 'race_id': rid, 'votes': votes, 'pct_reporting': pr, 'status': 'official_preliminary',
                'retrieved_at': ts, 'url': 'https://example.gov', 'state': rid[:2], 'winner': winner or [], 'extra_parties': {}}

    def test_official_scoring_and_call(self):
        official = [self.rec('12', 'FL-GOV-2026', {'FL-GOV-2026:donalds': 560, 'FL-GOV-2026:jolly': 400, 'FL-GOV-2026:jewett': 40}, 96.0)]
        s = sc.Scorer(RACES, {}, {}, official, [], {}, {}, now='2026-11-04T02:05:00Z').run()
        r = s['results']['12']['FL-GOV-2026']
        self.assertEqual(r['status'], 'official_preliminary')
        self.assertEqual(r['confidence'], 98)                  # 40 + 0.6*96 = 97.6 -> 98
        self.assertEqual(r['pct'], {'D': 40.0, 'R': 56.0, 'O': 4.0})
        self.assertEqual(r['leader'], 'R'); self.assertEqual(r['margin'], 16.0)
        self.assertEqual(r['swing_vs_2024'], 2.9); self.assertEqual(r['swing_vs_2022'], -3.4)
        self.assertTrue(r['called']); self.assertEqual(r['called_by'], 'official_count')
        types = {c['type'] for c in s['changes']}
        self.assertIn('newly_official', types); self.assertIn('race_called', types)
        called = [c for c in s['changes'] if c['type'] == 'race_called'][0]
        self.assertTrue(called['official'] and called['important'])
        self.assertIn('Byron Donalds (R)', called['text'])

    def test_zero_votes_stays_pending_and_media_fills(self):
        official = [self.rec('12', 'FL-GOV-2026', {'FL-GOV-2026:donalds': 0, 'FL-GOV-2026:jolly': 0}, 0.0)]
        media = [{'jkey': '12', 'race_id': 'FL-GOV-2026', 'figures': {'R': 55.0, 'D': 43.0}, 'claimed_source': 'AP', 'platform': 'web',
                  'account': 'apnews', 'tier': 1, 'posted_at': '2026-11-04T01:00:00Z', 'retrieved_at': '2026-11-04T01:05:00Z', 'url': 'https://apnews.com', 'type': 'article'}]
        s = sc.Scorer(RACES, {}, {}, official, [], {}, {}).run()
        self.assertEqual(s['results']['12']['FL-GOV-2026']['status'], 'pending')
        self.assertEqual(s['results']['12']['FL-GOV-2026']['confidence'], 0)
        self.assertFalse(any(c['type'] == 'newly_official' for c in s['changes']))
        s = sc.Scorer(RACES, {}, {}, official, media, {}, {}).run()
        r = s['results']['12']['FL-GOV-2026']
        self.assertEqual(r['status'], 'estimated'); self.assertEqual(r['confidence'], 60); self.assertEqual(r['leader'], 'R')

    def test_official_overrides_media_and_rejects_it(self):
        official = [self.rec('12', 'FL-GOV-2026', {'FL-GOV-2026:donalds': 50, 'FL-GOV-2026:jolly': 50}, 10.0)]
        media = [{'jkey': '12', 'race_id': 'FL-GOV-2026', 'figures': {'R': 70, 'D': 30}, 'claimed_source': 'AP', 'platform': 'web', 'account': 'x', 'tier': 1,
                  'posted_at': '2026-11-04T01:00:00Z', 'retrieved_at': '2026-11-04T01:05:00Z', 'url': 'u', 'type': 'article'}]
        s = sc.Scorer(RACES, {}, {}, official, media, {}, {}).run()
        r = s['results']['12']['FL-GOV-2026']
        self.assertEqual(r['status'], 'official_preliminary'); self.assertEqual(r['confidence'], 46)
        self.assertEqual(r['sources_rejected'][0]['reason'], 'official data available for this jurisdiction')
        self.assertFalse(r['called'])

    def test_media_tiers_and_contested(self):
        def m(tier, d, r, src='AP', acct='a', ts='2026-11-04T01:00:00Z'):
            return {'jkey': '35', 'race_id': 'NM-SEN-2026', 'figures': {'D': d, 'R': r}, 'claimed_source': src, 'platform': 'web', 'account': acct,
                    'tier': tier, 'posted_at': ts, 'retrieved_at': ts, 'url': 'u', 'type': 'post'}
        s = sc.Scorer(RACES, {}, {}, [], [m(1, 52, 46)], {}, {}).run()
        r = s['results']['35']['NM-SEN-2026']; self.assertEqual((r['status'], r['confidence']), ('estimated', 60))
        s = sc.Scorer(RACES, {}, {}, [], [m(1, 52, 46), m(1, 52.5, 45.8, 'NBC', 'b'), m(1, 51.2, 46.9, 'CNN', 'c')], {}, {}).run()
        r = s['results']['35']['NM-SEN-2026']; self.assertEqual((r['status'], r['confidence']), ('estimated', 75))
        s = sc.Scorer(RACES, {}, {}, [], [m(2, 52, 46)], {}, {}).run()
        self.assertEqual(s['results']['35']['NM-SEN-2026']['confidence'], 45)
        s = sc.Scorer(RACES, {}, {}, [], [m(3, 52, 46)], {}, {}).run()
        self.assertEqual(s['results']['35']['NM-SEN-2026']['confidence'], 30)
        s = sc.Scorer(RACES, {}, {}, [], [m(3, 52, 46, src=None)], {}, {}).run()
        r = s['results']['35']['NM-SEN-2026']
        self.assertEqual(r['status'], 'pending'); self.assertEqual(r['sources_rejected'][0]['reason'], 'unsourced social post')
        s = sc.Scorer(RACES, {}, {}, [], [m(1, 52, 46), m(1, 48.5, 49.5, 'Reuters', 'b')], {}, {}).run()
        r = s['results']['35']['NM-SEN-2026']
        self.assertEqual(r['status'], 'contested'); self.assertEqual(r['range']['D'], [48.5, 52.0])
        self.assertTrue(any(c['type'] == 'contested' for c in s['changes']))

    def test_flip_confidence_shift_and_carry_forward(self):
        first = [self.rec('12', 'FL-GOV-2026', {'FL-GOV-2026:donalds': 40, 'FL-GOV-2026:jolly': 60}, 10.0, ts='2026-11-04T01:00:00Z')]
        prev = sc.Scorer(RACES, {}, {}, first, [], {}, {}, now='2026-11-04T01:00:00Z').run()
        second = [self.rec('12', 'FL-GOV-2026', {'FL-GOV-2026:donalds': 600, 'FL-GOV-2026:jolly': 400}, 50.0, ts='2026-11-04T02:00:00Z')]
        s = sc.Scorer(RACES, {}, prev, second, [], {}, {}, now='2026-11-04T02:05:00Z').run()
        types = [c['type'] for c in s['changes'] if c['ts'] == '2026-11-04T02:00:00Z']
        self.assertIn('flip', types); self.assertIn('confidence_shift', types); self.assertNotIn('newly_official', types)
        flip = [c for c in s['changes'] if c['type'] == 'flip'][0]
        self.assertTrue(flip['official']); self.assertFalse(flip['important'])
        # third run: the feed vanished -> previous official result carried forward, no new changes
        s3 = sc.Scorer(RACES, {}, s, [], [], {}, {}, now='2026-11-04T02:10:00Z').run()
        self.assertTrue(s3['results']['12']['FL-GOV-2026'].get('carried_forward'))
        self.assertEqual(s3['meta']['counts']['new_changes'], 0)
        # a glitch back to zero votes also keeps the previous figures
        s4 = sc.Scorer(RACES, {}, s, [self.rec('12', 'FL-GOV-2026', {'FL-GOV-2026:donalds': 0}, 0.0, ts='2026-11-04T02:20:00Z')], [], {}, {}).run()
        self.assertEqual(s4['results']['12']['FL-GOV-2026']['status'], 'official_preliminary')

    def test_majority_crossed(self):
        # fixture Senate: pretend not_up gives R 50; one called R seat -> 51
        import score as scm
        orig = scm.senate_not_up
        scm.senate_not_up = lambda races: {'D': 45, 'R': 50, 'I': 2}
        try:
            official = [self.rec('31', 'NE-SEN-2026', {'NE-SEN-2026:ricketts': 700, 'NE-SEN-2026:osborn': 300}, 100.0)]
            s = scm.Scorer(RACES, {}, {}, official, [], {}, {}, now='2026-11-04T03:00:00Z').run()
            mc = [c for c in s['changes'] if c['type'] == 'majority_crossed']
            self.assertEqual(len(mc), 1); self.assertIn('Republicans reach 51', mc[0]['text'])
            self.assertTrue(mc[0]['official'] and mc[0]['important'])
            # independent candidate shown because race has no D
            self.assertIn('I', s['results']['31']['NE-SEN-2026']['pct'])
            # second run: already crossed -> no repeat
            s2 = scm.Scorer(RACES, {}, s, official, [], {}, {}, now='2026-11-04T03:05:00Z').run()
            self.assertFalse(any(c['type'] == 'majority_crossed' for c in s2['changes'] if c['ts'] == '2026-11-04T03:05:00Z'))
            self.assertEqual(len([c for c in s2['changes'] if c['type'] == 'majority_crossed']), 1)
        finally:
            scm.senate_not_up = orig

    def test_county_results_not_called_and_flip_threshold(self):
        official = [self.rec('12086', 'FL-GOV-2026', {'FL-GOV-2026:donalds': 600, 'FL-GOV-2026:jolly': 400}, 100.0)]
        s = sc.Scorer(RACES, {}, {}, official, [], {}, {'12086': 'Miami-Dade'}).run()
        r = s['results']['12086']['FL-GOV-2026']
        self.assertFalse(r['called']); self.assertEqual(r['confidence'], 99)
        self.assertEqual(s['changes'], [])   # no state-level change types for counties
        official2 = [self.rec('12086', 'FL-GOV-2026', {'FL-GOV-2026:donalds': 400, 'FL-GOV-2026:jolly': 600}, 100.0, ts='2026-11-04T03:00:00Z')]
        s2 = sc.Scorer(RACES, {}, s, official2, [], {}, {'12086': 'Miami-Dade'}).run()
        self.assertEqual([c['type'] for c in s2['changes'] if c['ts'] == '2026-11-04T03:00:00Z'], ['flip'])
        self.assertIn('Miami-Dade, FL', s2['changes'][0]['text'])


if __name__ == '__main__':
    unittest.main(verbosity=1)
