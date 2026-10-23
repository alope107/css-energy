#!/usr/bin/env python3
"""Face widgets: the 8-body engine with real HTML controls on the faces of its boxes.

  python3 experiments/widgets/build.py [out/widgets.html]      (from css-physics/)

Builds one 8-body engine (4 big boxes, 4 spheres, bodies.json) with src/build3d.py, then swaps each box face's
empty <i> for a face holding form controls, a video, a marquee, an editable text… Some of them drive the engine
through the inputs its own controls use (--kick, --rst, --gy, the camera's --yaw), with :has(). Still no script.
The TV's video (tv.webm, made by record.js) is copied next to the page.
"""
import os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, '..', 'shared', 'py'))
import csslabel as lbl
dst = sys.argv[1] if len(sys.argv) > 1 else 'out/widgets.html'

env = dict(os.environ, COUNTS='8', BODIES_JSON=os.path.join(HERE, 'bodies.json'), SCENE=os.environ.get('SCENE', 'desk'), SCENE_LIST='desk,drop,pile')
subprocess.run([sys.executable, os.path.join(ROOT, 'src', 'build3d.py'), dst], env=env, check=True)
html = open(dst).read()

# faces: 0 front (+z), 1 back, 2 right (+x), 3 left, 4 top, 5 bottom (box order as in bodies.json)
CHK = lambda id_, text, checked='': f'<label class="wg tg"><input type="checkbox" id="{id_}"{checked}><span>{text}</span></label>'
FACES = {
    0: [  # the TV
        '<div class="scr"><video class="wg" src="widgets-tv.webm" autoplay muted loop playsinline controls></video><i class="snow"></i></div>',
        '<div class="dvd"><i><b>DVD</b></i></div>',
        '<input class="wg vol" type="range" value="70" title="volume (does nothing)">',
        CHK('wg-pw', '⏻', ' checked') + CHK('wg-ch', 'CH'),
        '<marquee class="wg" scrollamount="3">BREAKING: box discovers gravity &middot; spheres refuse to comment &middot; '
        'film at 11 &middot; </marquee>',
        '<small>MADE IN CSS &middot; NO USER-SERVICEABLE JS INSIDE</small>',
    ],
    1: [  # the control cube
        '<button type="button" class="wg big" id="wg-shake">SHAKE</button>',
        CHK('wg-zg', 'zero g'),
        '<select class="wg" id="wg-cam"><option value="">camera…</option><option value="a">front</option>'
        '<option value="b">corner</option><option value="c">side</option><option value="o">orbit</option></select>',
        '<button type="button" class="wg" id="wg-reset">reset<br>everything</button>',
        CHK('wg-up', 'gravity ↑'),
        '<small>you found the bottom</small>' + CHK('wg-disco', 'disco'),
    ],
    2: [  # the form brick
        '<label class="word"><span>say the magic word</span><input class="wg" id="wg-word" required pattern="[Ff][Ll][Oo][Aa][Tt]" '
        'placeholder="(it’s “float”)" autocomplete="off" spellcheck="false"></label>',
        '<textarea class="wg" placeholder="leave a note on the back of the brick"></textarea>',
        '<details class="wg"><summary>secret</summary><p>the cube is lying about its bottom</p></details>',
        '<div class="mood">' + ''.join(f'<label class="wg"><input type="radio" name="wg-mood" id="wg-m{k}"{" checked" if k == 1 else ""}>{m}</label>'
                                       for k, m in enumerate(['calm', 'spicy', 'void'], 1)) + '</div>',
        CHK('wg-bot', 'I’m not a robot') + '<small class="ok">✓ verified: you are a box</small>',
        '<progress></progress><small>loading physics…</small>',
    ],
    3: [  # the book
        '<b>PHYSICS FOR BOXES</b>',
        '<small>vol. II &middot; 2nd edition</small>',
        '<input class="wg" placeholder="bookmark" spellcheck="false">',
        '<small>ISBN 0-000-CSS</small>',
        '<div class="wg terms" contenteditable="true" spellcheck="false"><h3>Terms of Gravity</h3>'
        '<p>1. Every body shall fall.</p><p>2. Bodies at rest shall sleep, and shall not be woken except by a neighbour, '
        'a shake, or a mouse.</p><p>3. No body shall pass through another body, or the floor, or the walls; the ceiling '
        'is a suggestion.</p><p>4. Spheres roll. Boxes tumble. This book is a box.</p><p>5. These terms are editable. '
        'Edits do not change physics.</p><p>6. You scrolled this far on a moving book.</p></div>',
        '<label><small>return by</small><input class="wg" type="date"></label><meter value="0.7"></meter>',
    ],
}
SPHERES = {4: '<button type="button" class="wg boop">boop</button>', 5: '<input type="checkbox" class="wg" id="wg-8" title="8-ball">'}


