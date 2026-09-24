/* API + WebSocket client for the command center. */
(function () {
  const API = location.origin;

  function headers() {
    const h = { "Content-Type": "application/json" };
    const t = localStorage.getItem("cc_token");
    if (t) h["Authorization"] = "Bearer " + t;
    return h;
  }

  async function req(method, path, body) {
    const res = await fetch(API + path, {
      method,
      headers: headers(),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (e) {}
      throw new Error(detail);
    }
    return res.status === 204 ? null : res.json();
  }

  const api = {
    get: (p) => req("GET", p),
    post: (p, b) => req("POST", p, b),
    patch: (p, b) => req("PATCH", p, b),
    login: (b) => req("POST", "/api/auth/login", b),
    snapshot: () => req("GET", "/api/snapshot"),
    robotAction: (id, action, extra) => req("POST", `/api/robots/${id}/action`, { action, ...(extra || {}) }),
    createMission: (b) => req("POST", "/api/missions", b),
    setMissionStatus: (id, status) => req("PATCH", `/api/missions/${encodeURIComponent(id)}`, { status }),
    victimAction: (id, action, extra) => req("POST", `/api/victims/${id}/action`, { action, ...(extra || {}) }),
    ackAlert: (id) => req("POST", `/api/alerts/${id}/ack`),
    swarm: () => req("GET", "/api/swarm"),
  };

  /* --------------------------- WebSocket manager --------------------------- */
  class LiveSocket {
    constructor() {
      this.ws = null;
      this.handlers = {};
      this.reconnectMs = 1500;
      this.forcedClose = false;
    }
    on(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); return this; }
    emit(type, data) { (this.handlers[type] || []).forEach((f) => f(data)); }

    connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      this.ws = new WebSocket(`${proto}://${location.host}/ws`);
      this.ws.onopen = () => this.emit("status", { connected: true });
      this.ws.onclose = () => {
        this.emit("status", { connected: false });
        if (!this.forcedClose) setTimeout(() => this.connect(), this.reconnectMs);
      };
      this.ws.onerror = () => { try { this.ws.close(); } catch (e) {} };
      this.ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          this.emit(msg.type || "message", msg);
        } catch (e) {}
      };
    }
    close() { this.forcedClose = true; if (this.ws) this.ws.close(); }
  }

  window.API = api;
  window.LiveSocket = LiveSocket;
})();
