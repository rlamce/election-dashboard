#!/usr/bin/env python3
"""Parse 2022 Senate / governor summary tables (candidates with %) from Wikipedia wikitext."""
import re, json, sys
sys.path.insert(0, '/home/claude/election-dashboard/tools')
import parse_wiki as pw

def parse(text, start_marker, link_prefix_re):
    i = text.find(start_marker)
    j = text.find('\n|}', i)
    table = text[i:j]
    table = pw.strip_refs(table)
    rows = re.split(r'\n\|-[^\n]*\n', table)
    out = {}
    for row in rows:
        m = re.search(link_prefix_re, row)
        if not m: continue
        state = m.group(1).strip()
        special = '(special)' in row.split('\n')[0].lower() or 'special' in m.group(0).lower()
        cm = re.search(r'\{\{plainlist\s*[|}](.*)', row, flags=re.S | re.I)
        if not cm: continue
        cands = []
        for line in cm.group(1).split('\n'):
            line = line.strip()
            if not line.startswith('*'): continue
            pm = re.search(r'\(([^()]*)\)\s*([\d.]+)%', line)
            if not pm: continue
            plabel, pct = pm.group(1), float(pm.group(2))
            name = line[:pm.start()]
            name = re.sub(r'\{\{Party stripe\|[^}]*\}\}', '', name)
            name = pw.strip_templates(name)
            name = pw.clean_link(name).lstrip('*').strip()
            cands.append({'name': name, 'party': pw.party_code(plabel), 'party_label': plabel, 'pct': pct})
        key = state + (' (special)' if special else '')
        out[key] = cands
    return out

if __name__ == '__main__':
    sen = parse(open('/home/claude/dl/wiki/sen22_raw.txt', encoding='utf-8').read(),
                '=== Elections leading to the next Congress ===',
                r'\[\[2022 United States Senate (?:special )?election in ([^\]|]*)\|')
    sen_sp = parse(open('/home/claude/dl/wiki/sen22_raw.txt', encoding='utf-8').read(),
                '=== Special elections during the preceding Congress ===',
                r'\[\[2022 United States Senate (?:special )?election in ([^\]|]*)\|')
    gov = parse(open('/home/claude/dl/wiki/gov22_raw.txt', encoding='utf-8').read(),
                '=== States ===',
                r'\[\[2022 ([A-Za-z ]+) gubernatorial election\|')
    json.dump({'SEN': sen, 'SEN_special': sen_sp, 'GOV': gov}, open('/home/claude/dl/wiki/res22_parsed.json', 'w'), indent=1, ensure_ascii=False)
    for label, d in (('SEN', sen), ('SEN_special', sen_sp), ('GOV', gov)):
        print('==', label, len(d))
        for k, v in d.items():
            top = sorted(v, key=lambda c: -c['pct'])[:3]
            print(f"  {k:22}", ' | '.join(f"{c['party']} {c['name']} {c['pct']}" for c in top))
