/* ==========================================================================
   MOROAI App — Frontend Logic
   ========================================================================== */

(function () {
"use strict";

// ───────────────────────────────────────────────
// Config
// ───────────────────────────────────────────────
const API = {
    chat:      "/api/moro/chat",
    status:    "/api/status",
    history:   "/api/history",
    models:    "/api/models",
    import:    "/api/import",
    search:    "/api/search",
};

const LS_KEYS = {
    theme: "moroai_theme",
    style: "moroai_style",
};

// ───────────────────────────────────────────────
// State
// ───────────────────────────────────────────────
const state = {
    busy: false,
    streaming: null,   // controller
    theme: localStorage.getItem(LS_KEYS.theme) || "purple",
    style: localStorage.getItem(LS_KEYS.style) || "detailed",
    attachments: [],
    session: [],
};

// ───────────────────────────────────────────────
// DOM refs
// ───────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const els = {};

function cacheDom() {
    els.body          = document.body;
    els.chatFeed      = $("chat-feed");
    els.welcomeCard   = $("welcome-card");
    els.composerInput = $("composer-input");
    els.sendBtn       = $("send-btn");
    els.attachBtn     = $("attach-btn");
    els.micBtn        = $("mic-btn");
    els.menuBtn       = $("menu-btn");
    els.themeBtn      = $("theme-btn");
    els.searchBtn     = $("search-btn");
    els.profileBtn    = $("profile-btn");
    els.drawer        = $("drawer");
    els.drawerClose   = $("drawer-close");
    els.drawerStatus  = $("drawer-status");
    els.previewPane   = $("preview-pane");
    els.previewTitle  = $("preview-title");
    els.previewContent= $("preview-content");
    els.mainSplit     = document.querySelector(".main-split");
    els.themeModal    = $("theme-modal");
    els.importModal   = $("import-modal");
    els.searchModal   = $("search-modal");
    els.bottomSheet   = $("bottom-sheet");
    els.sheetBody     = $("sheet-body");
    els.sheetTitle    = $("sheet-title");
    els.sheetClose    = $("sheet-close");
    els.modeIndicator = $("mode-indicator");
    els.voiceBar      = $("voice-bar");
    els.voiceStatus   = $("voice-status");
    els.voiceTimer    = $("voice-timer");
    els.voiceStop     = $("voice-stop");
    els.attachments   = $("attachments");
}

// ───────────────────────────────────────────────
// Theme
// ───────────────────────────────────────────────
function applyTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(LS_KEYS.theme, theme);
    const meta = document.querySelector('meta[name="theme-color"]');
    const colors = { purple: "#7c3aed", gold: "#d97706", emerald: "#059669", ruby: "#e11d48" };
    if (meta && colors[theme]) meta.setAttribute("content", colors[theme]);
    document.querySelectorAll(".theme-option").forEach(el => {
        el.classList.toggle("active", el.dataset.theme === theme);
    });
}

// ───────────────────────────────────────────────
// Style (detailed / brief / friendly)
// ───────────────────────────────────────────────
function applyStyle(style) {
    state.style = style;
    localStorage.setItem(LS_KEYS.style, style);
    const labels = { detailed: "🎯 مفصّل", brief: "⚡ مختصر", friendly: "😊 صديق" };
    if (els.modeIndicator) els.modeIndicator.textContent = labels[style] || style;
}

function cycleStyle() {
    const order = ["detailed", "brief", "friendly"];
    const i = order.indexOf(state.style);
    applyStyle(order[(i + 1) % order.length]);
}

// ───────────────────────────────────────────────
// Drawer / Modals / Sheet
// ───────────────────────────────────────────────
function openDrawer() { els.drawer.classList.add("open"); }
function closeDrawer() { els.drawer.classList.remove("open"); }

function openModal(id) {
    const m = $(id);
    if (m) m.hidden = false;
}
function closeModal(id) {
    const m = $(id);
    if (m) m.hidden = true;
}
function closeAllModals() {
    document.querySelectorAll(".modal").forEach(m => m.hidden = true);
}

function openSheet(title, content) {
    if (els.sheetTitle) els.sheetTitle.textContent = title;
    if (els.sheetBody) els.sheetBody.innerHTML = content;
    els.bottomSheet.classList.add("open");
    els.bottomSheet.setAttribute("aria-hidden", "false");
}
function closeSheet() {
    els.bottomSheet.classList.remove("open");
    els.bottomSheet.setAttribute("aria-hidden", "true");
}

// ───────────────────────────────────────────────
// Preview
// ───────────────────────────────────────────────
function setPreview(title, html) {
    els.previewTitle.textContent = title || "الورشة";
    els.previewContent.innerHTML = html;
    els.mainSplit.classList.add("has-preview");
    // On mobile, use bottom sheet
    if (window.innerWidth < 1024) {
        openSheet(title || "المعاينة", html);
    }
}
function clearPreview() {
    els.mainSplit.classList.remove("has-preview");
    els.previewContent.innerHTML = `
        <div class="preview-empty">
            <div class="preview-empty-icon">✨</div>
            <p>المعاينة ستظهر هنا حسب المهمة</p>
            <p class="text-muted" style="font-size:.85rem;">
                صور، صوت، 3D، كود، تقارير...
            </p>
        </div>`;
}

// ───────────────────────────────────────────────
// Chat — messages
// ───────────────────────────────────────────────
function hideWelcome() {
    if (els.welcomeCard) els.welcomeCard.style.display = "none";
}

function addMessage(role, text) {
    hideWelcome();
    const wrap = document.createElement("div");
    wrap.className = "msg " + (role === "user" ? "user" : "ai");

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const now = new Date().toLocaleTimeString("ar", { hour: "2-digit", minute: "2-digit" });
    meta.textContent = (role === "user" ? "أنت" : "MOROAI") + " · " + now;

    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.textContent = text;

    wrap.appendChild(meta);
    wrap.appendChild(bubble);
    els.chatFeed.appendChild(wrap);
    scrollToBottom();
    return bubble;
}

function scrollToBottom() {
    els.chatFeed.scrollTop = els.chatFeed.scrollHeight;
}

function showThinking() {
    hideWelcome();
    let pill = document.getElementById("active-thinking");
    if (!pill) {
        pill = document.createElement("div");
        pill.id = "active-thinking";
        pill.className = "thinking-pill";
        els.chatFeed.appendChild(pill);
    }
    pill.textContent = "🧠 أفكر...";
    scrollToBottom();
    return pill;
}

function updateThinking(text) {
    const pill = document.getElementById("active-thinking");
    if (pill) pill.textContent = text;
}

function clearThinking() {
    const pill = document.getElementById("active-thinking");
    if (pill) pill.remove();
}

// ───────────────────────────────────────────────
// Chat — sending
// ───────────────────────────────────────────────
async function sendMessage(text) {
    if (!text || !text.trim() || state.busy) return;
    text = text.trim();
    state.busy = true;
    els.sendBtn.disabled = true;

    addMessage("user", text);
    state.session.push({ role: "user", text });
    els.composerInput.value = "";
    autoResize();

    const pill = showThinking();
    const stages = ["🧠 أفكر...", "📐 أخطط...", "🔍 أدقّق...", "⚙️ أنفّذ..."];
    let stageIdx = 0;
    const stageTimer = setInterval(() => {
        stageIdx = (stageIdx + 1) % stages.length;
        updateThinking(stages[stageIdx]);
    }, 900);

    try {
        const res = await fetch(API.chat, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: text,
                style: state.style,
                tools: true,
            }),
        });
        const data = await res.json();
        clearInterval(stageTimer);
        clearThinking();

        if (data.ok && data.reply) {
            addMessage("ai", data.reply);
            state.session.push({ role: "ai", text: data.reply });

            // Handle preview hints from backend
            if (data.preview) {
                setPreview(data.preview.title || "المعاينة",
                           data.preview.html || "");
            }
        } else {
            addMessage("ai", "❌ " + (data.error || "خطأ غير معروف"));
        }
    } catch (e) {
        clearInterval(stageTimer);
        clearThinking();
        addMessage("ai", "❌ تعذّر الاتصال بـ MOROAI: " + e.message);
    } finally {
        state.busy = false;
        els.sendBtn.disabled = false;
        autoResize();
    }
}

