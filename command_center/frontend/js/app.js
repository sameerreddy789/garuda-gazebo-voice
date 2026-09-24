/* GarudaOne Disaster Response Command Center — frontend app */
(function () {
  const I = (n, c) => ICONS.icon(n, c);
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const NAV = [
    ["dashboard", "Dashboard", "Disaster Overview"],
    ["fleet", "Fleet", "Fleet Management"],
    ["missions", "Missions", "Mission Control"],
    ["victims", "Requests", "Emergency Requests"],
    ["alerts", "Alerts", "Disaster Alerts"],
    ["resources", "Resources", "Resource Management"],
    ["map", "Live Map", "Live Disaster Map"],
    ["analytics", "Analytics", "Mission Analytics"],
    ["activity", "Activity", "Live Activity Log"],
  ];
  const NAV_ICON = { dashboard: "dashboard", fleet: "fleet", missions: "mission",
    victims: "victim", alerts: "alert", resources: "resource", map: "map",
    analytics: "analytics", activity: "activity" };

  const state = {
    data: null, user: null, panel: "dashboard",
    charts: {}, map: null, layers: {}, lastLogId: 0, notifications: [],
    fleetType: "all", fleetQuery: "",
  };

  /* ---------------------------------------------------- style helpers */
  const SEV = {
    critical: "text-rose-600 bg-rose-100 dark:text-rose-300 dark:bg-rose-950/60 border-rose-200 dark:border-rose-900",
    high: "text-orange-600 bg-orange-100 dark:text-orange-300 dark:bg-orange-950/60 border-orange-200 dark:border-orange-900",
    medium: "text-amber-600 bg-amber-100 dark:text-amber-300 dark:bg-amber-950/50 border-amber-200 dark:border-amber-900",
    low: "text-emerald-600 bg-emerald-100 dark:text-emerald-300 dark:bg-emerald-950/50 border-emerald-200 dark:border-emerald-900",
  };
  const STATUS = {
    active: "text-emerald-600 bg-emerald-100 dark:text-emerald-300 dark:bg-emerald-950/50",
    charging: "text-amber-600 bg-amber-100 dark:text-amber-300 dark:bg-amber-950/50",
    idle: "text-sky-600 bg-sky-100 dark:text-sky-300 dark:bg-sky-950/50",
    offline: "text-slate-500 bg-slate-200 dark:text-slate-400 dark:bg-slate-800",
    maintenance: "text-purple-600 bg-purple-100 dark:text-purple-300 dark:bg-purple-950/50",
    pending: "text-slate-600 bg-slate-200 dark:text-slate-300 dark:bg-slate-800",
    assigned: "text-sky-600 bg-sky-100 dark:text-sky-300 dark:bg-sky-950/50",
    in_progress: "text-brand-600 bg-sky-100 dark:text-brand-500 dark:bg-sky-950/50",
    delayed: "text-orange-600 bg-orange-100 dark:text-orange-300 dark:bg-orange-950/50",
    completed: "text-emerald-600 bg-emerald-100 dark:text-emerald-300 dark:bg-emerald-950/50",
    cancelled: "text-slate-500 bg-slate-200 dark:text-slate-400 dark:bg-slate-800",
    rescued: "text-emerald-600 bg-emerald-100 dark:text-emerald-300 dark:bg-emerald-950/50",
    accepted: "text-sky-600 bg-sky-100 dark:text-sky-300 dark:bg-sky-950/50",
    rejected: "text-rose-600 bg-rose-100 dark:text-rose-300 dark:bg-rose-950/50",
    acknowledged: "text-slate-500 bg-slate-200 dark:text-slate-400 dark:bg-slate-800",
    resolved: "text-emerald-600 bg-emerald-100 dark:text-emerald-300 dark:bg-emerald-950/50",
  };
  const TYPE_ICON = { drone: "drone", medical: "medical", ground: "robot" };
  const ALERT_ICON = { building_collapse: "shield", fire: "zap", flood: "wind",
    aftershock: "activity", gas_leak: "alert", road_blocked: "close", comms_failure: "signal" };

  function badge(txt, cls) {
    return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border border-transparent ${cls}">${esc(txt)}</span>`;
  }
  function sevBadge(s) { return badge((s || "").toUpperCase(), SEV[s] || SEV.low); }
  function statusBadge(s) { return badge((s || "").replace(/_/g, " "), STATUS[s] || STATUS.idle); }
  function batteryColor(p) {
    if (p >= 60) return "bg-emerald-500"; if (p >= 30) return "bg-amber-500";
    if (p >= 15) return "bg-orange-500"; return "bg-rose-500";
  }
  const fmtTime = (iso) => { try { return new Date(iso).toLocaleTimeString(); } catch (e) { return "--"; } };
  function ago(iso) {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return `${s | 0}s ago`; if (s < 3600) return `${(s / 60) | 0}m ago`;
    return `${(s / 3600) | 0}h ago`;
  }
  const logColor = { info: "bg-sky-500", success: "bg-emerald-500", warning: "bg-amber-500", critical: "bg-rose-500" };

  function toast(msg, kind = "info") {
    const colors = { info: "bg-slate-800 text-white", success: "bg-emerald-600 text-white",
      error: "bg-rose-600 text-white", warning: "bg-amber-500 text-white" };
    const t = document.createElement("div");
    t.className = `toast-in ${colors[kind] || colors.info} px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium max-w-xs`;
    t.textContent = msg;
    $("#toast-root").appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, 3000);
  }

  const isTyping = () => { const a = document.activeElement; return a && /INPUT|SELECT|TEXTAREA/.test(a.tagName); };

  /* ---------------------------------------------------- modal */
  function openModal(title, bodyHtml, onMount) {
    const root = $("#modal-root");
    root.innerHTML = `
      <div class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-black/50" data-close></div>
        <div class="relative w-full max-w-lg bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-white/10 max-h-[90vh] overflow-y-auto">
          <div class="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-white/10">
            <h3 class="font-bold">${esc(title)}</h3>
            <button data-close class="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer">${I("close", "w-5 h-5")}</button>
          </div>
          <div class="p-5">${bodyHtml}</div>
        </div>
      </div>`;
    root.querySelectorAll("[data-close]").forEach((e) => e.addEventListener("click", closeModal));
    if (onMount) onMount(root);
  }
  function closeModal() { $("#modal-root").innerHTML = ""; }

  /* ---------------------------------------------------- auth */
  function initStaticIcons() {
    $("#login-logo").innerHTML = I("shield", "w-6 h-6");
    $("#side-logo").innerHTML = I("shield", "w-5 h-5");
    $("#menu-btn").innerHTML = I("menu", "w-5 h-5");
    $("#theme-btn").innerHTML = document.documentElement.classList.contains("dark") ? I("sun", "w-5 h-5") : I("moon", "w-5 h-5");
    $("#logout-btn").innerHTML = I("logout", "w-5 h-5");
    $("#notif-btn").innerHTML = I("bell", "w-5 h-5");
    $("#fs-btn").innerHTML = I("fullscreen", "w-5 h-5");
  }

  async function doLogin(e) {
    e.preventDefault();
    const username = $("#username").value.trim();
    const password = $("#password").value;
    const role = $("#role").value;
    const remember = $("#remember").checked;
    try {
      const res = await API.login({ username, password, role, remember });
      localStorage.setItem("cc_token", res.token);
      localStorage.setItem("cc_user", JSON.stringify({ username: res.username, role: res.role }));
      state.user = { username: res.username, role: res.role };
      await enterApp();
    } catch (err) {
      const el = $("#login-error"); el.textContent = err.message || "Login failed"; el.classList.remove("hidden");
    }
  }

  function logout() {
    localStorage.removeItem("cc_token"); localStorage.removeItem("cc_user");
    if (window._sock) window._sock.close();
    location.reload();
  }

  /* ---------------------------------------------------- app bootstrap */
  async function enterApp() {
    $("#login-view").classList.add("hidden");
    $("#app-view").classList.remove("hidden");
    $("#user-name").textContent = state.user.username;
    $("#user-role").textContent = state.user.role;
    buildNav();
    try { const s = await API.snapshot(); setData(s); } catch (e) {}
    try { const sw = await API.swarm(); renderSwarmLink(sw); } catch (e) {}
    connectLive();
    setPanel("dashboard");
    startClock();
  }

  function renderSwarmLink(sw) {
    const dot = sw.garuda_available ? "bg-emerald-500" : "bg-amber-500";
    $("#swarm-link").innerHTML = `
      <div class="flex items-center gap-1.5">
        <span class="h-2 w-2 rounded-full ${dot}"></span>
        <span>Swarm link: <b>${esc(sw.mode)}</b></span>
      </div>
      <div class="mt-0.5 opacity-70">${sw.garuda_available ? "garuda stack linked" : "sim only"} · ${sw.drone_states ? sw.drone_states.length : 0} states</div>`;
  }

  function buildNav() {
    const nav = $("#nav");
    nav.innerHTML = NAV.map(([key, label]) => `
      <button data-panel="${key}" class="nav-item w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors duration-150 cursor-pointer">
        ${I(NAV_ICON[key], "w-5 h-5 shrink-0")}<span>${label}</span>
        ${key === "alerts" ? '<span id="nav-alert-count" class="ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-rose-500 text-white hidden"></span>' : ""}
        ${key === "victims" ? '<span id="nav-victim-count" class="ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-amber-500 text-white hidden"></span>' : ""}
      </button>`).join("");
    nav.querySelectorAll("[data-panel]").forEach((b) =>
      b.addEventListener("click", () => { setPanel(b.dataset.panel); closeSidebar(); }));
  }

  function setPanel(name) {
    // teardown heavy panels
    if (state.panel === "map" && state.map) { state.map.remove(); state.map = null; state.layers = {}; }
    if (state.panel === "analytics") { Object.values(state.charts).forEach((c) => c.destroy()); state.charts = {}; }
    state.panel = name;
    const meta = NAV.find((n) => n[0] === name);
    $("#panel-title").textContent = meta ? meta[2] : name;
    document.querySelectorAll(".nav-item").forEach((b) => {
      const on = b.dataset.panel === name;
      b.classList.toggle("bg-brand-600", on); b.classList.toggle("text-white", on);
      b.classList.toggle("dark:text-white", on); b.classList.toggle("hover:bg-brand-700", on);
    });
    renderPanel();
  }

  function renderPanel() {
    const map = { dashboard: renderDashboard, fleet: renderFleet, missions: renderMissions,
      victims: renderVictims, alerts: renderAlerts, resources: renderResources,
      map: renderMap, analytics: renderAnalytics, activity: renderActivity };
    (map[state.panel] || renderDashboard)();
  }

  /* ---------------------------------------------------- data + live */
  function setData(d) {
    state.data = d;
    // detect new logs for notifications
    const logs = d.activity || [];
    const fresh = logs.filter((l) => l.id > state.lastLogId);
    if (fresh.length && state.lastLogId > 0) {
      fresh.reverse().forEach((l) => {
        if (l.level === "critical" || l.level === "warning") {
          state.notifications.unshift(l);
        }
      });
      state.notifications = state.notifications.slice(0, 30);
      if (state.notifications.length) $("#notif-dot").classList.remove("hidden");
    }
    if (logs.length) state.lastLogId = Math.max(state.lastLogId, ...logs.map((l) => l.id));
    updateTopbar();
    updateNavCounts();
  }

  function connectLive() {
    const sock = new LiveSocket();
    window._sock = sock;
    sock.on("status", ({ connected }) => setWsStatus(connected))
      .on("snapshot", (m) => { setData(m); renderPanel(); })
      .on("tick", (m) => onTick(m));
    sock.connect();
  }

  function onTick(m) {
    setData(m);
    if (isTyping()) return; // don't disrupt typing / open forms
    if (state.panel === "map") { updateMapMarkers(); return; }
    if (state.panel === "analytics") { updateCharts(); return; }
    renderPanel();
  }

  function setWsStatus(connected) {
    const el = $("#ws-status"); if (!el) return;
    el.innerHTML = `<span class="h-2 w-2 rounded-full ${connected ? "bg-emerald-500 pulse-dot text-emerald-500" : "bg-rose-500"}"></span><span>${connected ? "LIVE" : "Reconnecting"}</span>`;
  }

  function updateTopbar() {
    const o = state.data && state.data.overview; if (!o) return;
    $("#severity-badge").innerHTML = sevBadge(o.severity ? o.severity.toLowerCase() : "low");
    $("#weather-chip").innerHTML = `${I("wind", "w-4 h-4")}<span>${esc(o.weather)}</span>`;
  }
  function updateNavCounts() {
    const o = state.data && state.data.overview; if (!o) return;
    const a = $("#nav-alert-count"), v = $("#nav-victim-count");
    if (a) { a.textContent = o.active_alerts; a.classList.toggle("hidden", !o.active_alerts); }
    if (v) { v.textContent = o.pending_victims; v.classList.toggle("hidden", !o.pending_victims); }
  }

  function startClock() {
    const upd = () => { const el = $("#clock"); if (el) el.textContent = new Date().toLocaleTimeString(); };
    upd(); clearInterval(window._clk); window._clk = setInterval(upd, 1000);
  }

  /* ==================================================== PANELS ==================================================== */
  const card = (inner, extra = "") =>
    `<div class="card-in bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-white/10 ${extra}">${inner}</div>`;

  function statCard(icon, label, value, accent) {
    return `<div class="card-in bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-white/10 p-4">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-slate-500 dark:text-slate-400">${label}</span>
        <span class="${accent}">${I(icon, "w-5 h-5")}</span>
      </div>
      <div class="mt-2 text-2xl font-extrabold tabular-nums">${value}</div>
    </div>`;
  }

  function renderDashboard() {
    const d = state.data; if (!d) return;
    const o = d.overview;
    const cards = [
      statCard("fleet", "Total Robots", o.total_robots, "text-slate-400"),
      statCard("check_circle", "Active Robots", o.active_robots, "text-emerald-500"),
      statCard("battery", "Charging", o.charging_robots, "text-amber-500"),
      statCard("signal", "Offline", o.offline_robots, "text-rose-500"),
      statCard("mission", "Emergency Missions", o.emergency_missions, "text-brand-500"),
      statCard("check", "Completed Missions", o.completed_missions, "text-emerald-500"),
      statCard("people", "Victims Rescued", o.victims_rescued, "text-sky-500"),
      statCard("medical", "Medical Deliveries", o.medical_deliveries, "text-rose-500"),
      statCard("drone", "Available Drones", o.available_drones, "text-brand-500"),
      statCard("battery", "Avg Battery", o.avg_battery + "%", "text-emerald-500"),
    ].join("");

    const zones = (d.zones || []).map((z) =>
      `<div class="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-800/50">
        <div><div class="text-sm font-semibold">${z.id}</div><div class="text-xs text-slate-500 dark:text-slate-400">${esc(z.name)}</div></div>
        ${sevBadge(z.severity)}</div>`).join("");

    const recent = (d.activity || []).slice(0, 7).map(logRow).join("");

    $("#content").innerHTML = `
      <div class="rounded-xl p-5 mb-5 bg-gradient-to-r from-rose-600 to-orange-500 text-white flex flex-wrap items-center gap-4 ${o.severity === "CRITICAL" ? "sos-flash" : ""}">
        <div class="shrink-0">${I("alert", "w-9 h-9")}</div>
        <div class="flex-1 min-w-[200px]">
          <div class="text-xs uppercase tracking-wide opacity-90">Current Disaster Severity</div>
          <div class="text-2xl font-extrabold">${esc(o.severity)}</div>
        </div>
        <div class="text-sm"><div class="opacity-90 flex items-center gap-1">${I("wind", "w-4 h-4")} Weather</div><div class="font-semibold">${esc(o.weather)}</div></div>
        <div class="text-sm"><div class="opacity-90 flex items-center gap-1">${I("map", "w-4 h-4")} Active Zones</div><div class="font-semibold">${o.active_zones}</div></div>
        <div class="text-sm"><div class="opacity-90 flex items-center gap-1">${I("clock", "w-4 h-4")} Local Time</div><div class="font-semibold tabular-nums">${new Date().toLocaleTimeString()}</div></div>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4 mb-5">${cards}</div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div class="lg:col-span-2">${card(`
          <div class="px-4 py-3 border-b border-slate-200 dark:border-white/10 font-semibold flex items-center gap-2">${I("activity", "w-4 h-4 text-brand-500")} Live Activity</div>
          <div class="divide-y divide-slate-100 dark:divide-white/5">${recent || '<div class="p-4 text-sm text-slate-500">No activity yet</div>'}</div>`)}</div>
        <div>${card(`
          <div class="px-4 py-3 border-b border-slate-200 dark:border-white/10 font-semibold flex items-center gap-2">${I("map", "w-4 h-4 text-brand-500")} Disaster Zones</div>
          <div class="p-3 space-y-2">${zones}</div>`)}</div>
      </div>`;
  }

  /* ---------------- Fleet ---------------- */
  function renderFleet() {
    const d = state.data; if (!d) return;
    $("#content").innerHTML = `
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <div class="relative flex-1 min-w-[200px]">
          <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">${I("search", "w-4 h-4")}</span>
          <input id="fleet-search" placeholder="Search robots, zones..." value="${esc(state.fleetQuery)}"
            class="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-900 text-sm outline-none focus:ring-2 focus:ring-brand-500" />
        </div>
        <div class="flex gap-1 bg-slate-200 dark:bg-slate-800 rounded-lg p-1">
          ${["all", "ground", "drone", "medical"].map((t) => `
            <button data-ftype="${t}" class="px-3 py-1.5 rounded-md text-xs font-semibold capitalize cursor-pointer transition-colors ${state.fleetType === t ? "bg-white dark:bg-slate-700 shadow" : "text-slate-500"}">${t}</button>`).join("")}
        </div>
      </div>
      <div id="fleet-grid" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"></div>`;
    $("#fleet-search").addEventListener("input", (e) => { state.fleetQuery = e.target.value; renderFleetGrid(); });
    $("#content").querySelectorAll("[data-ftype]").forEach((b) =>
      b.addEventListener("click", () => { state.fleetType = b.dataset.ftype; renderFleet(); }));
    renderFleetGrid();
  }

  function renderFleetGrid() {
    const grid = $("#fleet-grid"); if (!grid) return;
    const q = state.fleetQuery.toLowerCase();
    let robots = state.data.robots.filter((r) =>
      (state.fleetType === "all" || r.type === state.fleetType) &&
      (!q || (r.name + r.id + r.location.zone).toLowerCase().includes(q)));
    grid.innerHTML = robots.map(robotCard).join("") ||
      '<div class="text-sm text-slate-500 col-span-full py-8 text-center">No robots match.</div>';
    grid.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () =>
      onRobotAction(b.dataset.rid, b.dataset.act)));
  }

  function robotCard(r) {
    const paused = r.status === "idle";
    return `<div class="card-in bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-white/10 p-4">
      <div class="flex items-start gap-3">
        <div class="h-10 w-10 rounded-lg grid place-items-center bg-slate-100 dark:bg-slate-800 text-brand-500 shrink-0">${I(TYPE_ICON[r.type], "w-6 h-6")}</div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2"><span class="font-bold truncate">${esc(r.name)}</span>${statusBadge(r.status)}</div>
          <div class="text-xs text-slate-500 dark:text-slate-400">${r.id} · ${r.type} · ${r.location.zone}</div>
        </div>
      </div>
      <div class="mt-3">
        <div class="flex items-center justify-between text-xs mb-1">
          <span class="text-slate-500 dark:text-slate-400 flex items-center gap-1">${I("battery", "w-4 h-4")} Battery</span>
          <span class="font-semibold tabular-nums">${(r.battery || 0).toFixed(0)}%</span>
        </div>
        <div class="h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
          <div class="battery-fill h-full ${batteryColor(r.battery)}" style="width:${Math.max(0, Math.min(100, r.battery))}%"></div>
        </div>
      </div>
      <div class="grid grid-cols-2 gap-x-4 gap-y-1.5 mt-3 text-xs">
        <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Signal</span><span class="font-medium">${r.signal}%</span></div>
        <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Speed</span><span class="font-medium">${(r.speed||0).toFixed(1)} m/s</span></div>
        <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Temp</span><span class="font-medium">${(r.temperature||0).toFixed(0)}°C</span></div>
        <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Mission</span><span class="font-medium">${r.mission_id || "—"}</span></div>
        <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Operator</span><span class="font-medium truncate">${esc(r.operator || "—")}</span></div>
        <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">ETA</span><span class="font-medium">${r.eta_min ? r.eta_min + "m" : "—"}</span></div>
      </div>
      <div class="text-[10px] text-slate-400 mt-2">Updated ${ago(r.last_updated)}</div>
      <div class="grid grid-cols-4 gap-1.5 mt-3">
        <button data-act="assign" data-rid="${r.id}" title="Assign Mission" class="col-span-1 py-1.5 rounded-lg text-xs font-semibold bg-brand-600 hover:bg-brand-700 text-white cursor-pointer transition-colors">Assign</button>
        <button data-act="${paused ? "resume" : "pause"}" data-rid="${r.id}" title="${paused ? "Resume" : "Pause"}" class="py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors">${paused ? "Resume" : "Pause"}</button>
        <button data-act="recall" data-rid="${r.id}" title="Recall" class="py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors">Recall</button>
        <button data-act="emergency_stop" data-rid="${r.id}" title="Emergency Stop" class="py-1.5 rounded-lg text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white cursor-pointer transition-colors">Stop</button>
      </div>
    </div>`;
  }

  async function onRobotAction(rid, act) {
    if (act === "emergency_stop" && !confirm(`Emergency stop ${rid}? This halts the robot immediately.`)) return;
    if (act === "assign") return openAssignMissionModal(rid);
    try { await API.robotAction(rid, act); toast(`${rid}: ${act.replace(/_/g, " ")}`, act === "emergency_stop" ? "warning" : "success"); }
    catch (e) { toast(e.message, "error"); }
  }

  function openAssignMissionModal(rid) {
    const missions = state.data.missions.filter((m) => m.status !== "completed" && m.status !== "cancelled");
    const opts = missions.map((m) => `<option value="${m.id}">${m.id} · ${esc(m.title)} [${m.priority}]</option>`).join("");
    openModal(`Assign mission to ${rid}`, `
      <label class="block text-sm font-medium mb-1">Select mission</label>
      <select id="assign-mission" class="w-full rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-800 px-3 py-2 text-sm cursor-pointer">${opts || '<option value="">No open missions — create one first</option>'}</select>
      <div class="flex justify-end gap-2 mt-5">
        <button data-close class="px-4 py-2 rounded-lg text-sm bg-slate-100 dark:bg-slate-800 cursor-pointer">Cancel</button>
        <button id="assign-go" class="px-4 py-2 rounded-lg text-sm font-semibold bg-brand-600 hover:bg-brand-700 text-white cursor-pointer">Assign</button>
      </div>`, (root) => {
      root.querySelectorAll("[data-close]").forEach((e) => e.addEventListener("click", closeModal));
      $("#assign-go").addEventListener("click", async () => {
        const mid = $("#assign-mission").value; if (!mid) return closeModal();
        try { await API.robotAction(rid, "assign", { mission_id: mid }); toast(`${rid} assigned to ${mid}`, "success"); }
        catch (e) { toast(e.message, "error"); }
        closeModal();
      });
    });
  }

  /* ---------------- Missions ---------------- */
  function renderMissions() {
    const d = state.data; if (!d) return;
    const rows = d.missions.map((m) => {
      const prog = m.status === "in_progress" ? `
        <div class="h-1.5 w-24 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden mt-1">
          <div class="h-full bg-brand-500" style="width:${m.progress}%"></div></div>` : "";
      const statuses = ["pending", "assigned", "in_progress", "delayed", "completed", "cancelled"];
      return `<tr class="border-b border-slate-100 dark:border-white/5 hover:bg-slate-50 dark:hover:bg-slate-800/40">
        <td class="px-3 py-2.5 font-semibold">${m.id}</td>
        <td class="px-3 py-2.5"><div class="font-medium">${esc(m.title)}</div><div class="text-xs text-slate-500">${esc(m.category.replace(/_/g," "))}${m.medical_team ? " · " + esc(m.medical_team) : ""}</div></td>
        <td class="px-3 py-2.5">${m.zone}</td>
        <td class="px-3 py-2.5">${m.robot_id || "—"}</td>
        <td class="px-3 py-2.5">${sevBadge(m.priority)}</td>
        <td class="px-3 py-2.5">${statusBadge(m.status)}${prog}</td>
        <td class="px-3 py-2.5">
          <select data-mid="${m.id}" class="mstatus rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-800 px-2 py-1 text-xs cursor-pointer">
            ${statuses.map((s) => `<option value="${s}" ${s === m.status ? "selected" : ""}>${s.replace(/_/g," ")}</option>`).join("")}
          </select>
        </td></tr>`;
    }).join("");

    $("#content").innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div class="text-sm text-slate-500 dark:text-slate-400">${d.missions.length} missions</div>
        <button id="new-mission" class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-semibold bg-brand-600 hover:bg-brand-700 text-white cursor-pointer transition-colors">${I("plus","w-4 h-4")} Create Mission</button>
      </div>
      ${card(`<div class="overflow-x-auto"><table class="w-full text-sm">
        <thead class="text-left text-xs uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-white/10">
          <tr><th class="px-3 py-2.5">ID</th><th class="px-3 py-2.5">Mission</th><th class="px-3 py-2.5">Zone</th><th class="px-3 py-2.5">Robot</th><th class="px-3 py-2.5">Priority</th><th class="px-3 py-2.5">Status</th><th class="px-3 py-2.5">Set Status</th></tr>
        </thead><tbody>${rows}</tbody></table></div>`)}`;

    $("#new-mission").addEventListener("click", openCreateMissionModal);
    $("#content").querySelectorAll(".mstatus").forEach((s) => s.addEventListener("change", async (e) => {
      try { await API.setMissionStatus(e.target.dataset.mid, e.target.value); toast(`Mission ${e.target.dataset.mid} → ${e.target.value}`, "success"); }
      catch (err) { toast(err.message, "error"); }
    }));
  }

  function openCreateMissionModal() {
    const d = state.data;
    const zoneOpts = d.zones.map((z) => `<option value="${z.id}">${z.id} · ${esc(z.name)}</option>`).join("");
    const robotOpts = `<option value="">— unassigned —</option>` + d.robots.filter((r) => r.status !== "offline")
      .map((r) => `<option value="${r.id}">${r.id} · ${esc(r.name)}</option>`).join("");
    const field = (l, inner) => `<div><label class="block text-sm font-medium mb-1">${l}</label>${inner}</div>`;
    const sel = (id, opts) => `<select id="${id}" class="w-full rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-800 px-3 py-2 text-sm cursor-pointer">${opts}</select>`;
    openModal("Create Rescue Mission", `
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        ${field("Title", `<input id="m-title" placeholder="e.g. Evacuate Riverside" class="w-full rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-800 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-500">`)}
        ${field("Disaster Zone", sel("m-zone", zoneOpts))}
        ${field("Assign Robot", sel("m-robot", robotOpts))}
        ${field("Priority", sel("m-priority", ["critical","high","medium","low"].map((p)=>`<option value="${p}" ${p==="high"?"selected":""}>${p}</option>`).join("")))}
        ${field("Rescue Category", sel("m-cat", ["search_rescue","medical","supply","surveillance","evacuation"].map((c)=>`<option value="${c}">${c.replace(/_/g," ")}</option>`).join("")))}
        ${field("Medical Team", sel("m-team", `<option value="">None</option>`+["Team Red","Team Blue","Team Green"].map((t)=>`<option>${t}</option>`).join("")))}
        ${field("Estimated Time (min)", `<input id="m-eta" type="number" value="15" min="1" class="w-full rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-800 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-500">`)}
      </div>
      <div class="flex justify-end gap-2 mt-5">
        <button data-close class="px-4 py-2 rounded-lg text-sm bg-slate-100 dark:bg-slate-800 cursor-pointer">Cancel</button>
        <button id="m-create" class="px-4 py-2 rounded-lg text-sm font-semibold bg-brand-600 hover:bg-brand-700 text-white cursor-pointer">Create Mission</button>
      </div>`, (root) => {
      root.querySelectorAll("[data-close]").forEach((e) => e.addEventListener("click", closeModal));
      $("#m-create").addEventListener("click", async () => {
        const body = { title: $("#m-title").value.trim() || "Untitled Mission", zone: $("#m-zone").value,
          robot_id: $("#m-robot").value || null, priority: $("#m-priority").value,
          category: $("#m-cat").value, medical_team: $("#m-team").value || null,
          eta_min: parseInt($("#m-eta").value) || 15 };
        try { await API.createMission(body); toast("Mission created", "success"); closeModal(); }
        catch (e) { toast(e.message, "error"); }
      });
    });
  }

  /* ---------------- Victims ---------------- */
  function renderVictims() {
    const d = state.data; if (!d) return;
    const chips = (v) => [v.medical_required && "Medical", v.food_required && "Food", v.water_required && "Water"]
      .filter(Boolean).map((c) => `<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800">${c}</span>`).join("");
    const cards = d.victims.map((v) => `
      <div class="card-in bg-white dark:bg-slate-900 rounded-xl border ${v.severity === "critical" && v.status === "pending" ? "border-rose-400 sos-flash" : "border-slate-200 dark:border-white/10"} p-4">
        <div class="flex items-start justify-between gap-2">
          <div><div class="font-bold flex items-center gap-2">${esc(v.name)} ${sevBadge(v.severity)}</div>
            <div class="text-xs text-slate-500 dark:text-slate-400">${v.id} · ${v.location.zone} · ${ago(v.request_time)}</div></div>
          ${statusBadge(v.status)}
        </div>
        <div class="grid grid-cols-2 gap-x-4 gap-y-1 mt-3 text-xs">
          <div class="flex justify-between"><span class="text-slate-500">People</span><span class="font-semibold">${v.people_count}</span></div>
          <div class="flex justify-between"><span class="text-slate-500">Trapped</span><span class="font-semibold capitalize">${v.trapped_level}</span></div>
        </div>
        <div class="flex gap-1 mt-2">${chips(v)}</div>
        <div class="grid grid-cols-4 gap-1.5 mt-3">
          <button data-va="accept" data-vid="${v.id}" class="py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer">Accept</button>
          <button data-va="reject" data-vid="${v.id}" class="py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer">Reject</button>
          <button data-va="assign" data-vid="${v.id}" class="py-1.5 rounded-lg text-xs font-semibold bg-brand-600 hover:bg-brand-700 text-white cursor-pointer">Assign</button>
          <button data-va="rescued" data-vid="${v.id}" class="py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer">Rescued</button>
        </div>
      </div>`).join("");
    $("#content").innerHTML = `<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">${cards}</div>`;
    $("#content").querySelectorAll("[data-va]").forEach((b) => b.addEventListener("click", () => onVictimAction(b.dataset.vid, b.dataset.va)));
  }

  async function onVictimAction(vid, act) {
    if (act === "assign") {
      const opts = state.data.robots.filter((r) => r.status !== "offline")
        .map((r) => `<option value="${r.id}">${r.id} · ${esc(r.name)} (${r.type})</option>`).join("");
      return openModal(`Assign robot to ${vid}`, `
        <select id="v-robot" class="w-full rounded-lg border border-slate-300 dark:border-white/10 bg-white dark:bg-slate-800 px-3 py-2 text-sm cursor-pointer">${opts}</select>
        <div class="flex justify-end gap-2 mt-5">
          <button data-close class="px-4 py-2 rounded-lg text-sm bg-slate-100 dark:bg-slate-800 cursor-pointer">Cancel</button>
          <button id="v-go" class="px-4 py-2 rounded-lg text-sm font-semibold bg-brand-600 hover:bg-brand-700 text-white cursor-pointer">Assign</button>
        </div>`, (root) => {
        root.querySelectorAll("[data-close]").forEach((e) => e.addEventListener("click", closeModal));
        $("#v-go").addEventListener("click", async () => {
          try { await API.victimAction(vid, "assign", { robot_id: $("#v-robot").value }); toast(`${vid} assigned`, "success"); }
          catch (e) { toast(e.message, "error"); } closeModal();
        });
      });
    }
    try { await API.victimAction(vid, act); toast(`${vid}: ${act}`, act === "rescued" ? "success" : "info"); }
    catch (e) { toast(e.message, "error"); }
  }

  /* ---------------- Alerts ---------------- */
  function renderAlerts() {
    const d = state.data; if (!d) return;
    const rows = d.alerts.map((a) => `
      <div class="card-in flex items-center gap-3 p-3.5 bg-white dark:bg-slate-900 rounded-xl border ${a.severity === "critical" && a.status === "active" ? "border-rose-400" : "border-slate-200 dark:border-white/10"}">
        <div class="h-10 w-10 rounded-lg grid place-items-center ${a.status === "active" ? "bg-rose-100 dark:bg-rose-950/60 text-rose-500" : "bg-slate-100 dark:bg-slate-800 text-slate-400"} shrink-0">${I(ALERT_ICON[a.type] || "alert", "w-6 h-6")}</div>
        <div class="flex-1 min-w-0">
          <div class="font-semibold capitalize">${esc(a.type.replace(/_/g, " "))}</div>
          <div class="text-xs text-slate-500 dark:text-slate-400">${a.zone} · ${fmtTime(a.time)} · ${ago(a.time)}</div>
        </div>
        ${sevBadge(a.severity)} ${statusBadge(a.status)}
        ${a.status === "active" ? `<button data-ack="${a.id}" class="ml-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer">Acknowledge</button>` : ""}
      </div>`).join("");
    $("#content").innerHTML = `<div class="space-y-2.5">${rows}</div>`;
    $("#content").querySelectorAll("[data-ack]").forEach((b) => b.addEventListener("click", async () => {
      try { await API.ackAlert(b.dataset.ack); toast(`Alert acknowledged`, "success"); } catch (e) { toast(e.message, "error"); }
    }));
  }

  /* ---------------- Resources ---------------- */
  function renderResources() {
    const d = state.data; if (!d) return;
    const icons = { "Medical Kits": "medical", "Food Packs": "resource", "Water Supplies": "resource",
      "Ambulances": "truck", "Fuel (L)": "zap", "Power Stations": "battery" };
    const cards = d.resources.map((r) => {
      const pctUsed = Math.round((r.used / r.total) * 100);
      const low = (r.remaining / r.total) < 0.3;
      return `<div class="card-in bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-white/10 p-4">
        <div class="flex items-center gap-2 mb-3"><span class="text-brand-500">${I(icons[r.name] || "resource", "w-5 h-5")}</span><span class="font-semibold">${esc(r.name)}</span>
          ${low ? badge("LOW", SEV.high) : ""}</div>
        <div class="flex items-end justify-between mb-2"><div class="text-2xl font-extrabold tabular-nums">${r.remaining}</div><div class="text-xs text-slate-500">of ${r.total} remaining</div></div>
        <div class="h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden"><div class="h-full ${low ? "bg-orange-500" : "bg-emerald-500"}" style="width:${100 - pctUsed}%"></div></div>
        <div class="flex justify-between text-xs mt-1.5 text-slate-500"><span>Used ${r.used}</span><span>${pctUsed}% consumed</span></div>
      </div>`;
    }).join("");
    $("#content").innerHTML = `<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">${cards}</div>`;
  }

  /* ---------------- Activity ---------------- */
  function logRow(l, isNew) {
    return `<div class="flex items-start gap-3 px-4 py-2.5 ${isNew ? "log-new" : ""}">
      <span class="mt-1.5 h-2 w-2 rounded-full shrink-0 ${logColor[l.level] || logColor.info}"></span>
      <div class="min-w-0 flex-1"><div class="text-sm">${esc(l.message)}</div>
        <div class="text-[11px] text-slate-400">${fmtTime(l.time)} · ${esc(l.source)}</div></div>
    </div>`;
  }
  function renderActivity() {
    const d = state.data; if (!d) return;
    const rows = (d.activity || []).map((l, i) => logRow(l, i === 0)).join("");
    $("#content").innerHTML = card(`
      <div class="px-4 py-3 border-b border-slate-200 dark:border-white/10 font-semibold flex items-center gap-2">
        ${I("activity", "w-4 h-4 text-brand-500")} Live Activity Log
        <span class="ml-auto text-xs font-normal text-slate-400 flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-emerald-500 pulse-dot text-emerald-500"></span>streaming</span></div>
      <div class="divide-y divide-slate-100 dark:divide-white/5 max-h-[70vh] overflow-y-auto">${rows}</div>`);
  }

  /* ---------------- Map ---------------- */
  function renderMap() {
    const d = state.data; if (!d) return;
    $("#content").innerHTML = `<div id="cc-map" class="w-full h-[72vh] rounded-xl border border-slate-200 dark:border-white/10"></div>`;
    const center = d.zones.length ? [d.zones[0].lat, d.zones[0].lon] : [12.9716, 77.5946];
    const map = L.map("cc-map", { zoomControl: true }).setView(center, 14);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
    state.map = map; state.layers = { zones: L.layerGroup().addTo(map), robots: L.layerGroup().addTo(map), victims: L.layerGroup().addTo(map) };
    const sevHex = { critical: "#f43f5e", high: "#f97316", medium: "#f59e0b", low: "#10b981" };
    d.zones.forEach((z) => {
      L.circle([z.lat, z.lon], { radius: z.radius_m, color: sevHex[z.severity], fillColor: sevHex[z.severity], fillOpacity: 0.12, weight: 2 })
        .bindPopup(`<b>${z.id}</b> — ${esc(z.name)}<br>Severity: ${z.severity}`).addTo(state.layers.zones);
    });
    updateMapMarkers();
  }
  function robotMarker(r) {
    const color = r.type === "drone" ? "#0ea5e9" : r.type === "medical" ? "#f43f5e" : "#10b981";
    const dim = r.status === "offline" ? "opacity:.4;" : "";
    return L.divIcon({ className: "", iconSize: [26, 26], html:
      `<div style="${dim}background:${color};width:22px;height:22px;border-radius:50%;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,.5);display:grid;place-items:center;color:white;font-size:9px;font-weight:700">${r.type[0].toUpperCase()}</div>` });
  }
  function updateMapMarkers() {
    if (!state.map || !state.layers.robots) return;
    state.layers.robots.clearLayers();
    state.data.robots.forEach((r) => {
      L.marker([r.location.lat, r.location.lon], { icon: robotMarker(r) })
        .bindPopup(`<b>${esc(r.name)}</b> (${r.id})<br>${r.type} · ${r.status}<br>Battery: ${(r.battery||0).toFixed(0)}%<br>Zone: ${r.location.zone}`)
        .addTo(state.layers.robots);
    });
  }

  /* ---------------- Analytics ---------------- */
  function chartColors() {
    const dark = document.documentElement.classList.contains("dark");
    return { grid: dark ? "rgba(148,163,184,.15)" : "rgba(100,116,139,.15)", text: dark ? "#cbd5e1" : "#475569" };
  }
  function renderAnalytics() {
    const d = state.data; if (!d) return;
    const c = chartColors();
    Chart.defaults.color = c.text; Chart.defaults.font.family = "Inter, sans-serif";
    $("#content").innerHTML = `
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        ${chartCard("Mission Status", "ch-status")}
        ${chartCard("Battery by Robot", "ch-battery")}
        ${chartCard("Rescue & Completion Trend", "ch-trend")}
        ${chartCard("Robot Utilization", "ch-util")}
      </div>`;
    const a = d.analytics;
    const sColor = { pending: "#94a3b8", assigned: "#38bdf8", in_progress: "#0ea5e9", delayed: "#f97316", completed: "#10b981", cancelled: "#64748b" };
    const sk = Object.keys(a.mission_status);
    state.charts.status = new Chart($("#ch-status"), { type: "doughnut",
      data: { labels: sk.map((s) => s.replace(/_/g, " ")), datasets: [{ data: sk.map((s) => a.mission_status[s]), backgroundColor: sk.map((s) => sColor[s] || "#94a3b8"), borderWidth: 0 }] },
      options: { plugins: { legend: { position: "bottom" } }, cutout: "60%" } });
    state.charts.battery = new Chart($("#ch-battery"), { type: "bar",
      data: { labels: a.battery_by_robot.map((r) => r.id), datasets: [{ label: "Battery %", data: a.battery_by_robot.map((r) => r.battery),
        backgroundColor: a.battery_by_robot.map((r) => r.battery >= 60 ? "#10b981" : r.battery >= 30 ? "#f59e0b" : "#f43f5e") }] },
      options: { scales: { y: { beginAtZero: true, max: 100, grid: { color: c.grid } }, x: { grid: { display: false } } }, plugins: { legend: { display: false } } } });
    state.charts.trend = new Chart($("#ch-trend"), { type: "line",
      data: { labels: a.rescued_trend.map((_, i) => "T-" + (a.rescued_trend.length - i)), datasets: [
        { label: "Victims Rescued", data: a.rescued_trend, borderColor: "#0ea5e9", backgroundColor: "rgba(14,165,233,.15)", fill: true, tension: .35 },
        { label: "Missions Completed", data: a.completion_trend, borderColor: "#10b981", backgroundColor: "rgba(16,185,129,.12)", fill: true, tension: .35 } ] },
      options: { scales: { y: { grid: { color: c.grid } }, x: { grid: { display: false } } }, plugins: { legend: { position: "bottom" } } } });
    const u = a.utilization;
    state.charts.util = new Chart($("#ch-util"), { type: "polarArea",
      data: { labels: ["On mission", "Idle", "Charging", "Offline"], datasets: [{ data: [u.on_mission, u.idle, u.charging, u.offline], backgroundColor: ["#0ea5e9", "#38bdf8", "#f59e0b", "#64748b"] }] },
      options: { plugins: { legend: { position: "bottom" } }, scales: { r: { grid: { color: c.grid } } } } });
  }
  function chartCard(title, id) {
    return card(`<div class="px-4 py-3 border-b border-slate-200 dark:border-white/10 font-semibold text-sm">${title}</div>
      <div class="p-4"><div class="relative h-64"><canvas id="${id}"></canvas></div></div>`);
  }
  function updateCharts() {
    const a = state.data.analytics; if (!a) return;
    if (state.charts.battery) {
      state.charts.battery.data.labels = a.battery_by_robot.map((r) => r.id);
      state.charts.battery.data.datasets[0].data = a.battery_by_robot.map((r) => r.battery);
      state.charts.battery.data.datasets[0].backgroundColor = a.battery_by_robot.map((r) => r.battery >= 60 ? "#10b981" : r.battery >= 30 ? "#f59e0b" : "#f43f5e");
      state.charts.battery.update("none");
    }
    if (state.charts.status) {
      const sk = Object.keys(a.mission_status);
      state.charts.status.data.labels = sk.map((s) => s.replace(/_/g, " "));
      state.charts.status.data.datasets[0].data = sk.map((s) => a.mission_status[s]);
      state.charts.status.update("none");
    }
    if (state.charts.trend) {
      state.charts.trend.data.labels = a.rescued_trend.map((_, i) => "T-" + (a.rescued_trend.length - i));
      state.charts.trend.data.datasets[0].data = a.rescued_trend;
      state.charts.trend.data.datasets[1].data = a.completion_trend;
      state.charts.trend.update("none");
    }
    if (state.charts.util) {
      const u = a.utilization; state.charts.util.data.datasets[0].data = [u.on_mission, u.idle, u.charging, u.offline];
      state.charts.util.update("none");
    }
  }

  /* ---------------------------------------------------- topbar controls */
  function toggleTheme() {
    const dark = document.documentElement.classList.toggle("dark");
    localStorage.setItem("cc_theme", dark ? "dark" : "light");
    $("#theme-btn").innerHTML = dark ? I("sun", "w-5 h-5") : I("moon", "w-5 h-5");
    if (state.panel === "analytics") renderAnalytics();
  }
  function toggleFullscreen() {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
    else document.exitFullscreen && document.exitFullscreen();
  }
  function openSidebar() { $("#sidebar").classList.remove("-translate-x-full"); $("#sidebar-backdrop").classList.remove("hidden"); }
  function closeSidebar() { $("#sidebar").classList.add("-translate-x-full"); $("#sidebar-backdrop").classList.add("hidden"); }

  function toggleNotif() {
    const dr = $("#notif-drawer"); const show = dr.classList.contains("hidden");
    dr.classList.toggle("hidden");
    if (show) {
      $("#notif-dot").classList.add("hidden");
      $("#notif-count").textContent = `${state.notifications.length}`;
      $("#notif-list").innerHTML = state.notifications.length ? state.notifications.map((l) => `
        <div class="flex items-start gap-2.5 px-4 py-2.5">
          <span class="mt-1.5 h-2 w-2 rounded-full shrink-0 ${logColor[l.level] || logColor.info}"></span>
          <div><div class="text-sm">${esc(l.message)}</div><div class="text-[11px] text-slate-400">${fmtTime(l.time)}</div></div>
        </div>`).join("") : '<div class="p-4 text-sm text-slate-500">No new notifications</div>';
    }
  }

  /* ---------------------------------------------------- keyboard shortcuts */
  function onKey(e) {
    if (isTyping() || $("#app-view").classList.contains("hidden")) return;
    if (e.key >= "1" && e.key <= "9") { const n = NAV[+e.key - 1]; if (n) setPanel(n[0]); }
    else if (e.key.toLowerCase() === "n") { if (state.panel !== "missions") setPanel("missions"); openCreateMissionModal(); }
    else if (e.key === "/") { e.preventDefault(); if (state.panel !== "fleet") setPanel("fleet"); const s = $("#fleet-search"); if (s) s.focus(); }
    else if (e.key === "Escape") closeModal();
  }

  /* ---------------------------------------------------- init */
  function init() {
    if (localStorage.getItem("cc_theme") === "light") document.documentElement.classList.remove("dark");
    initStaticIcons();
    $("#login-form").addEventListener("submit", doLogin);
    $("#theme-btn").addEventListener("click", toggleTheme);
    $("#logout-btn").addEventListener("click", logout);
    $("#menu-btn").addEventListener("click", openSidebar);
    $("#sidebar-backdrop").addEventListener("click", closeSidebar);
    $("#fs-btn").addEventListener("click", toggleFullscreen);
    $("#notif-btn").addEventListener("click", toggleNotif);
    document.addEventListener("keydown", onKey);

    const token = localStorage.getItem("cc_token");
    const user = localStorage.getItem("cc_user");
    if (token && user) { state.user = JSON.parse(user); enterApp(); }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
