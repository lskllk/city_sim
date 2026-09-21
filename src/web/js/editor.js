/** editor.js —— 地图编辑器。
 *
 * 渲染完全复用游戏的 View + MapLayer（同一份 maprender.js），
 * 这里只多做两件事：**编辑手柄** 和 **工具**。
 *
 * ══ 交互：按下的那一刻就决定谁来管 ══
 *   onDown(点) → true   这个点我接了（拖房子 / 拖节点 / 画路）
 *              → false  没接 → 相机平移（默认行为，永远不会"拖不动"）
 *
 * 之前把"拖"和"点"当成互斥的两种模式 —— 结果是相机一动就卡住、
 * 画路永远等不到 pointerdown。现在按下即分派。
 */
import { Container, Graphics } from '../vendor/pixi.min.mjs';
import { View, U } from './view.js';
import { MapLayer } from './maprender.js';
import { MapDoc } from './mapdoc.js';

const SNAP_COLOR = { node: 0x4a7358, door: 0xb4552d, road: 0x9b6f16, free: 0x7a7264 };
const SNAP_TEXT = { node: "吸到节点", door: "吸到门", road: "吸到路中线", free: "自由" };

export class Editor {
  constructor(canvasEl, hudEl, assets, ui) {
    this.assets = assets;
    this.ui = ui;
    this.view = new View(canvasEl, hudEl);
    this.doc = new MapDoc();
    this.map = new MapLayer(assets, (lid, loc, p) =>
      this.view.paper("sign:" + lid, loc.name, p.x / U, p.y / U + 0.8, "plate"));
    this.handles = new Container();
    this.tool = "select";
    this.buildType = "";
    this.selected = "";
    this.snapHint = null;
    this._drag = null;
    this._last = [0, 0];
    this.doc.on(() => { this._dirty = true; });
  }

  async init() {
    await this.view.init(0x6d8a52);
    this.map.root.zIndex = 0;
    this.handles.zIndex = 20;
    this.view.worldLayer.addChild(this.map.root);
    this.view.overlay.addChild(this.handles);
    this.view.onDown = (x, y) => this._down(x, y);
    this.view.onDrag = (x, y) => this._move(x, y);
    this.view.onUp = (x, y) => this._up(x, y);
    this.view.onPick = (x, y) => this._click(x, y);
    this.view.onHover = (x, y) => this._hover(x, y);
    this.view.onView = () => this.view.syncPaper();
    return this;
  }

  async openLatest() {
    const list = await (await fetch("/api/scenes")).json();
    const cat = await (await fetch("/api/catalog")).json();
    this.doc.setTypes(cat);
    // ★ 默认打开【最近编辑的那张】；没有记录就取 mtime 最新的一张
    const name = (list.last && list.scenes.some(s => s.name === list.last))
      ? list.last : (list.scenes[0]?.name || "scene.json");
    this.doc.load(await (await fetch("/api/scene?name=" + encodeURIComponent(name))).json());
    this.name = name;
    this.view.setWorld(this.doc.canvas);
    this.view.fill();
    this.redraw();
    this.ui.setScene(name, this.doc.stats());
    return name;
  }

  async save(name) {
    const target = name || this.name || "scene.json";
    const r = await fetch("/api/scene?name=" + encodeURIComponent(target), {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify(this.doc.toScene()),
    });
    if (!r.ok) return this.ui.toast("保存失败：" + r.status);
    this.name = target; this.doc.dirty = false;
    this.ui.setScene(target, this.doc.stats(), true);
    this.ui.toast("已保存 " + target + "（旧文件留了一份 .bak）");
  }

  setTool(t, buildType) {
    this.tool = t;
    if (buildType) this.buildType = buildType;
    this._drag = null;
    this.ui.setTool?.(this.tool, this.buildType);
    this.redraw();
  }

  // ── 命中 ────────────────────────────────────────────────────────────
  _tol() { return 14 / this.view.cam.k / U; }

