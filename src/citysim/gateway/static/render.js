/* render.js —— Canvas 房间/实体/NPC/移动插值/传闻弧线(display_m5_ui 8.2)。 */
const Render = (() => {
  let canvas, ctx, geo = {};   // geo: locId -> {x,y,w,h,name}
  let fallbackIdx = 0;
  const W = 1200, H = 700;
  const ACT_COLOR = { sleep: "#3b5bdb", eat: "#e8890c", toilet: "#12b0c9",
                      fun: "#9c6ade", drink: "#4ab5e8", idle: "#9aa0ad", move: "#5ad35a" };
  const slotX = [0, 1, 2, 3, 4, 5, 0, 1, 2, 3, 4, 5];
  const slotY = [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1];

  function classify(npc) {
    if (npc.travel) return "move";
    const a = npc.activity || "";
    if (a.includes("床") || (npc.active && npc.active.entity && a.includes("床"))) return "sleep";
    if (a.includes("餐") || a.includes("食") || a.includes("冰箱")) return "eat";
    if (a.includes("马桶")) return "toilet";
    if (a.includes("电视")) return "fun";
    if (a.includes("饮水")) return "drink";
    return "idle";
  }

  function init(cv) { canvas = cv; ctx = canvas.getContext("2d"); }

  function setGeometry(locations) {
    geo = {}; fallbackIdx = 0;
    for (const [id, g] of Object.entries(locations.locations || {})) geo[id] = g;
  }

  function geom(loc) {
    if (geo[loc]) return geo[loc];
    if (!geo.__fallback) geo.__fallback = {};
    if (!geo.__fallback[loc]) {
      const x = 880 + (fallbackIdx % 3) * 0, y = 320 + (fallbackIdx % 2) * 180;
      fallbackIdx++;
      geo.__fallback[loc] = { x, y, w: 260, h: 160, name: loc };
    }
    return geo.__fallback[loc];
  }
  function center(loc) { const g = geom(loc); return { x: g.x + g.w / 2, y: g.y + g.h / 2 }; }

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const r = canvas.getBoundingClientRect();
    canvas.width = r.width * dpr; canvas.height = r.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function npcPos(npc, tickNow) {
    if (npc.travel) {
      const a = center(npc.travel.from), b = center(npc.travel.to);
      const dt = (npc.travel.arrive - npc.travel.depart) || 1;
      let t = (tickNow - npc.travel.depart) / dt;
      t = Math.max(0, Math.min(1, t));
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
    }
    const g = geom(npc.loc);
    const idx = npc.id in Render._idx ? Render._idx[npc.id] : 0;
    return { x: g.x + 44 + slotX[idx % 12] * 40, y: g.y + 60 + slotY[idx % 12] * 34 };
  }

  function draw(snap, tickNow, ui) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#12141a"; ctx.fillRect(0, 0, canvas.clientWidth || W, canvas.clientHeight || H);
    // 房间
    const locs = new Set();
    for (const n of snap.npcs) locs.add(n.loc);
    for (const n of snap.npcs) if (n.travel) { locs.add(n.travel.from); locs.add(n.travel.to); }
    for (const e of snap.entities) locs.add(e.loc);
    for (const loc of locs) {
      const g = geom(loc);
      const hi = ui.follow === loc || (ui.selected && snap.npcs.find(n => n.id === ui.selected && n.loc === loc));
      ctx.strokeStyle = hi ? "#e6c04a" : (geo.__fallback && geo.__fallback[loc] ? "#666" : "#3a4150");
      ctx.lineWidth = hi ? 3 : 1.5;
      roundRect(ctx, g.x, g.y, g.w, g.h, 10); ctx.stroke();
      ctx.fillStyle = "#9aa0ad"; ctx.font = "bold 13px system-ui";
      ctx.fillText(g.name, g.x + 12, g.y + 20);
    }
    // 实体
    const byLoc = {};
    for (const e of snap.entities) (byLoc[e.loc] = byLoc[e.loc] || []).push(e);
    for (const [loc, ents] of Object.entries(byLoc)) {
      const g = geom(loc);
      ents.sort((a, b) => a.id < b.id ? -1 : 1).forEach((e, i) => {
        const x = g.x + 14 + i * 34, y = g.y + 30;
        ctx.font = "20px system-ui"; ctx.textAlign = "center";
        ctx.fillText(e.icon || "📦", x, y + 16);
        ctx.font = "10px system-ui";
        ctx.fillStyle = "#9aa";
        ctx.fillText(e.stock === -1 ? "∞" : String(e.stock), x, y + 30);
        if (e.claimed_by) {
          ctx.strokeStyle = "#e6c04a"; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(x, y + 8, 14, 0, Math.PI * 2); ctx.stroke();
          ctx.fillStyle = "#e6c04a"; ctx.font = "11px system-ui";
          ctx.fillText(String(e.claimed_by).slice(-2), x, y + 11);
        }
      });
      ctx.textAlign = "left";
    }
    // NPC 索引
    const ids = snap.npcs.map(n => n.id).sort();
    ids.forEach((id, i) => { Render._idx[id] = i; });
    // NPC 点
    const lastPos = {};
    for (const n of snap.npcs) {
      const p = npcPos(n, tickNow); lastPos[n.id] = p;
      const act = classify(n);
      ctx.fillStyle = ACT_COLOR[act] || "#9aa0ad";
      ctx.beginPath(); ctx.arc(p.x, p.y, 9, 0, Math.PI * 2); ctx.fill();
      if (ui.selected === n.id) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke(); }
      if (ui.highlight && ui.highlight.has(n.id)) {
        ctx.strokeStyle = "#ffd54a"; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(p.x, p.y, 14, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.fillStyle = "#dfe3ea"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
      ctx.fillText(n.name, p.x, p.y - 13);
      if (act === "sleep") ctx.fillText("Zzz", p.x + 10, p.y - 14);
      if (ui.flags && ui.flags.failed.has(n.id)) { ctx.fillStyle = "#ff7a7a"; ctx.font = "bold 13px system-ui"; ctx.fillText("!", p.x + 8, p.y - 6); }
      if (ui.flags && ui.flags.talking.has(n.id)) ctx.fillText("💬", p.x + 10, p.y - 2);
      ctx.textAlign = "left";
    }
    Render._lastPos = lastPos;
    // 传闻弧线(淡出)
    const now = performance.now();
    for (const a of ui.arcs || []) {
      const age = now - a.born;
      if (age > 900) continue;
      const f = 1 - age / 900;
      const p1 = lastPos[a.from], p2 = lastPos[a.to];
      if (!p1 || !p2) continue;
      const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2 - 40;
      ctx.strokeStyle = `rgba(122,179,255,${0.9 * f})`;
      ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.quadraticCurveTo(mx, my, p2.x, p2.y); ctx.stroke();
    }
  }

  function roundRect(c, x, y, w, h, r) {
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }

  function hitTest(snap, tickNow, px, py) {
    for (const n of snap.npcs) {
      const p = npcPos(n, tickNow);
      if (Math.hypot(p.x - px, p.y - py) < 16) return { kind: "npc", id: n.id };
    }
    for (const loc of new Set([...snap.npcs.map(n => n.loc)])) {
      const g = geom(loc);
      if (px >= g.x && px <= g.x + g.w && py >= g.y && py <= g.y + g.h) return { kind: "room", id: loc };
    }
    return null;
  }

  return { init, resize, setGeometry, draw, hitTest, npcPos, geom, center, classify, _idx: {}, _lastPos: {} };
})();
