# writes child.html: a page whose style recalc is heavy (12,000 animated elements)
head = """<!doctype html><style>
@property --t{syntax:'<number>';inherits:true;initial-value:0}
@keyframes t{from{--t:0}to{--t:1000}}
#r{animation:t 1000s linear infinite;position:absolute;width:0;height:0;overflow:hidden}
#r i{display:block;--a:calc(sin(var(--t) + sibling-index()) * cos(var(--t) * 3) + tan(var(--t) * 0.1));--b:calc(var(--a) * var(--a) + sin(var(--a)));--c:calc(var(--b) * var(--a) - cos(var(--b)))}
</style><div id=r>"""
open('child.html', 'w').write(head + '<i></i>' * 12000)
