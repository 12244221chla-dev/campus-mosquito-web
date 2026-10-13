/* 校园公共卫生管理平台 · 数据驾驶舱 */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const STATUS_COLORS = {
  submitted: "#3b7dd8", accepted: "#7d5bd0", processing: "#cf7b17",
  review: "#2f6fb5", done: "#2f9e7f", rejected: "#9fb3b2",
};
const LEVEL_TEXT = { info: "提示", warn: "临期", overdue: "超期", escalate: "升级" };

let state = {
  overview: null, scenarios: [], matters: [], canManage: false, activeScenario: "all",
  points: [], mapStats: null, mapCategories: [], selectedPoint: null, placing: false, draft: null,
};

function esc(value) {
  const node = document.createElement("div");
  node.textContent = String(value ?? "");
  return node.innerHTML;
}
function csrf() {
  const item = document.cookie.split("; ").find(part => part.startsWith("csrftoken="));
  return item ? decodeURIComponent(item.slice("csrftoken=".length)) : "";
}
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 3600);
}
async function api(url, options) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    // 驾驶舱数据仅对管理人员开放：登录过期或被降权时回登录页
    if (data.loginRequired) {
      location.replace(data.loginUrl || "/account/?next=/");
      throw new Error("登录状态已失效，正在跳转登录");
    }
    throw new Error(data.message || "请求失败");
  }
  return data;
}

