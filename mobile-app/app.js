let copierEnabled = true;
let currentChannels = {};
let pollTimer = null;

function getConfig() {
  return {
    dbUrl: (localStorage.getItem("tg_copier_db_url") || "").trim().replace(/\/+$/, ""),
    userId: (localStorage.getItem("tg_copier_user_id") || "DEMO_USER_01").trim(),
  };
}

function saveConnection() {
  const dbUrl = document.getElementById("dbUrl").value.trim().replace(/\/+$/, "");
  const userId = document.getElementById("userId").value.trim() || "DEMO_USER_01";
  if (!dbUrl) {
    alert("يرجى إدخال رابط Firebase Database أولاً.");
    return;
  }
  localStorage.setItem("tg_copier_db_url", dbUrl);
  localStorage.setItem("tg_copier_user_id", userId);
  refreshAll();
}

function basePath(subPath = "") {
  const { dbUrl, userId } = getConfig();
  if (!dbUrl) return null;
  const clean = subPath.replace(/^\/+/, "");
  return `${dbUrl}/users/${encodeURIComponent(userId)}/${clean}.json`;
}

function renderCopierButton() {
  const btn = document.getElementById("toggleCopierBtn");
  if (copierEnabled) {
    btn.textContent = "مفعّل";
    btn.className = "px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white transition";
  } else {
    btn.textContent = "متوقف";
    btn.className = "px-4 py-2 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white transition";
  }
}

async function toggleCopier() {
  copierEnabled = !copierEnabled;
  renderCopierButton();
  await saveSettings();
}

async function saveSettings() {
  const url = basePath("settings");
  if (!url) return;
  const lotSize = parseFloat(document.getElementById("lotSizeInput").value) || 0.01;
  await fetch(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: copierEnabled, lot_size: lotSize }),
  });
}

async function addChannel() {
  const urlBase = getConfig().dbUrl;
  if (!urlBase) {
    alert("يرجى حفظ رابط Firebase أولاً.");
    return;
  }
  const title = document.getElementById("chTitle").value.trim() || "قناة توصيات";
  const chatId = document.getElementById("chId").value.trim();
  const defaultSymbol = document.getElementById("chDefaultSymbol").value.trim() || null;

  if (!chatId) {
    alert("يرجى إدخال Chat ID للقناة.");
    return;
  }

  const chUrl = basePath(`channels/${encodeURIComponent(chatId)}`);
  await fetch(chUrl, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      chat_id: Number(chatId) || chatId,
      default_symbol: defaultSymbol,
      enabled: true,
    }),
  });

  document.getElementById("chTitle").value = "";
  document.getElementById("chId").value = "";
  document.getElementById("chDefaultSymbol").value = "";
  refreshAll();
}

async function toggleChannel(chatId, nextState) {
  const chUrl = basePath(`channels/${encodeURIComponent(chatId)}`);
  await fetch(chUrl, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: nextState }),
  });
  refreshAll();
}

function renderChannels(channels = {}) {
  currentChannels = channels || {};
  const container = document.getElementById("channelsList");
  const keys = Object.keys(currentChannels);

  if (!keys.length) {
    container.innerHTML = `<p class="text-xs text-slate-500 text-center">لا توجد قنوات مضافة بعد</p>`;
    return;
  }

  container.innerHTML = keys.map((key) => {
    const ch = currentChannels[key] || {};
    const active = ch.enabled !== false;
    const symText = ch.default_symbol ? `رمز افتراضي: ${ch.default_symbol}` : "الرمز من النص";
    return `
      <div class="flex items-center justify-between bg-slate-950 border border-slate-800 rounded-xl p-3">
        <div>
          <div class="text-xs font-bold text-slate-100">${ch.title || key}</div>
          <div class="text-[11px] text-slate-400">${key} • ${symText}</div>
        </div>
        <button onclick="toggleChannel('${key}', ${!active})"
          class="px-3 py-1.5 rounded-lg text-[11px] font-bold ${active ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-400"}">
          ${active ? "نشط" : "معطّل"}
        </button>
      </div>
    `;
  }).join("");
}

function renderBridgeBadge(status = {}) {
  const badge = document.getElementById("bridgeBadge");
  if (!status || !status.online) {
    badge.textContent = "اللابتوب غير متصل";
    badge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-rose-950 text-rose-300 border border-rose-800";
    return;
  }
  if (status.mt5_connected) {
    badge.textContent = "متصل • MT5 جاهز";
    badge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800";
  } else {
    badge.textContent = "متصل • بانتظار MT5";
    badge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-amber-950 text-amber-300 border border-amber-800";
  }
}

function renderExecutions(executions = {}) {
  const container = document.getElementById("executionsList");
  const items = Object.values(executions || {}).slice(-8).reverse();
  if (!items.length) {
    container.innerHTML = `<p class="text-slate-500 text-center">لا توجد عمليات مسجلة بعد</p>`;
    return;
  }

  container.innerHTML = items.map((item) => {
    const ok = Boolean(item.success);
    return `
      <div class="bg-slate-950 border border-slate-800 rounded-xl p-2.5 flex items-center justify-between">
        <div>
          <span class="font-bold ${ok ? "text-emerald-400" : "text-rose-400"}">
            ${item.symbol || "-"} ${item.action || ""}
          </span>
          <span class="text-slate-400">(${item.lot || ""} lot)</span>
          <div class="text-[11px] text-slate-500">${item.message || ""}</div>
        </div>
        <span class="text-[11px] font-semibold ${ok ? "text-emerald-400" : "text-rose-400"}">
          ${ok ? "تم" : "فشل"}
        </span>
      </div>
    `;
  }).join("");
}

async function refreshAll() {
  const rootUrl = basePath("");
  if (!rootUrl) return;
  try {
    const res = await fetch(rootUrl);
    if (!res.ok) return;
    const data = await res.json();
    if (!data) return;

    if (data.settings) {
      copierEnabled = data.settings.enabled !== false;
      renderCopierButton();
      if (typeof data.settings.lot_size === "number") {
        document.getElementById("lotSizeInput").value = data.settings.lot_size;
      }
    }
    renderBridgeBadge(data.bridge_status);
    renderChannels(data.channels);
    renderExecutions(data.executions);
  } catch (e) {
    // تجاهل أخطاء الشبكة العابرة
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const cfg = getConfig();
  document.getElementById("dbUrl").value = cfg.dbUrl;
  document.getElementById("userId").value = cfg.userId;
  renderCopierButton();
  refreshAll();
  pollTimer = setInterval(refreshAll, 4000);
});
