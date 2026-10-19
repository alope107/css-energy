import re,sys
t=open(sys.argv[1]).read()
lines=t.split('\n')
out={}
for i,l in enumerate(lines):
    m=re.match(r'\s*name:\s*"([^"]+)"',l)
    if not m: continue
    n=m.group(1)
    if not re.search(r'ViewTransition|SMIL|Smil|SVG|Svg|EventTimingMatchingHTML|PageReveal|PageSwap|Navigation', n): continue
    # find status within next 40 lines until line starting with "    }," 
    st='(none)'
    for j in range(i+1,min(i+60,len(lines))):
        if re.match(r'\s*name:\s*"',lines[j]): break
        mm=re.match(r'\s*status:\s*(.*)',lines[j])
        if mm:
            s=mm.group(1)
            k=j
            while '{' in s and '}' not in s:
                k+=1; s+=' '+lines[k].strip()
            st=s; break
    out[n]=(i+1,st)
for n,(l,s) in sorted(out.items()): print(f"{l}\t{n}\t{s}")
