const $ = selector => document.querySelector(selector);
const RECEIPTS_KEY = "campus-mosquito-dorm-receipts-v1";
const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
const PHOTO_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const AREA_STATUS = { current: "计划内", due: "到期复查", unrecorded: "暂无记录" };
let areas = [];
let rooms = [];
let selectedAreaId = null;
let currentCampaign = null;
let previewUrl = null;
let canManage = false;

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = String(value ?? "");
  return node.innerHTML;
}

function csrfToken() {
  const item = document.cookie.split("; ").find(part => part.startsWith("csrftoken="));
  return item ? decodeURIComponent(item.slice("csrftoken=".length)) : "";
}

function toast(message) {
  const target = $("#toast");
  target.textContent = message;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { target.textContent = ""; }, 4500);
}

function showPanel(name) {
  const panel = name === "dorms" ? "dorms" : "areas";
  $("#areasPanel").hidden = panel !== "areas";
  $("#dormsPanel").hidden = panel !== "dorms";
  document.querySelectorAll(".nav-tab").forEach(button => {
    const active = button.dataset.panel === panel;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  if (location.hash !== `#${panel}`) history.replaceState(null, "", `#${panel}`);
}

document.querySelectorAll(".nav-tab").forEach(button => button.addEventListener("click", () => showPanel(button.dataset.panel)));
window.addEventListener("hashchange", () => showPanel(location.hash.slice(1)));
showPanel(location.hash.slice(1));

function metric(label, value) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderAreas() {
  const filter = $("#areaFilter").value;
  const visible = areas.filter(area => filter === "all" || area.status === filter);
  $("#areaMetrics").innerHTML = [
    metric("管理区域", areas.length),
    metric("计划内", areas.filter(area => area.status === "current").length),
    metric("到期复查", areas.filter(area => area.status === "due").length),
    metric("暂无记录", areas.filter(area => area.status === "unrecorded").length),
  ].join("");
  $("#mapPins").innerHTML = visible.map(area => {
    const x = Math.max(0, Math.min(100, Number(area.mapX) || 0));
    const y = Math.max(0, Math.min(100, Number(area.mapY) || 0));
    return `<button type="button" class="map-pin ${escapeHtml(area.status)} ${area.id === selectedAreaId ? "is-selected" : ""}" data-area-id="${area.id}" style="left:${x}%;top:${y}%" aria-label="${escapeHtml(area.name)}，${AREA_STATUS[area.status] || "暂无记录"}"><span class="map-pin-dot"></span><span class="map-pin-label">${escapeHtml(area.name)}</span></button>`;
  }).join("");
  $("#areaList").innerHTML = visible.length ? visible.map(area => `
    <button type="button" class="area-row ${area.id === selectedAreaId ? "is-selected" : ""}" data-area-id="${area.id}">
      <span class="area-row-top"><b>${escapeHtml(area.name)}</b><span class="status-pill ${escapeHtml(area.status)}">${AREA_STATUS[area.status] || "暂无记录"}</span></span>
      <small>${area.lastTreatedOn ? `最近处理 ${escapeHtml(area.lastTreatedOn)}` : "尚无处理记录"} · ${escapeHtml(area.category)}</small>
    </button>`).join("") : `<p class="empty-state">当前筛选下没有区域。</p>`;
  renderAreaDetail();
}

function renderAreaDetail() {
  const area = areas.find(item => item.id === selectedAreaId);
  if (!area) {
    $("#areaDetail").innerHTML = `<p class="empty-state">选择地图点位查看详情。</p>`;
    return;
  }
  const history = area.history.length ? area.history.map(item =>
    `<div class="history-line">${escapeHtml(item.date)} · ${escapeHtml(item.method)}${item.operator ? ` · ${escapeHtml(item.operator)}` : ""}${item.note ? `<br>${escapeHtml(item.note)}` : ""}</div>`
  ).join("") : `<p class="empty-state">暂未录入处理记录。</p>`;
  $("#areaDetail").innerHTML = `
    <h3>${escapeHtml(area.name)} <span class="status-pill ${escapeHtml(area.status)}">${AREA_STATUS[area.status] || "暂无记录"}</span></h3>
    <p>${escapeHtml(area.note || area.category)}</p>
    <div class="detail-grid"><div><span>最近处理</span><strong>${escapeHtml(area.lastTreatedOn || "未记录")}</strong></div><div><span>处理方式</span><strong>${escapeHtml(area.lastMethod || "—")}</strong></div><div><span>下次复查</span><strong>${escapeHtml(area.nextDueOn || "待首次处理")}</strong></div><div><span>计划间隔</span><strong>${escapeHtml(area.intervalDays)} 天</strong></div></div>
    <div class="history-title">处理记录</div>${history}
    ${canManage ? `<p><a href="/manage/?action=treatment&area=${area.id}">＋ 登记本区域消杀</a> · <a href="/manage/?action=area&id=${area.id}">编辑点位 / 周期</a></p>` : '<p><a href="/account/">管理者登录后登记消杀</a></p>'}`;
}

function selectArea(id) {
  selectedAreaId = id;
  renderAreas();
}

$("#mapPins").addEventListener("click", event => {
  const button = event.target.closest("[data-area-id]");
  if (button) selectArea(Number(button.dataset.areaId));
});
$("#areaList").addEventListener("click", event => {
  const button = event.target.closest("[data-area-id]");
  if (button) selectArea(Number(button.dataset.areaId));
});
$("#areaFilter").addEventListener("change", renderAreas);

async function loadAreas() {
  try {
    const response = await fetch(`/api/areas/?map=${encodeURIComponent($('#mapSwitch').value)}`, { credentials: "same-origin" });
    if (!response.ok) throw new Error("读取区域失败");
    const data = await response.json();
    const selectedMap = $('#mapSwitch').value;
    $('#mapSwitch').innerHTML = data.maps.map(map => `<option value="${escapeHtml(map.id)}">${escapeHtml(map.name)}</option>`).join('');
    if (data.maps.some(map => map.id === selectedMap)) $('#mapSwitch').value = selectedMap;
    const map = data.maps.find(map => map.id === $('#mapSwitch').value);
    $('.map-frame img').src = map.image;
    $('.map-frame img').alt = map.name;
    areas = data.areas;
    selectedAreaId = areas[0]?.id ?? null;
    renderAreas();
  } catch (_) {
    $("#areaMetrics").innerHTML = metric("读取状态", "失败");
    $("#areaList").innerHTML = `<p class="empty-state">无法读取区域。请确认演示服务器正在运行。</p>`;
  }
}

function renderRoomFilters() {
  const buildings = [...new Set(rooms.map(room => room.building))];
  const options = buildings.map(building => `<option value="${escapeHtml(building)}">${escapeHtml(building)}</option>`).join("");
  const oldFilter = $("#buildingFilter").value;
  $("#buildingFilter").innerHTML = `<option value="all">全部楼栋</option>${options}`;
  if (buildings.includes(oldFilter)) $("#buildingFilter").value = oldFilter;
  const oldForm = $("#formBuilding").value;
  $("#formBuilding").innerHTML = `<option value="">请选择宿舍楼</option>${options}`;
  if (buildings.includes(oldForm)) $("#formBuilding").value = oldForm;
  renderFormRooms();
}

function renderFormRooms() {
  const building = $("#formBuilding").value;
  const roomSelect = $("#formRoom");
  const previous = roomSelect.value;
  const choices = rooms.filter(room => room.building === building);
  roomSelect.innerHTML = `<option value="">请选择房号</option>${choices.map(room => `<option value="${room.id}">${escapeHtml(room.number)}</option>`).join("")}`;
  roomSelect.disabled = !building;
  if (choices.some(room => String(room.id) === previous)) roomSelect.value = previous;
}

function renderDorms(data) {
  currentCampaign = data.campaign;
  rooms = data.rooms;
  $("#campaignName").textContent = currentCampaign ? `当前批次：${currentCampaign.name}` : "未配置开放批次";
  $("#dormSubmit").disabled = !currentCampaign;
  $("#dormMetrics").innerHTML = [
    metric("房间总数", data.totals.rooms),
    metric("已领取蚊片", data.totals.pickedUp),
    metric("未领取蚊片", data.totals.notPickedUp),
    metric("已核对处理", data.totals.treated),
  ].join("");
  renderRoomFilters();
  renderRoomRows();
}

function renderRoomRows() {
  const building = $("#buildingFilter").value;
  const filter = $("#roomFilter").value;
  const visible = rooms.filter(room => {
    if (building !== "all" && room.building !== building) return false;
    return filter === "all" || (filter === "notPickedUp" && !room.pickedUp) ||
      (filter === "pickedUp" && room.pickedUp) || (filter === "notTreated" && !room.treated) ||
      (filter === "treated" && room.treated);
  });
  $("#roomRows").innerHTML = visible.length ? visible.map(room => `
    <tr><td>${escapeHtml(room.building)} ${escapeHtml(room.number)}</td>
      <td><span class="status-pill ${room.pickedUp ? "current" : ""}">${room.pickedUp ? "已领取" : "未领取"}</span>${room.lastPickupOn ? `<span class="row-date">${escapeHtml(room.lastPickupOn)}</span>` : ""}</td>
      <td><span class="status-pill ${room.treated ? "current" : ""}">${room.treated ? "已核对" : "未登记"}</span>${room.lastTreatmentOn ? `<span class="row-date">${escapeHtml(room.lastTreatmentOn)}</span>` : ""}</td></tr>`).join("") : `<tr><td colspan="3" class="empty-state">没有符合条件的房间。</td></tr>`;
}

$("#buildingFilter").addEventListener("change", renderRoomRows);
$("#roomFilter").addEventListener("change", renderRoomRows);
$("#formBuilding").addEventListener("change", renderFormRooms);

async function loadDorms() {
  try {
    const response = await fetch("/api/dorms/", { credentials: "same-origin" });
    if (!response.ok) throw new Error("读取宿舍失败");
    renderDorms(await response.json());
  } catch (_) {
    $("#dormMetrics").innerHTML = metric("读取状态", "失败");
    $("#roomRows").innerHTML = `<tr><td colspan="3">无法读取宿舍，请检查演示服务器。</td></tr>`;
  }
}

function updateKindFields() {
  const treatment = $("#recordKind").value === "treatment";
  $("#quantityField").hidden = treatment;
  $("#methodField").hidden = !treatment;
  $("#recordMethod").required = treatment;
  $("#dormPhoto").required = treatment;
  $("#photoRequired").textContent = treatment ? "（处理凭证必填）" : "（领取登记选填）";
}
$("#recordKind").addEventListener("change", updateKindFields);
updateKindFields();

function clearPhoto() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  $("#dormPhotoImage").removeAttribute("src");
  $("#dormPhotoPreview").hidden = true;
}

$("#dormPhoto").addEventListener("change", () => {
  clearPhoto();
  const input = $("#dormPhoto");
  const file = input.files[0];
  if (!file) return;
  if (!PHOTO_TYPES.has(file.type) || file.size === 0 || file.size > MAX_PHOTO_BYTES) {
    input.value = "";
    toast("请选择不超过5MB的 JPG、PNG 或 WebP 照片");
    return;
  }
  previewUrl = URL.createObjectURL(file);
  $("#dormPhotoImage").src = previewUrl;
  $("#dormPhotoPreview").hidden = false;
});
$("#removeDormPhoto").addEventListener("click", () => { $("#dormPhoto").value = ""; clearPhoto(); });

function receiptIds() {
  try {
    const value = JSON.parse(localStorage.getItem(RECEIPTS_KEY));
    return Array.isArray(value) ? value.filter(id => /^[0-9a-f-]{36}$/i.test(id)).slice(0, 20) : [];
  } catch (_) { return []; }
}

async function renderReceipts() {
  const ids = receiptIds();
  if (!ids.length) { $("#dormReceipts").innerHTML = `<p class="empty-state">暂无登记。</p>`; return; }
  const results = await Promise.all(ids.map(async id => {
    try {
      const response = await fetch(`/api/dorm-records/${encodeURIComponent(id)}/`, { credentials: "same-origin" });
      return response.ok ? response.json() : null;
    } catch (_) { return null; }
  }));
  $("#dormReceipts").innerHTML = results.filter(Boolean).map(item =>
    `<div class="receipt-row"><span>${escapeHtml(item.room)} · ${item.kind === "pickup" ? "蚊片领取" : "宿舍处理"}<br>${escapeHtml(item.createdAt)}</span><span class="status-pill ${item.status === "verified" ? "current" : ""}">${{ pending: "待核对", verified: "已核对", rejected: "未通过" }[item.status] || "待核对"}</span></div>`
  ).join("") || `<p class="empty-state">暂无可查询的登记。</p>`;
}

$("#dormForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("#dormSubmit");
  const payload = new FormData(event.currentTarget);
  if (!$("#dormPhoto").files.length) payload.delete("photo");
  button.disabled = true;
  try {
    const response = await fetch("/api/dorm-records/", {
      method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrfToken() }, body: payload,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || "登记失败，请重试");
    localStorage.setItem(RECEIPTS_KEY, JSON.stringify([data.id, ...receiptIds().filter(id => id !== data.id)].slice(0, 20)));
    const building = $("#formBuilding").value;
    event.currentTarget.reset();
    $("#formBuilding").value = building;
    renderFormRooms();
    clearPhoto();
    updateKindFields();
    await Promise.all([loadDorms(), renderReceipts()]);
    toast("登记已提交，待后台核对后计入统计");
  } catch (error) {
    toast(error.message || "登记失败，请稍后重试");
  } finally {
    button.disabled = !currentCampaign;
  }
});

window.addEventListener("focus", () => { loadAreas(); loadDorms(); renderReceipts(); });
loadAreas();
loadDorms();
renderReceipts();
$('#mapSwitch').addEventListener('change', loadAreas);
fetch('/api/session/').then(response => response.json()).then(session => {
  canManage = session.canManage;
  $('#accountLink').textContent = session.authenticated ? `${session.name} · 账号` : '登录 / 注册';
  renderAreaDetail();
}).catch(() => {});
