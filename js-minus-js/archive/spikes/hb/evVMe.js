async () => { const m = document.getElementById('m'); const us = [...document.querySelectorAll('.u')], outs = [...document.querySelectorAll('.out')], pr=[...document.querySelectorAll('.probe')];
  const snap = () => us.map((u,i) => [ +getComputedStyle(u).getPropertyValue('--s'), +getComputedStyle(outs[i]).getPropertyValue('--y'), pr[i].getBoundingClientRect().width*64 ]);
  m.style.setProperty('--s', 0); snap();
  m.style.setProperty('--s', 53); const a = snap();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const b = snap();
  m.style.setProperty('--s', 1); snap(); m.style.setProperty('--s', 53); const c = snap();
  return { first: a.map(x=>x.join('/')).join(' '), afterFrames: b.map(x=>x.join('/')).join(' '), again: c.map(x=>x.join('/')).join(' ') }; }