  hitNode(p) {
    const t = this._tol(); let best = "", bd = t;
    for (const [id, n] of Object.entries(this.doc.nodes)) {
      const d = Math.hypot(n.xy[0] - p[0], n.xy[1] - p[1]);
      if (d < bd) { bd = d; best = id; }
    }
    return best;
  }
  hitEdge(p) {
    const t = this._tol(); let best = "", bd = t;
    for (const [id, e] of Object.entries(this.doc.edges)) {
      const pts = e.geom || [];
      for (let i = 1; i < pts.length; i++) {
        const q = this.doc._closest(p, pts[i - 1], pts[i]);
        const d = Math.hypot(q[0] - p[0], q[1] - p[1]);
        if (d < bd) { bd = d; best = id; }
      }
    }
    return best;
  }
  hitBuilding(p) {
    for (const [id, b] of Object.entries(this.doc.buildings)) {
      const [cx, cy] = b.center, [w, h] = b.size;
      const r = -(b.rot || 0) * Math.PI / 180;
      const dx = p[0] - cx, dy = p[1] - cy;
      const lx = dx * Math.cos(r) - dy * Math.sin(r);
      const ly = dx * Math.sin(r) + dy * Math.cos(r);
      if (Math.abs(lx) <= w / 2 && Math.abs(ly) <= h / 2) return id;
    }
    return "";
  }

  // ── 按下：决定这次手势归谁 ──────────────────────────────────────────
  _down(x, y) {
    const p = [x, y];
    this._last = p;
    if (this.tool === "road") {                       // 画路：按下起点，拖出来
      this._drag = { kind: "road", from: this.doc.snap(p, this.hitNode(p)) };
      return true;
    }
    if (this.tool !== "select") return false;         // 摆房/删除都靠单击
    const bid = this.hitBuilding(p);
    if (bid) {
      const b = this.doc.buildings[bid];
      this.selected = bid;
      this._drag = { kind: "bld", id: bid, off: [p[0] - b.center[0], p[1] - b.center[1]] };
      this._draw();
      return true;
    }
    const nid = this.hitNode(p);
    if (nid) {
      this.selected = nid;
      this._drag = { kind: "node", id: nid };
      this._draw();
      return true;
    }
    return false;                                     // 没点中东西 → 让相机平移
  }

  _move(x, y) {
    const p = [x, y];
    this._last = p;
    const d = this._drag;
    if (d?.kind === "bld") this.doc.moveBuilding(d.id, [p[0] - d.off[0], p[1] - d.off[1]]);
    else if (d?.kind === "node") this.doc.moveNode(d.id, p);
    else { this.snapHint = this.doc.snap(p, this.hitNode(p)); }
    this.redraw();
  }

  _up(x, y) {
    const d = this._drag;
    this._drag = null;
    this._last = [x, y];
    if (!d) return;
    if (d.kind === "bld") this.doc.alignBuilding(d.id);        // ★ 松手贴边
    else if (d.kind === "road") {
      const from = this._nodeFor(d.from);
      const to = this._nodeFor(this.doc.snap([x, y], this.hitNode([x, y])));
      if (from && to && from !== to) this.doc.addEdge(from, to);
      else this.ui.toast("路要有两个不同的端点");
    }
    this.redraw();
  }

  /** 纯点击（没被 _down 接走、也没平移）。 */
  _click(x, y) {
    const p = [x, y];
    if (this.tool === "build") return this._place(p);
    if (this.tool === "erase") return this._erase(p);
    if (this.tool === "select") {                     // 点空白 = 取消选中
      this.selected = ""; this.redraw();
    }
  }

  _hover(x, y) {
    this.snapHint = this.doc.snap([x, y], this.hitNode([x, y]));
    this._last = [x, y];
    this.ui.setCursor?.(this.view.toWorld(x, y), this.snapHint);
    this._draw();
  }

  _place(p) {
    if (!this.buildType) return this.ui.toast("左边先挑一个建筑类型");
    if (!Object.keys(this.doc.edges).length)
      return this.ui.toast("先画一条路 —— 房子必须挨着路（规则强制）");
    const id = this.doc.addBuilding(this.buildType, p);
    if (!id) return this.ui.toast("摆不下");
    this.selected = id;
    this.redraw();
  }

