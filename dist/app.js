const DEFAULT_POINTS = [
  { id: 1, location: "宿舍区花盆托盘", risk: 1, checker: "示例数据", date: "2026-09-01", killStatus: 0, note: "演示待核查：花盆托盘内可能积水，需现场确认。" },
  { id: 2, location: "宿舍区闲置桶盆", risk: 2, checker: "示例数据", date: "2026-09-01", killStatus: 0, note: "演示待核查：闲置容器可能存水，建议翻盆倒罐。" },
  { id: 3, location: "教学楼外围废弃瓶罐", risk: 2, checker: "示例数据", date: "2026-09-01", killStatus: 0, note: "演示待核查：废弃瓶罐可能形成小型积水。" },
  { id: 4, location: "第一食堂后侧容器", risk: 1, checker: "示例数据", date: "2026-09-01", killStatus: 0, note: "演示待核查：盛水容器需加盖、清空或定期清洗。" },
  { id: 5, location: "第二食堂排水角落", risk: 1, checker: "示例数据", date: "2026-09-01", killStatus: 0, note: "演示待核查：检查排水处是否有可清除的小型积水。" },
  { id: 6, location: "中心湖周边废弃容器", risk: 1, checker: "示例数据", date: "2026-09-01", killStatus: 0, note: "演示待核查：重点检查湖边废弃容器；不将湖体本身视为伊蚊孳生点。" },
  { id: 7, location: "运动场看台瓶罐", risk: 2, checker: "示例数据", date: "2026-09-01", killStatus: 0, note: "演示待核查：看台周边废弃瓶罐可能积水。" }
];

const STORAGE_KEY = "campus-mosquito-inspection-v3";
const REPORTS_KEY = "campus-mosquito-student-reports-v1";
const state = loadState();

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved && Array.isArray(saved.points) && Array.isArray(saved.logs)) return saved;
  } catch (_) {}
  return { points: structuredClone(DEFAULT_POINTS), logs: [] };
}

