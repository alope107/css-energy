// node tools/filmstrip.js page.html out.png [delayMs=1500] [durMs=1000] : what the user sees, frame by frame (harness only)
// Contact sheet of the compositor's frames plus a snap-back score: see ../../shared/js/filmstrip.js. Crops to .arena (CLIP=sel).
require('../../shared/js/filmstrip.js').main(require('./lib/physics').profile,process.argv.slice(2),{viewport:{width:1000,height:900},clip:'.arena'});
