/** editor.js —— 地图编辑器。
 *
 * 渲染完全复用游戏的 View + MapLayer（同一份 maprender.js），
 * 这里只多做两件事：**编辑手柄** 和 **工具**。
 *
 * ══ 道路：两点法，提交才动数据 ══
 *   按下（起点） → 拖 → 松开（终点）。**整个过程一个节点都不建** ——
 *   预览是画出来的，数据等松手才提交。所以"没画成"就真的什么都没留下。
 *   （旧做法是按下就建节点，取消后满地孤儿节点。用户规则 1。）
 *
 *   起点/终点落点分三种，松手时由 MapDoc.resolve() 处理：
 *     落在【既有节点】→ 复用
 *     落在【既有路的中段】→ 把那一条拆成两条（于是变成三条路 + 四个节点）★ 规则 3
 *     落在【门】→ 复用/生成门节点，房子和路从此绑一起
 *
 * ══ 交互：按下的那一刻决定谁管 ══
 *   onDown → true   工具接了（画路 / 拖房子 / 拖节点）
 *          → false  没接 → 相机平移（默认行为，永远不会"拖不动"）
 */
import { Container, Graphics } from '../vendor/pixi.min.mjs';
import { View, U } from './view.js';
import { MapLayer } from './maprender.js';
import { MapDoc } from './mapdoc.js';

const SNAP_COLOR = { node: 0x4a7358, door: 0xb4552d, road: 0x9b6f16, free: 0x7a7264 };
const SNAP_TEXT = { node: "节点", door: "门", road: "路中线（会拆成两条）", free: "自由" };

export class Editor {
  constructor(canvasEl, hudEl, assets, ui) {
    this.assets = assets;
    this.ui = ui;
    this.view = new View(canvasEl, hudEl);
    this.doc = new MapDoc();
    this.map = new MapLayer(assets, (lid, loc, p) =>
      loc ? this.view.paper("sign:" + lid, loc.name, p.x / U, p.y / U, "plate", 5)
          : this.view.paper("sign:" + lid, null));      // 房子没了 → 名牌也撤
    this.handles = new Container();     // 手柄（节点 / 选中框 / 幽灵）
    this.overlay2 = new Container();    // 高亮（在更上面）
    this.tool = "select";
    this.buildType = "";               // 摆放：建筑类型
    this.propName = "";                // 摆放：环境物件名
    this.roadWidth = 4;                // 画路：宽度（米）
    this.selected = "";
    this.snapHint = null;
    this._pending = null;               // 画路中的起点（未提交）
    this._drag = null;
    this._last = null;
    this.doc.on(() => this.map.draw(this.doc.toScene()));
  }

