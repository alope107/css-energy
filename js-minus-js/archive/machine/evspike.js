async () => { await document.fonts.ready; await new Promise(r => setTimeout(r, 300));
  const exp = {"CR": 98, "NI": 4, "HPC": 220, "HSP": 6416, "HFP": 6410, "HRES": 0, "HMAR": 6414, "HT1lo": 10, "HT1hi": 0, "HT2lo": 0, "HT2hi": 0, "L0A": 22795, "L0B": 49, "L0C": 0, "L1A": 22794, "L1B": 2307, "L1C": 1, "L2A": 22793, "L2B": 1765, "L2C": 0, "L3A": 22788, "L3B": 0, "L3C": 0, "L4A": 22798, "L4B": 0, "L4C": 0, "L5A": 20530, "L5B": 8, "L5C": 0, "L6A": 12327, "L6B": 1320, "L6C": 1, "L7A": 12343, "L7B": 56, "L7C": 1, "L8A": 12376, "L8B": 4, "L8C": 0, "L9A": 22799, "L9B": 10, "L9C": 0, "L10A": 13616, "L10B": 49, "L10C": 0, "L11A": 12393, "L11B": 3, "L11C": 0, "L12A": 20532, "L12B": 0, "L12C": 0, "L13A": 55568, "L13B": 32, "L13C": 0, "L14A": 22797, "L14B": 0, "L14C": 0, "L15A": 22796, "L15B": 3, "L15C": 0}; let bad = 0, first = null, n = 0;
  for (const [k, v] of Object.entries(exp)) { const el = document.getElementById(k); if (!el) continue; n++;
    const w = Math.round(el.getBoundingClientRect().width * 64);
    if (w !== v) { bad++; if (!first) first = { k, w, v }; } }
  return { n, bad, first, total: document.getElementById('p').getBoundingClientRect().width }; }
