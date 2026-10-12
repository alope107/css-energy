() => { const p = document.getElementById('probe'), o = document.getElementById('out'), u = document.getElementById('u'), rd=document.getElementById('rd');
 u.style.setProperty('--fs','1024px'); u.style.setProperty('--k',1); p.textContent='';
 return {pw:p.getBoundingClientRect().width, rw: rd.getBoundingClientRect().width, y:getComputedStyle(o).getPropertyValue('--y'), font:getComputedStyle(p).font, fam: document.fonts.check('10px P')}; }