  async init() {
    await this.view.init(0x6d8a52);
    this.map.root.zIndex = 0;
    this.handles.zIndex = 20;
    this.overlay2.zIndex = 21;
    this.view.worldLayer.addChild(this.map.root);
    this.view.overlay.addChild(this.handles, this.overlay2);
    this.view.onDown = (x, y) => this._down(x, y);
    this.view.onDrag = (x, y) => this._move(x, y);
    this.view.onUp = (x, y) => this._up(x, y);
    this.view.onPick = (x, y) => this._click(x, y);
    this.view.onHover = (x, y) => this._hover(x, y);
    this.view.onView = () => this.view.syncPaper();
    // 编辑器没有帧循环（只在输入时重画），但平滑缩放需要每帧推进一下。
    // 只 step 相机的缩放，别整帧重画 —— 那才是卡的原因。
    const loop = () => {
      if (this.view.step() && !document.getElementById("editor")?.classList.contains("hide"))
        this._paint();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
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
    if (buildType) { this.buildType = buildType; this.propName = ""; }
    this._drag = null; this._pending = null;
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

  _snapAt(p) { return this.doc.snap(p, this.hitNode(p)); }

  // ── 按下 ────────────────────────────────────────────────────────────
  _down(x, y) {
    const p = [x, y];
    this._last = p;
    if (this.tool === "road") {                  // ★ 两点法：只记起点，不建任何东西
      this._pending = this._snapAt(p);
      return true;
    }
    if (this.tool !== "select") return false;
    const bid = this.hitBuilding(p);
    if (bid) {
      const b = this.doc.buildings[bid];
      this.selected = bid;
      this._drag = { kind: "bld", id: bid, off: [p[0] - b.center[0], p[1] - b.center[1]] };
      return true;
    }
    const nid = this.hitNode(p);
    if (nid) {
      this.selected = nid;
      this._drag = { kind: "node", id: nid };
      return true;
    }
    const pi = this.doc.propNear(p);
    if (pi >= 0) {                               // 拖环境物件
      this.selected = "prop:" + pi;
      this._drag = { kind: "prop", idx: pi };
      return true;
    }
    return false;                                // 没点中东西 → 让相机平移
  }

  _move(x, y) {
    const p = [x, y];
    this._last = p;
    const d = this._drag;
    if (d?.kind === "bld") {
      this.doc.moveBuilding(d.id, [p[0] - d.off[0], p[1] - d.off[1]]);
    } else if (d?.kind === "node") {
      // ★ 拖节点也走栅格捕获（和画路同一套 grid()，关掉栅格时它就原样返回）
      this.doc.moveNode(d.id, this.doc.grid(p));
    } else if (d?.kind === "prop") {
      const g = this.doc.grid(p);
      this.doc.props[d.idx].xy = [g[0], g[1]];
      this.doc._changed();
    } else {
      this.snapHint = this._snapAt(p);
    }
    this.redraw();
  }

  _up(x, y) {
    const d = this._drag, pend = this._pending;
    this._drag = null; this._pending = null;
    if (d?.kind === "bld") {
      this.doc.alignBuilding(d.id);              // ★ 松手贴边
    } else if (pend) {
      // ★ 提交：两端各自 resolve（复用节点 / 拆边 / 建门节点），再连边。
      //   任何一端不合法 → connect 什么都不做 → 一个节点都不会留下。
      const to = this._snapAt([x, y]);
      const id = this.doc.connect(pend, to, { width: this.roadWidth });
      if (!id) this.ui.toast("没连成 —— 两端要么重合，要么落点无效");
      this.doc.pruneOrphans();
    }
    this.redraw();
  }

  /** 纯点击（没被 _down 接走、也没平移）。 */
  _click(x, y) {
    const p = [x, y];
    if (this.tool === "place") return this._place(p);
    if (this.tool === "erase") return this._erase(p);
    if (this.tool === "select") { this.selected = ""; this.redraw(); }
  }

  _hover(x, y) {
    this._last = [x, y];
    this.snapHint = this._snapAt([x, y]);
    this.ui.setCursor?.(this.snapHint);
    this._paint();
  }

  _place(p) {
    if (this.propName) {                         // 环境：随便摆，不用挨着路
      this.doc.addProp(this.propName,
        this.doc.gridSnap === false ? p : this.doc.grid(p));
      return this.redraw();
    }
    if (!this.buildType) return this.ui.toast("左边先挑一个");
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
    else if (this.doc.removePropNear(p)) { this.selected = ""; }
    else {
      const nid = this.hitNode(p);
      if (nid) this.doc.removeNode(nid);
      else { const eid = this.hitEdge(p); if (eid) this.doc.removeEdge(eid); }
    }
    this.doc.pruneOrphans();
    this.redraw();
  }

  // ── 重画 ────────────────────────────────────────────────────────────
  redraw() {
    this.map.draw(this.doc.toScene());
    this._paint();
  }

  _paint() {
    this.handles.removeChildren();
    this.overlay2.removeChildren();

    // ① 栅格：只在【看得清】的时候画。
    //    4 米栅格在整图视角下只有 7 屏幕像素 —— 画出来是一片噪声，
    //    用户看到的就是"一堆不知道干嘛的虚线"。
    const gm = Math.max(1, Math.round(this.doc.gridM || 4));
    if (this.doc.gridSnap !== false && gm * U * this.view.cam.k >= 14) this._paintGrid(gm);

    // ② 节点
    for (const [id, n] of Object.entries(this.doc.nodes)) {
      const x = n.xy[0] * U, y = n.xy[1] * U;
      const sel = id === this.selected;
      this.handles.addChild(new Graphics().circle(x, y, n.door_of ? 5 : 4.5)
        .fill(n.door_of ? 0xb4552d : 0xf7f4ee)
        .stroke({ color: sel ? 0xb4552d : 0x26221c, width: sel ? 3 : 1.5 }));
    }

    // ③ 选中的建筑外框
    const b = this.doc.buildings[this.selected];
    if (b) {
      const [cx, cy] = b.center, [w, h] = b.size;
      const o = new Graphics()
        .poly([-w / 2 * U, -h / 2 * U, w / 2 * U, -h / 2 * U, w / 2 * U, h / 2 * U, -w / 2 * U, h / 2 * U])
        .fill({ color: 0xb4552d, alpha: 0.12 }).stroke({ color: 0xb4552d, width: 2 });
      o.position.set(cx * U, cy * U);
      o.rotation = (b.rot || 0) * Math.PI / 180;
      this.handles.addChild(o);
    }

    // ④ 画路：高亮"这次会拆哪条路" + 起点 → 落点的橡皮筋 ★ 规则 6
    const road = this.tool === "road" || this._pending;
    const s = road ? (this._pending || this.snapHint) : null;
    if (s) {
      if (s.edge) this._highlightEdge(s.edge);          // 拆哪条
      if (this.snapHint) this._paintSnap(this.snapHint);
      if (this._pending && this.snapHint
          && this._pending.point !== this.snapHint.point) {
        const f = this._pending.point, t2 = this.snapHint.point;
        this.overlay2.addChild(new Graphics()
          .moveTo(f[0] * U, f[1] * U).lineTo(t2[0] * U, t2[1] * U)
          .stroke({ color: SNAP_COLOR[this.snapHint.kind] ?? 0xffffff,
                    width: Math.max(4, 4 * U), alpha: 0.35, cap: "round" }));
        this.overlay2.addChild(new Graphics().circle(f[0] * U, f[1] * U, 7)
          .stroke({ color: 0x26221c, width: 2 }));
      }
    }

    // ⑤ 摆房：幽灵框画在【贴边之后】的位置 —— 否则看着落这儿、放下落那儿 ★ 规则 6
    if (this.tool === "place" && this.propName && this._last) {
      const g = this.doc.gridSnap === false ? this._last : this.doc.grid(this._last);
      this.overlay2.addChild(new Graphics().circle(g[0] * U, g[1] * U, 9)
        .fill({ color: 0xf7f4ee, alpha: 0.25 }).stroke({ color: 0xf7f4ee, width: 2 }));
      this.overlay2.addChild(new Graphics().circle(this._last[0] * U, this._last[1] * U, 3)
        .fill({ color: 0xf7f4ee }));
    }
    if (this.tool === "place" && this.buildType && !this.propName && this._last) {
      const [px, py] = this._last;
      const tmp = { type: this.buildType, center: [px, py],
                    size: this.doc.sizeFor(this.buildType), rot: 0, doors: [], floors: 1 };
      const a = this.doc.computeAlign(tmp);
      const c = a ? a.center : tmp.center, rot = a ? a.rot : 0;
      const hasRoad = Object.keys(this.doc.edges).length > 0;
      const [w, h] = tmp.size;
      const gh = new Graphics()
        .poly([-w / 2 * U, -h / 2 * U, w / 2 * U, -h / 2 * U, w / 2 * U, h / 2 * U, -w / 2 * U, h / 2 * U])
        .fill({ color: hasRoad ? 0xf7f4ee : 0xb4552d, alpha: hasRoad ? 0.3 : 0.18 })
        .stroke({ color: hasRoad ? 0xf7f4ee : 0xb4552d, width: 2, alpha: 0.9 });
      gh.position.set(c[0] * U, c[1] * U);
      gh.rotation = rot * Math.PI / 180;
      this.overlay2.addChild(gh);
      this.overlay2.addChild(new Graphics().circle(px * U, py * U, 3)
        .fill({ color: 0xf7f4ee }));                     // 鼠标落点
    }
    this.view.syncPaper();
    this.ui.setStats?.(this.doc.stats());
    this.ui.setDirty?.(this.doc.dirty);
  }

  _paintGrid(gm) {
    const c = this.doc.canvas, step = gm * U;
    const g = new Graphics();
    for (let x = 0; x <= c.w * U; x += step) g.moveTo(x, 0).lineTo(x, c.h * U);
    for (let y = 0; y <= c.h * U; y += step) g.moveTo(0, y).lineTo(c.w * U, y);
    g.stroke({ color: 0x000000, width: 0.6, alpha: 0.13 });
    this.handles.addChild(g);
  }

  _highlightEdge(eid) {
    const e = this.doc.edges[eid];
    if (!e) return;
    const pts = e.geom || [];
    const g = new Graphics();
    for (let i = 1; i < pts.length; i++)
      g.moveTo(pts[i - 1][0] * U, pts[i - 1][1] * U).lineTo(pts[i][0] * U, pts[i][1] * U);
    g.stroke({ color: 0x9b6f16, width: (e.width || 4) * U + 8, cap: "round", alpha: 0.3 });
    this.overlay2.addChild(g);
  }

  /** 吸附点的环 —— 颜色说明吸到了什么。 */
  _paintSnap(s) {
    const c = SNAP_COLOR[s.kind] ?? 0xffffff;
    const r = (s.kind === "free" ? 5 : 9);
    this.overlay2.addChild(new Graphics()
      .circle(s.point[0] * U, s.point[1] * U, r)
      .fill({ color: c, alpha: 0.18 })
      .stroke({ color: c, width: 2.5 }));
  }

  snapText() { return this.snapHint ? SNAP_TEXT[this.snapHint.kind] : ""; }
}

export { U };
