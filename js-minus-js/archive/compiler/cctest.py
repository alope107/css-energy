# standalone page: compile chain only; harness reads overlays
import sys
pre = sys.argv[1]
css = open(pre + '.css').read(); body = open(pre + '.html').read()
open(pre + '_test.html', 'w').write(f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>')
