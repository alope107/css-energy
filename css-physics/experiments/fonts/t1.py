import vf
A = {'AAAA': vf.POS}; B = {'BBBB': vf.POS}; AB = {'AAAA': vf.POS, 'BBBB': vf.POS}
font = vf.build(['AAAA', 'BBBB'], [(0x30, 'zero', 4096, [(A, 8192)]), (0x6C34, 'water', 4096, [(AB, 8192)]), (0x78, 'x', 4096, []), (0x41,'A',4096,[(B,4096)])],
                mvar={'xhgt': [(B, 4000)], 'cpht': [(A, 2000)]})
open('t1.ttf','wb').write(font)
css = f"@font-face{{font-family:C;src:url(data:font/ttf;base64,{vf.b64(font)})}}"
cases = [(0,0),(16384,0),(8192,8192),(16384,16384),(4096,12288)]
divs = ''.join(f'<div class=t style="font-variation-settings:\'AAAA\' {a},\'BBBB\' {b}"><span>0</span><span>水</span><span>A</span></div>' for a,b in cases)
open('t1.html','w').write(f'''<!doctype html><style>{css}
@property --ch{{syntax:'<length>';inherits:false;initial-value:0px}}
@property --ic{{syntax:'<length>';inherits:false;initial-value:0px}}
@property --ex{{syntax:'<length>';inherits:false;initial-value:0px}}
@property --cap{{syntax:'<length>';inherits:false;initial-value:0px}}
.t{{font-family:C;font-size:1024px;--ch:1ch;--ic:1ic;--ex:1ex;--cap:1cap;white-space:nowrap;line-height:1}}
</style>{divs}''')
