/** editor.js —— 地图编辑器。
 *
 * 渲染完全复用游戏的 View + MapLayer（同一份 maprender.js），
 * 这里只多做两件事：**编辑手柄**（节点/门/吸附预览）和**工具**。
 *
 * 数据模型见 mapdoc.js —— 路是【图】不是线，那五条规则都在那里。
 */
import { Container, Graphics, Sprite } from '../vendor/pixi.min.mjs';
import { View, U } from './view.js';
import { MapLayer } from './maprender.js';
import { MapDoc } from './mapdoc.js';

const SNAP_COLOR = { node: 0x4a7358, door: 0xb4552d, road: 0xc9a24a, free: 0x8a8779 };

export class Editor {
  constructor(canvasEl, hudEl, assets, ui) {
    this.assets = assets;
    this.ui = ui;                     // {toast, setScene, setStats, setSnap, setInfo}
    this.view = new View(canvasEl, hudEl);
    this.doc = new MapDoc();
    this.map = new MapLayer(assets, (loc, p) =>
      this.view.paper("sign:" + loc.name, loc.name, p.x, p.y, "bubble sign"));
    this.handles = new Container();
    this.tool = "select";             // select | road | build | erase
    this.buildType = "";
    this.selected = "";               // "bld_xxx" | "n_xxx" | ""
    this.snapHint = null;
    this._drag = null;
    this._ghost = null;
    this.doc.on(() => this.redraw());
  }

  async init() {
    await this.view.init(0x2b3a2b);
    this.map.root.zIndex = 0; this.handles.zIndex = 10;
    this.view.world.addChild(this.map.root);
    this.view.overlay.addChild(this.handles);
    this.view.onPick = (x, y) => this._click(x, y);
    this.view.onHover = (w) => this.hover(w);
    this.view.onDrag = (w) => this.hover(w);
    this.view.onDrop = () => this.release();
    return this;
  }

  async openLatest() {
    const list = await (await fetch("/api/scenes")).json();
    const cat = await (await fetch("/api/catalog")).json();
    this.doc.setTypes(cat);
    const name = list.last && list.scenes.some(s => s.name === list.last)
      ? list.last
      : (list.scenes[0]?.name || "scene.json");
    const scene = await (await fetch("/api/scene?name=" + encodeURIComponent(name))).json();
    this.doc.load(scene);
    this.name = name;
    this.ui.setScene(name, this.doc.stats());
    this.view.fit(this.doc.canvas);
    this.redraw();
    return name;
  }

  async save(asName) {
    const name = asName || this.name || "scene.json";
    const r = await fetch("/api/scene?name=" + encodeURIComponent(name), {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify(this.doc.toScene()),
    });
    if (!r.ok) { this.ui.toast("保存失败：" + r.status); return; }
    this.name = name; this.doc.dirty = false;
    this.ui.setScene(name, this.doc.stats(), true);
    this.ui.toast("已保存 " + name + "（旧文件留了一份 .bak）");
  }

  // ── 工具切换 ────────────────────────────────────────────────────────
  setTool(t, buildType = "") {
    this.tool = t;
    if (t === "build" && buildType) this.buildType = buildType;
    this._ghost = null;
    this.ui.setTool?.(this.tool, this.buildType);
    this.redraw();
  }

  // ── 命中 ────────────────────────────────────────────────────────────
  /** 屏幕上 14 像素的宽容 → 世界距离。 */
  _tol() { return 14 / this.view.cam.zoom / U; }

  hitNode(p) {
    const t = this._tol();
    let best = "", bestD = t;
    for (const [nid, n] of Object.entries(this.doc.nodes)) {
      const d = Math.hypot(n.xy[0] - p[0], n.xy[1] - p[1]);
      if (d < bestD) { bestD = d; best = nid; }
    }
    return best;
  }
  hitEdge(p) {
    const t = this._tol();
    let best = "", bestD = t;
    for (const [eid, e] of Object.entries(this.doc.edges)) {
      const pts = e.geom || [];
      for (let i = 1; i < pts.length; i++) {
        const q = this.doc._closest(p, pts[i - 1], pts[i]);
        const d = Math.hypot(q[0] - p[0], q[1] - p[1]);
        if (d < bestD) { bestD = d; best = eid; }
      }
    }
    return best;
  }
  hitBuilding(p) {
    for (const [bid, b] of Object.entries(this.doc.buildings)) {
      const [cx, cy] = b.center, [w, h] = b.size;
      const rot = -(b.rot || 0) * Math.PI / 180;
      const dx = p[0] - cx, dy = p[1] - cy;
      const lx = dx * Math.cos(rot) - dy * Math.sin(rot);
      const ly = dx * Math.sin(rot) + dy * Math.cos(rot);
      if (Math.abs(lx) <= w / 2 && Math.abs(ly) <= h / 2) return bid;
    }
    return "";
  }

  // ── 交互 ────────────────────────────────────────────────────────────
  _click(wx, wy) {
    const p = [wx, wy];
    if (this.tool === "erase") return this._erase(p);
    if (this.tool === "build") return this._place(p);
    if (this.tool === "road") return this._road(p);
    return this._select(p);
  }

  _place(p) {
    if (!this.buildType) return this.ui.toast("左边先挑一个建筑类型");
    if (!Object.keys(this.doc.edges).length)
      return this.ui.toast("先画一条路 —— 房子必须挨着路（规则强制）");
    const id = this.doc.addBuilding(this.buildType, p);
    if (!id) return this.ui.toast("摆不下");
    this.selected = id;
    this.ui.setStats(this.doc.stats());
  }