def faces(m):
    fs = FACES.get(int(m.group(2)))
    if fs is None:
        return m.group(0)
    return m.group(1) + ''.join(f'<div class="f f{k} wf">{c}</div>' for k, c in enumerate(fs)) + '</div>'


html, n = re.subn(r'(<div class="bd bx" id="\w*b(\d+)">)(?:<i class="f f\d"></i>){6}</div>', faces, html)
assert n == 4, n
html, n = re.subn(r'(<div class="bw" id="\w*w(\d+)"><i class="sh" id="\w*"></i>)<i class="disc"></i>',
                  lambda m: m.group(1) + (f'<i class="disc wd">{SPHERES[int(m.group(2))]}</i>' if int(m.group(2)) in SPHERES else '<i class="disc"></i>'), html)
assert n == 4, n

CSS = lbl.section('Face widgets', 'experiments/widgets: HTML controls on the box faces, and the ones wired to the engine') + '\n' + r"""
/* --- Pointer: widgets take the pointer (they paint above the grab grid), except while a body is being dragged --- */
.wg{pointer-events:auto}
#app:has(.gr:active) .wg{pointer-events:none}
/* (focusing a widget would scroll an overflow:hidden arena to show it) */
.arena{overflow:clip}
/* --- Faces --- */
.wf{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;padding:5px;overflow:hidden;
  font:10px/1.2 ui-monospace,Menlo,Consolas,monospace;color:#14161a;text-align:center}
.wf small{font-size:7px;opacity:.75}
.wf .tg{display:flex;align-items:center;gap:3px;cursor:pointer;background:rgb(255 255 255/.45);border-radius:3px;padding:2px 5px}
.wf input,.wf select,.wf textarea,.wf button{font:inherit;margin:0}
/* --- The TV --- */
.wf .scr{position:relative;width:100%;height:100%;background:#000;border-radius:4px;overflow:hidden}
.wf video{width:100%;height:100%;object-fit:cover;display:block}
.wf .snow{position:absolute;inset:0;display:none;pointer-events:none;
  background:repeating-radial-gradient(circle at 17% 32%,#fff 0 1px,#555 1px 2px,#bbb 2px 3px),#777;
  animation:wg-snow .12s steps(4) infinite}
@keyframes wg-snow{25%{background-position:3px 7px}50%{background-position:-5px 2px}75%{background-position:6px -4px}}
.bw:has(#wg-ch:checked) .snow{display:block}
.bw:has(#wg-pw:not(:checked)) .scr>*{visibility:hidden}
.bw:has(#wg-pw:not(:checked)) .scr video{display:none}
.wf .dvd{width:100%;height:100%;background:#000;border-radius:4px;overflow:hidden}
.wf .dvd i{display:block;animation:wg-dy 1.9s linear infinite alternate}
.wf .dvd b{display:block;width:34px;font:italic 900 12px/18px sans-serif;text-align:center;
  animation:wg-dx 2.9s linear infinite alternate,wg-dc 9.6s steps(1) infinite}
@keyframes wg-dx{from{translate:0 0}to{translate:116px 0}}
@keyframes wg-dy{from{translate:0 0}to{translate:0 72px}}
@keyframes wg-dc{0%{color:#ff3c7d}25%{color:#3cf0ff}50%{color:#b4ff3c}75%{color:#f2b134}}
.wf .vol{writing-mode:vertical-lr;direction:rtl;height:84px;width:16px}
.wf marquee{width:100%;color:#f2b134;background:#000;font-size:11px;line-height:18px;border-radius:2px}
.f4.wf:has(marquee),.f5.wf:has(small){padding:4px 6px}
/* --- The control cube --- */
.wf .big{width:72px;height:72px;border-radius:50%;border:3px solid #6b0f0f;background:radial-gradient(circle at 40% 35%,#ff6b5b,#c0141c);
  color:#fff;font-weight:700;cursor:pointer;box-shadow:0 4px 0 #6b0f0f}
.wf .big:active{translate:0 3px;box-shadow:0 1px 0 #6b0f0f}
.wf #wg-reset{padding:6px 8px;border-radius:4px;border:1px solid #14161a;background:#fff8;cursor:pointer}
.wf select{max-width:84px}
#app:has(#wg-shake:active){--kick:1}
#app:has(#wg-reset:active){--rst:1}
#app:has(#wg-zg:checked),#app:has(#wg-word:valid){--gy:0}
#app:has(#wg-up:checked){--gy:-1600}
#app:has(#wg-cam [value=a]:checked) .ptr{--yaw:0.25}
#app:has(#wg-cam [value=b]:checked) .ptr{--yaw:0.85}
#app:has(#wg-cam [value=c]:checked) .ptr{--yaw:1.45}
#app:has(#wg-cam [value=o]:checked) .ptr{animation:orbit 40s linear infinite,pmx linear both,pmy linear both;animation-timeline:auto,--pmx,--pmy}
#app:has(#wg-disco:checked) .bx{animation:wg-disco .48s steps(1) infinite}
@keyframes wg-disco{0%{--c:#ff3c7d}25%{--c:#3cf0ff}50%{--c:#b4ff3c}75%{--c:#a23cff}}
/* --- The form brick --- */
.wf .word{display:flex;flex-direction:column;gap:3px}
.wf .word input{width:112px;padding:2px 4px;border:1px solid #14161a;border-radius:3px}
.wf .word input:valid{background:#b4ff3c}
.wf textarea{width:100%;height:100%;resize:none;border:0;border-radius:3px;background:#fffd;padding:3px}
.wf details{background:rgb(255 255 255/.5);border-radius:3px;padding:2px 4px;cursor:pointer}
.wf details p{margin:3px 0 0;font-size:8px}
.f2.wf:has(details),.f3.wf:has(.mood){overflow:visible}
.wf .mood{display:flex;flex-direction:column;gap:1px;align-items:flex-start}
.wf .mood label{display:flex;gap:3px;align-items:center;cursor:pointer}
.bw:has(#wg-m2:checked){--c:#ff5a3c}
.bw:has(#wg-m3:checked){--c:#26232e}
.bw:has(#wg-m3:checked) .wf{color:#e8e6e1}
.wf .ok{display:none;color:#0a5d2a;opacity:1}
.wf:has(#wg-bot:checked) .ok{display:block}
.wf progress{width:110px}
/* --- The book --- */
.f0.wf:has(b),.f1.wf:has(small),.f2.wf:has(input),.f3.wf:has(small){padding:2px 6px}
.f2.wf input{width:96px;font-size:9px;padding:1px 3px;border:0;border-radius:2px}
.wf .terms{width:100%;height:100%;overflow:auto;text-align:left;background:#fffaf0;border-radius:3px;padding:4px 6px;font-size:8px;
  color:#14161a;outline:none;scrollbar-width:thin}
.wf .terms h3{font-size:10px;margin:0 0 3px}
.wf .terms p{margin:0 0 3px}
.wf input[type=date]{font-size:8px;width:96px}
/* --- Spheres --- */
.disc.wd{display:grid;place-items:center}
.wd .boop{font:700 9px ui-monospace,monospace;border:0;background:transparent;color:#fff;cursor:pointer;padding:4px}
.wd .boop::after{content:' •ᴗ•'}
.wd .boop:active::after{content:' >_<'}
.wd input{width:14px;height:14px;margin:0;cursor:pointer}
.bw:has(#wg-8:checked) .disc{background:radial-gradient(circle at 36% 30%,rgb(255 255 255/.5),rgb(255 255 255/0) 30%),
  radial-gradient(circle,#fff 0 7px,transparent 7.5px),#111}
"""
# the page's own text
html = html.replace('<title>rigid3d.css</title>', '<title>rigid3d.css: face widgets</title>')
html = html.replace('<h1>rigid3d<span>.css</span></h1>', '<h1>rigid3d<span>.css</span>: face widgets</h1>')
html = re.sub(r'<header>(.*?)<p>.*?</p>', r'<header>\1<p>The same CSS physics engine, with real HTML on the faces of its boxes: buttons, '
              'checkboxes, a select, text fields, a textarea, a video, a marquee, an editable book. Some of them push the '
              'engine back (shake, reset, gravity, camera, the magic word). Still no script. '
              '<a href="./">&larr; the plain engine</a></p>', html, count=1, flags=re.S)
html = re.sub(r'<div class="grp counts">.*?</div>', '', html, count=1, flags=re.S)
html = html.replace('<span class="m">Drag any body with the mouse.', '<span class="m">Drag a body by its edges or an empty spot; the widgets '
                    'take clicks. Find the controls on every side of the cube.')
html = html.replace('</style>', CSS + '</style>', 1)
lbl.check(html, dst)
open(dst, 'w').write(html)
tv = os.path.join(HERE, 'tv.webm')
if os.path.exists(tv):
    shutil.copy(tv, os.path.join(os.path.dirname(os.path.abspath(dst)), 'widgets-tv.webm'))
print(f'{dst}: {len(html) / 1e6:.1f} MB', file=sys.stderr)