  _erase(p) {
    const bid = this.hitBuilding(p);
    if (bid) { this.doc.removeBuilding(bid); this.selected = ""; }
    else {
      const nid = this.hitNode(p);
      if (nid) this.doc.removeNode(nid);
      else { const eid = this.hitEdge(p); if (eid) this.doc.removeEdge(eid); }
    }
    this.redraw();
  }

  /** 吸附结果 → 节点 id。落到门上就复用那颗门节点（房子和路从此绑一起）。 */
  _nodeFor(s) {
    if (!s) return "";
    if (s.kind === "node") return s.id;
    const id = this.doc.addNode(s.point);
    if (s.kind === "door" && s.building && this.doc.nodes[id]) {
      this.doc.nodes[id].door_of = s.building;
      this.doc.nodes[id].door_index = s.doorIndex;
      this.doc._changed();
    }
    return id;
  }

  // ── 重画 ────────────────────────────────────────────────────────────
  redraw() {
    this.map.draw(this.doc.toScene());
    this._draw();
  }

  _draw() {
    const g = this.handles;
    g.removeChildren();
    // 节点
    for (const [id, n] of Object.entries(this.doc.nodes)) {
      const x = n.xy[0] * U, y = n.xy[1] * U;
      const c = new Graphics().circle(x, y, n.door_of ? 5 : 4.5)
        .fill(n.door_of ? 0xb4552d : 0xf7f4ee)
        .stroke({ color: id === this.selected ? 0xb4552d : 0x26221c, width: id === this.selected ? 3 : 1.5 });
      g.addChild(c);
    }
    // 选中的建筑：外框
    const b = this.doc.buildings[this.selected];
    if (b) {
      const [cx, cy] = b.center, [w, h] = b.size;
      const o = new Graphics()
        .poly([-w / 2 * U, -h / 2 * U, w / 2 * U, -h / 2 * U, w / 2 * U, h / 2 * U, -w / 2 * U, h / 2 * U])
        .fill({ color: 0xb4552d, alpha: 0.12 }).stroke({ color: 0xb4552d, width: 2 });
      o.position.set(cx * U, cy * U);
      o.rotation = (b.rot || 0) * Math.PI / 180;
      g.addChild(o);
    }
    // 吸附预览 + 画路橡皮筋
    const s = this.snapHint;
    if (s && (this.tool === "road" || this._drag?.kind === "road")) {
      const col = SNAP_COLOR[s.kind] ?? 0xffffff;
      g.addChild(new Graphics().circle(s.point[0] * U, s.point[1] * U, 7)
        .stroke({ color: col, width: 2.5 }));
      if (this._drag?.kind === "road") {
        const f = this._drag.from.point;
        g.addChild(new Graphics().moveTo(f[0] * U, f[1] * U)
          .lineTo(s.point[0] * U, s.point[1] * U)
          .stroke({ color: col, width: 3, alpha: 0.8, cap: "round" }));
      }
    }
    // 摆房预览
    if (this.tool === "build" && this.buildType && this._last) {
      const [w, h] = this.doc.sizeFor(this.buildType);
      const gh = new Graphics()
        .poly([-w / 2 * U, -h / 2 * U, w / 2 * U, -h / 2 * U, w / 2 * U, h / 2 * U, -w / 2 * U, h / 2 * U])
        .fill({ color: 0xf7f4ee, alpha: 0.25 }).stroke({ color: 0xf7f4ee, width: 1.5 });
      gh.position.set(this._last[0] * U, this._last[1] * U);
      g.addChild(gh);
    }
    this.view.syncPaper();
    this.ui.setStats?.(this.doc.stats());
    this.ui.setDirty?.(this.doc.dirty);
  }

  snapText() { return this.snapHint ? SNAP_TEXT[this.snapHint.kind] : ""; }
}

export { U };
