/* 线上报备 + 进度跟踪（合并为同一页面：上半部分报备，下半部分进度） */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const CODES_KEY = "campus-pubhealth-codes-v1";
const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
const PHOTO_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

let scenarios = [];
let selected = null;
let previewUrl = null;

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
  toast.timer = setTimeout(() => el.classList.remove("show"), 4000);
}
async function api(url, options) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || "请求失败");
  return data;
}

/* ---------------- 页面区块定位（报备 / 进度同一页面，用锚点滚动） ---------------- */
function scrollToTrack() {
  $("#track").scrollIntoView({ behavior: "smooth", block: "start" });
}
function scrollToReport() {
  $("#report").scrollIntoView({ behavior: "smooth", block: "start" });
}
$$("a[href='#track'], a[href='#report']").forEach(link => link.addEventListener("click", event => {
  event.preventDefault();
  if (link.getAttribute("href") === "#track") scrollToTrack(); else scrollToReport();
}));

/* ---------------- 场景选择 ---------------- */
function renderPicker() {
  $("#scenarioPicker").innerHTML = scenarios.map(s => `
    <button type="button" class="picker-item ${selected && selected.code === s.code ? "is-active" : ""}"
      data-code="${esc(s.code)}" style="--sc:${esc(s.color)}">
      <span class="picker-top">
        <span class="picker-icon">${esc(s.icon)}</span>
        <span><h3>${esc(s.name)}</h3><span class="cat">${esc(s.categoryName)}</span></span>
      </span>
      <p>${esc(s.summary)}</p>
      <span class="picker-meta">
        <span class="chip">处置时限 ${s.slaHours}h</span>
        ${s.isEmergency ? '<span class="chip emergency">应急优先</span>' : ""}
        ${s.requiresPhoto ? '<span class="chip photo">需现场照片</span>' : ""}
      </span>
    </button>`).join("");
  $$(".picker-item").forEach(item => item.addEventListener("click", () => selectScenario(item.dataset.code)));
}

function selectScenario(code) {
  selected = scenarios.find(s => s.code === code) || null;
  renderPicker();
  if (!selected) return;
  document.title = `${selected.name} · 校园公共卫生管理平台`;
  document.querySelector('.brand-text strong').textContent = `校园公共卫生 · ${selected.name}`;
  const url = new URL(location.href); url.searchParams.set('scenario', selected.code); history.replaceState(null, '', url);
  document.querySelector('[name="title"]').placeholder = `填写${selected.name}事项标题`;
  document.querySelector('[name="location"]').placeholder = '填写该事项发生的楼栋、房间或公共区域';
  $("#formCard").hidden = false;
  $("#submitBanner").hidden = true;
  $("#tplBadge").textContent = selected.icon + " " + selected.name;
  $("#tplSummary").textContent = selected.summary;
  $("#slaStrip").innerHTML = `该场景承诺 <b>${selected.acceptSlaHours} 小时</b>内受理、总处置时限 <b>${selected.slaHours} 小时</b>；
    到期前 <b>${selected.reminderLeadHours} 小时</b>自动提醒承办人，超期后自动升级督办。${selected.requiresPhoto ? " 提交时<b>必须上传现场照片</b>。" : ""}`;
  $("#photoHint").textContent = selected.requiresPhoto ? "（必填）" : "（选填）";
  $("#photoInput").required = selected.requiresPhoto;
  renderDynamicFields();
  $("#formCard").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderDynamicFields() {
  if (!selected) return;
  $("#dynamicFields").innerHTML = selected.fields.map(field => {
    const required = field.required ? "<em>*</em>" : "";
    const name = `field_${esc(field.key)}`;
    if (field.type === "select") {
      const options = (field.options || []).map(opt => `<option value="${esc(opt)}">${esc(opt)}</option>`).join("");
      return `<label>${esc(field.label)} ${required}
        <select name="${name}" ${field.required ? "required" : ""}><option value="">请选择</option>${options}</select></label>`;
    }
    if (field.type === "textarea") {
      return `<label class="col-2">${esc(field.label)} ${required}
        <textarea name="${name}" rows="2" maxlength="200" ${field.required ? 'required' : ''} placeholder="${esc(field.placeholder || "")}"></textarea></label>`;
    }
    const type = field.type === "number" ? "number" : "text";
    return `<label>${esc(field.label)} ${required}
      <input type="${type}" name="${name}" maxlength="200" placeholder="${esc(field.placeholder || "")}" ${field.required ? "required" : ""}></label>`;
  }).join("");
}

$("#changeScenario").addEventListener("click", () => {
  $("#formCard").hidden = true;
  $("#scenarioPicker").scrollIntoView({ behavior: "smooth", block: "start" });
});

/* ---------------- 照片 ---------------- */
function clearPhoto() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  $("#photoImage").removeAttribute("src");
  $("#photoPreview").hidden = true;
}
$("#photoInput").addEventListener("change", () => {
  clearPhoto();
  const file = $("#photoInput").files[0];
  if (!file) return;
  if (!PHOTO_TYPES.has(file.type) || file.size === 0 || file.size > MAX_PHOTO_BYTES) {
    $("#photoInput").value = "";
    toast("请选择 5MB 以内的 JPG、PNG 或 WebP 图片");
    return;
  }
  previewUrl = URL.createObjectURL(file);
  $("#photoImage").src = previewUrl;
  $("#photoPreview").hidden = false;
});
$("#removePhoto").addEventListener("click", () => { $("#photoInput").value = ""; clearPhoto(); });

