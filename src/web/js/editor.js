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
import { Container, Graphics, Sprite } from '../vendor/pixi.min.mjs';
import { View, U } from './view.js';
import { MapLayer } from './maprender.js';
import { MapDoc } from './mapdoc.js';

// 亮一档的强调色 —— 细圈在草地和沥青上都看不清，换成高亮
const SNAP_COLOR = { node: 0x2fbf6f, door: 0xff6b3d, road: 0xffc53d, free: 0xffffff };
const SNAP_TEXT = { node: "节点", door: "门", road: "路中线（会拆成两条）", free: "自由" };
// 环境资产的逻辑尺寸（和 maprender.js 的 SIZE 一致）
const AREA_LABEL = { farm: "农田", concrete: "水泥地", tile: "地砖" };
// 第一个顶点允许落在哪：路 / 节点 / 建筑的门。空地不行。
const AREA_ANCHOR = new Set(["node", "door", "road"]);
// ★ 区域离【路边缘】至少让开这么多米 —— 不能让区域压在路里。
const AREA_CLEAR = 0.5;
const PROP_SIZE = { tree_s: [20, 24], tree_m: [27, 31], tree_l: [34, 38],
                    bush_1: [15, 16], bush_2: [18, 19], bench: [26, 12],
                    lamp: [10, 30], bin: [11, 13], flowerbed: [24, 14] };

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
    this.areaKind = "farm";            // 地面区域：用途
    this.selectedArea = "";            // 选中的地面区域
    this._areaPath = [];               // 地面区域：正在围的节点 id 序列
    this._areaStack = [];              // 每加一个顶点存一张快照 → 右键退一张
    this.selected = "";
    this.snapHint = null;
    this._pending = null;               // 画路中的起点（未提交）
    this._undo = [];                    // 撤销栈（整份地图快照）
    this._MAX_UNDO = 60;
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
    // 右键 = 【放下手上的东西 / 取消选中】。撤销归 Ctrl+Z。
    // ★ 右键分场景（撤销归 Ctrl+Z）：
    //     不在手势里 → 取消选中（放下手上的东西）
    //     画路中     → 回到初始（起点也放掉）
    //     围区域中   → 回到上一个点（退掉最后那个顶点）
    this.view.onContext = () => this._context();
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
    const list = await (await fetch("/api/scenes", { cache: "no-store" })).json();
    const cat = await (await fetch("/api/catalog", { cache: "no-store" })).json();
    this.doc.setTypes(cat);
    // ★ 默认打开【最近编辑的那张】；没有记录就取 mtime 最新的一张。
    //   fetch 一律带 no-store —— 不然浏览器缓存住 /api/scene，
    //   你刚保存、再进编辑器看到的还是改之前那张（踩过）。
    const name = (list.last && list.scenes.some(s => s.name === list.last))
      ? list.last : (list.scenes[0]?.name || "scene.json");
    this.doc.load(await (await fetch("/api/scene?name=" + encodeURIComponent(name), { cache: "no-store" })).json());
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

  /** 右键：放下手上拿的、取消选中。回到「选择」，什么都不拿。 */
  deselect() {
    this.cancelGesture();              // 半截手势（画路 / 围区域 / 拖动）一起放掉
    this.buildType = ""; this.propName = ""; this.selected = "";
    this.selectedArea = "";
    this.setTool("select");
    this.redraw();
  }

  /** 动数据之前先拍一张。栈满丢最老的。 */
  pushUndo() {
    this._undo.push(this.doc.snapshot());
    if (this._undo.length > this._MAX_UNDO) this._undo.shift();
    this.ui.setUndo?.(this._undo.length);
  }
  /** 撤销一步。空栈提示一下，别让人以为坏了。 */
  /** 删掉当前选中的东西（Delete / Backspace）。 */
  deleteSelected() {
    if (!this.selectedArea) return false;
    this.pushUndo();
    this.doc.areas = this.doc.areas.filter(a => a.id !== this.selectedArea);
    this.selectedArea = ""; this.selected = "";
    this.doc._changed(); this.redraw();
    return true;
  }

  undo() {
    const snap = this._undo.pop();
    this.ui.setUndo?.(this._undo.length);
    if (!snap) return this.ui.toast("没有可撤销的了");
    this.selected = ""; this._pending = null; this._drag = null;
    this.doc.restore(snap);
    this.redraw();
  }

  setTool(t, buildType) {
    this.cancelGesture();                    // 换工具别把半截手势留在画面上
    this.tool = t;
    // 选择 / 删除 不带"手上拿着的东西" —— 切过去就把调色盘的选择清掉，
    // 否则调色盘还亮着，人会以为点一下还能接着摆。
    if (t === "select" || t === "erase") { this.buildType = ""; this.propName = ""; }
    if (buildType) { this.buildType = buildType; this.propName = ""; }
    this._drag = null; this._pending = null;
    this.ui.setTool?.(this.tool, this.buildType);
    this.redraw();
  }

  // ── 命中 ────────────────────────────────────────────────────────────
  _tol() { return 14 / this.view.cam.k / U; }

  hitNode(p, exclude = "") {
    const t = this._tol(); let best = "", bd = t;
    for (const [id, n] of Object.entries(this.doc.nodes)) {
      if (id === exclude) continue;             // 别吸到自己身上（正在拖的那个）
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
    // ★ 有人在等一个建筑（人物设计器"在地图上选住所"）→ 这次点击【别被拖动接走】。
    //   不拦的话：点建筑 = 开始拖房子，onDown 返回 true，_click 根本不会触发，
    //   回调永远收不到（踩过：pickBuilding 看着装了却没反应）。
    if (this._pick) return false;
    // ★ 只有"拖"在这里接：房子 / 节点 / 环境物件。
    //   画路和围区域都是【点一下再点一下】，走 _click ——
    //   这样拖 = 平移、点 = 操作，两个工具同一套手感。
    if (this.tool !== "select") return false;
    const before = this.doc.snapshot();
    const bid = this.hitBuilding(p);
    if (bid) {
      const b = this.doc.buildings[bid];
      this.selected = bid;
      this._drag = { kind: "bld", id: bid, snap: before,
                     off: [p[0] - b.center[0], p[1] - b.center[1]] };
      return true;
    }
    const nid = this.hitNode(p);
    if (nid) {
      this.selected = nid;
      this._drag = { kind: "node", id: nid, snap: before };
      return true;
    }
    const pi = this.doc.propNear(p);
    if (pi >= 0) {                               // 拖环境物件
      this.selected = "prop:" + pi;
      this._drag = { kind: "prop", idx: pi, snap: before };
      return true;
    }
    // ★ 区域是"底"，所以【最后】判 —— 别把点房子 / 点物件挡住
    const ar = this.doc.areaAt(p);
    this.selectedArea = ar ? ar.id : "";
    if (ar) { this.selected = "area:" + ar.id; this.redraw(); return true; }
    return false;                                // 没点中东西 → 让相机平移
  }

  _move(x, y) {
    const p = [x, y];
    this._last = p;
    const d = this._drag;
    if (this._pending) this.snapHint = this._snapAt(p);   // 画路：橡皮筋跟着鼠标
    if (d?.kind === "bld") {
      this.doc.moveBuilding(d.id, [p[0] - d.off[0], p[1] - d.off[1]]);
    } else if (d?.kind === "node") {
      // ★ 拖节点也要【网络吸附】：吸到别的节点 / 门 / 路中线上，
      //   十字标跟着走，松手就能合并。只吸栅格是不够的。
      const s = this.doc.snap(p, this.hitNode(p, d.id));
      this.snapHint = s;
      this._dragTarget = s.kind === "node" ? s.id : "";
      this.doc.moveNode(d.id, s.point);
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
    const d = this._drag;
    this._drag = null;
    if (d?.snap) this._undo.push(d.snap);       // 拖动 = 一步撤销（记开始前那张）
    if (d?.kind === "node" && this._dragTarget && this._dragTarget !== d.id) {
      // ★ 松手时落在另一个节点上 → 合并（两边接上，多余的节点消失）
      this.doc.mergeNodes(this._dragTarget, d.id);
      this.selected = this._dragTarget;
      this.ui.toast("两块并成一块");
    }
    this._dragTarget = "";
    if (d?.kind === "bld") this.doc.alignBuilding(d.id);   // ★ 松手贴边
    this.redraw();
  }

  /** 这个吸附结果能不能当区域的【下一个】顶点。
   *  第一个点必须挂在路/建筑上（见 AREA_ANCHOR）；之后随便放，空地上也行。 */
  areaVertexOk(s) {
    if (!s) return false;
    if (!this._areaPath.length) return AREA_ANCHOR.has(s.kind);
    return true;
  }

  /** ★ 顶点落在【路上】时要让开：从路中心线挪到「路边 + 0.5m」。
   *
   *  往哪一侧挪？按【你点击在路的哪一边】定 —— 这是最自然、也最好预测的规则。
   *  正好点在中心线上时取正法线那一侧。
   *
   *  ★ 顺带的好处：不再去【拆】那条路了。
   *    本来点在路中段会 resolve 成"新建节点 + 拆边"，而区域顶点离开中心线以后，
   *    拆边就没有意义了（它不挂在路上），拆了反而把一条好路切成两段。
   */
  areaVertexPoint(s, click) {
    if (s.kind !== "road") return s.point;
    const rd = this.doc.nearestRoad(s.point);
    if (!isFinite(rd.dist) || !rd.normal) return s.point;
    const n = rd.normal;
    const side = ((click[0] - s.point[0]) * n[0] + (click[1] - s.point[1]) * n[1]) >= 0 ? 1 : -1;
    const off = (rd.width || 4) / 2 + AREA_CLEAR;
    return [s.point[0] + n[0] * side * off, s.point[1] + n[1] * side * off];
  }

  /** ★ 地面区域：依次点节点，点回【第一个节点】就闭合。
   *  落在路上会自动补一个节点（省得先去画路）；取消时把补出来的清掉。 */
  _areaClick(p) {
    const s = this._snapAt(p);
    if (!this.areaVertexOk(s)) {
      this.ui.toast("点节点（或路）—— 区域是用节点围出来的");
      return true;
    }
    // ★ 第一个点必须落在路 / 建筑上：区域要挂进世界，不能凭空浮着。
    //   之后的点随便放（空地上也行）—— "不需要完全依靠道路"。
    if (!this._areaPath.length && !AREA_ANCHOR.has(s.kind)) {
      this.ui.toast("第一个点要落在路上或者建筑上 —— 之后的点随便放");
      return true;
    }
    this._areaStack.push(this.doc.snapshot());  // 每加一个顶点先记一张（右键退一张）
    // 落在路上 → 让开路（新建一个"旁边"的自由节点）；落在节点/门 → 直接用；
    // 落在空地 → 新建。总之都不拆路。
    const nid = (s.kind === "road")
      ? this.doc.addNode(this.areaVertexPoint(s, p))
      : this.doc.resolve(s);
    if (!nid) { this._areaStack.pop(); return true; }
    const path = this._areaPath;
    if (path.length >= 3 && nid === path[0]) {  // 闭合
      this.pushUndo();
      const id = this.doc.addArea(path, this.areaKind);
      this._areaPath = []; this._areaStack = []; this._areaSnap = null;
      this.ui.toast(id ? `围好了（${AREA_LABEL[this.areaKind] || this.areaKind}）` : "围不起来");
    } else if (!path.includes(nid)) {
      path.push(nid);
    }
    this.redraw();
    return true;
  }
  /** ★ 一个入口放掉所有半截手势：正在画的路、正在围的区域、正在拖的东西。
   *  右键 / Esc / 换工具 都走它 —— 各写一遍迟早会漏掉一个。 */
  /** 右键。 */
  _context() {
    if (this._pending) {                       // 画路中：回到初始
      this._pending = null;
      this.snapHint = null;
      this.doc.pruneOrphans();
      this.redraw();
      return;
    }
    if (this._areaPath.length) {               // 围区域中：回到上一个点
      const snap = this._areaStack.pop();      // 退一张快照 —— 顶点若是在路上生成的
      this._areaPath.pop();                    //（还拆了边），也一起退干净
      if (snap) this.doc.restore(snap); else this.doc.pruneOrphans();
      if (!this._areaPath.length) this._areaStack = [];
      this.redraw();
      return;
    }
    this.deselect();                           // 没在手势里：放下手上的东西
  }

  cancelGesture() {
    const had = this._pending || this._areaPath.length || this._drag;
    this._pending = null; this._drag = null; this._dragTarget = "";
    this._areaPath = []; this._areaStack = [];
    if (!had) return;
    // ★ 用 pruneOrphans，【不是】整份还原。
    //   因为"点了第一个点就在那里生成了一个节点"是【有意的】——
    //   区域要挂在路/建筑上，那个节点本来就该留下（它还有边连着）。
    //   整份还原会把它一起抹掉，反而违背设计。
    //   只清"没边的悬空点"：过程中落在空地上的那些。
    this._areaSnap = null;
    this.doc.pruneOrphans();
    this.redraw();
  }

  /** ★ 等用户在【地图上点一个建筑】。设了它，下一次点击就走这里。
   *  人物设计器"在地图上选住所"用 —— 比下拉框直观得多。 */
  pickBuilding(cb) {
    this._pick = cb;
    this.setTool("select");   // 别让别的工具抢走这次点击
    this.redraw();
  }

  /** 纯点击（没被 _down 接走、也没平移）。 */
  _click(x, y) {
    const p = [x, y];
    if (this._pick) {                        // 有人在地图上等一个建筑
      const cb = this._pick;
      this._pick = null;
      cb(this.hitBuilding(p));
      this.redraw();
      return;
    }
    if (this.tool === "road") return this._roadClick(p);
    if (this.tool === "area") return this._areaClick(p);
    if (this.tool === "place") return this._place(p);
    if (this.tool === "erase") return this._erase(p);
    if (this.tool === "select") { this.selected = ""; this.redraw(); }
  }

  /** ★ 画路：点起点 → 点终点。和区域同一套（点一下定一点，不用按住拖）。
   *  第一次点击只把起点定下来，橡皮筋跟着鼠标走；第二下才动数据。 */
  _roadClick(p) {
    const s = this._snapAt(p);
    if (!this._pending) {
      this._pending = s;
      this.snapHint = s;
      this.ui.toast("再点一下定终点（右键取消）");
      this.redraw();
      return;
    }
    this.pushUndo();
    const id = this.doc.connect(this._pending, s, { width: this.roadWidth });
    if (!id) this.ui.toast("没连成 —— 两端要么重合，要么落点无效");
    this.doc.pruneOrphans();
    this._pending = null;
    this.redraw();
  }

  _hover(x, y) {
    this._last = [x, y];
    this.snapHint = this._snapAt([x, y]);
    this.ui.setCursor?.(this.snapHint);
    this._paint();
  }

  _place(p) {
    this.pushUndo();
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
    this.pushUndo();
    const bid = this.hitBuilding(p);
    if (bid) { this.doc.removeBuilding(bid); this.selected = ""; }
    else if (this.doc.removePropNear(p)) { this.selected = ""; }
    else if (this.doc.removeAreaAt(p)) { this.selected = ""; this.selectedArea = ""; }
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

    // ④ 十字标 —— 画路时【两个】：
    //      起点：固定在你按下时吸到的那个点上（深色描边，表示"已经定住了"）
    //      终点：跟着鼠标走，吸到节点 / 门 / 路中线就变色（释放即合并）
    //    别的工具下只画跟着鼠标的那一个。
    const target = this._pending || this.snapHint;
    if (target?.edge) this._highlightEdge(target.edge);      // 这次会拆哪条
    if (this._pending) {
      this._paintSnap(this._pending, { locked: true });
      if (this.snapHint && this._pending.point !== this.snapHint.point) {
        const f = this._pending.point, t2 = this.snapHint.point;
        this.overlay2.addChild(new Graphics()
          .moveTo(f[0] * U, f[1] * U).lineTo(t2[0] * U, t2[1] * U)
          .stroke({ color: SNAP_COLOR[this.snapHint.kind] ?? 0xffffff,
                    width: Math.max(4, 4 * U), alpha: 0.32, cap: "round" }));
      }
    }
    if (this.snapHint && (!this._pending || this._pending.point !== this.snapHint.point))
      this._paintSnap(this.snapHint);

    // ⑤ 摆房：幽灵框画在【贴边之后】的位置 —— 否则看着落这儿、放下落那儿 ★ 规则 6
    // ④b 选中的地面区域：亮外框 + 顶点手柄
    const sa = this.doc.areas.find(a => a.id === this.selectedArea);
    if (sa) {
      const poly = this.doc.areaPath(sa);
      if (poly.length >= 3) {
        const g = new Graphics();
        g.poly(poly.flatMap(([x, y]) => [x * U, y * U]));
        g.stroke({ color: 0xff6b3d, width: 3, alpha: 0.95 });
        this.overlay2.addChild(g);
        for (const [x, y] of poly)
          this.overlay2.addChild(new Graphics().circle(x * U, y * U, 6)
            .fill({ color: 0xf7f4ee }).stroke({ color: 0xff6b3d, width: 2.5 }));
      }
    }

    // ⑤ 地面区域：正在围的多边形（最后一个点连到鼠标）
    if (this.tool === "area" && this.snapHint?.kind === "road" && this._last) {
      const v = this.areaVertexPoint(this.snapHint, this._last);   // 让开后的落点
      this.overlay2.addChild(new Graphics().circle(v[0] * U, v[1] * U, 5)
        .fill({ color: 0xffc53d, alpha: 0.85 })
        .stroke({ color: 0x141414, width: 2 }));
      this.overlay2.addChild(new Graphics()
        .moveTo(this.snapHint.point[0] * U, this.snapHint.point[1] * U)
        .lineTo(v[0] * U, v[1] * U)
        .stroke({ color: 0xffc53d, width: 2, alpha: 0.7, cap: "round" }));
    }

    if (this.tool === "area" && this._areaPath.length) {
      const pts = this._areaPath.map(id => this.doc.nodes[id]?.xy).filter(Boolean);
      const cur = this.snapHint?.point;
      const all = cur ? [...pts, cur] : pts;
      if (all.length >= 2) {
        const g = new Graphics();
        g.poly(all.flatMap(([x, y]) => [x * U, y * U]));
        g.fill({ color: 0xffffff, alpha: 0.18 });
        g.stroke({ color: 0xffffff, width: 2.5, alpha: 0.9 });
        this.overlay2.addChild(g);
      }
      // 每个已选节点点一个亮圈；第一个再套一圈，提示"点它闭合"
      pts.forEach(([x, y], i) => {
        const r = i === 0 ? 12 : 8;
        this.overlay2.addChild(new Graphics().circle(x * U, y * U, r)
          .fill({ color: i === 0 ? 0xffc53d : 0x2fbf6f, alpha: 0.3 })
          .stroke({ color: i === 0 ? 0xffc53d : 0x2fbf6f, width: 2.5 }));
      });
    }

    // ⑥ 摆放预览：画【真资产】的半透明幽灵 —— 光一个圆圈看不出要摆的是什么
    if (this.tool === "place" && this.propName && this._last) {
      const g = this.doc.gridSnap === false ? this._last : this.doc.grid(this._last);
      // ★ PROP_SIZE 已经是【世界像素】（maprender 直接当像素用）—— 别再乘 U
      const sz = PROP_SIZE[this.propName] || [20, 20];
      this._ghost(`props/${this.propName}.svg`, g, sz, { bottomCenter: true, px: true });
    }
    if (this.tool === "place" && this.buildType && !this.propName && this._last) {
      const [px, py] = this._last;
      const tmp = { type: this.buildType, center: [px, py],
                    size: this.doc.sizeFor(this.buildType), rot: 0, doors: [], floors: 1 };
      const a = this.doc.computeAlign(tmp);
      const c = a ? a.center : tmp.center, rot = a ? a.rot : 0;
      const hasRoad = Object.keys(this.doc.edges).length > 0;
      const [w, h] = tmp.size;
      // 真资产的幽灵（半透明、跟鼠标走）
      const art = this.assets.buildingTypes()[this.buildType];
      if (art) this._ghost(`bld/${art}.svg`, c, [w * U, h * U], { rot, px: true });
      // 占地外框（贴边之后的位置，不是鼠标位置）
      const gh = new Graphics()
        .poly([-w / 2 * U, -h / 2 * U, w / 2 * U, -h / 2 * U, w / 2 * U, h / 2 * U, -w / 2 * U, h / 2 * U])
        .stroke({ color: hasRoad ? 0xffffff : 0xb4552d, width: 2, alpha: 0.9 });
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

  /** 吸附点：十字标 + 环。颜色说明吸到了什么。
   *
   *  ★ 两层描边：先粗深色再细亮色 —— 草地、沥青、人行道三种底色上都看得清。
   *    只有一个细圈的话，在沥青上几乎看不见。
   */
  _paintSnap(s, opt = {}) {
    // 区域模式下复用同一套吸附，只是"能不能当顶点"决定颜色 ——
    // 灰 = 这里不行（点了也白点），亮 = 可以当顶点。
    const col = (this.tool === "area" && !this.areaVertexOk(s))
      ? 0x8a8779 : (SNAP_COLOR[s.kind] ?? 0xffffff);
    const [x, y] = [s.point[0] * U, s.point[1] * U];
    const r = s.kind === "free" ? 6 : 9;
    const arm = r + 7;
    const g = new Graphics();
    // ① 深色底
    g.moveTo(x - arm, y).lineTo(x + arm, y);
    g.moveTo(x, y - arm).lineTo(x, y + arm);
    g.stroke({ color: 0x141414, width: 5.5, alpha: 0.6, cap: "round" });
    // ② 亮色十字
    g.moveTo(x - arm, y).lineTo(x + arm, y);
    g.moveTo(x, y - arm).lineTo(x, y + arm);
    g.stroke({ color: col, width: 2.6, cap: "round" });
    // ③ 环（实心淡 + 亮边）
    g.circle(x, y, r).fill({ color: col, alpha: 0.22 }).stroke({ color: col, width: 2.6 });
    if (opt.locked) {          // 起点：外圈再加一道深色，一眼看出"这个已经定住了"
      g.circle(x, y, r + 4).stroke({ color: 0x141414, width: 3, alpha: 0.8 });
    }
    this.overlay2.addChild(g);
  }

  /** 半透明幽灵：把真资产按世界尺寸画在目标位置。 */
  /** 幽灵。size 传【世界像素】（调用方自己乘好 U）。 */
  _ghost(file, at, size, opt = {}) {
    const tex = this.assets.get(file);
    const [w, h] = size;                 // 世界像素
    if (!tex) {                          // 贴图还没到货就先画个框
      this.overlay2.addChild(new Graphics()
        .rect(at[0] * U - w / 2, at[1] * U - h / 2, w, h)
        .fill({ color: 0xf7f4ee, alpha: 0.2 }).stroke({ color: 0xf7f4ee, width: 2 }));
      return;
    }
    const sp = new Sprite(tex);
    sp.width = w; sp.height = h;
    sp.alpha = 0.62;
    sp.anchor.set(0.5, opt.bottomCenter ? 1 : 0.5);
    sp.position.set(at[0] * U, at[1] * U);
    if (opt.rot) sp.rotation = opt.rot * Math.PI / 180;
    this.overlay2.addChild(sp);
  }

  snapText() {
    if (!this.snapHint) return "";
    if (this.tool === "area")
      return this.areaVertexOk(this.snapHint)
        ? (this._areaPath.length ? "可以当顶点（点它）" : "起点（挂在路上）")
        : (this._areaPath.length ? "这里不能当顶点" : "起点要落在路或建筑上");
    if (this.tool === "road") return this._pending ? "再点一下定终点" : "点一下定起点";
    return SNAP_TEXT[this.snapHint.kind];
  }
}

export { U };
