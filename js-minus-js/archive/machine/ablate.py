import re, sys
s = open(sys.argv[1]).read(); D = sys.argv[2]
def w(name, t): open(f'{D}/ab_{name}.html', 'w').write(t)
w('full', s)
w('noW', re.sub(r'@container style\(--wa[A-D]: \d+\) \{[^\n]*\n', '', s))
w('noMux', re.sub(r'\.rp \{ --sR: if\([^\n]*\n', '.rp { --sR: --c0; }\n', s))
w('noCells', re.sub(r'<div class="mem">.*?</div>\n<div class="con">', '<div class="mem"></div>\n<div class="con">', s, flags=re.S))
w('noState', re.sub(r'<div id="state">.*?</div>\n', '<div id="state"></div>\n', s, count=1, flags=re.S))
w('noCon', re.sub(r'<div class="oc oc\d+"><b></b></div>\n?', '', s))