/* ---------------- 提交 ---------------- */
$("#reportForm").addEventListener("submit", async event => {
  event.preventDefault();
  if (!selected) { toast("请先选择报备场景"); return; }
  const button = $("#submitBtn");
  const payload = new FormData(event.currentTarget);
  payload.set("template", selected.code);
  if (!$("#photoInput").files.length) payload.delete("photo");
  button.disabled = true;
  button.textContent = "正在提交…";
  try {
    const data = await api("/api/v1/matters/", { method: "POST", headers: { "X-CSRFToken": csrf() }, body: payload });
    rememberCode(data.matter.code);
    renderSubmitted(data.matter);
    $("#trackInput").value = data.matter.code;
    await queryTrack();
    toast("报备已提交，事项编号已生成");
    scrollToTrack();
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "提交报备";
  }
});

function renderSubmitted(matter) {
  $("#submitBanner").hidden = false;
  $("#submitBanner").innerHTML = `
    <div class="sb-head">
      <span class="result-check" aria-hidden="true">✓</span>
      <div>
        <b>报备已提交，事项已进入跟踪流程</b>
        <span>编号 <strong>${esc(matter.code)}</strong> · ${esc(matter.templateIcon)} ${esc(matter.templateName)} · 应在 ${esc(matter.dueAt || "—")} 前办结</span>
      </div>
    </div>
    <div class="point-actions">
      <button type="button" class="btn" id="copyCode">复制编号</button>
      <button type="button" class="btn primary" id="viewTrackBtn">查看办理进度</button>
    </div>`;
  $("#copyCode").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(matter.code);
      toast("编号已复制：" + matter.code);
    } catch (_) { toast("请手动记录编号：" + matter.code); }
  });
  $("#viewTrackBtn").addEventListener("click", scrollToTrack);
  // 表单复位，便于立即填报下一个事项（编号已记忆并在下方进度区展示）
  $("#reportForm").reset();
  clearPhoto();
}

/* ---------------- 编号记忆 ---------------- */
function readCodes() {
  try {
    const value = JSON.parse(localStorage.getItem(CODES_KEY));
    return Array.isArray(value) ? value.filter(code => /^[A-Z]{2}-\d{8}-\d{4}$/.test(code)).slice(0, 12) : [];
  } catch (_) { return []; }
}
function rememberCode(code) {
  const codes = [code, ...readCodes().filter(item => item !== code)].slice(0, 12);
  localStorage.setItem(CODES_KEY, JSON.stringify(codes));
  renderMyCodes();
}
function renderMyCodes() {
  const codes = readCodes();
  $("#myCodes").innerHTML = codes.map(code => `<button type="button" class="code-chip" data-code="${esc(code)}">${esc(code)}</button>`).join("");
  $("#myCodesHint").textContent = codes.length ? "本机最近提交的编号（点击即可查询）：" : "本机暂无提交记录，请手动输入编号。";
  $$("#myCodes .code-chip").forEach(chip => chip.addEventListener("click", () => {
    $("#trackInput").value = chip.dataset.code;
    queryTrack();
  }));
}

/* ---------------- 进度查询（与报备同一页面） ---------------- */
async function queryTrack() {
  const code = $("#trackInput").value.trim();
  if (!code) { toast("请输入事项编号"); return; }
  $("#trackBtn").disabled = true;
  try {
    const matter = await api(`/api/v1/track/?code=${encodeURIComponent(code)}`);
    $("#trackResultCard").hidden = false;
    $("#trackCode").textContent = matter.code;
    $("#trackTitle").textContent = matter.title;
    $("#trackStamp").textContent = `${matter.statusName}${matter.isOverdue ? " · 已超期" : ""} · 承办 ${matter.handler || "尚未分派"}`;
    $("#trackDetail").innerHTML = detailHtml(matter);
  } catch (error) {
    $("#trackResultCard").hidden = true;
    toast(error.message);
  } finally {
    $("#trackBtn").disabled = false;
  }
}
$("#trackBtn").addEventListener("click", queryTrack);
$("#trackInput").addEventListener("keydown", event => { if (event.key === "Enter") queryTrack(); });

