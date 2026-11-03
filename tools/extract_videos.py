import re, sys, json, os
# Extract (videoId, title, status, timeText) from ytInitialData lockupViewModel entries in a saved streams page.
def extract(path):
    s = open(path, encoding='utf-8', errors='ignore').read()
    m = re.search(r'ytInitialData = (\{.*?\});</script>', s, re.S)
    if not m: return []
    try: data = json.loads(m.group(1))
    except Exception: return []
    out = []
    def walk(o):
        if isinstance(o, dict):
            if 'lockupViewModel' in o:
                lv = o['lockupViewModel']
                vid = lv.get('contentId')
                md = lv.get('metadata',{}).get('lockupMetadataViewModel',{})
                title = md.get('title',{}).get('content','')
                blob = json.dumps(lv)
                status = 'vod'
                if 'THUMBNAIL_OVERLAY_BADGE_STYLE_LIVE' in blob: status = 'live'
                elif 'UPCOMING' in blob or 'upcoming' in blob.lower(): status = 'upcoming'
                # metadata rows: e.g. "1.2K watching" / "Streamed 2 hours ago" / "Scheduled for ..."
                parts = re.findall(r'"content":"([^"]*)"', blob)
                meta = [p for p in parts if re.search(r'watching|Streamed|Scheduled|ago|waiting', p)]
                out.append((vid, title, status, ' | '.join(meta[:3])))
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(data)
    seen=set(); res=[]
    for r in out:
        if not r[0] or r[0] in seen: continue
        seen.add(r[0]); res.append(r)
    return res

if __name__ == '__main__':
    for p in sys.argv[1:]:
        key = os.path.basename(p).replace('.html','')
        for vid, title, status, meta in extract(p):
            print(f"{key}\t{vid}\t{status}\t{meta}\t{title}")
