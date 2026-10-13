"""Does Blink copy the inherited custom-property map at every level below the root?
Hypothesis: StyleInheritedVariables keeps a pointer to the topmost declaring element's map (the "root") and
every deeper declaring element copies the cumulative map declared since the root. Then R vars declared at
level 1 of a D-deep chain cost O(D * R) per pass, while the same vars at the root cost nothing extra.
  in_r{R0}_m{R1}_d{D}.html : #a (root, animates --t) declares R0 vars; level 1 declares R1 vars; levels 2..D
                             declare one var each (so each is restyled and must copy).
Measure: node tools/stylebench.js in_*.html 500 1500"""
def page(R0, R1, D, ninh=False):
    props = ''.join(f"@property --r{k}{{syntax:'<number>';inherits:true;initial-value:0}}" for k in range(R0))
    props += ''.join(f"@property --m{k}{{syntax:'<number>';inherits:{'false' if ninh else 'true'};initial-value:0}}" for k in range(R1))
    props += ''.join(f"@property --l{d}{{syntax:'<number>';inherits:true;initial-value:0}}" for d in range(D))
    props += "@property --t{syntax:'<number>';inherits:true;initial-value:0}"
    css = props + "@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite;"
    css += ''.join(f'--r{k}:calc(var(--t) * {k});' for k in range(R0)) + '}'
    css += '#l1{' + ''.join(f'--m{k}:calc(var(--t) * {k});' for k in range(R1)) + '}'
    css += ''.join(f'#l{d}{{--l{d}:calc(var(--t) + {d})}}' for d in range(1, D + 1))
    html = '<div id=a>' + ''.join(f'<div id=l{d}>' for d in range(1, D + 1)) + '<b id=b></b>' + '</div>' * D + '</div>'
    open(f"in_r{R0}_m{R1}_d{D}{'_ni' if ninh else ''}.html", 'w').write(f'<!doctype html><style>{css}</style>{html}')
page(6000, 0, 66)
page(0, 6000, 66)
page(0, 6000, 8)
page(0, 6000, 130)
page(0, 6000, 66, ninh=True)
page(0, 0, 66)
page(0, 0, 130)