  _erase(p) {
    const bid = this.hitBuilding(p);
    if (bid) { this.doc.removeBuilding(bid); this.selected = ""; }
    else {
      const nid = this.hitNode(p);
      if (nid) this.doc.removeNode(nid);
      else { const eid = this.hitEdge(p); if (eid) this.doc.removeEdge(eid); }
    }
    this.ui.setStats(this.doc.stats());
  }

  _select(p) {
    const bid = this.hitBuilding(p);
    if (bid) {
      this.selected = bid;
      this._drag = { kind: "bld", id: bid, off: this._offset(p, this.doc.buildings[bid].center) };
      return this.redraw();
    }
    const nid = this.hitNode(p);
    if (nid) {
      this.selected = nid;
      this._drag = { kind: "node", id: nid };
      return this.redraw();
    }
    const eid = this.hitEdge(p);
    this.selected = eid ? "edge:" + eid : "";
    this.redraw();
  }

  _offset(p, c) { return [p[0] - c[0], p[1] - c[1]]; }

  /** 画路：按下起点 → 拖 → 松开落点。两个落点都走统一吸附。 */
  _road(p) {
    const s = this.doc.snap(p, this.hitNode(p));
    this._drag = { kind: "road", from: s };
  }

  /** 鼠标移动：拖动中 / 预览。 */
  hover(w) {
    if (this._drag?.kind === "bld") {
      this.doc.moveBuilding(this._drag.id, [w[0] - this._drag.off[0], w[1] - this._drag.off[1]]);
      return;
    }
    if (this._drag?.kind === "node") {
      this.doc.moveNode(this._drag.id, w);
      return;
    }
    this._lastHover = w;
    this.snapHint = this.doc.snap(w, this.hitNode(w));
    this._drawHandles();
  }

  release() {
    const d = this._drag;
    this._drag = null;
    if (!d) return;
    if (d.kind === "bld") {
      this.doc.alignBuilding(d.id);        // ★ 松手就贴边：门朝路 + 墙贴路沿
    } else if (d.kind === "road") {
      const to = this.doc.snap(this._lastHover || [0, 0], this.hitNode(this._lastHover || [0, 0]));
      const a = this._nodeFor(d.from), b = this._nodeFor(to);
      if (a && b && a !== b) this.doc.addEdge(a, b);
      this.ui.setStats(this.doc.stats());
    }
    this.redraw();
  }

  /** 吸附结果 → 节点 id（没有就新建；落到门上就复用门节点）。 */
  _nodeFor(s) {
    if (!s) return "";
    if (s.kind === "node") return s.id;
    const id = this.doc.addNode(s.point);
    // 落在建筑门上 → 那个节点就是门节点，房子和路从此绑在一起
    if (s.kind === "door" && s.building) {
      const n = this.doc.nodes[id];
      n.door_of = s.building; n.door_index = s.doorIndex;
      this.doc._changed();
    }
    return id;
  }

  // ── 重绘 ────────────────────────────────────────────────────────────
  redraw() {
    this.map.draw(this.doc.toScene());
    this._drawHandles();
    this.ui.setStats?.(this.doc.stats());
    this.ui.setDirty?.(this.doc.dirty);
  }

  _drawHandles() {
    const g = this.handles;
    g.removeChildren();
    const doc = this.doc;
    // 节点
    for (const [nid, n] of Object.entries(doc.nodes)) {
      const x = n.xy[0] * U, y = n.xy[1] * U;
      const h = new Graphics().circle(x, y, n.door_of ? 5 : 4.5)
        .fill(n.door_of ? 0xb4552d : 0xf7f4ee)
        .stroke({ color: 0x26221c, width: 1.5 });
      if (nid === this.selected) h.stroke({ color: 0xb4552d, width: 3 });
      g.addChild(h);
    }
    // 被选中的建筑：外框
    const b = doc.buildings[this.selected];
    if (b) {
      const [cx, cy] = b.center, [w, h] = b.size;
      const o = new Graphics();
      o.poly([-w / 2 * U, -h / 2 * U, w / 2 * U, -h / 2 * U, w / 2 * U, h / 2 * U, -w / 2 * U, h / 2 * U]);
      o.fill({ color: 0xb4552d, alpha: 0.12 }).stroke({ color: 0xb4552d, width: 2 });
      o.position.set(cx * U, cy * U);
      o.rotation = (b.rot || 0) * Math.PI / 180;
      g.addChild(o);
    }
    // 吸附预览（画路时）
    if (this.tool === "road" && this.snapHint) {
      const [x, y] = this.snapHint.point;
      const c = SNAP_COLOR[this.snapHint.kind] ?? 0xffffff;
      g.addChild(new Graphics().circle(x * U, y * U, 7)
        .stroke({ color: c, width: 2.5 }));
      if (this._drag?.kind === "road" && this._lastHover) {
        const f = this._drag.from.point;
        g.addChild(new Graphics()
          .moveTo(f[0] * U, f[1] * U).lineTo(x * U, y * U)
          .stroke({ color: c, width: 4, alpha: 0.7, cap: "round" }));
      }
    }
    // 摆房预览
    if (this.tool === "build" && this.buildType && this._lastHover) {
      const [w, h] = doc.sizeFor(this.buildType);
      const gh = new Graphics();
      gh.poly([-w / 2 * U, -h / 2 * U, w / 2 * U, -h / 2 * U, w / 2 * U, h / 2 * U, -w / 2 * U, h / 2 * U]);
      gh.fill({ color: 0xf7f4ee, alpha: 0.2 }).stroke({ color: 0xf7f4ee, width: 1.5 });
      gh.position.set(this._lastHover[0] * U, this._lastHover[1] * U);
      g.addChild(gh);
    }
    this.view.syncPaper();
  }
}

export { U };
