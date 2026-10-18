// node probe.js 'js expr' page.html ... — evaluate an expression on each page after load
const { launch } = require('./lib.js'); const url = require('url'), path = require('path');
(async () => {
  const [expr, ...pages] = process.argv.slice(2); const b = await launch();
  for (const f of pages) { const p = await b.newPage(); await p.goto(url.pathToFileURL(path.resolve(f)).href); await p.waitForTimeout(+(process.env.WAIT || 300));
    console.log(path.basename(f).padEnd(22), JSON.stringify(await p.evaluate(s => eval(s), expr))); await p.close(); }
  await b.close();
})();
