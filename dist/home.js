const sceneNav = document.querySelector('#sceneNav');
const sceneTrigger = document.querySelector('#chooseScene');
const sceneDropdown = document.querySelector('#sceneDropdown');
let closeTimer;
function setSceneMenu(open) {
 clearTimeout(closeTimer);
 sceneDropdown.hidden = !open;
 sceneTrigger.setAttribute('aria-expanded', String(open));
}
sceneNav.addEventListener('pointerenter', event => { if(event.pointerType === 'mouse') setSceneMenu(true); });
sceneNav.addEventListener('pointerleave', event => {
 if(event.pointerType === 'mouse') closeTimer = setTimeout(() => setSceneMenu(false), 180);
});
sceneNav.addEventListener('focusin', event => { if(event.target !== sceneTrigger) setSceneMenu(true); });
sceneNav.addEventListener('focusout', event => { if(!sceneNav.contains(event.relatedTarget)) setSceneMenu(false); });
sceneTrigger.addEventListener('click', event => setSceneMenu(event.pointerType === 'mouse' ? true : sceneDropdown.hidden));
sceneTrigger.addEventListener('keydown', event => {
 if(event.key === 'ArrowDown') { event.preventDefault(); setSceneMenu(true); document.querySelector('#sceneMenu a')?.focus(); }
});
sceneNav.addEventListener('keydown', event => {
 if(event.key === 'Escape') { event.preventDefault(); sceneTrigger.focus(); setSceneMenu(false); }
});
document.addEventListener('pointerdown', event => { if(!sceneNav.contains(event.target)) setSceneMenu(false); });
fetch('/api/v1/scenarios/').then(r => { if(!r.ok) throw new Error(); return r.json(); }).then(data => {
 const container=document.querySelector('#homeScenarios'); container.replaceChildren();
 const menu=document.querySelector('#sceneMenu'); menu.replaceChildren();
 data.scenarios.forEach(scene => { const link=document.createElement('a'); link.href=`/report/?scenario=${encodeURIComponent(scene.code)}`; link.textContent=scene.name; menu.append(link); });
 data.scenarios.forEach(scene => { const a=document.createElement('a'); a.className='group'; a.href=`/report/?scenario=${encodeURIComponent(scene.code)}`; const handle=document.createElement('span'); handle.className='drag-handle'; handle.setAttribute('aria-hidden','true'); handle.textContent='⋮⋮'; const text=document.createElement('div'); const h=document.createElement('h3'); h.textContent=scene.name; const p=document.createElement('p'); p.textContent=scene.summary; text.append(h,p); a.append(handle,text); container.append(a); });
}).catch(() => { document.querySelector('#homeScenarios').textContent='场景暂时无法读取，请刷新重试。'; document.querySelector('#sceneMenu').textContent='场景暂时无法读取，请刷新重试。'; });
