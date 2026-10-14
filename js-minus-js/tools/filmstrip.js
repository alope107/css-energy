// filmstrip.js page.xhtml out.png [delayMs=1500] [durMs=1000] — what the user sees, frame by frame (harness only): a
// contact sheet of the compositor's frames plus a snap-back score (../../shared/js/filmstrip.js). Whole page; CLIP=sel crops.
const { profile } = require('../../shared/js/browser.js');
require('../../shared/js/filmstrip.js').main(profile('fontcpu'), process.argv.slice(2), { viewport: { width: 1300, height: 950 }, clip: null });
