#!/usr/bin/env node
// Tiny CDP client for Chrome on Android (via `adb forward tcp:9222 localabstract:chrome_devtools_remote`).
// usage:
//   node cdp.js list                         -> list page targets
//   node cdp.js eval '<expr>' [urlSubstring] -> Runtime.evaluate in the first page whose URL contains urlSubstring
//   node cdp.js navigate <url> [urlSubstring]-> Page.navigate and wait for load event
// env: CDP_PORT (default 9222), CDP_TIMEOUT_MS (default 120000)
const port = process.env.CDP_PORT || 9222;
const timeoutMs = +(process.env.CDP_TIMEOUT_MS || 120000);

async function targets() {
  const r = await fetch(`http://127.0.0.1:${port}/json/list`);
  return (await r.json()).filter(t => t.type === 'page');
}

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const listeners = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    else listeners.forEach(f => f(m));
  };
  const opened = new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  const send = (method, params = {}) => new Promise((res, rej) => {
    const myId = ++id;
    const t = setTimeout(() => rej(new Error(`timeout: ${method}`)), timeoutMs);
    pending.set(myId, m => { clearTimeout(t); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); });
    ws.send(JSON.stringify({ id: myId, method, params }));
  });
  return { opened, send, ws, on: f => listeners.push(f) };
}

async function pick(sub) {
  const ts = await targets();
  const t = !sub ? ts[0] : sub.startsWith('=') ? ts.find(t => t.url === sub.slice(1)) : ts.find(t => t.url.includes(sub));
  if (!t) throw new Error('no matching page target; have: ' + ts.map(t => t.url).join(', '));
  return t;
}

(async () => {
  const [cmd, a, b] = process.argv.slice(2);
  if (cmd === 'list') {
    for (const t of await targets()) console.log(t.id, t.url, t.title);
  } else if (cmd === 'eval') {
    const t = await pick(b);
    const c = connect(t.webSocketDebuggerUrl); await c.opened;
    const r = await c.send('Runtime.evaluate', { expression: a, returnByValue: true, awaitPromise: true });
    console.log(JSON.stringify(r.exceptionDetails ? r.exceptionDetails : r.result.value));
    c.ws.close();
  } else if (cmd === 'navigate') {
    const t = await pick(b);
    const c = connect(t.webSocketDebuggerUrl); await c.opened;
    await c.send('Page.enable');
    const loaded = new Promise(res => c.on(m => m.method === 'Page.loadEventFired' && res()));
    const t0 = Date.now();
    await c.send('Page.navigate', { url: a });
    await loaded;
    console.log(`loaded in ${Date.now() - t0} ms`);
    c.ws.close();
  } else {
    console.error('usage: cdp.js list | eval <expr> [urlSub] | navigate <url> [urlSub]');
    process.exit(2);
  }
})().catch(e => { console.error(e.message); process.exit(1); });
