import sys, re
sys.path.insert(0, sys.argv[1])
import json5
m = {f['name']: f for f in json5.load('v/g_ref_main.json5')['data']}
o = {f['name']: f for f in json5.load('v/g_ref_8010.json5')['data']}
pat = re.compile(sys.argv[2])
for n, f in sorted(m.items()):
    s = f.get('status', '')
    if isinstance(s, dict): s = 'dict:' + str(s)
    if s in ('stable',) and len(sys.argv) < 4: continue
    if pat.search(n):
        s153 = (o[n].get('status', '') or 'off') if n in o else '—'
        if isinstance(s153, dict): s153 = 'dict'
        print(f"{n:55s} main={s or 'off':14s} 153={s153 or 'off':12s}", f.get('depends_on', '') or '', f.get('origin_trial_feature_name', '') or '', f.get('base_feature', '') if f.get('base_feature') not in (None, 'none') else '')