function autoResize() {
    const t = els.composerInput;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 200) + "px";
}

// ───────────────────────────────────────────────
// Attachments
// ───────────────────────────────────────────────
function renderAttachments() {
    if (!els.attachments) return;
    if (!state.attachments.length) {
        els.attachments.hidden = true;
        return;
    }
    els.attachments.hidden = false;
    els.attachments.innerHTML = state.attachments.map((a, i) => `
        <div class="badge badge-accent">
            ${a.name}
            <button class="icon-btn small" data-remove="${i}">✕</button>
        </div>
    `).join("");
    els.attachments.querySelectorAll("[data-remove]").forEach(btn => {
        btn.addEventListener("click", () => {
            state.attachments.splice(parseInt(btn.dataset.remove), 1);
            renderAttachments();
        });
    });
}

// ───────────────────────────────────────────────
// Voice (basic)
// ───────────────────────────────────────────────
let voiceTimer = null;
let voiceSecs = 0;

function toggleVoice() {
    if (voiceTimer) {
        clearInterval(voiceTimer);
        voiceTimer = null;
        els.voiceBar.hidden = true;
        return;
    }
    els.voiceBar.hidden = false;
    voiceSecs = 0;
    els.voiceTimer.textContent = "0:00";
    voiceTimer = setInterval(() => {
        voiceSecs++;
        const m = Math.floor(voiceSecs / 60);
        const s = String(voiceSecs % 60).padStart(2, "0");
        els.voiceTimer.textContent = m + ":" + s;
    }, 1000);
}

