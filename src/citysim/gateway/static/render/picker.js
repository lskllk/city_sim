/* picker.js —— hitTest 只读 VM（canvasrecode.md 第 8 节）。
   点选结果必须与渲染一致：位置唯一真源在 VM，禁止在此重算。 */
"use strict";

const Picker = (() => {
  // px,py = 相对画布左上角的 CSS 像素
  function hit(px, py) {
    const p = Camera.toWorld(px, py);
    // 从上层(高 y, 后绘制)往下测：NPC 优先于房间/实体
    const ord = [...VM.agents.values()].sort((a, b) => b.pos.y - a.pos.y);
    for (const a of ord) {
      if (Math.hypot(p.x - a.pos.x, p.y - a.pos.y) < 16)
        return { kind: "npc", id: a.id };
    }
    for (const e of VM.entities.values()) {
      if (Math.hypot(p.x - e.pos.x, p.y - (e.pos.y + 10)) < 16)
        return { kind: "entity", id: e.id };
    }
    for (const rm of VM.rooms()) {
      if (p.x >= rm.x && p.x <= rm.x + rm.w && p.y >= rm.y && p.y <= rm.y + rm.h)
        return { kind: "room", id: rm.id };
    }
    return null;
  }
  return { hit };
})();
