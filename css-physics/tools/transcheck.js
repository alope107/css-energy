// node tools/transcheck.js page.html [ms=5000] [delayMs=1000] : continuity check for transform transitions (harness only)
// Exits 1 on a restart off the running value; --selftest-ok / --selftest-bad check the checker. See ../../shared/js/transcheck.js.
require('../../shared/js/transcheck.js').main(require('./lib/physics').profile,process.argv.slice(2),{viewport:{width:1000,height:900}});
