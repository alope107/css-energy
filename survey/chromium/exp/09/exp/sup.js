const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const conds = {
  ident_anchor: 'anchor-name: ident(--a 3)', ident_str: 'anchor-name: ident("--a" 3)', inherit_fn: 'width: inherit(--x)', random_fn: 'width: random(0px, 10px)',
  event_trigger: 'event-trigger: --t click()', timeline_scope_all: 'timeline-scope: all', frame_sizing: 'frame-sizing: content-height',
  preserve_spaces: 'white-space-collapse: preserve-spaces', grid_lanes: 'display: grid-lanes', text_fit: 'text-fit: grow', snap_pair: 'scroll-snap-type: pair mandatory',
  overflow_scroll_clip: 'overflow: scroll clip', container_progress: 'width: calc(container-progress(width, 0px, 100px) * 1px)', first_valid: 'width: first-valid(10px)',
  if_fn: 'width: if(style(--x: 1): 1px; else: 2px)', sibling_index: 'width: calc(sibling-index() * 1px)', progress_fn: 'width: calc(progress(5, 0, 10) * 1px)',
  line_clamp: 'line-clamp: 2', animation_trigger: 'animation-trigger: --t play-forwards', timeline_trigger: 'timeline-trigger: --t view()',
};
(async () => {
  for (const f of ['', 'CSSIdentFunction,CSSInheritFunction,CSSRandomFunction,EventTrigger,CSSTimelineScopeAll,ResponsiveIframes,CSSGridLanesLayout,CSSContainerProgressNotation,CSSLineClamp']) {
    const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...(f ? ['--enable-blink-features=' + f] : [])] });
    const p = await b.newPage(); await p.setContent('<!doctype html><body>');
    const r = await p.evaluate(c => Object.fromEntries(Object.entries(c).map(([k, v]) => [k, CSS.supports(v)])), conds);
    console.log(f ? 'flags' : 'none ', Object.entries(r).map(([k, v]) => `${k}=${v ? 1 : 0}`).join(' '));
    await b.close();
  }
})();
