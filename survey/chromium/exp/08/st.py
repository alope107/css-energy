import re,sys
sys.path.insert(0,'.')
def parse(path):
    src=open(path).read(); out={}
    for m in re.finditer(r'\n    \{\n(.*?)\n    \},', src, re.S):
        body=m.group(1); n=re.search(r'name:\s*"([^"]+)"',body)
        if not n: continue
        st=re.search(r'\n      status:\s*(\{.*?\}|"[^"]*")',body,re.S)
        out[n.group(1)]=re.sub(r'\s+',' ',st.group(1)) if st else '-'
    return out
P=[parse(p) for p in sys.argv[1:5]]
names=sys.stdin.read().split()
for n in names:
    print(f"{n:42s}", ' | '.join((p.get(n,'ABSENT'))[:22] for p in P))
