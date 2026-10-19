import sys,re
def parse(path):
    txt=open(path).read()
    out={}
    # split on lines '    {' at depth of the data array
    for m in re.finditer(r'\n    \{\n(.*?)\n    \},?', txt, re.S):
        body=m.group(1)
        n=re.search(r'name:\s*"([^"]+)"',body)
        if not n: continue
        st=re.search(r'\n      status:\s*("[^"]*"|\{[^}]*\})',body)
        line=txt[:m.start()].count('\n')+2
        out[n.group(1)]=(line, re.sub(r'\s+',' ',st.group(1)) if st else '-')
    return out
a=parse(sys.argv[1]); b=parse(sys.argv[2])
pat=re.compile(sys.argv[3])
for k in sorted(set(a)|set(b)):
    if pat.search(k):
        print(f"{k}\t153:{a.get(k,('','absent'))[1]}@{a.get(k,('',''))[0]}\tmain:{b.get(k,('','absent'))[1]}@{b.get(k,('',''))[0]}")
