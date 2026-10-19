"""Probe pages for chapter 02. Writes into argv[1]."""
import os, sys
out = sys.argv[1]
def w(name, css, html):
    open(os.path.join(out, name), 'w').write(f'<!doctype html><style>{css}</style>{html}')
REG = ("@property --t{syntax:'<number>';inherits:true;initial-value:0}"
       "@property --x{syntax:'<number>';inherits:true;initial-value:0}"
       "@property --k{syntax:'<number>';inherits:false;initial-value:0}"
       "@property --o{syntax:'<number>';inherits:false;initial-value:0}"
       "@property --g{syntax:'<integer>';inherits:false;initial-value:0}")
ANIM = "@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite;--x:calc(var(--t) * 2)}"
# E1: propagation of a changing inherited property down a D-deep chain
D = 300
chain = lambda cls='l': ''.join(f'<div class={cls} id=l{d}>' for d in range(1, D + 1)) + '</div>' * D
w('e1a_decl.html', REG + ANIM + ".l{--k:1}", '<div id=a>' + chain() + '</div>')
w('e1b_redecl.html', REG + ANIM + ".l{--k:1}#l1{--x:0;--t:0}", '<div id=a>' + chain() + '</div>')
w('e1c_empty.html', REG + ANIM, '<div id=a>' + chain() + '</div>')
w('e1d_cvhidden.html', REG + ANIM + ".l{--k:1}#l1{content-visibility:hidden}", '<div id=a>' + chain() + '</div>')
w('e1e_redecl_x_only.html', REG + ANIM + ".l{--k:1}#l1{--x:0}", '<div id=a>' + chain() + '</div>')
w('e1f_ref.html', REG + ANIM + ".l{--o:var(--x)}", '<div id=a>' + chain() + '</div>')
# E2: R rules gated by a present name + false style(); one block each vs one shared block
R = 5000
head = REG + "@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite}#c1{container-name:pres q1;--g:calc(var(--t) * 0)}#b{--o:var(--t)}"
html = '<div id=a><div id=c1><div id=b></div></div></div>'
w('e2_base.html', head, html)
w('e2_sep.html', head + ''.join(f'@container pres style(--g: 7){{#b{{--o:calc(var(--t) * {k})}}}}' for k in range(R)), html)
w('e2_shared.html', head + '@container pres style(--g: 7){' + ''.join(f'#b{{--o:calc(var(--t) * {k})}}' for k in range(R)) + '}', html)
w('e2_nameonly.html', head + ''.join(f'@container zz{{#b{{--o:calc(var(--t) * {k})}}}}' for k in range(R)), html)
# E3: rejected rules (one absent name, cached after the first walk) with 1 vs 60 declarations
decls = lambda k, n: ''.join(f'--o:calc(var(--t) * {k + j});' for j in range(n))
w('e3_1.html', head + ''.join(f'@container zz{{#b{{{decls(k, 1)}}}}}' for k in range(R)), html)
w('e3_60.html', head + ''.join(f'@container zz{{#b{{{decls(k, 60)}}}}}' for k in range(R)), html)
# E5: MPC for identical siblings: 1000 siblings x 50 registered declarations
NS, ND = 1000, 50
reg5 = REG + ''.join(f"@property --o{j}{{syntax:'<number>';inherits:false;initial-value:0}}" for j in range(ND))
body5 = ''.join(f'--o{j}:calc(var(--t) * {j});' for j in range(ND))
sibs = '<div id=a>' + '<div class=s></div>' * NS + '</div>'
base5 = reg5 + "@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite}"
w('e5a_plain.html', base5 + f'.s{{{body5}}}', sibs)
w('e5b_anchorname.html', base5 + f'.s{{{body5}anchor-name:--q}}', sibs)
w('e5c_containername.html', base5 + f'.s{{{body5}container-name:foo}}', sibs)
w('e5d_cq.html', base5 + f'#a{{container-name:pa}}@container pa style(--t){{.s{{{body5}}}}}', sibs)
# E7: an animated element applies its whole cascade twice (base + animated)
N7 = 8000
reg7 = REG + ''.join(f"@property --p{j}{{syntax:'<number>';inherits:false;initial-value:0}}" for j in range(N7))
body7 = ''.join(f'--p{j}:calc(var(--t) * {j});' for j in range(N7))
kf = "@keyframes t{from{--t:0}to{--t:1000}}@keyframes op{from{opacity:0}to{opacity:1}}"
w('e7a_parent_anim.html', reg7 + kf + f"#a{{animation:t 1000s linear infinite}}#b{{{body7}}}", '<div id=a><div id=b></div></div>')
w('e7b_self_anim.html', reg7 + kf + f"#b{{animation:t 1000s linear infinite;{body7}}}", '<div id=a><div id=b></div></div>')
w('e7c_self_opacity.html', reg7 + kf + f"#a{{animation:t 1000s linear infinite}}#b{{animation:op 1000s linear infinite;{body7}}}", '<div id=a><div id=b></div></div>')
w('e7d_self_anim_child.html', reg7 + kf + f"#b{{animation:t 1000s linear infinite}}#c{{{body7}}}", '<div id=a><div id=b><div id=c></div></div></div>')
w('e7e_self_anim_uncacheable.html', reg7 + kf + f"#b{{animation:t 1000s linear infinite;anchor-name:--q;{body7}}}", '<div id=a><div id=b></div></div>')
w('e7f_parent_anim_uncacheable.html', reg7 + kf + f"#a{{animation:t 1000s linear infinite}}#b{{anchor-name:--q;{body7}}}", '<div id=a><div id=b></div></div>')
# E8: stale ContainerQueryEvaluator results: name present for the first 0.3 s, then absent
reg8 = REG + "@property --on{syntax:'<integer>';inherits:false;initial-value:0}"
head8 = reg8 + ("@keyframes t{from{--t:0}to{--t:1000}}@keyframes on{from{--on:1}to{--on:0}}"
        "#a{animation:t 1000s linear infinite}#b{--o:var(--t)}")
