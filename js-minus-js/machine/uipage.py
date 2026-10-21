"""uipage.py — the editor page's parts that don't depend on the CPU (taken out of the font CPU's page generator for
machine/gen_css.py): layout, the Run / Edit button, the compile status line, Edit clearing RAM, the ccgo gate."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'py'))
import csslabel as lbl

def static(COLS, ROWS, UIL, UIP, WOFF, EDS=1):
    """the editor page's hand-written CSS (EDS: the editors, #ed and the samples the picker shows)"""
    TOPS = ROWS * 20 + 48
    return f"""
  {lbl.section('Editor page', 'hand-written: the layout, the Run button and the compile status line')}
  {lbl.group('Layout and notes')}
  :root {{ --paper: #f3f5f7; --sheet: #fff; --ink: #17212b; --muted: #5b6875; --rule: #c9d1d9; --accent: #2456c9; }}
  body {{ background: var(--paper); color: var(--ink); }}
  #app {{ position: relative; overflow: hidden; margin: 0 0 0 {COLS * 11 + 72}px; padding: 20px 24px 48px 0; width: {UIP * 10 + 60}px; display: grid; gap: 1rem; align-content: start;
    contain: strict; height: {UIL * 24 + 640}px;   /* the scan relayouts stay inside #app (the CPU's fixed readers are not touched) */
    will-change: transform; }}   /* its own compositor layer: the CPU's per-pass paint invalidations then don't re-record the editor and notes */
  #app h1 {{ font-size: 1.15rem; margin: 0; }}
  .lede {{ margin: .3rem 0 0; color: var(--muted); }}
  .bar {{ display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }}
  .label {{ font: 600 .72rem/1 ui-monospace, monospace; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
  .scanpos {{ font: .8rem ui-monospace, monospace; color: var(--muted); }}
  .frame {{ background: var(--sheet); border: 1px solid var(--rule); border-radius: 6px; overflow: auto; }}
  .frame:focus-within {{ border-color: var(--accent); }}
  .ed {{ background: linear-gradient(to right, transparent {14 + UIP * 10}px, var(--rule) 0, var(--rule) {15 + UIP * 10}px, transparent 0); }}
  {lbl.group('Sample picker', 'radio buttons beside #run (#pk<i>) pick the editor that shows; each keeps its own edits')}
  .pkr {{ position: absolute; left: 0; top: 0; width: 1px; height: 1px; opacity: 0; margin: 0; }}
  .picker {{ display: flex; flex-wrap: wrap; gap: .4rem; }}
  .picker label {{ cursor: pointer; user-select: none; font: 500 .8rem/1 system-ui, sans-serif; padding: .38rem .72rem; border-radius: 999px;
    border: 1px solid var(--rule); background: var(--sheet); color: var(--muted); transition: background .15s, color .15s, border-color .15s; }}
  .picker label::before {{ content: attr(data-icon); margin-right: .35em; }}
  .picker label:hover {{ border-color: var(--accent); color: var(--ink); }}
  .ed {{ display: none; }}
  {" ".join(f"#pk{e}:checked ~ #app .ed{e}," for e in range(EDS))[:-1]} {{ display: block; }}
  {" ".join(f"#pk{e}:checked ~ #app label[for=pk{e}]," for e in range(EDS))[:-1]} {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  {" ".join(f"#pk{e}:focus-visible ~ #app label[for=pk{e}]," for e in range(EDS))[:-1]} {{ outline: 2px solid var(--ink); outline-offset: 2px; }}
  #run:checked ~ #app .picker {{ opacity: .45; pointer-events: none; }}   /* the scan reads the editor that shows: no switching while it runs */
  #run:checked ~ .pkr {{ visibility: hidden; }}
  {lbl.group('Run / Edit button')}
  .runbtn {{ position: relative; display: inline-block; cursor: pointer; font: 600 .9rem/1 system-ui, sans-serif; color: #fff; background: var(--accent);
    border-radius: 6px; padding: .55rem 1rem; user-select: none; }}
  .runcb {{ position: absolute; left: 0; top: 0; width: 1px; height: 1px; opacity: 0; margin: 0; }}
  #run:focus-visible ~ #app .runbtn {{ outline: 2px solid var(--ink); outline-offset: 2px; }}
  .runbtn span::before {{ content: "\\25B6  Run"; }}
  #run:checked ~ #app .runbtn {{ background: #5b6875; }}
  #run:checked ~ #app .runbtn span::before {{ content: "\\270E  Edit"; }}
  .limit, .nested {{ display: none; margin: 0; font-size: .85rem; color: var(--muted); }}
  .nested {{ color: #b00; }}
  .notes {{ color: var(--muted); font-size: .9rem; display: grid; gap: .5rem; }}
  .notes p {{ margin: 0; }}
  .notes code {{ font: .82rem ui-monospace, monospace; color: var(--ink); }}
  {lbl.group('Machine status')}
  .head {{ left: 16px; top: {TOPS + 56}px; width: {COLS * 11 + 40}px; }}
  .head .status {{ display: grid; gap: .1rem; }}
  {lbl.group('Compile status: the compiler\'s result, read from its anchors')}
  .cst, .cst2 {{ position: fixed; left: 16px; height: 1px; visibility: hidden; }}
  .cst {{ top: {TOPS}px; container-type: inline-size; width: anchor-size(--ccinfo width, 0px); }}
  .cst2 {{ top: {TOPS + 36}px; width: anchor-size(--cctoo width, 0px); overflow: hidden; }}
  .cst2 > b {{ visibility: visible; white-space: nowrap; font: 12px ui-monospace, monospace; color: #b00; }}
  .cstv {{ position: absolute; left: 0; top: 0; width: {COLS * 11 + 40}px; visibility: visible; font: 13px/1.35 ui-monospace, monospace;
    --csi: round(100cqi / 1px); --csd: mod(var(--csi), 2); --cse: mod(round(down, var(--csi) / 2), 512); --csn: round(down, var(--csi) / 1024);
    counter-set: csn var(--csn) cse var(--cse); }}
  .cstv::before {{ content: "edit the program, then Run"; color: var(--muted); }}
  #run:checked ~ .cst .cstv::before {{ color: var(--ink);
    content: if(style(--csd: 0): "compiling\\2026"; style(--cse: 0): "compiled: " counter(csn) " words";
      style(--cse: 4): "error: undefined variable"; style(--cse: 5): "error: undefined variable"; style(--cse: 6): "error: undefined variable";
      style(--cse: 7): "error: undefined variable"; style(--cse: 20): "error: too many labels"; style(--cse: 21): "error: blocks nested too deeply";
      style(--cse: 22): "error: expression too deep"; style(--cse: 23): "error: too many functions"; style(--cse: 24): "error: too many variables";
      style(--cse: 41): "error: nested function"; style(--cse: 61): "error: statement too long"; style(--cse: 62): "error: program too long";
      style(--cse: 40): "error: missing }}"; style(--cse: 54): "error: unexpected }}"; style(--cse: 56): "error: break outside a loop";
      style(--cse: 57): "error: return outside a function"; style(--cse: 60): "error: undefined function";
      style(--cse: 73): "error: case outside a switch"; style(--cse: 75): "error: two defaults in a switch";
      style(--cse: 76): "error: wrong number of arguments";
      style(--cse: 25): "error: too many globals"; style(--cse: 26): "error: too much string data"; style(--cse: 68): "error: too many distinct strings";
      style(--cse: 77): "error: wrong number of arguments to a method"; style(--cse: 78): "error: redeclared in this scope";
      else: "syntax error (" counter(cse) ")"); }}
"""

def props(WOFF, clear='.mem .cell'):
    """Run / Edit and the compile status properties. clear: the RAM leaves Edit zeroes (a selector after #run ~)"""
    return [lbl.section('Run / Edit', 'the Run checkbox starts the scan and the CPU; Edit clears RAM'),
                '@property --run { syntax: "<integer>"; inherits: true; initial-value: 0; }',
                '#run:checked ~ #clkw { --run: 1; }',
                f'#run:not(:checked) ~ {clear} {{ content-visibility: visible; width: {WOFF}px; }}   /* Edit: RAM back to zeros */',
                '#clkw > .oc { display: if(style(--ccgo: 1): block; else: none); }',
                # no CPU at all until Run's final scan sweep is done (its registers restart from zero on every Run)
                '#clkw { display: contents; animation: kccgo auto linear both; animation-timeline: --rbrdT; } #clk { display: if(style(--ccgo: 1): block; else: none); }'] + \
               [lbl.group('Compile status values')] + \
               [f'@property --{n} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}' for n in ('csi', 'csd', 'cse', 'csn')]
