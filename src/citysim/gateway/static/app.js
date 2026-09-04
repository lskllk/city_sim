/* app.js —— 控制器(canvasrecode 重构后)。
   职责只剩：ws 协议、事件→FX 映射、状态/详情按需查询、点选/高亮、事件流文本。
   位置/绘制全部交给 VM/Painter/FX；本模块不再画任何东西、不再跑 rAF。 */
(() => {
  const $ = s => document.querySelector(s);
  const canvas = $("#stage");
  const cvRect = () => canvas.getBoundingClientRect();
  Render.init(canvas);

  // ---------- 状态 ----------
  const state = {
    ws: null, snap: null,
    selected: null, tab: "status",
    ui: { selected: null, highlight: new Set() },
    names: {}, ents: {}, rooms: {},
    detail: null, detailFor: null, detailAt: 0,
    stateAt: 0, evRows: [],
    querySeq: 0, pending: new Map(),
  };
  const ACT_TXT = { sleep: "睡眠", eat: "进食", toilet: "如厕", fun: "娱乐",
                    drink: "饮水", idle: "闲逛", move: "赶路" };

  // ---------- 工具 ----------
  function _idToName(s) {
    const str = String(s);
    if (state.names[str]) return state.names[str];
    if (state.ents[str]) return state.ents[str];
    if (state.rooms[str]) return state.rooms[str];
    return str;
  }
  // npc/实体/房间 → 中文名; 句子内含的已知 id 片段也会被替换(供 reason 等用)
  const nameOf = id => {
    const str = String(id);
    const hit = _idToName(str);
    if (hit !== str) return hit;
    let out = str;
    for (const map of [state.names, state.ents, state.rooms]) {
      for (const k in map) {
        if (out.indexOf(k) !== -1) out = out.split(k).join(String(map[k]));
      }
    }
    return out;
  };
  const objOf = id => state.ents[id] || state.rooms[id] || id;

  function send(o) {
    if (state.ws && state.ws.readyState === 1) state.ws.send(JSON.stringify(o));
  }
  function query(args) {
    return new Promise(res => {
      const id = ++state.querySeq;
      state.pending.set(id, res);
      send({ name: "query", req_id: id, args });
      setTimeout(() => { if (state.pending.has(id)) { state.pending.delete(id); res(null); } }, 8000);
    });
  }
  function pushUI() { Render.setUI(state.ui); }
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    state.ws = new WebSocket(`${proto}://${location.host}/ws`);
    state.ws.onopen = () => Panels.conn(true);
    state.ws.onclose = () => { Panels.conn(false); setTimeout(connect, 1200); };
    state.ws.onmessage = e => { try { dispatch(JSON.parse(e.data)); } catch (_) {} };
  }
  function dispatch(m) {
    if (m.type === "hello") onHello(m);
    else if (m.type === "snapshot") onSnap(m);
    else if (m.type === "reply") {
      const cb = state.pending.get(m.req_id);
      if (cb) { state.pending.delete(m.req_id); cb(m.ok ? m.data : null); }
    }
  }

  // ---------- hello / snapshot ----------
  function onHello(m) {
    Render.hello(m);                      // 房间 + 相机 + 静态底图（仅此处/ resize）
    state.names = {}; state.ents = {}; state.rooms = {};
    const locs = (m.locations && m.locations.locations) || {};
    for (const [id, g] of Object.entries(locs)) state.rooms[id] = g.name || id;
    state.ui = { selected: null, highlight: new Set() }; pushUI();
    state.detail = null; state.detailFor = null; state.evRows = [];
    clearSelection();
    const scen = $("#scenario"); if (scen) scen.value = m.scenario;
    const seed = $("#seed"); if (seed) seed.value = m.seed;
    const kb = $("#kb_mode"); if (kb) kb.value = m.kb_mode || "off";
    speedGlow("pause");
    Panels.clock(`Day 1 00:00`);
    Panels.feed([]);
    Render.resize();
  }
  function onSnap(m) {
    state.snap = m;
    Render.snapshot(m);                   // 只 reconcile，不 draw
    m.npcs.forEach(n => { state.names[n.id] = n.name; });
    m.entities.forEach(e => { state.ents[e.id] = e.name; });
    processEvents(m.events || []);
    Panels.clock(`Day ${m.day} ${m.clock}`);
    if (m.events && m.events.length) {
      for (const e of m.events) state.evRows.push(evRow(e));
      if (state.evRows.length > 120) state.evRows = state.evRows.slice(-120);
      Panels.feed(state.evRows);
    }
    if (state.selected) {
      const now = performance.now();
      if (state.tab === "status" && now - state.stateAt > 900) fetchState();
      else if (state.tab !== "status" && (now - state.detailAt > 2000
             || state.detailFor !== state.selected)) fetchDetail();
    }
  }

  // 事件 → FX 映射（canvasrecode 第 7 节：在 onSnapshot 的 events 循环做）
  function processEvents(evs) {
    for (const e of evs) {
      if (!e || !e.kind) continue;
      const p = e.payload || {};
      if (e.kind === "decision") {
        if (e.intent && e.intent !== "idle") FX.push("think", e.subject);
        if (e.subject === state.selected && state.tab === "why") state.detailAt = 0;
      } else if (e.kind === "told") {
        FX.push("talk", e.subject);
        for (const r of (p.audience || [])) {
          FX.push("arc", e.subject, r);
          FX.push("learn", r, { short: p.short || "" });
        }
      } else if (e.kind === "intent_failed") {
        FX.push("fail", e.subject);
      }
      if (e.subject === state.selected && state.tab !== "status") state.detailAt = 0;
    }
  }

  // tick(每分钟一格) → 游戏时刻 "D1 14:43"; tick>=1440 带天数
  function fmtTick(tick) {
    if (typeof tick !== "number" || !isFinite(tick)) return "";
    const day = Math.floor(tick / 1440) + 1;
    const m = ((tick % 1440) + 1440) % 1440;
    const hh = String(Math.floor(m / 60)).padStart(2, "0");
    const mm = String(m % 60).padStart(2, "0");
    return `${day > 1 ? "D" + day + " " : ""}${hh}:${mm}`;
  }
  function evRow(e) {
    const base = `<span class="tk">${fmtTick(e.tick)}</span>`;
    const p = e.payload || {};
    switch (e.kind) {
      case "decision":
        return { kind: "decision", html: `${base} <b>${nameOf(e.subject)}</b> 决定 <i class="mono">${e.intent}</i>${e.target ? " " + objOf(e.target) : ""}` };
      case "told": {
        const aud = (p.audience || []).map(nameOf).join("、");
        const msg = p.short || `${p.subject || ""} ${p.relation || ""} ${p.obj || ""}`;
        return { kind: "told", html: `${base} 💬 <b>${nameOf(e.subject)}</b> 告诉 ${aud}：${msg}` };
      }
      case "intent_failed": {
        const want = e.intent || p.intent || "";
        return { kind: "intent_failed", html: `${base} ⚠ <b>${nameOf(e.subject)}</b> ${want ? "想" + want + " " : ""}${p.why || "未遂"}` };
      }
      case "interaction_done":
        return { kind: "interaction_done", html: `${base} ✓ <b>${nameOf(e.subject)}</b> 完成 ${objOf(e.target || p.entity)}` };
      default:
        return { kind: e.kind, html: `${base} ${e.kind} ${nameOf(e.subject)}` };
    }
  }

  // ---------- 选中 / 查询 ----------
  function clearSelection() {
    state.selected = null; state.detail = null; state.detailFor = null;
    state.ui.selected = null; pushUI();
    Panels.title("点一个小人查看");
    Panels.showTab("status"); state.tab = "status";
  }
  function selectNpc(id) {
    state.selected = id; state.ui.selected = id; pushUI();
    const n = state.snap && state.snap.npcs.find(x => x.id === id);
    Panels.title(`<b>${nameOf(id)}</b>${n ? " · " + (ACT_TXT[n.act_class] || n.act_class) : ""}`);
    Panels.showTab("status"); state.tab = "status";
    fetchState(); fetchDetail();
  }
  async function fetchState() {
    const d = await query({ what: "npc_state", npc_id: state.selected });
    state.stateAt = performance.now();
    if (d) Panels.status(d);
  }
  async function fetchDetail() {
    const d = await query({ what: "npc_detail", npc_id: state.selected });
    if (!d || state.selected !== d.id) return;
    state.detail = d; state.detailFor = d.id; state.detailAt = performance.now();
    routeDetail();
  }
  function routeDetail() {
    if (!state.selected) return;
    if (state.tab === "why") Panels.why(state.detail, nameOf);
    else if (state.tab === "kb") Panels.kb(state.detail, nameOf);
    else if (state.tab === "events") Panels.events((state.detail.events || []).slice().reverse().map(evRow).map(r => r.html));
  }

  // ---------- 悬停浮层(物体属性/容器内容) ----------
  const tipEl = document.createElement("div");
  tipEl.id = "tip"; tipEl.hidden = true; document.body.appendChild(tipEl);
  const TAG_TXT = { sleepable: "床铺", toilet: "卫生间", container: "容器",
                    edible: "食物", entertain: "娱乐", drink: "饮水",
                    consumable: "消耗品", work: "工作台" };
  function esc(s) { return String(s).replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function roomNameOf(loc) { const r = VM.rooms().find(x => x.id === loc); return r ? r.name : loc; }
  function stockTxt(stock) { return stock === -1 ? "∞" : stock === 0 ? "空" : String(stock); }
  function tipRow(k, v) { return `<div class="tp-row"><span class="tp-k">${esc(k)}</span><span class="tp-v">${esc(v)}</span></div>`; }
  function tipContent(hit) {
    if (!hit) return null;
    if (hit.kind === "npc") {
      const a = VM.agents.get(hit.id); if (!a) return null;
      return `<div class="tp-name">${esc(a.name)}</div>`
        + tipRow("活动", ACT_TXT[a.display_act || a.actClass] || a.actClass || "—")
        + tipRow("位置", roomNameOf(a.room));
    }
    if (hit.kind === "entity") {
      const e = VM.entities.get(hit.id); if (!e) return null;
      const tags = (e.tags || []).map(t => TAG_TXT[t] || t).join("、") || "—";
      const isCont = e.tags && e.tags.includes("container");
      let h = `<div class="tp-name">${esc(e.name)}</div>`;
      if (e.tags && e.tags.length) h += tipRow("类型", tags);
      const showStock = typeof e.stock === "number"
        && e.tags && (e.tags.includes("container") || e.tags.includes("edible"));
      if (showStock) h += tipRow(isCont ? "内部" : "库存", stockTxt(e.stock));
      h += tipRow("位置", roomNameOf(e.loc));
      if (e.claimedBy) h += tipRow("使用中", nameOf(e.claimedBy));
      if (isCont) h += `<div class="tp-dim">容器 · 内部库存 ${esc(stockTxt(e.stock))}</div>`;
      return h;
    }
    if (hit.kind === "room") {
      const rm = VM.rooms().find(x => x.id === hit.id); if (!rm) return null;
      const n = [...VM.agents.values()].filter(a => a.room === hit.id).length;
      return `<div class="tp-name">${esc(rm.name)}</div>` + tipRow("在场", `${n} 人`);
    }
    return null;
  }
  let tipLast = 0;
  function canvasMove(ev) {
    const now = performance.now();
    if (now - tipLast < 40) return;            // 节流 ~25Hz
    tipLast = now;
    const r = cvRect();
    if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) {
      tipEl.hidden = true; return;
    }
    const hit = Render.hit(ev.clientX - r.left, ev.clientY - r.top);
    const c = tipContent(hit);
    if (c) { tipEl.innerHTML = c; tipEl.hidden = false;
      tipEl.style.left = Math.max(0, Math.min(ev.clientX + 14, window.innerWidth - tipEl.offsetWidth - 8)) + "px";
      tipEl.style.top = Math.max(0, Math.min(ev.clientY + 16, window.innerHeight - tipEl.offsetHeight - 8)) + "px";
    } else tipEl.hidden = true;
  }

  // ---------- 右侧栏宽度拖拽 ----------
  const inspEl = $("#inspector"), handleEl = $("#inspHandle");
  let rzPending = false;
  function scheduleResize() { if (rzPending) return; rzPending = true;
    requestAnimationFrame(() => { rzPending = false; Render.resize(); }); }
  if (inspEl && handleEl) {
    const MIN = 240, MAX = 1000;
    const saved = parseInt(localStorage.getItem("inspWidth") || "380", 10);
    if (saved > 0) inspEl.style.width = saved + "px";
    function onDragMove(ev) {
      const rect = inspEl.parentElement.getBoundingClientRect();
      const w = rect.right - ev.clientX;
      inspEl.style.width = Math.max(MIN, Math.min(MAX, w)) + "px";
      scheduleResize();
    }
    function onDragUp() {
      handleEl.classList.remove("dragging"); document.body.classList.remove("resizing");
      document.removeEventListener("mousemove", onDragMove);
      document.removeEventListener("mouseup", onDragUp);
      localStorage.setItem("inspWidth", inspEl.style.width.replace("px", ""));
      scheduleResize();
    }
    function onDragDown(ev) {
      ev.preventDefault();
      handleEl.classList.add("dragging"); document.body.classList.add("resizing");
      document.addEventListener("mousemove", onDragMove);
      document.addEventListener("mouseup", onDragUp);
    }
    handleEl.addEventListener("mousedown", onDragDown);
  }

  // ---------- 输入 ----------
  function bindUI() {
    Panels.bindHandlers({
      onTab: t => { state.tab = t; if (state.selected) {
        if (t === "status") { fetchState(); if (state.detail) Panels.status(state.detail); }
        else { fetchDetail(); if (state.detailFor === state.selected) routeDetail(); } } },
      onFilter: () => Panels.feed(state.evRows),
    });
    Panels.setWhoHandler(async (s, r, o) => {
      const res = await query({ what: "who_knows", subject: s, relation: r, obj: o });
      if (!res) return;
      state.ui.highlight = new Set(res.npcs || []); pushUI();
      const many = (res.npcs || []).length;
      const hit = state.detail && state.detail.kb;
      Panels.title(`<b>${s} ${r} ${o}</b> · ${many} 人知晓（Esc 清除）`);
    });
    document.querySelectorAll("#speedbar [data-speed]").forEach(b =>
      b.addEventListener("click", () => send({ name: "set_speed", args: { speed: b.dataset.speed } })));
    const rb = $("#resetBtn");
    if (rb) rb.addEventListener("click", () => {
      send({ name: "reset", args: { seed: parseInt($("#seed").value, 10) || 3,
        kb_mode: $("#kb_mode").value } });
    });
    canvas.addEventListener("mousedown", ev => {
      const r = cvRect();
      const hit = Render.hit(ev.clientX - r.left, ev.clientY - r.top);
      state.ui.highlight = new Set(); pushUI();
      if (hit && hit.kind === "npc") {
        if (state.selected === hit.id) clearSelection();
        else selectNpc(hit.id);
      } else clearSelection();
    });
    canvas.addEventListener("mousemove", canvasMove);
    canvas.addEventListener("mouseleave", () => { tipEl.hidden = true; });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") { state.ui.highlight = new Set(); pushUI(); }
    });
    window.addEventListener("resize", () => Render.resize());
  }
  function speedGlow(spd) {
    document.querySelectorAll("#speedbar [data-speed]").forEach(b =>
      b.classList.toggle("on", b.dataset.speed === spd));
  }

  bindUI();
  connect();
  Render.resize();
})();
