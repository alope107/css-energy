// browser.js — headless Chromium for the harness scripts (harness only: the pages themselves never run script).
// CHROME=/path/to/chrome overrides; otherwise the npm package @sparticuz/chromium (Linux x64, Chromium 153) is unpacked
// to /tmp and used. The launcher is shared with css-physics: ../../shared/js/browser.js, profile `fontcpu`.
//   const { launch, open, fileUrl, envArgs } = require('../tools/browser.js');
//   const b = await launch();                          // --no-sandbox --no-proxy-server --disable-gpu
//   const b = await launch({ extraArgs: envArgs('FLAGS') });   // … plus the FLAGS environment variable
//   const b = await launch({ args: ['--no-sandbox'] });        // exactly these flags
// Timing harnesses call b.newPage() themselves and start their clock before p.goto(fileUrl(page)), so load time
// excludes opening the tab. `chromium.launch(opts)` (the old interface) fills in the executable only.
const { profile, fileUrl, envArgs } = require('../../shared/js/browser.js');
const B = profile('fontcpu');
exports.executablePath = B.executablePath;
exports.chromium = { launch: async (opts = {}) => B.chromium.launch({ ...opts, executablePath: await B.executablePath() }) };
Object.assign(exports, { launch: B.launch, open: B.open, fileUrl, envArgs });