/* ---------------- 时钟 ---------------- */
function tickClock() {
  const now = new Date();
  $("#clock").textContent = now.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
tickClock();
setInterval(tickClock, 1000);

/* ---------------- KPI ---------------- */
const KPI_DEFS = [
  { key: "all", label: "事项总量", tone: "primary", sub: t => `覆盖 ${t.templates} 个场景` },
  { key: "open", label: "在办事项", tone: "info", sub: () => "含受理 / 处理 / 复核" },
  { key: "overdue", label: "超期未办结", tone: "danger", sub: () => "需立即督办" },
  { key: "soon", label: "临期预警", tone: "warn", sub: () => "即将触及处置时限" },
  { key: "today", label: "今日新增报备", tone: "primary", sub: t => `今日办结 ${t.todayClosed} 条` },
  { key: "completionRate", label: "按时办结率", tone: "ok", suffix: "%", sub: t => t.onTimeRate === null ? "暂无已完成样本" : `整体办结率 ${t.completionRate}%` },
];

function renderKpi() {
  const t = state.overview.totals;
  $("#kpiRow").innerHTML = KPI_DEFS.map(def => {
    let value = t[def.key];
    if (def.key === "completionRate") value = t.onTimeRate === null ? "—" : `${t.onTimeRate}${def.suffix}`;
    const sub = typeof def.sub === "function" ? def.sub(t) : "";
    return `<div class="kpi tone-${def.tone}">
      <div class="kpi-label">${esc(def.label)}</div>
      <div class="kpi-value">${esc(value)}</div>
      <div class="kpi-sub">${esc(sub)}</div>
    </div>`;
  }).join("");
}

/* ---------------- 预警条 ---------------- */
function renderAlerts() {
  const items = [];
  const emergency = state.scenarios.filter(s => s.isEmergency);
  const emergTotal = emergency.reduce((sum, s) => sum + s.open, 0);
  if (emergTotal > 0) {
    items.push(`<div class="alert-item emergency"><span class="badge">应急</span>
      <span>疫情应急上报在办 <b>${emergTotal}</b> 条，最短受理时限 1 小时，请优先处置。</span>
      <a href="#" data-jump="emergency-report">查看 →</a></div>`);
  }
  if (state.overview.totals.overdue > 0) {
    items.push(`<div class="alert-item overdue"><span class="badge">超期</span>
      <span>当前有 <b>${state.overview.totals.overdue}</b> 条事项已超过处置时限，系统已自动升级提醒。</span>
      <a href="#" data-jump-overdue="1">查看超期清单 →</a></div>`);
  }
  if (!items.length) items.push(`<div class="alert-item" style="background:var(--ok-soft);color:#1f6b57;border-color:#bfe6da"><span class="badge" style="background:var(--ok)">正常</span><span>暂无超期与应急事项，全部在时限内推进。</span></div>`);
  $("#alertBar").innerHTML = items.join("");
  $$("#alertBar [data-jump]").forEach(link => link.addEventListener("click", event => {
    event.preventDefault();
    $("#filterScenario").value = event.currentTarget.dataset.jump;
    state.activeScenario = event.currentTarget.dataset.jump;
    loadMatters();
    renderScenarios();
    $("#ledgerRows").closest(".card").scrollIntoView({ behavior: "smooth", block: "center" });
  }));
  $$("#alertBar [data-jump-overdue]").forEach(link => link.addEventListener("click", event => {
    event.preventDefault();
    $("#filterStatus").value = "overdue";
    loadMatters();
    $("#ledgerRows").closest(".card").scrollIntoView({ behavior: "smooth", block: "center" });
  }));
}

/* ---------------- 场景矩阵 ---------------- */
function renderScenarios() {
  $("#scenarioTotal").textContent = state.scenarios.length;
  $("#scenarioGrid").innerHTML = state.scenarios.map(s => {
    const donePct = s.total ? Math.round(s.done / s.total * 100) : 0;
    const openPct = s.total ? Math.round(s.open / s.total * 100) : 0;
    return `<article class="scenario ${state.activeScenario === s.code ? "is-active" : ""}" data-code="${esc(s.code)}" style="--sc:${esc(s.color)};--sc-soft:${esc(s.color)}1f">
      <span class="scenario-top">
        <span class="scenario-icon">${esc(s.icon)}</span>
        <span><h3>${esc(s.name)}</h3><span class="cat">${esc(s.categoryName)} · 时限 ${s.slaHours}h</span></span>
      </span>
      ${s.overdue ? `<span class="scenario-tag">超期 ${s.overdue}</span>` : (s.isEmergency ? `<span class="scenario-tag" style="background:var(--danger-soft);color:var(--danger)">应急</span>` : "")}
      <div class="scenario-nums">
        <div><b>${s.total}</b>总量</div>
        <div><b>${s.open}</b>在办</div>
        <div class="od"><b>${s.overdue}</b>超期</div>
        <div class="dn"><b>${s.done}</b>完成</div>
      </div>
      <div class="scenario-bar"><i style="width:${donePct}%;background:var(--ok)"></i><i style="width:${openPct}%;background:${esc(s.color)}"></i></div>
      <div class="scenario-foot"><span>办结率 ${s.completionRate}%</span><span>${s.avgHours !== null ? `平均 ${s.avgHours}h` : "暂无办结样本"}</span></div>
    </article>`;
  }).join("");
  $$("#scenarioGrid .scenario").forEach(card => card.addEventListener("click", () => {
    const code = card.dataset.code;
    state.activeScenario = state.activeScenario === code ? "all" : code;
    $("#filterScenario").value = state.activeScenario;
    renderScenarios();
    loadMatters();
  }));
}

/* ---------------- 环形图 ---------------- */
function renderDonut() {
  const data = state.overview.statusDistribution.filter(d => d.value > 0);
  const total = data.reduce((sum, d) => sum + d.value, 0) || 1;
  const radius = 80, cx = 110, cy = 110, circ = 2 * Math.PI * radius;
  let offset = 0;
  const arcs = data.map(item => {
    const len = item.value / total * circ;
    const seg = `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" stroke="${STATUS_COLORS[item.key] || "#9fb3b2"}"
      stroke-width="26" stroke-dasharray="${len - 2} ${circ - len + 2}" stroke-dashoffset="${-offset}"
      transform="rotate(-90 ${cx} ${cy})" stroke-linecap="butt"></circle>`;
    offset += len;
    return seg;
  }).join("");
  $("#donutChart").innerHTML = `${arcs}
    <text x="${cx}" y="${cy - 6}" text-anchor="middle" font-size="30" font-weight="800" fill="#0f2020">${total}</text>
    <text x="${cx}" y="${cy + 18}" text-anchor="middle" font-size="12" fill="#6b8482">事项总数</text>`;
  $("#donutLegend").innerHTML = state.overview.statusDistribution.map(item => `
    <li><i style="background:${STATUS_COLORS[item.key] || "#9fb3b2"}"></i>${esc(item.name)}
      <b>${item.value} · ${Math.round(item.value / total * 100)}%</b></li>`).join("");
}

/* ---------------- 趋势图 ---------------- */
function renderTrend() {
  const data = state.overview.trend;
  const W = 720, H = 240, padL = 34, padR = 14, padT = 16, padB = 28;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const max = Math.max(4, ...data.map(d => Math.max(d.submitted, d.closed)));
  const stepX = plotW / data.length;
  const barW = Math.min(26, stepX * 0.46);
  const y = value => padT + plotH - (value / max) * plotH;
  let grid = "", bars = "";
  for (let i = 0; i <= 4; i++) {
    const gy = padT + (plotH / 4) * i;
    const val = Math.round(max - (max / 4) * i);
    grid += `<line x1="${padL}" y1="${gy}" x2="${W - padR}" y2="${gy}" stroke="#eef4f3" stroke-width="1"></line>
      <text x="${padL - 6}" y="${gy + 4}" text-anchor="end" font-size="10" fill="#93a8a6">${val}</text>`;
  }
  data.forEach((d, i) => {
    const cx = padL + stepX * i + stepX / 2;
    const barH = (d.submitted / max) * plotH;
    bars += `<rect x="${cx - barW / 2}" y="${padT + plotH - barH}" width="${barW}" height="${Math.max(barH, d.submitted ? 2 : 0)}" rx="4" fill="#0f6b6d" opacity="0.85"><title>${d.date} 报备 ${d.submitted}</title></rect>`;
    if (i % 2 === 0) bars += `<text x="${cx}" y="${H - 8}" text-anchor="middle" font-size="10" fill="#93a8a6">${esc(d.date)}</text>`;
  });
  const points = data.map((d, i) => [padL + stepX * i + stepX / 2, y(d.closed)]);
  const line = points.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const dots = points.map((p, i) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3" fill="#fff" stroke="#cf7b17" stroke-width="2"><title>${esc(data[i].date)} 办结 ${data[i].closed}</title></circle>`).join("");
  $("#trendChart").innerHTML = `${grid}${bars}<path d="${line}" fill="none" stroke="#cf7b17" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"></path>${dots}`;
}

/* ---------------- 效能 ---------------- */
function renderEff() {
  const t = state.overview.totals;
  const period = state.overview.period;
  const cards = [
    ["近 7 天报备", period.created],
    ["近 7 天办结", period.closed],
    ["平均办理时长", t.avgHours !== null ? `${t.avgHours}h` : "—"],
    ["整体办结率", `${t.completionRate}%`],
  ];
  $("#effList").innerHTML = cards.map(([label, value]) => `<div class="eff-item"><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join("");
  const maxCount = Math.max(1, ...period.byScenario.map(item => item.count));
  $("#effBars").innerHTML = period.byScenario.length ? period.byScenario.slice(0, 5).map(item => `
    <div class="eff-bar-row">
      <div class="eff-bar-top"><span>${esc(item.icon)} ${esc(item.name)}</span><span>${item.count}</span></div>
      <div class="eff-bar"><i style="width:${Math.round(item.count / maxCount * 100)}%;background:${esc(item.color)}"></i></div>
    </div>`).join("") : `<p class="empty" style="padding:8px 0">近 7 天暂无新增报备。</p>`;
}

/* ---------------- 提醒 / 超期 / 流水 ---------------- */
function renderReminders() {
  const data = state.overview.reminders;
  $("#remindCount").textContent = data.pending;
  $("#reminderList").innerHTML = data.items.length ? data.items.map(item => `
    <div class="reminder-item lv-${esc(item.level)}">
      <div class="r-top">
        <strong>${esc(item.title)}</strong>
        <span class="r-level">${esc(item.levelName)}</span>
      </div>
      <div class="r-meta"><span>${esc(item.templateIcon)} ${esc(item.templateName)}</span><span>${esc(item.ruleName)}</span><span>${esc(item.triggeredAt)}</span></div>
      <div class="r-actions">
        <button class="btn" data-open="${esc(item.matterId)}">查看事项</button>
        ${state.canManage ? `<button class="btn primary" data-ack="${item.id}">确认提醒</button>` : ""}
      </div>
    </div>`).join("") : `<p class="empty">暂无待响应提醒。</p>`;
  $$("#reminderList [data-open]").forEach(btn => btn.addEventListener("click", () => openDrawer(btn.dataset.open)));
  $$("#reminderList [data-ack]").forEach(btn => btn.addEventListener("click", async () => {
    try {
      await api(`/api/v1/reminders/${btn.dataset.ack}/ack/`, { method: "POST", headers: { "X-CSRFToken": csrf() } });
      toast("已确认提醒，并写入办理流水");
      refresh();
    } catch (error) { toast(error.message); }
  }));
}

function renderOverdue() {
  const items = state.overview.topOverdue;
  $("#overdueList").innerHTML = items.length ? items.map(item => `
    <div class="overdue-item" data-open="${esc(item.id)}" style="cursor:pointer">
      <div class="o-top"><span class="o-code">${esc(item.code)}</span><strong>${esc(item.title)}</strong></div>
      <div class="o-meta"><span>${esc(item.templateIcon)} ${esc(item.templateName)}</span><span>${esc(item.location)}</span><span>应于 ${esc((item.dueAt || "").slice(5))} 前办结</span></div>
    </div>`).join("") : `<p class="empty">没有超期事项，保持得不错。</p>`;
  $$("#overdueList [data-open]").forEach(el => el.addEventListener("click", () => openDrawer(el.dataset.open)));
}

function renderTimeline() {
  $("#timelineList").innerHTML = state.overview.recentEvents.map(event => `
    <div class="tl-item" style="--tc:${esc(event.templateColor)}">
      <span class="tl-dot"></span>
      <div class="tl-body">
        <div class="tl-line"><span class="tl-kind">${esc(event.kindName)}</span><b>${esc(event.code)}</b><span class="tl-time">${esc(event.at)}</span></div>
        <p>${esc(event.note || event.title)} · ${esc(event.actor)}</p>
      </div>
    </div>`).join("");
}

/* ---------------- 地图：消杀点位（已处理 = 绿 / 未处理 = 红） ---------------- */
const OPERATOR_KEY = "campus-pubhealth-operator-v1";

function operatorName() {
  const input = $("#pointOperator");
  return input ? input.value.trim() : "";
}
function rememberOperator(name) {
  try { if (name) localStorage.setItem(OPERATOR_KEY, name); } catch (_) { /* 忽略隐私模式限制 */ }
}
function storedOperator() {
  try { return localStorage.getItem(OPERATOR_KEY) || ""; } catch (_) { return ""; }
}
function liveOperator() {
  const input = $("#pointOperator");
  return input && input.value ? input.value : storedOperator();
}

function renderMapMetrics() {
  const s = state.mapStats || { total: 0, done: 0, pending: 0, rate: 0 };
  $("#mapMetrics").innerHTML = `
    <div class="map-metric"><span>点位总数</span><b>${s.total}</b></div>
    <div class="map-metric is-done"><span>已处理（绿）</span><b>${s.done}</b></div>
    <div class="map-metric is-pending"><span>未处理（红）</span><b>${s.pending}</b></div>
    <div class="map-metric"><span>处理率</span><b>${s.rate}%</b></div>`;
}

function renderMapPins() {
  $("#mapPins").innerHTML = state.points.map(point => {
    const x = Math.max(0, Math.min(100, Number(point.mapX) || 0));
    const y = Math.max(0, Math.min(100, Number(point.mapY) || 0));
    return `<button type="button" class="map-pin ${esc(point.status)} ${point.isCustom ? "is-custom" : ""} ${point.id === state.selectedPoint ? "is-selected" : ""}"
      data-point="${point.id}" style="left:${x}%;top:${y}%"
      title="${esc(point.name)} · ${esc(point.statusName)}${point.lastDoneAt ? ` · 最近处理 ${esc(point.lastDoneAt)}` : ""}">
      <span class="map-pin-dot"></span><span class="map-pin-label">${esc(point.name)}</span></button>`;
  }).join("");
  $$("#mapPins [data-point]").forEach(pin => pin.addEventListener("click", event => {
    event.stopPropagation();
    setPlacing(false);
    state.selectedPoint = Number(pin.dataset.point);
    renderMapPins(); renderPointList(); renderPointDetail();
  }));
}

function renderPointList() {
  $("#mapPointList").innerHTML = state.points.map(point => `
    <div class="area-mini ${point.id === state.selectedPoint ? "is-selected" : ""}" data-point="${point.id}">
      <span class="mi-dot ${esc(point.status)}"></span>
      <span class="mi-name" title="${esc(point.name)}">${esc(point.name)}${point.isCustom ? " ·" : ""}</span>
      <span class="pill ${esc(point.status)}">${esc(point.statusName)}</span>
    </div>`).join("") || `<p class="empty">暂无点位，点击「＋ 自定义点位」在地图上新增。</p>`;
  $$("#mapPointList [data-point]").forEach(el => el.addEventListener("click", () => {
    state.selectedPoint = Number(el.dataset.point);
    renderMapPins(); renderPointList(); renderPointDetail();
  }));
}

function renderPointDetail() {
  const point = state.points.find(item => item.id === state.selectedPoint);
  if (!point) {
    $("#pointDetail").innerHTML = `<h4>点位详情</h4>
      <p class="pd-note">点按地图上的绿点 / 红点查看详情；<b>红点为未处理</b>，处理后一键标记即可变绿。</p>
      <p class="pd-note">也可以点击「＋ 自定义点位」，在地图上点选位置新增自己的点位。</p>`;
    return;
  }
  const doneText = point.lastDoneAt
    ? `最近处理 ${esc(point.lastDoneAt)}（${point.lastDoneDays} 天前）`
    : "暂无处理记录";
  $("#pointDetail").innerHTML = `
    <div class="pd-head">
      <span class="mi-dot ${esc(point.status)}"></span>
      <span><b>${esc(point.name)}</b><span class="pd-sub">${esc(point.categoryName)} · ${point.isCustom ? "自定义点位" : "系统预置点位"}</span></span>
      <span class="pill ${esc(point.status)}">${esc(point.statusName)}</span>
    </div>
    <div class="pd-meta">
      <span>坐标 ${point.mapX}% / ${point.mapY}%</span>
      <span>${doneText}</span>
      ${point.lastActionBy ? `<span>最近操作人 ${esc(point.lastActionBy)}</span>` : ""}
    </div>
    <p class="pd-note">${esc(point.note || "暂无说明")}</p>
    <input class="pd-op" id="pointOperator" maxlength="60" placeholder="操作人（选填，便于留痕）" value="${esc(liveOperator())}">
    <div class="point-actions">
      <button type="button" class="btn primary" data-mark="done" ${point.isDone ? "disabled" : ""}>标记已处理</button>
      <button type="button" class="btn" data-mark="pending" ${point.isDone ? "" : "disabled"}>标记未处理</button>
      ${state.canManage
        ? `<button type="button" class="btn danger" data-remove="${point.id}">删除点位</button>`
        : `<span class="hint">以管理者身份登录后可删除点位</span>`}
    </div>`;
  $$("#pointDetail [data-mark]").forEach(btn => btn.addEventListener("click", () => markPoint(point.id, btn.dataset.mark)));
  const removeBtn = $("#pointDetail [data-remove]");
  if (removeBtn) removeBtn.addEventListener("click", () => removePoint(Number(removeBtn.dataset.remove)));
}

function renderPointForm() {
  const container = $("#pointForm");
  if (!state.draft) { container.hidden = true; container.innerHTML = ""; return; }
  container.hidden = false;
  const options = state.mapCategories.map(item =>
    `<option value="${esc(item.key)}">${esc(item.name)}</option>`).join("");
  container.innerHTML = `
    <h4>新增自定义点位</h4>
    <label>点位名称 <em style="color:var(--danger);font-style:normal">*</em>
      <input id="pfName" maxlength="60" placeholder="例如：南门快递点旁废弃水桶"></label>
    <div class="pf-row">
      <label>点位类型<select id="pfCategory">${options}</select></label>
      <label>登记人<input id="pfOperator" maxlength="60" placeholder="选填" value="${esc(storedOperator())}"></label>
    </div>
    <label>点位说明<input id="pfNote" maxlength="180" placeholder="选填，例如：积水约 2㎡，需尽快消杀"></label>
    <span class="hint">已记录坐标 <b id="pfCoord">${state.draft.x}% / ${state.draft.y}%</b>，再次点击地图可微调位置。</span>
    <div class="point-actions">
      <button type="button" class="btn primary" id="pfSave">保存点位</button>
      <button type="button" class="btn" id="pfCancel">取消</button>
    </div>`;
  $("#pfSave").addEventListener("click", savePoint);
  $("#pfCancel").addEventListener("click", () => { state.draft = null; setPlacing(false); });
  $("#pfName").addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); savePoint(); } });
}

function setPlacing(on) {
  state.placing = on;
  $("#mapFrame").classList.toggle("is-placing", on);
  $("#addPointBtn").textContent = on ? "× 退出添加" : "＋ 自定义点位";
  const tip = $("#mapTip");
  tip.hidden = !on;
  if (on) tip.innerHTML = "正在添加自定义点位：<b>点击地图上任意位置</b>确定位置，填写名称后保存；新点位默认标记为<b>未处理（红点）</b>。";
  if (!on) { state.draft = null; $("#mapGhost").hidden = true; }
  renderPointForm();
}

function mapCoords(event) {
  const rect = $("#mapFrame").getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width) * 100;
  const y = ((event.clientY - rect.top) / rect.height) * 100;
  return { x: Math.max(0, Math.min(100, Math.round(x * 10) / 10)), y: Math.max(0, Math.min(100, Math.round(y * 10) / 10)) };
}

async function savePoint() {
  const name = $("#pfName").value.trim();
  if (!name) { toast("请填写点位名称"); $("#pfName").focus(); return; }
  const operator = $("#pfOperator").value.trim();
  const button = $("#pfSave");
  button.disabled = true;
  button.textContent = "保存中…";
  try {
    const data = await api("/api/v1/map/points/create/", {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({
        name, operator, map: $('#mapSwitch').value,
        category: $("#pfCategory").value,
        note: $("#pfNote").value.trim(),
        x: state.draft.x, y: state.draft.y,
      }),
    });
    rememberOperator(operator);
    state.selectedPoint = data.point.id;
    state.mapStats = data.stats;
    toast(data.message || "自定义点位已保存");
    setPlacing(false);
    await loadMapPoints();
  } catch (error) {
    toast(error.message);
    button.disabled = false;
    button.textContent = "保存点位";
  }
}

async function markPoint(id, status) {
  const operator = operatorName();
  try {
    const data = await api(`/api/v1/map/points/${id}/status/`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ status, operator }),
    });
    rememberOperator(operator);
    state.mapStats = data.stats;
    toast(data.message || "已更新点位状态");
    await loadMapPoints();
    renderPointDetail();
  } catch (error) { toast(error.message); }
}

async function removePoint(id) {
  try {
    const data = await api(`/api/v1/map/points/${id}/delete/`, {
      method: "POST", headers: { "X-CSRFToken": csrf() },
    });
    state.mapStats = data.stats;
    if (state.selectedPoint === id) state.selectedPoint = null;
    toast(data.message || "点位已删除");
    await loadMapPoints();
    renderPointDetail();
  } catch (error) { toast(error.message); }
}

$("#addPointBtn").addEventListener("click", () => setPlacing(!state.placing));
$("#mapFrame").addEventListener("click", event => {
  if (!state.placing || event.target.closest(".map-pin")) return;
  const coords = mapCoords(event);
  state.draft = coords;
  const ghost = $("#mapGhost");
  ghost.style.left = `${coords.x}%`;
  ghost.style.top = `${coords.y}%`;
  ghost.hidden = false;
  renderPointForm();
  const coord = $("#pfCoord");
  if (coord) coord.textContent = `${coords.x}% / ${coords.y}%`;
});

/* ---------------- 台账 ---------------- */
const URGENCY_TEXT = { overdue: "已超期", urgent: "紧急", soon: "临近", normal: "正常" };
function renderLedger(items) {
  if (!items.length) { $("#ledgerRows").innerHTML = `<tr><td colspan="9" class="empty">没有符合条件的事项。</td></tr>`; return; }
  $("#ledgerRows").innerHTML = items.map(item => {
    let deadline = "—", cls = "";
    if (item.dueAt) {
      if (item.isOverdue) { deadline = `超期 ${Math.abs(Math.round(item.remainingHours)).toLocaleString()}h`; cls = "overdue"; }
      else if (item.remainingHours !== null && item.remainingHours <= 12) { deadline = `剩 ${Math.round(item.remainingHours)}h`; cls = "soon"; }
      else deadline = item.dueAt.slice(5, 16);
    }
    return `<tr data-open="${esc(item.id)}">
      <td class="mono">${item.isOverdue ? '<span class="row-flag"></span>' : ""}${esc(item.code)}</td>
      <td><span class="tpl-chip"><i style="background:${esc(item.templateColor)}"></i>${esc(item.templateIcon)} ${esc(item.templateName)}</span></td>
      <td>${esc(item.title)}</td>
      <td>${esc(item.location)}</td>
      <td><span class="status-chip st-${esc(item.status)}">${esc(item.statusName)}</span></td>
      <td><span class="mini-bar"><i style="width:${item.progress}%"></i></span></td>
      <td class="deadline ${cls}">${esc(deadline)}</td>
      <td>${esc(item.handler || "—")}</td>
      <td class="mono">${esc(item.submittedAt.slice(5, 16))}</td>
    </tr>`;
  }).join("");
  $$("#ledgerRows [data-open]").forEach(row => row.addEventListener("click", () => openDrawer(row.dataset.open)));
}

/* ---------------- 抽屉详情 ---------------- */
async function openDrawer(id) {
  const matter = state.matters.find(item => item.id === id);
  $("#drawer").hidden = false;
  $("#drawerCode").textContent = matter ? matter.code : "—";
  $("#drawerTitle").textContent = matter ? matter.title : "加载中…";
  $("#drawerBody").innerHTML = `<p class="empty">正在读取办理轨迹…</p>`;
  try {
    const detail = await api(`/api/v1/matters/${encodeURIComponent(id)}/`);
    renderDrawer(detail);
  } catch (error) {
    $("#drawerBody").innerHTML = `<p class="empty">${esc(error.message)}</p>`;
  }
}

function renderDrawer(d) {
  $("#drawerCode").textContent = d.code;
  $("#drawerTitle").textContent = d.title;
  const doneIndex = d.currentStageIndex;
  const stepper = d.stages.map((stage, index) => {
    const cls = d.status === "rejected" ? "" : (index < doneIndex ? "done" : (index === doneIndex ? "current" : ""));
    return `<div class="step ${cls}">
      <div class="step-rail"><span class="step-dot"></span>${index < d.stages.length - 1 ? '<span class="step-line"></span>' : ""}</div>
      <div class="step-body"><b>${esc(stage.name)}</b><span>${esc(stage.desc || "")}</span></div>
    </div>`;
  }).join("");
  const labelMap = {};
  (d.fields || []).forEach(field => { labelMap[field.key] = field.label; });
  const payloadRows = Object.entries(d.payload || {}).map(([key, value]) =>
    `<div><span>${esc(labelMap[key] || key)}</span><b>${esc(value)}</b></div>`).join("")
    || `<div><span>场景问卷</span><b>—</b></div>`;
  const reminders = (d.reminders || []).map(item => `<li>
      <span class="tl-mark" style="background:${item.level === "warn" ? "var(--warn)" : "var(--danger)"}"></span>
      <span class="tl-txt"><b>[${esc(item.levelName)}] ${esc(item.title)}</b><span class="t">${esc(item.triggeredAt)}</span>
      <p>${esc(item.ruleName)} · ${item.status === "pending" ? "待响应" : "已确认"}</p></span></li>`).join("");
  const timeline = (d.timeline || []).map(event => `<li>
      <span class="tl-mark"></span>
      <span class="tl-txt"><b>${esc(event.kindName)}</b><span class="t">${esc(event.at)}</span>
      <p>${esc(event.note || "—")} · ${esc(event.actor)}</p></span></li>`).join("");
  const statusOptions = d.stages.map(stage => `<option value="${esc(stage.key)}" ${stage.key === d.status ? "selected" : ""}>${esc(stage.name)}</option>`).join("");
  $("#drawerBody").innerHTML = `
    <div class="stepper">${stepper}</div>
    <div class="detail-block">
      <h4>场景与时限</h4>
      <div class="kv">
        <div><span>所属场景</span><b>${esc(d.templateIcon)} ${esc(d.templateName)}</b></div>
        <div><span>优先级</span><b>${esc(d.priorityName)}${d.isOverdue ? " · 已超期" : ""}</b></div>
        <div><span>报备人</span><b>${esc(d.reporter || "—")}</b></div>
        <div><span>承办单位</span><b>${esc(d.handler || "尚未分派")}</b></div>
        <div><span>报备时间</span><b>${esc(d.submittedAt)}</b></div>
        <div><span>处置时限</span><b>${d.sla.totalHours} 小时（受理 ${d.sla.acceptHours}h / 处置 ${d.sla.handleHours}h）</b></div>
        <div><span>到期时间</span><b>${esc(d.dueAt || "—")}</b></div>
        <div><span>办结时间</span><b>${esc(d.closedAt || "—")}</b></div>
      </div>
    </div>
    <div class="detail-block">
      <h4>情况描述与问卷</h4>
      <p style="font-size:12.5px;margin:0 0 9px;color:var(--ink-2)">${esc(d.detail || "无补充描述")}</p>
      <div class="kv">${payloadRows}</div>
    </div>
    <div class="detail-block">
      <h4>自动提醒记录（${ (d.reminders || []).length }）</h4>
      <ul class="tl">${reminders || '<li><span class="tl-txt"><p>暂无提醒记录</p></span></li>'}</ul>
    </div>
    <div class="detail-block">
      <h4>办理轨迹 · 全程可追溯（${ (d.timeline || []).length }）</h4>
      <ul class="tl">${timeline}</ul>
    </div>
    ${state.canManage ? `<div class="detail-block">
      <h4>管理者操作</h4>
      <div class="drawer-actions">
        <select id="advStatus">${statusOptions}</select>
        <input id="advNote" placeholder="办理说明（选填）">
        <button class="btn primary" id="advBtn">更新进度</button>
        <input id="advHandler" placeholder="分派承办单位 / 人员">
        <button class="btn" id="assignBtn">分派</button>
      </div>
    </div>` : `<p class="hint">登录管理者账号后可在此推进进度与分派承办。</p>`}
  `;
  if (state.canManage) {
    $("#advBtn").addEventListener("click", () => advance(d.id, { action: $("#advStatus").value, note: $("#advNote").value }));
    $("#assignBtn").addEventListener("click", () => advance(d.id, { action: "assign", handler: $("#advHandler").value }));
  }
}

async function advance(id, payload) {
  try {
    const result = await api(`/api/v1/matters/${encodeURIComponent(id)}/advance/`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(payload),
    });
    toast(result.message || "已更新");
    renderDrawer(result.matter);
    refresh();
  } catch (error) { toast(error.message); }
}

/* ---------------- 数据加载 ---------------- */
async function loadMatters() {
  const params = new URLSearchParams({
    scenario: $("#filterScenario").value,
    status: $("#filterStatus").value,
    q: $("#filterKeyword").value.trim(),
  });
  try {
    const data = await api(`/api/v1/matters/list/?${params}`);
    state.matters = data.items;
    renderLedger(data.items);
  } catch (error) {
    $("#ledgerRows").innerHTML = `<tr><td colspan="9" class="empty">读取失败：${esc(error.message)}</td></tr>`;
  }
}

async function loadMapPoints() {
  try {
    const selectedMap = $('#mapSwitch').value;
    const data = await api(`/api/v1/map/points/?map=${encodeURIComponent(selectedMap)}`);
    $('#mapSwitch').innerHTML = data.maps.map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
    if (data.maps.some(m => m.id === selectedMap)) $('#mapSwitch').value = selectedMap;
    $('#campusMap').src = data.maps.find(m => m.id === $('#mapSwitch').value).image;
    state.points = data.points;
    state.mapStats = data.stats;
    if (data.categories && data.categories.length) state.mapCategories = data.categories;
    if (state.selectedPoint !== null && !data.points.some(item => item.id === state.selectedPoint)) {
      state.selectedPoint = null;
    }
    renderMapMetrics(); renderMapPins(); renderPointList();
    if (!state.placing) renderPointDetail();
  } catch (error) {
    $("#mapPointList").innerHTML = `<p class="empty">点位读取失败：${esc(error.message)}</p>`;
  }
}

$('#mapSwitch').addEventListener('change', () => { state.selectedPoint = null; setPlacing(false); loadMapPoints(); });

/* ---------------- 身份展示（驾驶舱为管理端） ---------------- */
function renderIdentity(overview) {
  const chip = $("#userChip");
  if (!chip) return;
  chip.textContent = "管理端 · " + (overview.userName || "已登录");
  chip.title = "数据驾驶舱仅对管理人员开放，登录账号：" + (overview.userName || "");
}

async function refresh() {
  try {
    const [overview, scenarios] = await Promise.all([api("/api/v1/overview/"), api("/api/v1/scenarios/")]);
    state.overview = overview;
    state.scenarios = scenarios.scenarios;
    state.canManage = overview.canManage;
    renderIdentity(overview);
    const select = $("#filterScenario");
    if (select.options.length <= 1) {
      select.innerHTML = `<option value="all">全部场景</option>` +
        scenarios.scenarios.map(s => `<option value="${esc(s.code)}">${esc(s.name)}</option>`).join("");
    }
    renderKpi(); renderAlerts(); renderScenarios(); renderDonut(); renderTrend();
    renderEff(); renderReminders(); renderOverdue(); renderTimeline();
  } catch (error) {
    toast(`总览加载失败：${error.message}`);
  }
}

/* ---------------- 事件绑定 ---------------- */
$("#filterScenario").addEventListener("change", event => { state.activeScenario = event.target.value; renderScenarios(); loadMatters(); });
$("#filterStatus").addEventListener("change", loadMatters);
let searchTimer = null;
$("#filterKeyword").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadMatters, 280); });
$$("#drawer [data-close]").forEach(el => el.addEventListener("click", () => { $("#drawer").hidden = true; }));
document.addEventListener("keydown", event => { if (event.key === "Escape") $("#drawer").hidden = true; });
$("#logoutBtn").addEventListener("click", async () => {
  try {
    await fetch("/account/logout/", { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf() } });
  } catch (_) { /* 即使退出请求失败也回到公众页 */ }
  location.href = "/report/";
});

refresh();
loadMatters();
loadMapPoints();
setInterval(refresh, 60000);
setInterval(loadMatters, 60000);
setInterval(() => { if (!state.placing) loadMapPoints(); }, 60000);
