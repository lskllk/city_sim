/* render.js —— 装配层：连接 VM/Camera/Painter/Picker/FX，掌管 rAF。
   canvasrecode.md 第 5 节：onSnapshot 只 reconcile；渲染节奏完全由本模块 rAF 掌管。
   相机只在 hello / resize（都在 Painter.layout 内）计算。 */
"use strict";

const Render = (() => {
  let canvas = null;
  let ui = { selected: null, highlight: new Set() };
  let lastMs = 0;

  function init(cv) {
    canvas = cv;
    Painter.init(cv);
    requestAnimationFrame(frame);
  }

  // hello：载入房间(只含场景实际房间) + 相机 fit + 重建静态底图 + 清空 VM/FX
  function hello(m) {
    VM.loadRooms((m && m.locations) || {});   // 已是 {canvas, locations}
    Painter.layout(VM.rooms());
    ui = { selected: null, highlight: new Set() };
    FX.clear();
  }

  // 每个 snapshot：只 reconcile（把 snapshot 当"目标"喂给 VM）
  function snapshot(s) {
    if (!s) return;
    VM.reconcile(s);
    if (VM.changedRooms()) Painter.rebuildStatic(VM.rooms());
  }

  function resize() {
    if (!canvas) return;
    Painter.layout(VM.rooms());
  }

  function setUI(o) { ui = o || { selected: null, highlight: new Set() }; }
  function hit(px, py) { return Picker.hit(px, py); }
  function roomNames() {
    const m = {};
    for (const r of VM.rooms()) m[r.id] = r.name;
    return m;
  }

  function frame(nowMs) {
    requestAnimationFrame(frame);
    const dt = Math.min(0.05, (nowMs - (lastMs || nowMs)) / 1000);
    lastMs = nowMs;
    VM.update(dt);
    FX.update();
    Painter.draw(ui);
  }

  // 调试/点选定位：返回相对画布左上角的 CSS 像素坐标（读 VM 唯一真源）
  function locate(id) {
    const a = VM.agents.get(id);
    if (!a) return null;
    const c = Camera.get();
    return { x: c.ox + a.pos.x * c.s, y: c.oy + a.pos.y * c.s };
  }
  function locateAll() {
    const c = Camera.get();
    const o = {};
    for (const [id, a] of VM.agents) o[id] = { x: c.ox + a.pos.x * c.s, y: c.oy + a.pos.y * c.s };
    return o;
  }

  return { init, hello, snapshot, resize, setUI, hit, roomNames, locate, locateAll };
})();
