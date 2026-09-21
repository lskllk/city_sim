/** store.js —— 世界状态（hello + 增量 snapshot 合并）。
 *
 * 后端契约（见 gateway/snapshot.py）：
 *   · npcs/entities 是**增量**：只推渲染状态变了的那些 → 本地按 id 合并
 *   · `gone` 里的 id 必须删掉，否则会留下幽灵
 *   · 被选中的人（focus）额外带 memory/intent/events —— 10Hz 才来一次
 *   · 每个 NPC 带 `bubble {text, until}`：过期由前端自己判，后端不会再推空帧
 */

export class Store {
  constructor() {
    this.hello = null;
    this.canvas = { w: 800, h: 600 };
    this.locations = {};
    this.map = {};
    this.companies = [];
    this.npcs = new Map();
    this.entities = new Map();
    this.tick = 0; this.day = 1; this.clock = "--:--"; this.speed = "pause";
    this.focus = "";
    this.listeners = new Set();
  }

  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  _emit(what) { for (const fn of this.listeners) fn(what, this); }

  applyHello(h) {
    this.hello = h;
    this.canvas = h.locations?.canvas || this.canvas;
    this.locations = h.locations?.locations || {};
    this.map = h.map || {};
    this.companies = h.companies || [];
    this._emit("hello");
  }

  applySnapshot(s) {
    this.tick = s.tick; this.day = s.day; this.clock = s.clock; this.speed = s.speed;
    for (const n of s.npcs || []) this.npcs.set(n.id, { ...this.npcs.get(n.id), ...n });
    for (const e of s.entities || []) this.entities.set(e.id, { ...this.entities.get(e.id), ...e });
    const gone = s.gone || {};
    for (const id of gone.npcs || []) this.npcs.delete(id);
    for (const id of gone.entities || []) this.entities.delete(id);
    this._emit("snapshot");
  }

  /** 地图的指纹 —— 变了才重画地面/路/建筑（每帧重画 = 60Hz 建几万个对象）。 */
  builtKey() {
    return Object.keys(this.locations).sort()
      .map(id => `${id}:${this.locations[id].x},${this.locations[id].y}`).join("|");
  }

  /** 这一帧里带着完整记忆的那个人（没在看谁时是 undefined）。 */
  focused() { return this.focus ? this.npcs.get(this.focus) : undefined; }

  /** 老板自己的店 —— 开局镜头对准它。 */
  myShop() {
    for (const c of this.companies)
      for (const id of c.shops || []) if (this.locations[id]) return this.locations[id];
    return null;
  }

  /** 还没过期的气泡（前端自己算过期，后端不再补空帧）。 */
  bubbleOf(npc) {
    const b = npc.bubble;
    if (!b) return null;
    if (b.until != null && b.until <= this.tick) return null;
    return b.text || null;
  }
}
