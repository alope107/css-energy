() => { const m = document.getElementById('m'); m.style.setProperty('--s', 0);
  const us = [...document.querySelectorAll('.u')], outs = [...document.querySelectorAll('.out')], pr=[...document.querySelectorAll('.probe')];
  return us.slice(0,3).map((u,i) => ({ s: getComputedStyle(u).getPropertyValue('--s'), y: getComputedStyle(outs[i]).getPropertyValue('--y'),
     pw: pr[i].getBoundingClientRect().width*64, txt: getComputedStyle(pr[i], '::before').content.codePointAt(1)?.toString(16) + ',' + getComputedStyle(pr[i], '::before').content.length })); }
