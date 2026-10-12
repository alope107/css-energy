// browser.js — headless Chromium for the harness scripts (harness only: the pages themselves never run script).
// CHROME=/path/to/chrome overrides; otherwise the npm package @sparticuz/chromium (Linux x64, Chromium 153)
// is unpacked to /tmp and used. Exports a playwright-core `chromium` whose launch() fills in the executable.
const { chromium } = require('playwright-core');
async function executablePath() {
  if (process.env.CHROME) return process.env.CHROME;
  const m = await import('@sparticuz/chromium');
  return m.default.executablePath();
}
exports.executablePath = executablePath;
exports.chromium = { launch: async (opts = {}) => chromium.launch({ ...opts, executablePath: await executablePath() }) };
