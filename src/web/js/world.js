/** world.js —— 游戏里的世界。相机/输入/纸片/地图都在别处，这里只加「人」。
 *
 *   View     相机 + 拖动缩放 + 屏幕纸片      （view.js，和编辑器共用）
 *   MapLayer 地图：地面/路/建筑              （maprender.js，和编辑器共用）
 *   本文件   人 + 气泡 + 点人                ← 只有游戏需要
 */
import { Container, Sprite } from '../vendor/pixi.min.mjs';
import { View, U } from './view.js';
import { MapLayer } from './maprender.js';

export class World {
  constructor(canvasEl, store, hudEl, assets) {
    this.store = store;
    this.assets = assets;
    this.view = new View(canvasEl, hudEl);
    this.map = new MapLayer(assets, (lid, loc, p) =>
      this.view.paper("sign:" + lid, loc.name, p.x / U, p.y / U + 0.8, "plate"));
    this.npc = new Container();
    this.npc.sortableChildren = true;
    this._people = new Map();
    this.onSelect = null;
  }

  async init() {
    await this.view.init();
    this.map.root.zIndex = 0; this.npc.zIndex = 1;
    this.view.worldLayer.addChild(this.map.root, this.npc);
    this.view.onView = () => this.view.syncPaper();
    // 点人；拖是平移（onDown 不接 → 相机默认接管）
    this.view.onPick = (x, y) => this.onSelect?.(this.pick(x, y), [x, y]);
    return this;
  }

  /** 场景形状和编辑器导出的一样：{canvas, locations, map} */
  scene() {
    return { canvas: this.store.canvas, locations: this.store.locations, map: this.store.map };
  }

  /** 点到谁了。人优先 —— 他们很小，但最该点得中。 */
  pick(wx, wy) {
    let best = "", bestD = 26 / this.view.cam.k;
    for (const [id, p] of this._people) {
      const d = Math.hypot(p.spr.x / U - wx, p.spr.y / U - wy);
      if (d < bestD) { bestD = d; best = id; }
    }
    if (best) return best;
    for (const [lid, loc] of Object.entries(this.store.locations))
      if (wx >= loc.x && wx <= loc.x + loc.w && wy >= loc.y && wy <= loc.y + loc.h)
        return "loc:" + lid;
    return "";
  }

  frame() {
    this.view.step();
    this.map.draw(this.scene());
    const alive = new Set();
    for (const [id, npc] of this.store.npcs) {
      alive.add(id);
      const [wx, wy] = npc.position || [0, 0];
      const p = this._people.get(id) || this._spawn(id);
      p.spr.x = wx * U; p.spr.y = wy * U;
      p.spr.zIndex = Math.round(wy);
      p.spr.tint = this.store.focus === id ? 0xffd9a0 : 0xffffff;
      const key = `people/${id}_${this._dir(npc, p)}_idle.svg`;
      const t = this.assets.get(key);
      if (t && p.spr.texture !== t) p.spr.texture = t;
      this._bubble(id, npc, wx, wy);
    }
    for (const [id, p] of [...this._people])
      if (!alive.has(id)) { p.spr.destroy(); this._people.delete(id); this.view.dropPaper("npc:" + id); }
    this.view.syncPaper();
  }

  _spawn(id) {
    const spr = new Sprite(this.assets.get("people/me_down_idle.svg") || undefined);
    spr.width = 18; spr.height = 24; spr.anchor.set(0.5, 1);
    spr.eventMode = "static";
    this.npc.addChild(spr);
    const p = { spr, dir: "down", last: null };
    this._people.set(id, p);
    return p;
  }

  /** 朝向按位移判断；站着不动就沿用上次的（别每帧抖）。 */
  _dir(npc, p) {
    const cur = npc.position || [0, 0];
    if (p.last) {
      const dx = cur[0] - p.last[0], dy = cur[1] - p.last[1];
      if (Math.hypot(dx, dy) > 0.15)
        p.dir = Math.abs(dx) > Math.abs(dy) ? "side" : (dy < 0 ? "up" : "down");
    }
    p.last = cur;
    return p.dir;
  }

  _bubble(id, npc, wx, wy) {
    const txt = this.store.bubbleOf(npc);
    this.view.paper("npc:" + id, txt, wx, wy - 1.6);
  }
}
