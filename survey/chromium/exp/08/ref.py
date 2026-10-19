import re,sys,json
def parse(path):
    src=open(path).read()
    out={}
    # split on top-level entries
    for m in re.finditer(r'\n    \{\n(.*?)\n    \},', src, re.S):
        body=m.group(1)
        n=re.search(r'name:\s*"([^"]+)"',body)
        if not n: continue
        st=re.search(r'\n      status:\s*(\{.*?\}|"[^"]*")',body,re.S)
        s=st.group(1) if st else '-'
        s=re.sub(r'\s+',' ',s)
        out[n.group(1)]=s
    return out
a=parse(sys.argv[1]); b=parse(sys.argv[2])
print(len(a),len(b))
for k in sorted(set(a)|set(b)):
    if a.get(k)!=b.get(k):
        print(f"{k}: {a.get(k,'ABSENT')} -> {b.get(k,'ABSENT')}")
