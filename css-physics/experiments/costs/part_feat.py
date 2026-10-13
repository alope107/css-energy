REG = ("@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}"
       "@property --x{syntax:'<number>';inherits:true;initial-value:3}@property --y{syntax:'<number>';inherits:true;initial-value:3}"
       "@property --lo{syntax:'<number>';inherits:true;initial-value:1}@property --hi{syntax:'<number>';inherits:true;initial-value:5}"
       "@property --g0{syntax:'<integer>';inherits:true;initial-value:0}")
HEAD = "@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite}#b{--o:var(--t)}"
def emit(name, rules, c1extra=''):
    css = f"{REG}{HEAD}#c1{{container-name:pres o0;--g0:calc(var(--t) * 0);--x:calc(var(--t) * 0 + 3);--y:calc(var(--t) * 0 + 3);{c1extra}}}{rules}"
    open(name, 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=c1><div id=b></div></div></div>')
# range with var() bounds (true: 1 < 3 < 5)
emit('rv1.html', '@container pres style(--x > var(--lo)){#b{--o:777}}')
emit('rv2.html', '@container pres style(var(--lo) < --x < var(--hi)){#b{--o:777}}')
emit('rv3.html', '@container pres style(var(--lo) < --x < var(--hi)){#b{--o:777}}', '--lo:4')   # false: 4 < 3
# calc on the bound
emit('rv4.html', '@container pres style(--x > calc(var(--lo) + 1)){#b{--o:777}}')
emit('rv5.html', '@container pres style(--x > calc(var(--lo) + 3)){#b{--o:777}}')   # false
# comparing two props: abs difference via calc on one side
emit('rv6.html', '@container pres style(--x < calc(var(--y) + 0.5)) and style(--x > calc(var(--y) - 0.5)){#b{--o:777}}')
# unregistered ident equality
emit('id1.html', '@container pres style(--cell: c3){#b{--o:777}}', '--cell:c3')
emit('id2.html', '@container pres style(--cell: var(--cell2)){#b{--o:777}}', '--cell:c3;--cell2:c3')
emit('id3.html', '@container pres style(--cell: var(--cell2)){#b{--o:777}}', '--cell:c3;--cell2:c4')   # false
