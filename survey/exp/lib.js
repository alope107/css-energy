// tiny harness for the survey's probes: launch the image's Chromium with the css-physics profile's flags
const path = require('path');
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
async function launch(args = []) {
  return chromium.launch({ executablePath: process.env.CHROME || '/usr/local/bin/chromium', args: ['--no-sandbox', ...args] });
}
module.exports = { launch, path };
