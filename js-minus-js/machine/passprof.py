import json, sys, statistics
ev = json.load(open(sys.argv[1]))['traceEvents']
ul = [e for e in ev if e.get('name') == 'LocalFrameView::UpdateStyleAndLayout' and e.get('ph') == 'X' and e['dur'] > 1000]
sh = [e for e in ev if e.get('name') == 'InlineNode::ShapeTextIncludingFirstLine' and e.get('ph') == 'X' and e['dur'] > 2000]
cm = sorted(e['ts'] for e in ev if e.get('name') == 'Commit' and e.get('ph') == 'X')
fr = []
for a, b in zip(cm, cm[1:]):
    p = [e['dur'] / 1000 for e in ul if a <= e['ts'] < b]; s = [e['dur'] / 1000 for e in sh if a <= e['ts'] < b]
    if p: fr.append((len(p), sum(p), sum(s), (b - a) / 1000))
print(f"{sys.argv[2] if len(sys.argv) > 2 else ''} frames {len(fr)}: passes/frame {statistics.mean(f[0] for f in fr):.2f}, style+layout ms/frame {statistics.median(f[1] for f in fr):.0f}, "
      f"shaping ms/frame {statistics.median(f[2] for f in fr):.0f}, frame ms {statistics.median(f[3] for f in fr):.0f}")
