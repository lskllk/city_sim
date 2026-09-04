/* layout.js —— 房间几何 / 分区 / 槽位分配。
   canvasrecode.md 第 3 节：纯函数、无 let 状态、可单测。
   职责边界：painter 不许算位置，layout 不许有状态。 */
"use strict";

const Layout = (() => {
  const CAPACITY = 24;            // 每房间待机槽上限

  // hello.locations → rooms 数组 [{id,x,y,w,h,name}]（只含场景实际房间）
  function loadRooms(locJson) {
    const src = (locJson && locJson.locations) || {};
    const out = [];
    for (const [id, g] of Object.entries(src)) {
      out.push({ id, x: g.x || 0, y: g.y || 0, w: g.w || 0,
                 h: g.h || 0, name: g.name || id });
    }
    out.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    return out;
  }

  // 全部房间的包围盒（相机 fit 用）
  function bbox(rooms) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const r of rooms) {
      x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y);
      x1 = Math.max(x1, r.x + r.w); y1 = Math.max(y1, r.y + r.h);
    }
    if (!isFinite(x0)) { x0 = y0 = 0; x1 = y1 = 1; }
    return { x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 };
  }

  // 房间三分区（第 3.1 节）
  function zones(room) {
    return {
      title: { x: room.x, y: room.y, w: room.w, h: 28 },
      shelf: { x: room.x, y: room.y + 28, w: room.w, h: 64 },
      floor: { x: room.x, y: room.y + 92, w: room.w,
               h: Math.max(30, room.h - 92) },
    };
  }

  // 实体槽位（第 3.2 节）：shelf_index 来自服务端，前端只排布
  function entitySlot(room, shelfIndex) {
    const z = zones(room).shelf, step = 44;
    const cols = Math.max(1, Math.floor((z.w - 24) / step));
    const row = Math.floor(shelfIndex / cols);
    return { x: z.x + 22 + (shelfIndex % cols) * step,
             y: z.y + 20 + row * 34 };
  }

  function fnv1a32(s) {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }
  function hashSlot(npcId, roomId) {
    return fnv1a32(npcId + "@" + roomId) % CAPACITY;
  }

  // 确定性待机槽分配（第 3.3 节）：同 (npc,room) 永远同槽；冲突线性探测
  function assignFloorSlots(roomId, npcIds) {
    const taken = {}, out = {};
    for (const id of npcIds) {
      let k = hashSlot(id, roomId);
      while (taken[k]) k = (k + 1) % CAPACITY;
      taken[k] = true; out[id] = k;
    }
    return out;
  }

  function floorSlotPos(room, slotIndex) {
    const z = zones(room).floor, step = 46;
    const cols = Math.max(1, Math.floor((z.w - 24) / step));
    const maxRows = Math.max(1, Math.floor((z.h - 34) / 44));
    let c = slotIndex % cols, row = Math.floor(slotIndex / cols);
    row = Math.min(row, maxRows - 1);            // 钳制在房内地板区内
    c = Math.min(c, cols - 1);
    return { x: z.x + 24 + c * step,
             y: z.y + 26 + row * 44 };
  }

  function roomCenter(r) { return { x: r.x + r.w / 2, y: r.y + r.h / 2 }; }

  return { CAPACITY, loadRooms, bbox, zones, entitySlot, hashSlot,
           assignFloorSlots, floorSlotPos, roomCenter };
})();
