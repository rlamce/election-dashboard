#!/usr/bin/env python3
"""Parse Wikipedia 2026 election summary tables (wikitext) into candidate lists."""
import re, json, sys

PARTY_MAP = {
    'republican': 'R', 'democratic': 'D', 'democrat': 'D', 'dfl': 'D', 'minnesota democratic–farmer–labor': 'D',
    'democratic–farmer–labor': 'D', 'democratic-farmer-labor': 'D', 'democratic-npl': 'D', 'democratic–npl': 'D',
    'north dakota democratic–npl': 'D',
    'independent': 'I', 'libertarian': 'L', 'green': 'G',
}

def strip_refs(s):
    s = re.sub(r'<ref[^>/]*/>', '', s)
    s = re.sub(r'<ref[^>]*>.*?</ref>', '', s, flags=re.S)
    s = re.sub(r'<!--.*?-->', '', s, flags=re.S)
    return s

def strip_templates(s):
    # remove simple templates {{...}} (non-nested) repeatedly
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\{\{[^{}]*\}\}', '', s)
    return s

def clean_link(s):
    # [[a|b]] -> b ; [[a]] -> a
    s = re.sub(r'\[\[([^\]|]*)\|([^\]]*)\]\]', r'\2', s)
    s = re.sub(r'\[\[([^\]]*)\]\]', r'\1', s)
    s = re.sub(r"'''?", '', s)
    return s.strip()

def party_code(label):
    l = label.lower().strip()
    l = re.sub(r'\s*party.*$', '', l)
    l = l.replace(' (us)', '').replace(' (united states)', '')
    if l in PARTY_MAP: return PARTY_MAP[l]
    if 'republican' in l: return 'R'
    if 'democrat' in l: return 'D'
    if 'libertarian' in l: return 'L'
    if 'green' in l: return 'G'
    if 'independent' in l or 'nonpartisan' in l or 'no party' in l or 'unaffiliated' in l: return 'I'
    return 'O'

CAND_RE = re.compile(r'^\*\s*(?:\{\{Party stripe\|([^}]*)\}\})?\s*(.*)$')

def parse_candidates(block):
    """block: text inside {{Plainlist | ... }} ; returns list of dicts"""
    out = []
    for line in block.split('\n'):
        line = line.strip()
        if not line.startswith('*'): continue
        raw = strip_refs(line)
        raw = re.sub(r'\}\}\s*$', '', raw).strip() if raw.rstrip().endswith('}}') and raw.count('{{') < raw.count('}}') else raw
        m = CAND_RE.match(raw)
        if not m: continue
        stripe, rest = m.group(1) or '', m.group(2)
        rest = strip_refs(rest)
        # party label in trailing parentheses
        pm = re.search(r'\(([^()]*)\)\s*(?:\{\{[^}]*\}\}\s*)*$', rest.strip())
        plabel = pm.group(1) if pm else stripe
        name = rest
        if pm: name = rest[:pm.start()]
        name = clean_link(strip_templates(name)).strip().rstrip(',').strip()
        # flags like (incumbent) embedded
        name = re.sub(r'\s*\((incumbent|write-in)\)', '', name, flags=re.I)
        extra = ''
        if '(write-in' in rest.lower(): extra = 'write-in'
        if not name: continue
        code = party_code(plabel or stripe)
        out.append({'name': name, 'party': code, 'party_label': clean_link(plabel or stripe).strip(), 'note': extra})
    return out

def split_rows(table_text):
    rows = re.split(r'\n\|-[^\n]*\n', table_text)
    return rows

def parse_summary_table(text, start_marker, end_marker=None):
    i = text.find(start_marker)
    if i < 0: raise SystemExit('start marker not found: ' + start_marker)
    j = text.find('\n|}', i)
    if end_marker:
        k = text.find(end_marker, i)
        if 0 <= k < j: j = k
    table = text[i:j]
    rows = split_rows(table)
    results = []
    for row in rows:
        if not row.strip().startswith('!'): continue
        head = row.strip().split('\n')[0]
        hm = re.search(r'\[\[(2026 [^\]|]*)\|([^\]]*)\]\]', head)
        if not hm: continue
        page, label = hm.group(1), clean_link(hm.group(2))
        # incumbent
        im = re.search(r'\{\{sortname\|([^|}]*)\|([^|}]*)', row)
        inc_name = None
        if im: inc_name = (im.group(1) + ' ' + im.group(2)).strip()
        else:
            im2 = re.search(r'\n\|\s*\[\[([^\]|]*)(?:\|([^\]]*))?\]\]', row)
            if im2: inc_name = (im2.group(2) or im2.group(1)).strip()
        pm = re.search(r'\{\{Party shading/([A-Za-z–\- ]+)\}\}\s*\|\s*([^\n|]*)', row)
        inc_party = clean_link(pm.group(2)).strip() if pm else None
        # results text (status) — cell before Plainlist
        status = None
        sm = re.search(r'data-sort-value=-?\d+\s*\|\s*([^\n]*)\n\|\s*nowrap', row)
        if sm: status = clean_link(strip_refs(strip_templates(sm.group(1)))).strip()
        # candidates
        cm = re.search(r'\{\{plainlist\s*[|}](.*)', row, flags=re.S|re.I)
        cands = parse_candidates(cm.group(1)) if cm else []
        results.append({'page': page, 'label': label, 'incumbent': inc_name, 'incumbent_party': inc_party, 'status': status, 'candidates': cands, 'raw_head': head})
    return results

if __name__ == '__main__':
    path, marker = sys.argv[1], sys.argv[2]
    text = open(path, encoding='utf-8').read()
    res = parse_summary_table(text, marker)
    json.dump(res, sys.stdout, indent=1, ensure_ascii=False)


def parse_gov_table(text):
    """Governor summary table ('=== States ===' on the 2026 gubernatorial page)."""
    i = text.find('=== States ===')
    j = text.find('\n|}', i)
    table = text[i:j]
    rows = split_rows(table)
    out = []
    for row in rows:
        if not row.strip().startswith('!'): continue
        head = row.strip().split('\n')[0]
        hm = re.search(r'\[\[(2026 [^\]|]*)\|([^\]]*)\]\]', head)
        if not hm: continue
        page, label = hm.group(1), clean_link(hm.group(2))
        im = re.search(r'\{\{sortname\|([^|}]*)\|([^|}]*)', row)
        inc = (im.group(1) + ' ' + im.group(2)).strip() if im else None
        if not inc:
            im2 = re.search(r'\n\|\s*\[\[([^\]|]*)(?:\|([^\]]*))?\]\]', row)
            if im2: inc = (im2.group(2) or im2.group(1)).strip()
        pm = re.search(r'\{\{party shading/(?:Text/)?([A-Za-z–\- ]+)\}\}', row, flags=re.I)
        incp = pm.group(1) if pm else None
        if incp and 'Farmer' in incp: incp = 'DFL'
        body = row[len(head):]
        pre = re.split(r'\{\{plainlist', body, flags=re.I)[0]
        cells = re.split(r'\n\|', pre)
        status = None
        for c in reversed(cells):
            c2 = clean_link(strip_refs(strip_templates(c))).replace('nowrap', '').strip(' |\n')
            if c2:
                status = c2; break
        cm = re.search(r'\{\{plainlist\s*[|}](.*)', row, flags=re.S | re.I)
        cands = parse_candidates(cm.group(1)) if cm else []
        out.append({'page': page, 'label': label, 'incumbent': inc, 'incumbent_party': incp, 'status': status, 'candidates': cands})
    return out
