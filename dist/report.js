const RECEIPTS_KEY = "campus-mosquito-report-receipts-v1";
const form = document.querySelector("#reportForm");
const list = document.querySelector("#myReports");
const announce = document.querySelector("#announce");
const photoInput = document.querySelector("#reportPhoto");
const photoPreview = document.querySelector("#photoPreview");
const photoPreviewImage = document.querySelector("#photoPreviewImage");
let renderVersion = 0;
let previewUrl = null;
const PHOTO_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_PHOTO_BYTES = 5 * 1024 * 1024;

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = String(value ?? "");
  return node.innerHTML;
}

function loadReceipts() {
  try {
    const value = JSON.parse(localStorage.getItem(RECEIPTS_KEY));
    return Array.isArray(value) ? value.filter(id => /^[0-9a-f-]{36}$/i.test(id)) : [];
  } catch (_) { return []; }
}

function saveReceipts(ids) {
  localStorage.setItem(RECEIPTS_KEY, JSON.stringify(ids));
}

function csrfToken() {
  const item = document.cookie.split("; ").find(part => part.startsWith("csrftoken="));
  return item ? decodeURIComponent(item.slice("csrftoken=".length)) : "";
}

function notify(message) {
  announce.textContent = message;
  clearTimeout(notify.timeout);
  notify.timeout = setTimeout(() => { announce.textContent = ""; }, 3500);
}

function clearPhotoPreview() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  photoPreviewImage.removeAttribute("src");
  photoPreview.hidden = true;
}

photoInput.addEventListener("change", () => {
  clearPhotoPreview();
  const photo = photoInput.files[0];
  if (!photo) return;
  if (!PHOTO_TYPES.has(photo.type) || photo.size === 0 || photo.size > MAX_PHOTO_BYTES) {
    photoInput.value = "";
    notify("请选择不超过5MB的 JPG、PNG 或 WebP 照片");
    return;
  }
  previewUrl = URL.createObjectURL(photo);
  photoPreviewImage.src = previewUrl;
  photoPreview.hidden = false;
});

document.querySelector("#removePhoto").addEventListener("click", () => {
  photoInput.value = "";
  clearPhotoPreview();
});

async function renderReports() {
  const version = ++renderVersion;
  const ids = loadReceipts().slice(0, 50);
  if (!ids.length) {
    list.innerHTML = `<p class="empty-reports">还没有本机提交的线索。可以在上方填一条虚构演示线索试试。</p>`;
    return;
  }
  list.innerHTML = `<p class="empty-reports">正在从演示后台查询进度…</p>`;
  const results = await Promise.all(ids.map(async id => {
    try {
      const response = await fetch(`/api/reports/${encodeURIComponent(id)}/`, { credentials: "same-origin" });
      return response.ok ? await response.json() : null;
    } catch (_) { return null; }
  }));
  if (version !== renderVersion) return;
  const reports = results.filter(Boolean).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
  list.innerHTML = reports.length ? reports.map(item => {
    const label = { pending: "待核查", checking: "核查中", resolved: "已处理" }[item.status] || "待核查";
    return `<article class="mini-report"><div><b>${escapeHtml(item.location)}</b><span class="mini-status">${label}</span></div><p>${escapeHtml(item.type)}</p>${item.hasPhoto ? `<p>已附现场照片</p>` : ""}${item.processingNote ? `<p class="processing-note">处理说明：${escapeHtml(item.processingNote)}</p>` : ""}<small>${escapeHtml(String(item.createdAt || "").replace("T", " "))}</small></article>`;
  }).join("") : `<p class="empty-reports">暂时无法查询已保存的线索，请确认 Django 演示服务器正在运行。</p>`;
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const location = document.querySelector("#reportLocation").value.trim();
  const type = document.querySelector("#reportType").value;
  const detail = document.querySelector("#reportDetail").value.trim();
  if (!location || !type) return;
  const payload = new FormData(form);
  payload.set("location", location);
  payload.set("type", type);
  payload.set("detail", detail);
  if (!photoInput.files.length) payload.delete("photo");
  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  try {
    const response = await fetch("/api/reports/", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken() },
      body: payload,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || "提交失败，请确认从 Django 演示地址打开页面");
    saveReceipts([data.id, ...loadReceipts().filter(id => id !== data.id)]);
    form.reset();
    clearPhotoPreview();
    await renderReports();
    notify("线索已提交到演示后台");
    document.querySelector("#mineTitle").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    notify(error.message || "提交失败，请稍后重试");
  } finally {
    submitButton.disabled = false;
  }
});

window.addEventListener("focus", renderReports);
window.addEventListener("storage", event => { if (event.key === RECEIPTS_KEY) renderReports(); });
renderReports();