/* ---------------- 详情渲染（步进器 + 时限 + 提醒 + 轨迹） ---------------- */
function detailHtml(d) {
  const labelMap = {};
  (d.fields || []).forEach(field => { labelMap[field.key] = field.label; });
  const doneIndex = d.currentStageIndex;
  const stepper = d.stages.map((stage, index) => {
    const cls = d.status === "rejected" ? "" : (index < doneIndex ? "done" : (index === doneIndex ? "current" : ""));
    return `<div class="step ${cls}">
      <div class="step-rail"><span class="step-dot"></span>${index < d.stages.length - 1 ? '<span class="step-line"></span>' : ""}</div>
      <div class="step-body"><b>${esc(stage.name)}</b><span>${esc(stage.desc || "")}</span></div>
    </div>`;
  }).join("");
  const payload = Object.entries(d.payload || {}).map(([key, value]) =>
    `<div><span>${esc(labelMap[key] || key)}</span><b>${esc(value)}</b></div>`).join("") || `<div><span>场景问卷</span><b>—</b></div>`;
  const remaining = d.remainingHours === null ? "已办结"
    : (d.isOverdue ? `已超期 ${Math.abs(Math.round(d.remainingHours))} 小时` : `剩余 ${Math.round(d.remainingHours)} 小时`);
  const reminders = (d.reminders || []).map(item => `<li>
      <span class="tl-mark" style="background:${item.level === "warn" ? "var(--warn)" : "var(--danger)"}"></span>
      <span class="tl-txt"><b>[${esc(item.levelName)}] ${esc(item.title)}</b><span class="t">${esc(item.triggeredAt)}</span>
      <p>${esc(item.ruleName)} · ${item.status === "pending" ? "待响应" : "已确认"}</p></span></li>`).join("");
  const timeline = (d.timeline || []).map(event => `<li>
      <span class="tl-mark"></span>
      <span class="tl-txt"><b>${esc(event.kindName)}</b><span class="t">${esc(event.at)}</span>
      <p>${esc(event.note || "—")} · ${esc(event.actor)}</p></span></li>`).join("");
  return `
    <div class="stepper">${stepper}</div>
    <div class="detail-block">
      <h4>办理时限</h4>
      <div class="kv">
        <div><span>所属场景</span><b>${esc(d.templateIcon)} ${esc(d.templateName)}</b></div>
        <div><span>当前状态</span><b>${esc(d.statusName)}${d.isOverdue ? "（已超期）" : ""}</b></div>
        <div><span>报备时间</span><b>${esc(d.submittedAt)}</b></div>
        <div><span>处置到期</span><b>${esc(d.dueAt || "—")}</b></div>
        <div><span>时限占用</span><b>${esc(remaining)}</b></div>
        <div><span>承办单位</span><b>${esc(d.handler || "尚未分派")}</b></div>
      </div>
    </div>
    <div class="detail-block">
      <h4>报备内容</h4>
      <p style="font-size:12.5px;margin:0 0 9px;color:var(--ink-2)">${esc(d.detail || "无补充描述")}</p>
      <div class="kv">${payload}</div>
    </div>
    <div class="detail-block">
      <h4>自动提醒记录（${(d.reminders || []).length}）</h4>
      <ul class="tl">${reminders || '<li><span class="tl-txt"><p>暂无提醒记录，系统会在临近到期时自动生成。</p></span></li>'}</ul>
    </div>
    <div class="detail-block">
      <h4>办理轨迹 · 全程可追溯（${(d.timeline || []).length}）</h4>
      <ul class="tl">${timeline}</ul>
    </div>`;
}

/* ---------------- 初始化 ---------------- */
(async function init() {
  try {
    const data = await api("/api/v1/scenarios/");
    scenarios = data.scenarios;
    renderPicker();
    const sceneCode = new URLSearchParams(location.search).get('scenario');
    if (sceneCode) selectScenario(sceneCode);
  } catch (error) {
    $("#scenarioPicker").innerHTML = `<p class="empty">场景加载失败：${esc(error.message)}</p>`;
  }
  renderMyCodes();
  const hash = decodeURIComponent(location.hash.replace("#", ""));
  if (hash === "track") { scrollToTrack(); }
  else if (hash) { $("#trackInput").value = hash; queryTrack(); scrollToTrack(); }
})();