// ───────────────────────────────────────────────
// Import
// ───────────────────────────────────────────────
async function importModel() {
    const input = $("import-model-input");
    const results = $("import-model-results");
    if (!input || !results) return;
    const value = input.value.trim();
    if (!value) return;
    results.innerHTML = "<p class='text-muted'>⏳ جاري الفحص...</p>";
    try {
        const res = await fetch(API.import, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ kind: "model", target: value }),
        });
        const data = await res.json();
        results.innerHTML = data.ok
            ? `<p>✅ ${data.message || "تم الاستيراد"}</p>`
            : `<p>❌ ${data.error || "فشل"}</p>`;
    } catch (e) {
        results.innerHTML = `<p>❌ ${e.message}</p>`;
    }
}

// ───────────────────────────────────────────────
// Status
// ───────────────────────────────────────────────
async function refreshStatus() {
    if (!els.drawerStatus) return;
    try {
        const res = await fetch(API.status);
        const d = await res.json();
        if (!d.ok) throw new Error(d.error || "?");
        const providers = Object.keys(d.providers || {}).length;
        els.drawerStatus.textContent =
            `${providers} مزودين · ${d.episodes || 0} حلقة · ${d.lessons || 0} درس`;
    } catch (e) {
        els.drawerStatus.textContent = "تعذّر تحميل الحالة";
    }
}

