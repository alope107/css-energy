import re,sys
def parse(path):
    t=open(path).read()
    i=t.find('data: [')
    t=t[i:]
    out={}
    for blk in re.split(r'\n    \{', t)[1:]:
        blk=blk.split('\n    }')[0]
        nm=re.search(r'\n      name:\s*"([^"]+)"', blk)
        if not nm: continue
        st = re.search(r'\n      status:\s*("([^"]*)"|\{.*?\})', blk, re.S)
        s = '-' if not st else re.sub(r'\s+',' ',st.group(1))
        out[nm.group(1)]=s
    return out
a=parse(sys.argv[1])
b=parse(sys.argv[2]) if len(sys.argv)>2 and sys.argv[2]!='-' else {}
pat=re.compile(sys.argv[3] if len(sys.argv)>3 else '.')
for k in sorted(set(a)|set(b)):
    if pat.search(k):
        print(f"{k:55s} | {b.get(k,'(absent)') if b else ''} | {a.get(k,'(absent)')}")
