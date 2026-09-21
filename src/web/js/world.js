/** world.js —— 用 PixiJS 画世界。
 *
 *  地面 = 平铺图。9600×7200 px 铺满要 67500 个精灵，用 TilingSprite 只有一次绘制。
 *  道路 = 从 map 的 nodes/edges 描线 —— 路是【图】，路面是渲染出来的结果。
 *  建筑 = 把美术按【世界占地】缩放。占地是真值，美术是贴上去的。
 *  人   = 脚底对齐位置点，和建筑一起按 y 排序（站在房子前面就该压在房子上）。
 *
 * 坐标：世界单位（米）→ 像素，统一乘 U。
 */
import { Application, Container, Graphics, Sprite, TilingSprite, Assets } from '../vendor/pixi.min.mjs';

export const U = 12;                 // 1 世界单位 = 12 px（让美术自然尺寸≈占地尺寸）

const ROAD = 0x4c4a4a, ROAD_EDGE = 0x3a3838;

export class World {
  constructor(canvasEl, store, hudEl) {
    this.el = canvasEl;
    this.store = store;
    this.hud = hudEl;
    this.app = new Application();
    this.cam = { x: 0, y: 0, zoom: 1 };
    this.onPick = null;                     // (npcId|"loc:xx"|"", {x,y}) => void
    this._nodes = new Map();                // 显示对象，用来命中/更新
    this._people = new Map();               // npcId -> {spr, dir, texKey}
    this._paper = new Map();                // npcId -> 气泡 div
    this._builtKey = "";
  }

  async init() {
    await this.app.init({
      canvas: this.el, background: 0x6d8a52, antialias: true,
      resolution: Math.min(devicePixelRatio || 1, 2), autoDensity: true,
      resizeTo: this.el.parentElement,
    });
    this.root = new Container();
    this.root.sortableChildren = true;
    this.app.stage.addChild(this.root);
    this.L = {};
    for (const [i, k] of ["ground", "road", "bld", "npc"].entries()) {
      const c = new Container();
      c.sortableChildren = (k === "bld" || k === "npc");
      c.zIndex = i; this.L[k] = c; this.root.addChild(c);
    }
    this._input();
    return this;
  }

  async preload(manifest) {
    this.manifest = manifest;
    const files = manifest.assets
      .filter(a => ["ground", "body", "shadow"].includes(a.sub))
      .map(a => a.file);
    const out = await Promise.allSettled(files.map(f => Assets.load("/art/" + f)));
    this._tex = new Map();
    files.forEach((f, i) => this._tex.set(f, out[i].status === "fulfilled" ? out[i].value : null));
    return this;
  }

  tex(f) {
    if (this._tex.has(f)) return this._tex.get(f);
    // 人物这类按需加载的，先给 null，纹理到了再填（Pixi 的 Assets 自己有缓存）
    this._tex.set(f, null);
    Assets.load("/art/" + f).then(t => this._tex.set(f, t)).catch(() => {});
    return null;
  }

  // ── 相机 ────────────────────────────────────────────────────────────
  _apply() { this.root.scale.set(this.cam.zoom); this.root.position.set(this.cam.x, this.cam.y); }
  viewport() {
    return [this.app.renderer.width / this.app.renderer.resolution,
            this.app.renderer.height / this.app.renderer.resolution];
  }
  centerOn(wx, wy, zoom) {
    if (zoom) this.cam.zoom = zoom;
    const [vw, vh] = this.viewport();
    this.cam.x = vw / 2 - wx * U * this.cam.zoom;
    this.cam.y = vh / 2 - wy * U * this.cam.zoom;
    this._apply();
  }
  fit() {
    const { w, h } = this.store.canvas, [vw, vh] = this.viewport();
    this.centerOn(w / 2, h / 2, Math.min((vw - 70) / (w * U), (vh - 70) / (h * U)));
  }
  toWorld(sx, sy) {
    const s = this.root.scale.x, p = this.root.position;
    return { x: (sx - p.x) / s / U, y: (sy - p.y) / s / U };
  }

