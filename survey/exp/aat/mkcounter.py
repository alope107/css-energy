#!/usr/bin/env python3
"""mkcounter.py MODE M out.ttf — a font whose shaping increments a binary counter M times.

Text: a run of '0'/'1' digits, most significant first. Each increment is one pass over the run from the right:
flip trailing 1s to 0 and the first 0 to 1. Advances: zero = 100 units, one = 200, so the shaped width tells the
popcount and the counter can be checked exactly.

MODE morx: one ContextualMorph subtable per increment (ReversedLayoutOrder, a 2-state machine: carry / done).
MODE gsub: one ReverseChainSingleSubst lookup per increment needs lookahead of unbounded length, which GSUB can't
           express in one rule, so the GSUB version uses the CPU's technique: a carry glyph that ripples leftward
           through a ReverseChainSingleSubst (rsub) — 'zero' before a carried glyph becomes 'one', 'one' before a
           carried glyph becomes 'zeroC' (carried). Each increment: MAP last digit to its carried form, then one rsub,
           then MAP carried forms back. Three lookups per increment, referenced from the LookupList like cpugen's
           stages (fontTools feaLib, one lookup set per increment).
"""
import sys
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

MODE, M, OUT = sys.argv[1], int(sys.argv[2]), sys.argv[3]
order = ['.notdef', 'zero', 'one', 'zeroC', 'oneC', 'endm']
fb = FontBuilder(1000, isTTF=True)
fb.setupGlyphOrder(order)
fb.setupCharacterMap({ord('0'): 'zero', ord('1'): 'one', ord('|'): 'endm'})
empty = TTGlyphPen(None).glyph()
fb.setupGlyf({g: empty for g in order})
adv = {'.notdef': 100, 'zero': 100, 'one': 200, 'zeroC': 100, 'oneC': 200, 'endm': 0}
fb.setupHorizontalMetrics({g: (adv[g], 0) for g in order})
fb.setupHorizontalHeader(ascent=800, descent=-200)
fb.setupNameTable({'familyName': f'Ctr{MODE}', 'styleName': 'Regular'})
fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
fb.setupPost()
f = fb.font
gid = {g: i for i, g in enumerate(order)}

if MODE == 'morx':
    def act(new, cur=0xFFFF):
        a = ot.ContextualMorphAction(); a.NewState = new; a.CurrentIndex = cur; return a
    def subtable():
        st = ot.AATStateTable()
        # classes: 0 EOT, 1 OOB, 2 deleted, 3 EOL, 4 zero, 5 one
        st.GlyphClasses = {'zero': 4, 'one': 5}
        carry = ot.AATState(); done = ot.AATState()
        carry.Transitions = {0: act(0), 1: act(1), 2: act(1), 3: act(1), 4: act(2, 0), 5: act(1, 1)}
        done.Transitions = {c: act(2) for c in range(6)}
        st.States = [carry, carry, done]          # 0 = start of text, 1 = start of line: both "carry"
        st.PerGlyphLookups = [{'zero': 'one'}, {'one': 'zero'}]
        cm = ot.ContextualMorph(); cm.StateTable = st
        s = ot.MorxSubtable(); s.TextDirection = 'Horizontal'; s.ProcessingOrder = 'ReversedLayoutOrder'
        s.Reserved = 0; s.MorphType = 1; s.SubFeatureFlags = 1; s.SubStruct = cm
        return s
    ch = ot.MorxChain(); ch.DefaultFlags = 1; ch.MorphFeature = []; ch.MorphFeatureCount = 0
    ch.MorphSubtable = [subtable() for _ in range(M)]; ch.MorphSubtableCount = M
    t = newTable('morx'); t.table = ot.morx(); t.table.Version = 2; t.table.Reserved = 0
    t.table.MorphChain = [ch]; t.table.MorphChainCount = 1
    f['morx'] = t
else:
    # fea can't alias lookups; emit M copies by name
    body = []
    for k in range(M):
        body += [f"lookup L{k} {{ sub zero' endm by zeroC; sub one' endm by oneC; }} L{k};",
                 f"lookup R{k} {{ rsub zero' oneC by zeroC; rsub one' oneC by oneC; }} R{k};",
                 f"lookup F{k} {{ sub zeroC by one; sub oneC by zero; }} F{k};"]
    # XC = digit X with a carry coming in. A one with carry-in passes it on (rsub: one before oneC -> oneC), a zero
    # absorbs it (zero before oneC -> zeroC). FIX: oneC -> zero, zeroC -> one.
    body.append('feature calt { ' + ' '.join(f'lookup L{k}; lookup R{k}; lookup F{k};' for k in range(M)) + ' } calt;')
    addOpenTypeFeaturesFromString(f, '\n'.join(body))
f.save(OUT)
print(OUT, MODE, M)
