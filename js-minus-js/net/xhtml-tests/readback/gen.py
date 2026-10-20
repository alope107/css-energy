import os
SW=100; MAXV=3000; OBJ_W=2*SW+MAXV; MAXS=OBJ_W-SW; API='http://127.0.0.1:9482/api'
CHILD='''<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="2; url={nxt}#t">
<style>html,body{{margin:0;overflow:hidden}} body{{white-space:nowrap;height:1px;font-size:0}}
span{{display:inline-block;height:1px}} .base{{width:{sw}px}} .v{{width:0}} #t{{width:{sw}px}}</style>
<link rel="stylesheet" crossorigin="anonymous" href="{api}">
</head><body><span class="base"></span><span class="v"></span><span id="t"></span></body></html>'''
for me,nxt in (('a','b'),('b','a')):
    open(f'www/c_{me}.html','w').write(CHILD.format(nxt=f'c_{nxt}.html',api=API,sw=SW))
CSS=f'''
@property --r {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}
@keyframes rd {{ from {{ --r: 0; }} to {{ --r: {MAXS}; }} }}
body {{ margin: 16px; font: 16px system-ui, sans-serif; timeline-scope: --s; }}
.slot {{ width: {SW}px; height: 4px; overflow: hidden; scroll-timeline: --s x; outline: 1px solid #888; }}
.slot object {{ display: block; width: {OBJ_W}px; height: 4px; border: 0; }}
.out {{ animation: rd 1s linear both; animation-timeline: --s; }}
.out::after {{ counter-reset: v calc(var(--r) - {SW}); content: "read " counter(v); }}
'''
BODY='<div class="slot"><object data="c_a.html#t"></object></div><p class="out"></p>'
open('www/p.html','w').write(f'<!doctype html><html><head><meta charset="utf-8"><title>html parent</title><style>{CSS}</style></head><body>{BODY}</body></html>')
open('www/p.xhtml','w').write(f'<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml"><head><title>xhtml parent</title><style>/*<![CDATA[*/{CSS}/*]]>*/</style></head><body>{BODY}</body></html>')