rules8 = ''.join(f'@container pres style(--g: 7){{#b{{--o:calc(var(--t) * {k})}}}}' for k in range(R))
w('e8_stale.html', head8 + "#c1{animation:on 0.3s step-end forwards;container-name:if(style(--on: 1): pres; else: none);--g:calc(var(--t) * 0)}" + rules8, html)
w('e8_never.html', head8 + "#c1{container-name:none;--g:calc(var(--t) * 0)}" + rules8, html)
w('e8_always.html', head8 + "#c1{container-name:pres;--g:calc(var(--t) * 0)}" + rules8, html)
w('e8_ifon.html', head8.replace('@keyframes on{from{--on:1}to{--on:0}}', '@keyframes on{from{--on:1}to{--on:1}}') + "#c1{animation:on 0.3s step-end forwards;container-name:if(style(--on: 1): pres; else: none);--g:calc(var(--t) * 0)}" + rules8, html)
w('e8_stale_late.html', head8.replace('@keyframes on{from{--on:1}to{--on:0}}', '@keyframes on{from{--on:1}to{--on:0}}') + "#c1{animation:on 1.2s step-end forwards;container-name:if(style(--on: 1): pres; else: none);--g:calc(var(--t) * 0)}" + rules8, html)
reg8b = REG + "@property --on{syntax:'<integer>';inherits:true;initial-value:0}"
def e8b(name, kf_on, dur):
    css = (reg8b + "@keyframes t{from{--t:0}to{--t:1000}}" + kf_on +
           f"#a{{animation:t 1000s linear infinite,on {dur} step-end forwards}}#b{{--o:var(--t)}}"
           "#c1{container-name:if(style(--on: 1): pres; else: none);--g:calc(var(--t) * 0)}" + rules8)
    w(name, css, html)
