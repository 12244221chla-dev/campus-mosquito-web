const panel = document.querySelector('#scenePanel');
function showScenes() { panel.hidden = false; panel.scrollIntoView({behavior:'smooth',block:'start'}); }
document.querySelector('#chooseScene').addEventListener('click', showScenes);
document.querySelector('#startScene').addEventListener('click', showScenes);
document.querySelector('#closeScenes').addEventListener('click', () => { panel.hidden = true; document.querySelector('#chooseScene').focus(); });
fetch('/api/v1/scenarios/').then(r => { if(!r.ok) throw new Error(); return r.json(); }).then(data => {
 const container=document.querySelector('#homeScenarios'); container.replaceChildren();
 data.scenarios.forEach(scene => { const a=document.createElement('a'); a.href=`/report/?scenario=${encodeURIComponent(scene.code)}`; const h=document.createElement('h3'); h.textContent=scene.name; const p=document.createElement('p'); p.textContent=scene.summary; a.append(h,p); container.append(a); });
}).catch(() => { document.querySelector('#homeScenarios').textContent='场景暂时无法读取，请刷新重试。'; });
