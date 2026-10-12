() => { const w = id => document.getElementById(id).getBoundingClientRect().width * 64;
  const r = { a: w('a'), b: w('b'), c: w('c'), expect: { a: 100*3+7+1, b: 100*7+5+1, c: 100*5+2+1 } };
  // change only span c's content; does span b's width (which depends on its right neighbour) update?
  document.getElementById('c').textContent = ''; r.b_after = w('b'); r.b_after_expect = 100*7+9+1;
  // different element styles that don't affect font: does it still shape across?
  document.getElementById('b').style.color = 'red'; document.getElementById('b').style.outline = '1px solid'; r.b_styled = w('b');
  return r; }
