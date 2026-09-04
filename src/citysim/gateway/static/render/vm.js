/* vm.js —— ViewModel: snapshot 只喂"目标"，位置由 VM 演化。canvasrecode 第 4 节。
   修正(用户要求): 人物移动"实时、不平滑插值"——删除 ease/缓动。
     - 跨房间: 按 tick 沿 from→to 中心线线性推进(真实速度)
     - 房内: 恒速走向目标(slot/物件下方), 非 easeInOut
     - idle: 停在房间地板槽位内(坐标钳制, 不越框)
   draw()/painter 只读 VM。 */
"use strict";

const VM = (() => {
  const agents = new Map();
  const entities = new Map();
  let rooms = [];
  let roomById = new Map();
  let tick = 0, tps = 0;
  let roomsDirty = false;
  let fallbackN = 0;
  const ROOM_SPEED = 150;        // 房内移动速度(世界单位/秒, 恒速)

  function _dirty() { roomsDirty = true; }
  function loadRooms(locJson) {
    rooms = Layout.loadRooms(locJson);
    roomById = new Map(rooms.map(r => [r.id, r]));
    entities.clear(); agents.clear();
    fallbackN = 0; roomsDirty = true;
  }
  function clear() { entities.clear(); agents.clear(); }
  function changedRooms() { const d = roomsDirty; roomsDirty = false; return d; }

  function ensureRoom(locId) {
    if (roomById.has(locId)) return roomById.get(locId);
    const box = Layout.bbox(rooms);
    const rm = { id: locId, x: box.x0 + (fallbackN % 3) * 280,
                 y: Math.max(box.y0, box.y1 - 190), w: 260, h: 180,
                 name: locId };
    rooms.push(rm); roomById.set(locId, rm); fallbackN++; _dirty();
    return rm;
  }

  function spawnAgent(n) {
    return { id: n.id, name: n.name, room: n.loc, pos: { x: 0, y: 0 },
             dest: null, state: "IDLE", floorSlot: 0, targetEntity: null,
             actClass: "idle", progress: null,
             signals: { prev: {}, next: {}, at: 0 }, needs: [], travel: null };
  }

  function reconcile(s) {
    tick = s.tick; tps = s.tps || 0;
    for (const n of s.npcs) ensureRoom(n.loc);
    for (const e of s.entities) ensureRoom(e.loc);

    for (const e of s.entities) {
      let ev = entities.get(e.id);
      if (!ev) { ev = { id: e.id, pos: { x: 0, y: 0 } }; entities.set(e.id, ev); }
      ev.name = e.name; ev.loc = e.loc; ev.icon = e.icon; ev.tags = e.tags;
      ev.stock = e.stock; ev.claimedBy = e.claimed_by;
      ev.pos = Layout.entitySlot(ensureRoom(e.loc), e.shelf_index || 0);
    }

    const slotsByRoom = new Map();
    const byRoom = new Map();
    for (const n of s.npcs) {
      if (!byRoom.has(n.loc)) byRoom.set(n.loc, []);
      byRoom.get(n.loc).push(n.id);
    }
    for (const [rid, ids] of byRoom)
      if (roomById.has(rid)) slotsByRoom.set(rid, Layout.assignFloorSlots(rid, [...ids].sort()));

    const seen = new Set();
    for (const n of s.npcs) {
      seen.add(n.id);
      let a = agents.get(n.id);
      const rm = roomById.get(n.loc);
      const slot = rm && slotsByRoom.get(n.loc) ? (slotsByRoom.get(n.loc)[n.id] ?? 0) : 0;
      if (!a) {
        a = spawnAgent(n); agents.set(n.id, a);
        a.floorSlot = slot;
        a.pos = rm ? { ...Layout.floorSlotPos(rm, slot) } : { x: 0, y: 0 };
      }
      a.name = n.name; a.actClass = n.act_class || "idle";
      a.progress = n.active ? { rem: n.active.remaining, total: n.active.total } : null;
      const sig = n.signals || {};
      a.signals = { prev: (a.signals && a.signals.next) || sig, next: sig, at: s.tick };
      a.needs = Object.keys(sig).filter(k => sig[k] < 0.30);

      // ① 跨房间: update 沿路径线性推进
      if (n.travel) { a.state = "TRAVEL"; a.travel = n.travel; a.dest = null;
        a.display_act = "move"; continue; }
      a.travel = null;
      if (a.room !== n.loc) a.room = n.loc;
      a.floorSlot = slot;

      const home = rm ? Layout.floorSlotPos(rm, slot) : a.pos;
      let target;
      if (n.active) {
        a.targetEntity = n.active.entity;
        const ev = entities.get(a.targetEntity);
        const base = ev ? ev.pos : a.pos;
        target = { x: base.x, y: base.y + 22 };
      } else {
        a.targetEntity = null;
        target = home;
      }
      // 恒速走向 target; 已在目标则停住
      const near = Math.hypot(a.pos.x - target.x, a.pos.y - target.y) < 1;
      if (near) { a.dest = { ...target };
        a.state = a.targetEntity ? "ENGAGED" : "IDLE"; }
      else { a.dest = { ...target };
        a.state = a.targetEntity ? "WALK_TO" : "WALK_TO"; }
      a.display_act = (a.state === "TRAVEL" || a.state === "WALK_TO")
        ? "move" : (a.actClass || "idle");
    }

    for (const id of [...agents.keys()]) if (!seen.has(id)) agents.delete(id);
    const seenE = new Set(s.entities.map(e => e.id));
    for (const id of [...entities.keys()]) if (!seenE.has(id)) entities.delete(id);
  }

  function update(dt) {
    tick += dt * tps;
    for (const a of agents.values()) {
      if (a.state === "TRAVEL" && a.travel) {
        const tv = a.travel;
        const f = Math.max(0, Math.min(1, (tick - tv.depart) / Math.max(1, tv.arrive - tv.depart)));
        const A = roomCenter(tv.from), B = roomCenter(tv.to);
        a.pos = { x: A.x + (B.x - A.x) * f, y: A.y + (B.y - A.y) * f };
      } else if (a.dest) {
        const dx = a.dest.x - a.pos.x, dy = a.dest.y - a.pos.y;
        const d = Math.hypot(dx, dy);
        if (d < 0.5) {
          a.pos = { ...a.dest };
          if (a.targetEntity) a.state = "ENGAGED";
        } else {
          const step = Math.min(d, ROOM_SPEED * dt);
          a.pos = { x: a.pos.x + dx / d * step, y: a.pos.y + dy / d * step };
        }
      }
    }
  }

  function roomCenter(id) {
    const r = roomById.get(id);
    return r ? Layout.roomCenter(r) : { x: 0, y: 0 };
  }
  function signalAt(a, key) {
    if (!a.signals || !(key in a.signals.next)) return 1;
    const span = Math.max(1, (tps || 0) * 0.1);
    const f = Math.max(0, Math.min(1, (tick - a.signals.at) / span));
    const pv = key in a.signals.prev ? a.signals.prev[key] : a.signals.next[key];
    return pv + (a.signals.next[key] - pv) * f;
  }

  return { rooms: () => rooms, agents, entities, loadRooms, clear, reconcile,
           update, signalAt, changedRooms, roomCenter };
})();
