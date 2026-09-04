/* app.js —— WS 连接 + 状态机 + 渲染循环 + 控制(display_m5_ui G1~G4)。 */
const App = (() => {
  const TPS = { pause: 0, "1x": 2, "3x": 6, "10x": 20, "60x": 120, max: -1 };
  let ws = null, retry = 0, connected = false;
  let speed = "pause";
  let hello = null;
  let lastSnap = null, prevTick = 0, prevMs = 0, tickRate = 2;
  let ui = { selected: null, follow: null, highlight: new Set(),
             flags: { failed: new Set(), talking: new Set() }, arcs: [] };
  const pending = new Map(); let reqId = 0;
  let evFilter = "all";

  function log(...a) { console.log("[app]", ...a); }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => { connected = true; retry = 0;
      document.getElementById("conn").textContent = "● 已连接";
      document.getElementById("conn").className = "status online"; };
    ws.onclose = () => { connected = false;
      document.getElementById("conn").textContent = "○ 重连中";
      document.getElementById("conn").className = "status offline";
      setTimeout(connect, 800 * Math.min(5, ++retry)); };
    ws.onmessage = (m) => { const d = JSON.parse(m.data); onMsg(d); };
  }

  function send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }
  function query(args, cb) { const id = ++reqId; pending.set(id, cb);
    send({ name: "query", args, req_id: id }); }

  function onMsg(d) {
    if (d.type === "hello") {
      hello = d;
      Render.setGeometry(d.locations);
      document.getElementById("seed").value = d.seed;
      document.getElementById("scenario").value = d.scenario;
      document.getElementById("kb_mode").value = d.kb_mode || "off";
      speed = "pause"; setSpeedButtons();
      ui = { selected: null, follow: null, highlight: new Set(),
             flags: { failed: new Set(), talking: new Set() }, arcs: [] };
      clearFeed();
      return;
    }
    if (d.type === "reply") {
      const cb = pending.get(d.req_id); if (cb) { pending.delete(d.req_id); cb(d); }
      return;
    }
    if (d.type === "snapshot") {
      const nowMs = performance.now();
      if (lastSnap) { const dt = nowMs - prevMs;
        if (dt > 0) tickRate = Math.max(0.5, Math.min(1000, (d.tick - prevTick) * 1000 / dt)); }
      prevTick = d.tick; prevMs = nowMs; lastSnap = d;
      document.getElementById("clock").textContent =
        `Day ${d.day} ${d.clock} · ${d.speed}`;
      handleEvents(d.events || []);
    }
  }

  function handleEvents(evs) {
    const now = performance.now();
    for (const ev of evs) {
      if (ev.kind === "told") {
        ui.flags.talking.add(ev.subject);
        ui.arcs.push({ from: ev.subject, to: (ev.payload.audience || "")[0], born: now });
        setTimeout(() => ui.flags.talking.delete(ev.subject), 900);
      }
      if (ev.kind === "intent_failed") {
        ui.flags.failed.add(ev.subject);
        setTimeout(() => ui.flags.failed.delete(ev.subject), 3000);
      }
      pushEvent(ev);
    }
    while (ui.arcs.length && now - ui.arcs[0].born > 900) ui.arcs.shift();
  }

  function pushEvent(ev) {
    if (evFilter !== "all" && ev.kind !== evFilter) return;
    const ul = document.getElementById("events");
    const li = document.createElement("li");
    li.innerHTML = Panels.eventLine(ev);
    li.dataset.subject = ev.subject || "";
    ul.appendChild(li);
    while (ul.children.length > 300) ul.removeChild(ul.firstChild);
  }

  function clearFeed() { document.getElementById("events").innerHTML = ""; }

  function tickNow() {
    if (!lastSnap) return 0;
    if (speed === "pause") return lastSnap.tick;
    const el = (performance.now() - prevMs) / 1000;
    return lastSnap.tick + el * tickRate;
  }

  function drawLoop() {
    requestAnimationFrame(drawLoop);
    if (!lastSnap) return;
    Render.draw(lastSnap, tickNow(), ui);
  }

  function setSpeed(s) {
    speed = s;
    send({ name: "set_speed", args: { speed: s } });
    setSpeedButtons();
  }
  function setSpeedButtons() {
    document.querySelectorAll("#speedbar button").forEach(b =>
      b.classList.toggle("active", b.dataset.speed === speed));
  }

  function stepTicks(n) { send({ name: "step", args: { ticks: n } }); speed = "pause"; setSpeedButtons(); }

  function reset() {
    send({ name: "reset", args: {
      scenario: document.getElementById("scenario").value,
      seed: Number(document.getElementById("seed").value) || 3,
      n_npc: 5,
      kb_mode: document.getElementById("kb_mode").value,
      tell_p: 0.0 } });
  }

  function pickAt(clientX, clientY) {
    if (!lastSnap) return;
    const cv = document.getElementById("stage");
    const r = cv.getBoundingClientRect();
    const hit = Render.hitTest(lastSnap, tickNow(), clientX - r.left, clientY - r.top);
    if (hit && hit.kind === "npc") {
      ui.selected = hit.id; ui.follow = null;
      Panels.select(hit.id);
    } else if (hit && hit.kind === "room") {
      ui.follow = hit.id;
    } else {
      ui.selected = null; ui.follow = null;
    }
  }

  function wire() {
    document.getElementById("speedbar").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (b) setSpeed(b.dataset.speed);
    });
    document.getElementById("resetBtn").addEventListener("click", reset);
    document.getElementById("scenario").addEventListener("change", reset);
    const stage = document.getElementById("stage");
    stage.addEventListener("click", (e) => pickAt(e.clientX, e.clientY));
    document.getElementById("evbar").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-filter]");
      if (b) { evFilter = b.dataset.filter;
        document.querySelectorAll("#evbar button[data-filter]")
          .forEach(x => x.classList.toggle("active", x === b)); return; }
      const li = e.target.closest("li"); if (li && li.dataset.subject) {
        ui.selected = li.dataset.subject; Panels.select(li.dataset.subject);
      }
    });
    window.addEventListener("keydown", (e) => {
      if (e.code === "Space") { e.preventDefault(); setSpeed(speed === "pause" ? "3x" : "pause"); }
      else if (e.key === "1") setSpeed("1x");
      else if (e.key === "2") setSpeed("3x");
      else if (e.key === "3") setSpeed("10x");
      else if (e.key === "4") setSpeed("60x");
      else if (e.key === "5") setSpeed("max");
      else if (e.key === ".") stepTicks(1);
      else if (e.key === "ArrowRight") stepTicks(60);
      else if (e.key === "Escape") { ui.selected = null; ui.highlight.clear(); }
      else if (e.key.toLowerCase() === "f" && ui.selected) { ui.follow = ui.selected; }
    });
    window.addEventListener("resize", () => { Render.resize(); });
    Render.init(stage); Render.resize();
  }

  function start() { connect(); drawLoop(); }

  return { query, send, wire, start,
           get state() { return { speed, lastSnap }; } };
})();

window.addEventListener("DOMContentLoaded", () => {
  App.wire();
  App.start();
});
