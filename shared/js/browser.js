// browser.js — headless Chromium for the harness scripts of both projects (harness only: the pages never run script).
//
//   const B = require('../../shared/js/browser.js').profile('physics');
//   const b = await B.launch();                       // profile flags; {args: [...]} replaces them, {extraArgs} appends
//   const p = await B.open(b, 'out/p16.html', {viewport: {width: 1000, height: 900}});
//
// Each project launches with its own flags, kept here as named profiles so that every number in its
// docs/BENCHMARKS.md stays comparable. --disable-gpu changes the raster and compositor path: don't merge the
// profiles without re-measuring both projects' baselines.
//   physics  css-physics/tools: npm `playwright`; CHROME=/path, else Playwright's own Chromium; --no-sandbox
//   fontcpu  js-minus-js: npm `playwright-core`; CHROME=/path, else @sparticuz/chromium (Linux x64);
//            --no-sandbox --no-proxy-server --disable-gpu
// The npm packages resolve from the running tool's own project, so each project keeps its own node_modules; a tool
// outside both projects (engine/) gets the profile's own project's (physics: css-physics, fontcpu: js-minus-js).
const path = require('path'), url = require('url');
const ROOT = path.join(__dirname, '..', '..');

function load(name, home) {
  const paths = [require.main && require.main.path, path.join(ROOT, home)].filter(Boolean);
  return require(require.resolve(name, { paths }));
}

const PROFILES = {
  physics: {
    pkg: 'playwright', home: 'css-physics',
    args: ['--no-sandbox'],
    executablePath: async () => process.env.CHROME || undefined,
  },
  fontcpu: {
    pkg: 'playwright-core', home: 'js-minus-js',
    args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu'],
    executablePath: async () => {
      if (process.env.CHROME) return process.env.CHROME;
      const m = await import(url.pathToFileURL(require.resolve('@sparticuz/chromium', { paths: [path.join(ROOT, 'js-minus-js')] })).href);
      return m.default.executablePath();
    },
  },
};

// file path (resolved against the cwd) -> file:// URL
const fileUrl = f => url.pathToFileURL(path.resolve(f)).href;

// space-separated extra flags from an environment variable (the tools' ARGS / FLAGS)
const envArgs = name => (process.env[name] ? process.env[name].split(' ') : []);

function profile(name) {
  const P = PROFILES[name];
  if (!P) throw new Error(`unknown browser profile ${name} (${Object.keys(PROFILES).join(', ')})`);
  let chromium;
  const pw = () => (chromium = chromium || load(P.pkg, P.home).chromium);
  return {
    name,
    args: P.args,
    executablePath: P.executablePath,
    get chromium() { return pw(); },
    async launch(opts = {}) {
      const { args, extraArgs = [], ...rest } = opts;
      return pw().launch({ ...rest, executablePath: await P.executablePath(), args: [...(args || P.args), ...extraArgs] });
    },
    async open(browser, file, pageOpts = {}, gotoOpts) {
      const p = await browser.newPage(pageOpts);
      await p.goto(fileUrl(file), gotoOpts);
      return p;
    },
  };
}

module.exports = { profile, fileUrl, envArgs, PROFILES };