// ───────────────────────────────────────────────
// Event wiring
// ───────────────────────────────────────────────
function wireEvents() {
    // Composer
    els.sendBtn.addEventListener("click", () => sendMessage(els.composerInput.value));
    els.composerInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage(els.composerInput.value);
        }
    });
    els.composerInput.addEventListener("input", autoResize);

    // Quick actions
    document.querySelectorAll(".chip[data-prompt]").forEach(chip => {
        chip.addEventListener("click", () => sendMessage(chip.dataset.prompt));
    });

    // Theme
    els.themeBtn.addEventListener("click", () => openModal("theme-modal"));
    document.querySelectorAll(".theme-option").forEach(el => {
        el.addEventListener("click", () => {
            applyTheme(el.dataset.theme);
            closeModal("theme-modal");
        });
    });

    // Mode indicator
    els.modeIndicator.addEventListener("click", cycleStyle);

    // Search
    els.searchBtn.addEventListener("click", () => {
        openModal("search-modal");
        const inp = $("omni-input");
        if (inp) { inp.value = ""; inp.focus(); }
    });

    // Drawer
    els.menuBtn.addEventListener("click", openDrawer);
    els.drawerClose.addEventListener("click", closeDrawer);
    els.drawer.querySelectorAll("a[data-action]").forEach(a => {
        a.addEventListener("click", (e) => {
            e.preventDefault();
            const action = a.dataset.action;
            handleDrawerAction(action);
            closeDrawer();
        });
    });

    // Profile
    els.profileBtn.addEventListener("click", () => openDrawer());

    // Modals close
    document.querySelectorAll("[data-close]").forEach(el => {
        el.addEventListener("click", () => {
            const modal = el.closest(".modal");
            if (modal) modal.hidden = true;
        });
    });

    // Attach / mic
    els.attachBtn.addEventListener("click", () => {
        openModal("import-modal");
    });
    els.micBtn.addEventListener("click", toggleVoice);
    els.voiceStop.addEventListener("click", toggleVoice);

    // Import tabs
    document.querySelectorAll(".tab").forEach(tab => {
        tab.addEventListener("click", () => {
            const name = tab.dataset.tab;
            document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
            tab.classList.add("active");
            const panel = document.querySelector(`.tab-panel[data-panel="${name}"]`);
            if (panel) panel.classList.add("active");
        });
    });
    const importBtn = $("import-model-btn");
    if (importBtn) importBtn.addEventListener("click", importModel);

    // Sheet close
    els.sheetClose.addEventListener("click", closeSheet);

    // Bottom sheet swipe (basic)
    let startY = null;
    els.bottomSheet.addEventListener("touchstart", (e) => {
        startY = e.touches[0].clientY;
    }, { passive: true });
    els.bottomSheet.addEventListener("touchmove", (e) => {
        if (startY === null) return;
        const dy = e.touches[0].clientY - startY;
        if (dy > 80) { closeSheet(); startY = null; }
    }, { passive: true });

    // Keyboard shortcuts
    window.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeAllModals();
            closeDrawer();
            closeSheet();
        }
        if (e.key === "/" && document.activeElement !== els.composerInput) {
            e.preventDefault();
            els.composerInput.focus();
        }
    });
}

// ───────────────────────────────────────────────
// Drawer actions
// ───────────────────────────────────────────────
function handleDrawerAction(action) {
    const map = {
        studio:      { title: "🎬 Studio",       msg: "🎬 استوديو الإنتاج — قريباً" },
        learn:       { title: "📚 Learn",        msg: "📚 منصة التعلّم — قريباً" },
        gamer:       { title: "🎮 Gamer",        msg: "🎮 بناء الألعاب — قريباً" },
        build:       { title: "🏗️ Build",        msg: "🏗️ بناء المشاريع — قريباً" },
        tools:       { title: "🔧 الأدوات",      msg: "🔧 قائمة الأدوات — قريباً" },
        agents:      { title: "🤖 الوكلاء",      msg: "🤖 الوكلاء — قريباً" },
        sources:     { title: "🌐 المصادر",      msg: "🌐 المصادر والمزودون — قريباً" },
        skills:      { title: "🎓 المهارات",     msg: "🎓 المهارات — قريباً" },
        sessions:    { title: "💬 الجلسات",      msg: "💬 الجلسات — قريباً" },
    };
    if (action === "models") {
        openModal("import-modal");
        return;
    }
    if (action === "projects") {
        openModal("import-modal");
        // switch to project tab
        const tab = document.querySelector('.tab[data-tab="project"]');
        if (tab) tab.click();
        return;
    }
    if (action === "insights") {
        fetch("/api/insights")
            .then(r => r.json())
            .then(d => {
                const summary = d.summary_ar || "لا توجد بيانات";
                setPreview("🧠 التحليل الذاتي",
                    "<pre style='white-space:pre-wrap;font-family:var(--font-mono);font-size:.85rem'>"
                    + summary + "</pre>");
            })
            .catch(() => setPreview("🧠 التحليل الذاتي", "<p>تعذّر التحميل</p>"));
        return;
    }
    if (action === "settings") {
        openModal("theme-modal");
        return;
    }
    const info = map[action];
    if (info) setPreview(info.title, `<p>${info.msg}</p>`);
}

// ───────────────────────────────────────────────
// Init
// ───────────────────────────────────────────────
function init() {
    cacheDom();
    applyTheme(state.theme);
    applyStyle(state.style);
    wireEvents();
    autoResize();
    refreshStatus();
    setInterval(refreshStatus, 30000);
}

document.addEventListener("DOMContentLoaded", init);

})();