  _input() {
    const el = this.el;
    let drag = null, moved = 0;
    el.addEventListener("pointerdown", e => {
      drag = { x: e.clientX, y: e.clientY, cx: this.cam.x, cy: this.cam.y };
      moved = 0; el.setPointerCapture(e.pointerId);
    });
    el.addEventListener("pointermove", e => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      moved = Math.max(moved, Math.hypot(dx, dy));
      this.cam.x = drag.cx + dx; this.cam.y = drag.cy + dy; this._apply();
    });
    el.addEventListener("pointerup", e => {
      el.releasePointerCapture?.(e.pointerId);
      const dragged = moved > 4; drag = null;
      if (dragged || !this.onPick) return;
      const r = el.getBoundingClientRect();
      const p = this.toWorld(e.clientX - r.left, e.clientY - r.top);
      this.onPick(this.pick(p.x, p.y), p);
    });
    el.addEventListener("wheel", e => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const sx = e.clientX - r.left, sy = e.clientY - r.top;
      const before = this.toWorld(sx, sy);
      this.cam.zoom = Math.max(0.12, Math.min(8, this.cam.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
      this._apply();
      const after = this.toWorld(sx, sy);
      this.cam.x += (after.x - before.x) * U * this.cam.zoom;
      this.cam.y += (after.y - before.y) * U * this.cam.zoom;
      this._apply();
    }, { passive: false });
  }

