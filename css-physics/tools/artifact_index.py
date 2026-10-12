"""python3 tools/artifact_index.py site/rigid3d.html site/index_artifact.html
Strip doctype/html/head/body tags from a built page: the claude.ai artifact host wraps the page in its own
document skeleton, so the published index must be a bare fragment (style + markup)."""
import re, sys
h = open(sys.argv[1]).read()
h = re.sub(r'(?is)<!doctype html>\s*', '', h)
for t in ('<html lang="en">', '</html>', '<head>', '</head>', '<body>', '</body>'):
    h = h.replace(t, '')
open(sys.argv[2], 'w').write(h)