function saveState() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const riskText = risk => ({1: "高危", 2: "中危", 3: "低危"}[Number(risk)] || "未知");
const riskClass = risk => ({1: "high", 2: "mid", 3: "low"}[Number(risk)] || "low");
const priority = point => (point.killStatus ? 20 : 0) + Number(point.risk);
const byPriority = (a, b) => priority(a) - priority(b) || Number(a.risk) - Number(b.risk) || a.id - b.id;
const formatDateTime = value => new Intl.DateTimeFormat("zh-CN", {year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", hour12:false}).format(new Date(value));
const today = () => { const date = new Date(Date.now() - new Date().getTimezoneOffset() * 60000); return date.toISOString().slice(0, 10); };
const nowLocal = () => { const date = new Date(Date.now() - new Date().getTimezoneOffset() * 60000); return date.toISOString().slice(0, 16); };

function escapeHtml(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
function searchableText(point) { return `${point.id} ${point.location} ${point.checker} ${point.note}`.toLowerCase(); }
function toast(message) { const node = document.createElement("div"); node.className = "toast"; node.textContent = message; $("#toastRegion").append(node); setTimeout(() => node.remove(), 2600); }

function renderAll() { renderOverview(); renderPoints(); renderTasks(); refreshSelects(); renderLogs(); renderReports(); }

function loadReports() {
  try { const reports = JSON.parse(localStorage.getItem(REPORTS_KEY)); return Array.isArray(reports) ? reports : []; }
  catch (_) { return []; }
}
function renderReports() {
  const reports = loadReports().sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
  const pending = reports.filter(item => item.status === "pending").length;
  const checking = reports.filter(item => item.status === "checking").length;
  const resolved = reports.filter(item => item.status === "resolved").length;
  $("#reportStats").innerHTML = `<span>全部线索 <b>${reports.length}</b></span><span>待核查 <b>${pending}</b></span><span>核查中 <b>${checking}</b></span><span>已处理 <b>${resolved}</b></span>`;
  $("#reportList").innerHTML = reports.length ? reports.map(item => `<article class="report-card" data-report-id="${escapeHtml(item.id)}"><div><small>${escapeHtml(item.createdAt?.replace("T", " ") || "")}</small><h3>${escapeHtml(item.location || "未填写地点")}</h3><p>${escapeHtml(item.type || "其他积水隐患")} · ${escapeHtml(item.detail || "无补充说明")}</p></div><div class="report-card-actions"><span class="status ${item.status === "resolved" ? "done" : "pending"}">${{pending:"待核查",checking:"核查中",resolved:"已处理"}[item.status] || "待核查"}</span><button type="button" class="task-action" data-report-action="checking" ${item.status === "checking" ? "disabled" : ""}>标记核查中</button><button type="button" class="task-action" data-report-action="resolved" ${item.status === "resolved" ? "disabled" : ""}>标记已处理</button></div></article>`).join("") : `<div class="empty-result">尚无线索。可在手机端演示页提交一条积水隐患。</div>`;
}

function renderOverview() {
  const points = [...state.points];
  const high = points.filter(point => point.risk === 1).length;
  const mid = points.filter(point => point.risk === 2).length;
  const low = points.filter(point => point.risk === 3).length;
  const done = points.filter(point => point.killStatus === 1).length;
  const queue = points.sort(byPriority);
  const focus = queue[0];
  $("#metricHigh").textContent = high; $("#metricPending").textContent = points.length - done; $("#metricDone").textContent = done; $("#metricTotal").textContent = points.length;
  $("#legendHigh").textContent = high; $("#legendMid").textContent = mid; $("#legendLow").textContent = low;
  const total = Math.max(points.length, 1), highEnd = high / total * 100, midEnd = highEnd + mid / total * 100;
  $("#riskDonut").style.background = `conic-gradient(var(--danger) 0 ${highEnd}%, var(--amber) ${highEnd}% ${midEnd}%, var(--green) ${midEnd}% 100%)`;
  if (focus) { $("#heroTitle").textContent = focus.location; $("#heroNote").textContent = focus.note; $("#heroDate").textContent = `上次排查 ${focus.date}`; }
  else { $("#heroTitle").textContent = "暂无排查点位"; $("#heroNote").textContent = "新增点位后，系统会自动生成任务优先级。"; $("#heroDate").textContent = "等待录入"; }
  $("#priorityList").innerHTML = queue.length ? queue.slice(0, 4).map((point, index) => `<div class="priority-item"><span class="priority-rank">${String(index + 1).padStart(2, "0")}</span><div><b>${escapeHtml(point.location)}</b><small>${point.killStatus ? "常规复查" : "待消杀处理"}</small></div><span class="risk-pill ${riskClass(point.risk)}">${riskText(point.risk)}</span></div>`).join("") : `<div class="empty-result">暂无排查任务</div>`;
  renderOverviewTable();
}

function renderOverviewTable() {
  const filter = $("#riskFilter").value, search = $("#globalSearch").value.trim().toLowerCase();
  const rows = state.points.filter(point => (filter === "all" || String(point.risk) === filter) && (!search || searchableText(point).includes(search)));
  $("#overviewTableBody").innerHTML = rows.length ? rows.map(point => `<tr><td>#${String(point.id).padStart(2, "0")}</td><td><b>${escapeHtml(point.location)}</b></td><td><span class="risk-pill ${riskClass(point.risk)}">${riskText(point.risk)}</span></td><td>${escapeHtml(point.checker)}</td><td>${point.date}</td><td><span class="status ${point.killStatus ? "done" : "pending"}">${point.killStatus ? "已消杀" : "未消杀"}</span></td></tr>`).join("") : `<tr><td colspan="6" class="empty-result">没有匹配的点位</td></tr>`;
}

function renderPoints() {
  const search = $("#pointSearch").value.trim().toLowerCase(), sort = $("#pointSort").value;
  const points = state.points.filter(point => !search || searchableText(point).includes(search));
  points.sort(sort === "id" ? (a,b) => a.id - b.id : sort === "risk" ? (a,b) => a.risk - b.risk || a.id - b.id : sort === "date" ? (a,b) => b.date.localeCompare(a.date) : byPriority);
  $("#pointGrid").innerHTML = points.length ? points.map(point => `<article class="point-card" data-point-id="${point.id}"><header><span class="point-number">#${String(point.id).padStart(2,"0")}</span><div><h3>${escapeHtml(point.location)}</h3><span class="risk-pill ${riskClass(point.risk)}">${riskText(point.risk)}</span></div><div class="card-actions"><button class="icon-button" data-action="edit" title="编辑点位" aria-label="编辑 ${escapeHtml(point.location)}">✎</button><button class="icon-button" data-action="delete" title="删除点位" aria-label="删除 ${escapeHtml(point.location)}">×</button></div></header><p class="point-note">${escapeHtml(point.note)}</p><div class="point-meta"><span>${escapeHtml(point.checker)}</span><span>${point.date}</span><span class="status ${point.killStatus ? "done" : "pending"}">${point.killStatus ? "已消杀" : "未消杀"}</span></div></article>`).join("") : `<div class="empty-result">没有匹配的点位记录</div>`;
}

function renderTasks() {
  const queue = [...state.points].sort(byPriority), done = queue.filter(point => point.killStatus).length;
  $("#taskCompletion").textContent = `${done} / ${queue.length} 已处理`;
  $("#taskList").innerHTML = queue.length ? queue.map((point, index) => `<article class="task-row ${point.killStatus ? "done" : ""}" data-point-id="${point.id}"><span class="task-index">${String(index + 1).padStart(2,"0")}</span><div><h3>${escapeHtml(point.location)}</h3><p>${point.killStatus ? "已完成消杀，等待常规复查" : escapeHtml(point.note)}</p></div><span class="risk-pill ${riskClass(point.risk)}">${riskText(point.risk)}</span><button class="task-action" data-action="log">${point.killStatus ? "记录复查" : "开始排查"}</button></article>`).join("") : `<div class="empty-result">暂无任务，请先新增点位</div>`;
}

function renderLogs() {
  const filter = $("#logSiteFilter").value;
  const logs = [...state.logs].filter(log => filter === "all" || String(log.siteId) === filter).sort((a,b) => b.time.localeCompare(a.time));
  $("#logEmpty").classList.toggle("visible", logs.length === 0);
  $("#logList").innerHTML = logs.map(log => { const point = state.points.find(item => item.id === log.siteId); return `<article class="log-entry"><span class="timeline-dot"></span><div class="log-card"><header><div><h3>${escapeHtml(point?.location || `已删除点位 #${log.siteId}`)}</h3><time datetime="${log.time}">${formatDateTime(log.time)}</time></div><span class="status ${log.result ? "done" : "pending"}">${log.result ? "已整改" : "待整改"}</span></header><div class="log-details"><div><small>发现问题</small><p>${escapeHtml(log.problem)}</p></div><div><small>处理方式</small><p>${escapeHtml(log.handle)}</p></div></div></div></article>`; }).join("");
  $("#logCount").textContent = state.logs.length; $("#resolvedCount").textContent = state.logs.filter(log => log.result).length;
}

function refreshSelects() {
  const options = [...state.points].sort((a,b) => a.id - b.id).map(point => `<option value="${point.id}">#${String(point.id).padStart(2,"0")} ${escapeHtml(point.location)}</option>`).join("");
  const currentFilter = $("#logSiteFilter").value, currentLogSite = $("#logSite").value;
  $("#logSiteFilter").innerHTML = `<option value="all">全部片区</option>${options}`; $("#logSite").innerHTML = options;
  if (["all", ...state.points.map(point => String(point.id))].includes(currentFilter)) $("#logSiteFilter").value = currentFilter;
  if (state.points.some(point => String(point.id) === currentLogSite)) $("#logSite").value = currentLogSite;
}

function setView(view) {
  $$(".view").forEach(element => element.classList.toggle("active", element.id === `${view}View`));
  $$(".nav-item").forEach(element => element.classList.toggle("active", element.dataset.view === view));
  $("#pageTitle").textContent = {overview:"工作台", points:"隐患点位", tasks:"排查任务", logs:"排查日志", reports:"公众线索"}[view];
  $(".sidebar").classList.remove("open");
}

function nextPointId() { let id = 1; const ids = new Set(state.points.map(point => point.id)); while (ids.has(id)) id += 1; return id; }
function openPointDialog(point = null) {
  $("#pointForm").reset(); $("#pointDialogTitle").textContent = point ? "编辑点位" : "新增点位"; $("#originalPointId").value = point?.id ?? "";
  $("#pointId").value = point?.id ?? nextPointId(); $("#pointLocation").value = point?.location ?? ""; $("#pointRisk").value = point?.risk ?? 2; $("#pointChecker").value = point?.checker ?? ""; $("#pointDate").value = point?.date ?? today(); $("#pointStatus").value = point?.killStatus ?? 0; $("#pointNote").value = point?.note ?? "";
  $("#pointDialog").showModal();
}
function openLogDialog(siteId = null) {
  if (!state.points.length) return toast("请先新增一个排查点位");
  $("#logForm").reset(); refreshSelects(); if (siteId && state.points.some(point => point.id === Number(siteId))) $("#logSite").value = String(siteId); $("#logTime").value = nowLocal(); $("#logDialog").showModal();
}

function upsertPoint(data) {
  const originalId = Number(data.originalId || 0), id = Number(data.id);
  if (!Number.isInteger(id) || id <= 0) throw new Error("点位编号必须是正整数");
  if (state.points.some(point => point.id === id && point.id !== originalId)) throw new Error(`编号 ${id} 已存在`);
  const point = { id, location: data.location.trim(), risk: Number(data.risk), checker: data.checker.trim(), date: data.date, killStatus: Number(data.killStatus), note: data.note.trim() };
  if (!point.location || !point.checker || !point.date || !point.note) throw new Error("请完整填写点位信息");
  const index = state.points.findIndex(item => item.id === originalId);
  if (index >= 0) { state.points[index] = point; if (originalId !== id) state.logs.forEach(log => { if (log.siteId === originalId) log.siteId = id; }); } else state.points.push(point);
  saveState(); renderAll(); return point;
}
function addLog(data) {
  const siteId = Number(data.siteId), point = state.points.find(item => item.id === siteId); if (!point) throw new Error("未找到对应片区");
  const log = { id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`, siteId, time: data.time, problem: data.problem.trim(), handle: data.handle.trim(), result: Number(data.result) };
  if (!log.time || !log.problem || !log.handle) throw new Error("请完整填写排查日志");
  state.logs.push(log); point.date = log.time.slice(0, 10); point.checker = point.checker === "系统初始化" ? "现场排查" : point.checker; if (log.result === 1) point.killStatus = 1;
  saveState(); renderAll(); return log;
}
function deletePoint(id) {
  const index = state.points.findIndex(point => point.id === Number(id)); if (index < 0) throw new Error("点位不存在");
  const [removed] = state.points.splice(index, 1); state.logs = state.logs.filter(log => log.siteId !== Number(id)); saveState(); renderAll(); return removed;
}

function registerWebMcpTools() {
  const context = document.modelContext; if (!context?.registerTool) return;
  const safeRegister = tool => { try { void Promise.resolve(context.registerTool(tool)).catch(() => {}); } catch (_) {} };
  safeRegister({ name:"list_mosquito_points", title:"查询灭蚊点位", description:"读取当前校园灭蚊点位，可按风险等级和消杀状态筛选。", inputSchema:{type:"object",properties:{risk:{type:"integer",enum:[1,2,3]},killStatus:{type:"integer",enum:[0,1]}},additionalProperties:false}, annotations:{readOnlyHint:true,untrustedContentHint:false}, execute(input={}){return state.points.filter(point=>(input.risk==null||point.risk===input.risk)&&(input.killStatus==null||point.killStatus===input.killStatus)).map(point=>({...point,riskText:riskText(point.risk)}));} });
  safeRegister({ name:"create_mosquito_point", title:"新增灭蚊点位", description:"新增一个校园灭蚊排查点位并立即更新页面与本机数据。", inputSchema:{type:"object",properties:{id:{type:"integer",minimum:1},location:{type:"string",minLength:1},risk:{type:"integer",enum:[1,2,3]},checker:{type:"string",minLength:1},date:{type:"string"},killStatus:{type:"integer",enum:[0,1]},note:{type:"string",minLength:1}},required:["id","location","risk","checker","date","killStatus","note"],additionalProperties:false}, annotations:{readOnlyHint:false,untrustedContentHint:false}, execute(input){const point=upsertPoint(input);return{created:true,point};} });
  safeRegister({ name:"record_mosquito_inspection", title:"记录灭蚊排查", description:"为指定片区新增排查日志；整改完成时同步更新点位消杀状态。", inputSchema:{type:"object",properties:{siteId:{type:"integer",minimum:1},time:{type:"string"},problem:{type:"string",minLength:1},handle:{type:"string",minLength:1},result:{type:"integer",enum:[0,1]}},required:["siteId","time","problem","handle","result"],additionalProperties:false}, annotations:{readOnlyHint:false,untrustedContentHint:false}, execute(input){const log=addLog(input);return{created:true,log};} });
}

$$('[data-view]').forEach(button => button.addEventListener("click", () => setView(button.dataset.view)));
$$('[data-go]').forEach(button => button.addEventListener("click", () => setView(button.dataset.go)));
$$('[data-close]').forEach(button => button.addEventListener("click", () => $(`#${button.dataset.close}`).close()));
$("#menuButton").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
$("#riskFilter").addEventListener("change", renderOverviewTable); $("#globalSearch").addEventListener("input", renderOverviewTable); $("#pointSearch").addEventListener("input", renderPoints); $("#pointSort").addEventListener("change", renderPoints); $("#logSiteFilter").addEventListener("change", renderLogs);
$("#addPointButton").addEventListener("click", () => openPointDialog()); $("#addLogButton").addEventListener("click", () => openLogDialog()); $("#emptyAddLog").addEventListener("click", () => openLogDialog()); $("#startHeroTask").addEventListener("click", () => openLogDialog([...state.points].sort(byPriority)[0]?.id));
$("#resetToday").addEventListener("click", () => { if (!confirm("恢复默认七大片区并清空排查日志？")) return; state.points = structuredClone(DEFAULT_POINTS); state.logs = []; saveState(); renderAll(); toast("已恢复默认数据"); });
$("#pointGrid").addEventListener("click", event => { const action = event.target.closest("[data-action]")?.dataset.action, card = event.target.closest("[data-point-id]"); if (!action || !card) return; const point = state.points.find(item => item.id === Number(card.dataset.pointId)); if (action === "edit") openPointDialog(point); if (action === "delete") { $("#deletePointId").value = point.id; $("#deleteMessage").textContent = `将删除“${point.location}”及其关联日志，此操作无法撤销。`; $("#deleteDialog").showModal(); } });
$("#taskList").addEventListener("click", event => { const button = event.target.closest('[data-action="log"]'), row = event.target.closest("[data-point-id]"); if (button && row) openLogDialog(Number(row.dataset.pointId)); });
$("#reportList").addEventListener("click", event => {
  const button = event.target.closest("[data-report-action]"), card = event.target.closest("[data-report-id]");
  if (!button || !card) return;
  const reports = loadReports(), report = reports.find(item => item.id === card.dataset.reportId);
  if (!report) return;
  report.status = button.dataset.reportAction;
  localStorage.setItem(REPORTS_KEY, JSON.stringify(reports));
  renderReports(); toast("线索进度已更新（本机演示）");
});
window.addEventListener("storage", event => { if (event.key === REPORTS_KEY) renderReports(); });
$("#pointForm").addEventListener("submit", event => { event.preventDefault(); try { const originalId = $("#originalPointId").value; upsertPoint({originalId,id:$("#pointId").value,location:$("#pointLocation").value,risk:$("#pointRisk").value,checker:$("#pointChecker").value,date:$("#pointDate").value,killStatus:$("#pointStatus").value,note:$("#pointNote").value}); $("#pointDialog").close(); toast(originalId ? "点位信息已更新" : "新点位已添加"); } catch(error){toast(error.message);} });
$("#logForm").addEventListener("submit", event => { event.preventDefault(); try { addLog({siteId:$("#logSite").value,time:$("#logTime").value,problem:$("#logProblem").value,handle:$("#logHandle").value,result:$("#logResult").value}); $("#logDialog").close(); setView("logs"); toast("排查日志已保存"); } catch(error){toast(error.message);} });
$("#deleteForm").addEventListener("submit", event => { event.preventDefault(); try { const removed=deletePoint($("#deletePointId").value); $("#deleteDialog").close(); toast(`已删除 ${removed.location}`); } catch(error){toast(error.message);} });
$$('.app-dialog').forEach(dialog => dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); }));
$("#todayLabel").textContent = new Intl.DateTimeFormat("zh-CN", {year:"numeric",month:"long",day:"numeric",weekday:"short"}).format(new Date());
renderAll(); registerWebMcpTools();