  /** 点到谁了。人优先 —— 他们很小，但最该点得中。 */
  pick(wx, wy) {
    let best = "", bestD = 26 / this.cam.zoom;
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

  // ── 地图（变了才重画）──────────────────────────────────────────────
  rebuildIfNeeded() {
    const key = `${this.store.canvas.w}x${this.store.canvas.h}|${this.store.builtKey()}`;
    if (key === this._builtKey) return;
    this._builtKey = key;
    this._ground(); this._roads(); this._buildings();
  }

  _tile(layer, file, x, y, w, h, fallbackColor) {
    const t = this.tex(file);
    layer.addChild(t ? new TilingSprite({ texture: t, x, y, width: w, height: h })
                     : new Graphics().rect(x, y, w, h).fill(fallbackColor));
  }

  _ground() {
    const g = this.L.ground; g.removeChildren();
    const { w, h } = this.store.canvas;
    this._tile(g, "ground/grass.svg", 0, 0, w * U, h * U, 0x6d8a52);
  }

  _roads() {
    const g = this.L.road; g.removeChildren();
    const { nodes = {}, edges = {} } = this.store.map || {};
    for (const e of Object.values(edges)) {
      const a = nodes[e.a]?.xy, b = nodes[e.b]?.xy;
      if (!a || !b) continue;
      const pts = (e.geom && e.geom.length >= 2) ? e.geom : [a, b];
      const w = (e.width || 4) * U;
      const gr = new Graphics();
      gr.moveTo(pts[0][0] * U, pts[0][1] * U);
      for (let i = 1; i < pts.length; i++) gr.lineTo(pts[i][0] * U, pts[i][1] * U);
      gr.stroke({ color: ROAD_EDGE, width: w + 3, cap: "round", join: "round" });
      gr.stroke({ color: ROAD, width: w, cap: "round", join: "round" });
      g.addChild(gr);
    }
  }

  _buildings() {
    const g = this.L.bld; g.removeChildren();
    this._nodes.clear();
    const types = this.store.map?.buildings || {};
    const map = this.manifest?.buildingTypes || {};
    for (const [lid, loc] of Object.entries(this.store.locations)) {
      const x = loc.x * U, y = loc.y * U, w = loc.w * U, h = loc.h * U;
      if (loc.kind === "public") { this._tile(g, "ground/plaza.svg", x, y, w, h, 0xc9c2b1); this._sign(g, loc, x, y, h); continue; }
      const name = map[types[lid]?.type] || KIND_ART[loc.kind] || "home_a";
      const sh = this.tex(`bld/${name}_shadow.svg`);
      if (sh) { const s = new Sprite(sh); s.x = x - 3; s.y = y + 3; s.width = w + 6; s.height = h + 7; s.zIndex = 1; g.addChild(s); }
      const t = this.tex(`bld/${name}.svg`);
      if (t) {
        const s = new Sprite(t); s.x = x; s.y = y; s.width = w; s.height = h; s.zIndex = 2;
        g.addChild(s); this._nodes.set("loc:" + lid, s);
      } else {
        g.addChild(new Graphics().rect(x, y, w, h).fill(0x8c5b48).stroke({ color: 0x5a3a2e, width: 2 }));
      }
      this._sign(g, loc, x, y, h);
    }
  }

  /** 建筑名 —— 屏幕空间的纸片。 */
  _sign(_g, loc, x, y, h) {
    if (!loc.name) return;
    const el = document.createElement("div");
    el.className = "bubble"; el.textContent = loc.name;
    el.style.cssText = "background:transparent;border:0;color:#fff;text-shadow:0 1px 3px #000";
    el.dataset.world = `${x / U} ${(y + h) / U + 0.8}`;
    this.hud.appendChild(el);
    this._paper.set("loc:" + loc.name, el);
  }

  // ── 每帧 ────────────────────────────────────────────────────────────
  frame() {
    this.rebuildIfNeeded();
    const alive = new Set();
    for (const [id, npc] of this.store.npcs) {
      alive.add(id);
      const [wx, wy] = npc.position || [0, 0];
      const p = this._people.get(id) || this._spawn(id);
      p.spr.x = wx * U; p.spr.y = wy * U;
      p.spr.zIndex = 10 + Math.round(wy);            // y 大的压在上面
      p.spr.tint = this.store.focus === id ? 0xffd9a0 : 0xffffff;
      p.dir = this._dir(npc, p);
      const key = `people/${id}_${p.dir}_idle.svg`;
      const t = this.tex(key);
      if (t && p.spr.texture !== t) p.spr.texture = t;
      this._bubble(id, npc, wx, wy);
    }
    for (const [id, p] of [...this._people])
      if (!alive.has(id)) { p.spr.destroy(); this._people.delete(id); this._drop(id); }
    this._syncPaper();
  }

  _spawn(id) {
    const fallback = this.tex("people/me_down_idle.svg");
    const spr = new Sprite(fallback || undefined);
    spr.width = 18; spr.height = 24; spr.anchor.set(0.5, 1);
    this.L.npc.addChild(spr);
    const p = { spr, dir: "down", last: null };
    this._people.set(id, p);
    return p;
  }

  /** 朝向按位移判断；站着不动就沿用上次的（别每帧抖）。 */
  _dir(npc, p) {
    const cur = npc.position || [0, 0];
    if (p.last) {
      const dx = cur[0] - p.last[0], dy = cur[1] - p.last[1];
      if (Math.hypot(dx, dy) > 0.15) p.dir = Math.abs(dx) > Math.abs(dy) ? "side" : (dy < 0 ? "up" : "down");
    }
    p.last = cur;
    return p.dir;
  }

  _bubble(id, npc, wx, wy) {
    const txt = this.store.bubbleOf(npc);
    let el = this._paper.get("npc:" + id);
    if (!txt) { el?.remove(); this._paper.delete("npc:" + id); return; }
    if (!el) {
      el = document.createElement("div");
      el.className = "bubble"; this.hud.appendChild(el);
      this._paper.set("npc:" + id, el);
    }
    if (el.textContent !== txt) el.textContent = txt;
    el.dataset.world = `${wx} ${wy - 1.6}`;
  }

  _drop(id) { this._paper.get("npc:" + id)?.remove(); this._paper.delete("npc:" + id); }

  _syncPaper() {
    const s = this.root.scale.x, p = this.root.position;
    for (const el of this.hud.children) {
      if (!el.dataset?.world) continue;
      const [wx, wy] = el.dataset.world.split(" ").map(Number);
      el.style.left = (wx * U * s + p.x) + "px";
      el.style.top = (wy * U * s + p.y) + "px";
    }
  }
}

const KIND_ART = {
  home: "home_a", shop: "shop_a", market: "market", factory: "factory",
  clinic: "clinic", school: "school", work: "office", public: "plaza",
};
