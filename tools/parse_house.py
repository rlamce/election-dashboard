#!/usr/bin/env python3
"""Parse the per-state district tables on the Wikipedia 2026 House elections page."""
import re, json, sys
sys.path.insert(0, '/home/claude/election-dashboard/tools')
import parse_wiki as pw

def parse_house(text):
    # restrict to the state sections (after '==Alabama==')
    i = text.find('\n==Alabama==')
    body = text[i:]
    # cut off at Notes/References
    for end in ('\n==See also==', '\n== See also ==', '\n==Notes==', '\n== Notes ==', '\n==References==', '\n== References =='):
        k = body.find(end)
        if k > 0: body = body[:k]
    # find all district markers inside table header cells
    markers = list(re.finditer(r'\{\{ushr\|([A-Z]{2})\|([A-Za-z0-9]+)\|X\}\}', body))
    out = {}
    for n, m in enumerate(markers):
        st, dist = m.group(1), m.group(2)
        start = m.end()
        end = markers[n+1].start() if n+1 < len(markers) else len(body)
        block = body[start:end]
        # stop at table end
        te = block.find('\n|}')
        if te >= 0: block = block[:te]
        dnum = 0 if dist.upper() == 'AL' else int(dist)
        key = f'{st}-{dnum:02d}'
        # incumbents: sortname or [[link]] in a cell before the party cell
        incs = []
        for im in re.finditer(r'\n\|(?:rowspan=\d+\s*\|)?\s*(?:\{\{sortname\|([^|}]*)\|([^|}]*)(?:\|[^}]*)?\}\}|\[\[([^\]|]*)(?:\|([^\]]*))?\]\])', block):
            if im.group(1): name = (im.group(1) + ' ' + im.group(2)).strip()
            else: name = (im.group(4) or im.group(3)).strip()
            if re.search(r'elections? in|election', name): continue
            incs.append(name)
        # status cells
        statuses = re.findall(r'\n\|(?:\{\{Party shading/[^}]*\}\}\s*\|)?\s*(Incumbent[^\n|]*|New representative[^\n|]*|Member[^\n|]*)', block)
        statuses = [pw.clean_link(pw.strip_refs(pw.strip_templates(s))).strip() for s in statuses]
        # candidates
        cands = []
        cm = re.search(r'\{\{plainlist\s*[|}](.*?)(?:\{\{endplainlist\}\}|\n\}\})', block, flags=re.S | re.I)
        if cm:
            cands = pw.parse_candidates(cm.group(1))
        else:
            # maybe a non-plainlist bullet list
            cm2 = re.search(r'(\n\*.*)', block, flags=re.S)
            if cm2: cands = pw.parse_candidates(cm2.group(1))
        out[key] = {'state': st, 'district': dnum, 'wiki_incumbents': incs, 'status': statuses, 'candidates': cands}
    return out

if __name__ == '__main__':
    text = open(sys.argv[1], encoding='utf-8').read()
    res = parse_house(text)
    json.dump(res, open(sys.argv[2], 'w'), indent=1, ensure_ascii=False)
    print(len(res), 'districts parsed')
    nocand = [k for k, v in res.items() if not v['candidates']]
    print('no candidates:', len(nocand), nocand[:40])
    one = [k for k, v in res.items() if len(v['candidates']) == 1]
    print('one candidate:', len(one), one)
