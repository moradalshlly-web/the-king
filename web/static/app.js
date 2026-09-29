// MOROAI Web Interface - app.js (v2)

const chat = document.getElementById("chat");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const toolsChip = document.getElementById("tools-chip");
const statusPanel = document.getElementById("status-panel");
const drawer = document.getElementById("drawer");
const drawerToggle = document.getElementById("drawer-toggle");
const drawerClose = document.getElementById("drawer-close");
const overlay = document.getElementById("overlay");

let toolsOn = true;

// ---------- Drawer ----------
function openDrawer() {
  drawer.classList.add("open");
  overlay.classList.add("show");
}
function closeDrawer() {
  drawer.classList.remove("open");
  overlay.classList.remove("show");
}
drawerToggle.addEventListener("click", openDrawer);
drawerClose.addEventListener("click", closeDrawer);
overlay.addEventListener("click", closeDrawer);

// ---------- Welcome ----------
function renderWelcome() {
  chat.innerHTML = `
    <div class="welcome">
      <div class="welcome-orb">M</div>
      <h1>MOROAI</h1>
      <p class="tagline">الذكاء الاصطناعي المستقل · العربي · المجاني</p>
      <p class="subtag">اسأل، ابنِ، تعلّم — بلا حدود</p>
      <div class="suggestions">
        <button class="suggestion" data-p="من أنت وماذا تستطيع أن تفعل؟">
          <span class="ico">💬</span>
          <div class="t">تعرّف عليّ</div>
          <div class="d">من أنت وماذا تستطيع؟</div>
        </button>
        <button class="suggestion" data-p="اكتب لي دالة بايثون لحساب الأعداد الأولية">
          <span class="ico">🐍</span>
          <div class="t">برمجة بايثون</div>
          <div class="d">دالة لحساب الأعداد الأولية</div>
        </button>
        <button class="suggestion" data-p="ابحث لي في Reddit عن أحدث مواضيع الذكاء الاصطناعي">
          <span class="ico">🔍</span>
          <div class="t">بحث في Reddit</div>
          <div class="d">أحدث مواضيع الذكاء الاصطناعي</div>
        </button>
        <button class="suggestion" data-p="أنشئ لي ملف HTML لصفحة تسجيل دخول عربية فاخرة">
          <span class="ico">🎨</span>
          <div class="t">ابنِ صفحة HTML</div>
          <div class="d">صفحة تسجيل دخول عربية</div>
        </button>
      </div>
    </div>`;
  chat.querySelectorAll(".suggestion").forEach(b => {
    b.addEventListener("click", () => {
      input.value = b.dataset.p;
      send();
    });
  });
}

// ---------- Messages ----------
function addMessage(role, text, meta) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + (role === "user" ? "user" : "ai");

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "أنا" : "M";

  const bubbleWrap = document.createElement("div");
  bubbleWrap.className = "bubble-wrap";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  bubbleWrap.appendChild(bubble);

  if (meta) {
    const m = document.createElement("div");
    m.className = "meta";
    m.textContent = meta;
    bubbleWrap.appendChild(m);
  }

  wrap.appendChild(avatar);
  wrap.appendChild(bubbleWrap);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

function addLoading() {
  const wrap = document.createElement("div");
  wrap.className = "msg ai";
  wrap.innerHTML = `
    <div class="avatar">M</div>
    <div class="bubble-wrap">
      <div class="bubble">
        <div class="loading-dots"><span></span><span></span><span></span></div>
      </div>
    </div>`;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

// ---------- Send ----------
async function send() {
  const msg = input.value.trim();
  if (!msg) return;

  if (chat.querySelector(".welcome")) chat.innerHTML = "";
  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;

  addMessage("user", msg);
  const loading = addLoading();

  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, tools: toolsOn }),
    });
    const data = await r.json();
    loading.remove();

    if (data.ok) {
      const meta = `${data.provider} · ${data.model} · ${Math.round(data.latency_ms || 0)}ms`;
      addMessage("ai", data.reply, meta);
    } else {
      addMessage("ai", "⚠️ خطأ: " + (data.error || "غير معروف"));
    }
  } catch (e) {
    loading.remove();
    addMessage("ai", "⚠️ تعذّر الاتصال بالخادم: " + e.message);
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

// ---------- Status ----------
async function loadStatus() {
  try {
    const r = await fetch("/api/status");
    const d = await r.json();
    if (!d.ok) { statusPanel.textContent = "خطأ في الحالة"; return; }
    const p = Object.keys(d.providers || {}).join(" · ");
    statusPanel.innerHTML = `
      <div>👤 المالك: <b>${d.owner || "غير محدد"}</b></div>
      <div>🔌 المزودون: <b>${p || "—"}</b></div>
      <div>📚 الدروس: <b>${d.lessons || 0}</b></div>
      <div>💬 التفاعلات: <b>${d.episodes || 0}</b></div>`;
  } catch (e) {
    statusPanel.textContent = "تعذّر تحميل الحالة";
  }
}

// ---------- Events ----------
sendBtn.addEventListener("click", send);

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
});

toolsChip.addEventListener("click", () => {
  toolsOn = !toolsOn;
  toolsChip.classList.toggle("on", toolsOn);
  toolsChip.textContent = toolsOn ? "🛠 الأدوات" : "🛠 معطّلة";
});

// ---------- Init ----------
renderWelcome();
loadStatus();
input.focus();
