const image = document.querySelector('#editorMap');
if (image) {
  const selector = document.querySelector('#id_campus_map');
  const x = document.querySelector('#id_map_x'), y = document.querySelector('#id_map_y');
  const pin = document.querySelector('#editorPin');
  function draw() { pin.hidden = x.value === '' || y.value === ''; pin.style.left = `${x.value}%`; pin.style.top = `${y.value}%`; }
  function switchMap() { image.src = selector.value ? `/maps/${selector.value}/image/` : '/static/assets/gdmu-dongguan-campus-2025.jpg'; }
  selector.addEventListener('change', switchMap); switchMap(); draw();
  image.addEventListener('click', event => { const box = image.getBoundingClientRect(); x.value = Math.round((event.clientX-box.left)/box.width*100); y.value = Math.round((event.clientY-box.top)/box.height*100); draw(); });
  x.addEventListener('input', draw); y.addEventListener('input', draw);
}
