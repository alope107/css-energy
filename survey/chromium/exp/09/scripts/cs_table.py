# merge chromestatus list dumps; print a table of features with milestones
import json, sys, re
files = sys.argv[1:]
feats = {}
for fn in files:
    d = json.load(open(fn))
    for f in d['features']:
        feats[f['id']] = f
def ms(f):
    out = {}
    for s in f.get('stages', []):
        t = s['stage_type'] % 100
        kind = {30: 'dt', 50: 'ot', 51: 'otx', 60: 'ship', 61: 'roll'}.get(t)
        if not kind: continue
        a, b = s.get('desktop_first'), s.get('desktop_last')
        if a or b:
            out.setdefault(kind, []).append(f"{a or ''}{'-'+str(b) if b else ''}")
    return out
rows = []
for f in feats.values():
    b = f['browsers']['chrome']
    rows.append(dict(id=f['id'], name=f['name'], cat=f.get('category'), comp=','.join(f.get('blink_components') or []),
        status=b['status']['text'], desk=b.get('desktop'), ms=ms(f), flag=f.get('flag_name') or '', finch=f.get('finch_name') or '',
        ff=f['browsers']['ff']['view']['text'], sf=f['browsers']['safari']['view']['text'], type=f.get('feature_type'),
        updated=f['updated']['when'][:10], created=f['created']['when'][:10]))
json.dump(rows, open('/dev/stdout', 'w'), indent=0)
