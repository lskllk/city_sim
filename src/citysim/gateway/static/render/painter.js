/* painter.js —— 分层绘制；只读 VM/FX，禁止自己算位置。canvasrecode.md 第 6 节。
   Pass 0: 静态底图(缓存 offscreen, 只在 hello/resize/兜底房间出现时重绘)
   Pass 1-6: 旅行虚线 → 实体 → 交互连线 → NPC 本体(按 y 排序) → 头顶层 → FX */
"use strict";

const Painter = (() => {
  const ACT_COLOR = { sleep: "#3b5bdb", eat: "#e8890c", toilet: "#12b0c9",
                      fun: "#9c6ade", drink: "#4ab5e8", idle: "#9aa0ad",
                      move: "#5ad35a" };
  const NEED_ICON = { hunger: "🍚", thirst: "💧", energy: "😴", bladder: "🚽",
                      fun: "🎮", hp: "❤️" };
  const BG = "#0f1117";
  let canvas = null, ctx = null, staticLayer = null;
  let dpr = 1;

  function init(cv) { canvas = cv; ctx = cv.getContext("2d"); }

  function sizeBacking() {
    const r = canvas.getBoundingClientRect();
    dpr = window.devicePixelRatio || 1;
    Camera.setDpr(dpr);
    canvas.width = Math.max(1, Math.round(r.width * dpr));
    canvas.height = Math.max(1, Math.round(r.height * dpr));
    return r;
  }

  // hello/resize：量画布 + 相机 fit（仅这两处）+ 重建静态底图
  function layout(rooms) {
    if (!canvas) return;
    const r = sizeBacking();
    Camera.fit(rooms, r);
    rebuildStatic(rooms);
  }

  // 仅重建静态底图（兜底房间出现时；不动相机）
  function rebuildStatic(rooms) {
    if (!canvas) return;
    const r = canvas.getBoundingClientRect();
    dpr = window.devicePixelRatio || 1;
    Camera.setDpr(dpr);
    staticLayer = document.createElement("canvas");
    staticLayer.width = Math.max(1, Math.round(r.width * dpr));
    staticLayer.height = Math.max(1, Math.round(r.height * dpr));
    const c = staticLayer.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, r.width, r.height);
    c.fillStyle = BG; c.fillRect(0, 0, r.width, r.height);
    Camera.applyTo(c);
    for (const rm of rooms) drawRoomBackdrop(c, rm);
  }

  function drawRoomBackdrop(c, rm) {
    const z = Layout.zones(rm);
    c.fillStyle = "#181c26"; rr(c, rm.x, rm.y, rm.w, rm.h, 12); c.fill();
    c.strokeStyle = "#39415a"; c.lineWidth = 1.5;
    rr(c, rm.x, rm.y, rm.w, rm.h, 12); c.stroke();
    c.fillStyle = "#9fd1ff"; c.font = "bold 14px system-ui";
    c.textAlign = "left"; c.fillText(rm.name, rm.x + 16, rm.y + 20);
    c.strokeStyle = "#2c3242"; c.lineWidth = 1;
    c.beginPath(); c.moveTo(rm.x, z.shelf.y); c.lineTo(rm.x + rm.w, z.shelf.y); c.stroke();
    c.font = "11px system-ui";
  }

  function draw(ui) {
    if (!ctx || !staticLayer) return;
    const sel = (ui && ui.selected) || null;
    const hl = (ui && ui.highlight) || new Set();

    // Pass 0：静态底图（一次性缓存）
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(staticLayer, 0, 0);

    ctx.save();
    Camera.applyTo(ctx);

    // Pass 1：旅行虚线
    for (const a of VM.agents.values()) {
      if (a.state !== "TRAVEL") continue;
      const A = VM.roomCenter(a.travel.from), B = VM.roomCenter(a.travel.to);
      ctx.strokeStyle = "#3f6f4f"; ctx.setLineDash([5, 5]); ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(A.x, A.y); ctx.lineTo(B.x, B.y); ctx.stroke();
      ctx.setLineDash([]);
    }

    // Pass 2：实体
    for (const e of VM.entities.values()) drawEntity(e);

    // Pass 3：交互连线（NPC ↔ 正在使用的物件）
    for (const a of VM.agents.values()) {
      if (a.state !== "ENGAGED" || !a.targetEntity) continue;
      const e = VM.entities.get(a.targetEntity);
      if (!e) continue;
      ctx.strokeStyle = "rgba(159,209,255,.35)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(a.pos.x, a.pos.y); ctx.lineTo(e.pos.x, e.pos.y + 8); ctx.stroke();
    }

    // Pass 4：NPC 本体（按 pos.y 排序 → 伪深度）
    const ord = [...VM.agents.values()].sort((a, b) => a.pos.y - b.pos.y);
    for (const a of ord) drawBody(a, sel, hl);

    // Pass 5：头顶层（信息密度，永不被遮挡）
    for (const a of ord) drawOverlay(a);

    // Pass 6：FX
    drawFx();

    ctx.restore();
  }

  function drawEntity(e) {
    const x = e.pos.x, y = e.pos.y;
    if (e.name === "冰箱") {                 // 冰箱画矢量造型(无冰箱 emoji)
      drawFridge(x, y);
    } else {
      ctx.fillStyle = "#e6e9ef";
      ctx.font = "22px system-ui"; ctx.textAlign = "center";
      ctx.fillText(e.icon || "📦", x, y + 26);
      ctx.textAlign = "left"; ctx.font = "11px system-ui";
    }
    const hasStock = (e.tags && (e.tags.includes("container") || e.tags.includes("edible")));
    if (hasStock && typeof e.stock === "number") {
      const txt = e.stock === 0 ? "空" : String(e.stock);
      ctx.font = "10px system-ui";
      ctx.fillStyle = e.stock === 0 ? "#ff7a7a" : "#9aa0ad";
      ctx.textAlign = "center";
      ctx.fillText(txt, x, y + 42);
      ctx.textAlign = "left"; ctx.font = "11px system-ui";
    }
    if (e.claimedBy) {                       // 占用黄环
      ctx.strokeStyle = "#e6c04a"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x, y + 10, 15, 0, Math.PI * 2); ctx.stroke();
    }
  }

  // 矢量小冰箱(无对应 emoji): 门+上下分舱+把手; 世界坐标单位, 中心在 (x, y+14)
  function drawFridge(x, y) {
    const w = 22, h = 30, top = y + 2, left = x - w / 2;
    // 外框/主体
    ctx.fillStyle = "#d7deea";
    rr(ctx, left, top, w, h, 3); ctx.fill();
    ctx.strokeStyle = "#8a93a6"; ctx.lineWidth = 1.2;
    rr(ctx, left, top, w, h, 3); ctx.stroke();
    // 冷冻/冷藏分舱线
    const split = top + h * 0.42;
    ctx.strokeStyle = "#a8b0c1"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(left + 2, split); ctx.lineTo(left + w - 2, split); ctx.stroke();
    // 把手(左右门各一个小竖条, 上下舱)
    ctx.fillStyle = "#5b6478";
    const handleX = left + w - 5;
    ctx.fillRect(handleX, top + 3, 1.8, split - top - 6);
    ctx.fillRect(handleX, split + 3, 1.8, top + h - split - 6);
  }

  function drawBody(a, sel, hl) {
    const x = a.pos.x, y = a.pos.y;
    ctx.fillStyle = "rgba(0,0,0,.35)";            // 影子
    ctx.beginPath(); ctx.ellipse(x, y + 9, 9, 3, 0, 0, Math.PI * 2); ctx.fill();
    const col = ACT_COLOR[a.display_act || a.actClass] || "#9aa0ad";
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = BG; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.stroke();
    if (a.state === "WALK_TO") {                  // 脚下小尘点
      ctx.fillStyle = "rgba(255,255,255,.5)";
      ctx.beginPath(); ctx.arc(x - 4, y + 9, 1.5, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.arc(x + 4, y + 9, 1.2, 0, Math.PI * 2); ctx.fill();
    }    if (sel === a.id) {                           // 选中白环
      ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x, y, 13, 0, Math.PI * 2); ctx.stroke();
    }
    if (hl && hl.has(a.id)) {                     // who_knows 金环
      ctx.strokeStyle = "#ffd54a"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(x, y, 16, 0, Math.PI * 2); ctx.stroke();
    }
  }

  function glyph(txt, x, y, alpha, size) {
    ctx.globalAlpha = alpha === undefined ? 1 : alpha;
    ctx.font = (size || 15) + "px system-ui";
    ctx.textAlign = "center";
    ctx.fillText(txt, x, y);
    ctx.textAlign = "left"; ctx.font = "11px system-ui";
    ctx.globalAlpha = 1;
  }

  function drawOverlay(a) {
    const x = a.pos.x, y = a.pos.y;
    const settled = a.state !== "TRAVEL" && a.state !== "WALK_TO";
    ctx.fillStyle = "#dfe3ea"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
    ctx.fillText(a.name, x, y - 17);
    ctx.textAlign = "left"; ctx.font = "11px system-ui";

    if (!settled) return;               // 没落位: 不画动作/需求(避免"走着却睡着")

    // 交互进度环
    if (a.progress && a.progress.total > 0) {
      const p = 1 - a.progress.rem / a.progress.total;
      ctx.strokeStyle = ACT_COLOR[a.actClass] || "#9fd1ff"; ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.arc(x, y, 15, -Math.PI / 2, -Math.PI / 2 + p * Math.PI * 2); ctx.stroke();
    }
    // 状态符号（互斥）
    if (a.actClass === "sleep") glyph("Zzz", x + 14, y - 14, 1, 12);
    else if (FX.has("fail", a.id)) { ctx.font = "bold 15px system-ui"; ctx.fillStyle = "#ff7a7a";
      ctx.textAlign = "center"; ctx.fillText("!", x + 13, y - 2);
      ctx.textAlign = "left"; ctx.font = "11px system-ui"; }
    else if (FX.has("talk", a.id)) glyph("💬", x + 14, y - 4);

    // 需求气泡：最急的 1 个（用插值后的信号）
    if (a.needs && a.needs.length) {
      let worst = a.needs[0], wv = VM.signalAt(a, worst);
      for (const k of a.needs) { const v = VM.signalAt(a, k); if (v < wv) { wv = v; worst = k; } }
      const emoji = NEED_ICON[worst];
      if (emoji) {
        const now = performance.now();
        const blink = wv < 0.15 && (now / 400) % 2 < 1;
        if (!blink) glyph(emoji, x, y - 30);
      }
    }
  }

  function drawFx() {
    const now = performance.now();
    for (const f of FX.list()) {
      const u = 1 - (now - f.born) / (FX.TTL[f.kind] || 1);
      if (u <= 0) continue;
      const A = VM.agents.get(f.a);
      if (!A) continue;
      switch (f.kind) {
        case "arc": {
          const B = VM.agents.get(f.b);
          if (!B) break;
          const mx = (A.pos.x + B.pos.x) / 2;
          const my = Math.min(A.pos.y, B.pos.y) - 60;
          ctx.strokeStyle = `rgba(122,179,255,${0.9 * u})`; ctx.lineWidth = 2.5;
          ctx.beginPath(); ctx.moveTo(A.pos.x, A.pos.y);
          ctx.quadraticCurveTo(mx, my, B.pos.x, B.pos.y); ctx.stroke();
          break;
        }
        case "think": {
          const r2 = 10 + 14 * (1 - u);
          ctx.strokeStyle = `rgba(255,255,255,${0.7 * u})`; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(A.pos.x, A.pos.y, r2, 0, Math.PI * 2); ctx.stroke();
          break;
        }
        case "talk": glyph("💬", A.pos.x + 14, A.pos.y - 6, u); break;
        case "learn": {
          glyph("💡", A.pos.x + 2, A.pos.y - 42 - 8 * (1 - u), u);
          if (f.data && f.data.short) {
            ctx.fillStyle = `rgba(122,179,255,${u})`;
            ctx.font = "10px system-ui"; ctx.textAlign = "center";
            ctx.fillText(f.data.short, A.pos.x, A.pos.y - 30);
            ctx.textAlign = "left"; ctx.font = "11px system-ui";
          }
          break;
        }
        default: break;
      }
    }
  }

  function rr(c, x, y, w, h, r) {
    c.beginPath(); c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }

  return { init, layout, rebuildStatic, draw };
})();