e8b('e8b_ifon.html', '@keyframes on{from{--on:1}to{--on:1}}', '0.3s')
e8b('e8b_stale.html', '@keyframes on{from{--on:1}to{--on:0}}', '0.3s')
e8b('e8b_never.html', '@keyframes on{from{--on:0}to{--on:0}}', '0.3s')
reg8c = reg8b + "@property --on2{syntax:'<integer>';inherits:false;initial-value:0}"
def e8c(name, kf_on, dur, launder=True):
    cn = "--on2:var(--on);container-name:if(style(--on2: 1): pres; else: none);" if launder else "container-name:if(style(--on: 1): pres; else: none);"
    css = (reg8c + "@keyframes t{from{--t:0}to{--t:1000}}" + kf_on +
           f"#a{{animation:t 1000s linear infinite,on {dur} step-end forwards}}#b{{--o:var(--t)}}"
           "#c1{" + cn + "--g:calc(var(--t) * 0)}" + rules8)
    w(name, css, html)
e8c('e8c_ifon.html', '@keyframes on{from{--on:1}to{--on:1}}', '0.3s')
e8c('e8c_stale.html', '@keyframes on{from{--on:1}to{--on:0}}', '0.3s')
e8c('e8c_never.html', '@keyframes on{from{--on:0}to{--on:0}}', '0.3s')
reg8d = reg8c + "@property --fl{syntax:'<integer>';inherits:true;initial-value:0}"
css8d = (reg8d + "@keyframes t{from{--t:0}to{--t:1000}}@keyframes on{from{--on:1}to{--on:0}}"
         "@keyframes fl{0%{--fl:0}40%{--fl:7}60%{--fl:0}100%{--fl:0}}"
         "#a{animation:t 1000s linear infinite,on 0.3s step-end forwards,fl 1s step-end forwards}#b{--o:var(--t)}"
         "#c1{--on2:var(--on);container-name:if(style(--on2: 1): pres; else: none);--g:calc(var(--t) * 0 + var(--fl))}" + rules8)
w('e8d_stale_flip.html', css8d, html)
# E9: if() cost per branch tried: 1,000 registered declarations, 32-branch if(), match first vs last; plus registered vs unregistered tested property
N9 = 1000
reg9 = REG + "@property --s{syntax:'<integer>';inherits:true;initial-value:0}" + ''.join(f"@property --q{j}{{syntax:'<number>';inherits:false;initial-value:0}}" for j in range(N9))
def ifexpr(prop, hit):
    br = ''.join(f'style({prop}: {b}): calc(var(--t) * {b});' for b in range(32))
    return f'if({br} else: 0)'
def e9(name, prop, s_val, extra=''):
    body = ''.join(f'--q{j}:{ifexpr(prop, s_val)};' for j in range(N9))
    css = reg9 + extra + f"@keyframes t{{from{{--t:0}}to{{--t:1000}}}}#a{{animation:t 1000s linear infinite;--s:{s_val};--u:{s_val}}}#b{{{body}}}"
    w(name, css, '<div id=a><div id=b></div></div>')
e9('e9_first.html', '--s', 0)
e9('e9_last.html', '--s', 31)
e9('e9_none.html', '--s', 99)
e9('e9_first_unreg.html', '--u', 0)
e9('e9_last_unreg.html', '--u', 31)
body0 = ''.join(f'--q{j}:calc(var(--t) * {j});' for j in range(N9))
w('e9_noif.html', reg9 + f"@keyframes t{{from{{--t:0}}to{{--t:1000}}}}#a{{animation:t 1000s linear infinite}}#b{{{body0}}}", '<div id=a><div id=b></div></div>')
# E10: same 5,000 separate gates, but the container's custom properties never change; only the child animates itself
head10 = REG + "@keyframes t{from{--t:0}to{--t:1000}}#c1{container-name:pres q1;--g:0}#b{animation:t 1000s linear infinite;--o:var(--t)}"
w('e10_stablecont.html', head10 + ''.join(f'@container pres style(--g: 7){{#b{{--o:calc(var(--t) * {k})}}}}' for k in range(R)), html)
w('e10_base.html', head10, html)
