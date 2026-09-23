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
import { clampRel } from "./layout.js";
// ★ 光标标记只有这一份实现（形状/颜色/手势的语义都写在它的文件头里）
import { MARK, markRing } from "./markers.js";
import { Container, Graphics, Sprite } from '../vendor/pixi.min.mjs';
import { View, U } from './view.js';
import { MapLayer } from './maprender.js';
import { MapDoc } from './mapdoc.js';

// 亮一档的强调色 —— 细圈在草地和沥青上都看不清，换成高亮
// 吸附点用哪个颜色 —— 语义表在 markers.js 里，这里只是把"吸附种类"对到"标记语义"。
// 节点/门/路中线本来就是三类东西，各占一个色；它们同时也是 item/door/road 的色。
const SNAP_KIND = { node: "node", door: "door", road: "road", free: "free" };
// 吸附到什么：短词就行，别写句子（“路中线（会拆成两条）”这种太长，顶栏一闪一闪的）。
const SNAP_TEXT = { node: "节点", door: "门", road: "路段", free: "自由" };
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
    this.map = new MapLayer(assets);
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
    this.hoverLoc = "";                // 人物/建筑名单悬浮时，在地图上高亮这栋楼
    this.selected = "";
    this.snapHint = null;
    this._pending = null;               // 画路中的起点（未提交）
    this._undo = [];                    // 撤销栈（整份地图快照）
    this._MAX_UNDO = 60;
    this._drag = null;
    this._last = null;
    // placing: 屋内摆放模式。★ 家具位置是【前端的事】—— 后端只说"在哪个 region
    //   里"，楼里摆在哪儿存在场景文件的 entities[].pos（相对 0~1 比值），
    //   游戏端自己读。进摆放 = 【双击地图上的楼】（见 _double），出来 = Esc/右键。
    this.placing = false;
    this.pick = "";          // 手上【拿着】哪件家具（跟着鼠标走）；空 = 没拿
    this.pickAt = null;      // 拿着的时候鼠标在哪（世界坐标）
    this.hoverItem = "";     // 鼠标悬在哪件上（要亮起来，不然不知道点得中哪个）
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
    this.view.onDouble = (x, y) => this._double(x, y);
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
    this.ui.toast("已保存 " + target);      // 直接覆盖，不留 .bak
  }

  /** 右键：放下手上拿的、取消选中。回到「选择」，什么都不拿。 */
  deselect() {
    if (this.placing) { this.exitPlacing(); return; }   // ESC / 右键 = 退出摆放
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

  // ── 摆家具（屋内摆放模式）────────────────────────────────────────
  //  ★ 家具在楼【里面】，命中必须在 hitBuilding 之前判 ——
  //    不然点家具会先被楼抢走，变成拖房子。
  //  坐标走 doc.layoutOf()（和游戏端同一个 layout.js）→
  //    编辑器里看到的位置，就是游戏里画出来的位置。

  /** 当前在摆哪栋楼（没选中 / 没开摆放模式 = 空）。 */
  placingIn() { return this.placing && this.doc.buildings[this.selected] ? this.selected : ""; }

  /** 进屋摆放：把镜头平滑推到那栋楼，占窗口 80%。
   *
   *  ★ 为什么要自动推：屋里的东西才 0.6 米宽，整城视角下就是几个像素，
   *    根本没法摆。手动缩放到那栋楼又太绕。
   */
  enterPlacing(bid) {
    if (!this.doc.buildings[bid]) return;
    this.placing = true;
    this.pick = ""; this.pickAt = null; this.hoverItem = "";
    this.selected = bid;
    this.setTool("select");                 // 命中/拖拽只在 select 下走
    const [cx, cy] = this.doc.buildings[bid].center;
    const r4 = this._rect4(bid);
    this.fitBox(cx, cy, r4[2], r4[3], 0.8);
    this.redraw();
  }

  exitPlacing() {
    if (!this.placing) return;
    this.placing = false;
    this.pick = ""; this.pickAt = null; this.hoverItem = "";
    this._pickSnap = null;
    this.view.el.style.cursor = "crosshair";
    this.redraw();
  }

  /** 楼的世界矩形 (x, y, w, h)。只按 center+size —— 和 toScene() 写的
   *  locations 一致（那边也是 x=cx-w/2），所以两边看到的框是同一个。 */
  _rect4(bid) {
    const b = this.doc.buildings[bid];
    const [cx, cy] = b.center, [w, h] = b.size;
    return [cx - w / 2, cy - h / 2, w, h];
  }

  /** 把某个矩形平滑推到窗口的 frac（0~1）大小。 */
  fitBox(cx, cy, w, h, frac = 0.8) {
    const [vw, vh] = this.view.viewport();
    const k = Math.min((vw * frac) / (Math.max(0.1, w) * U),
                       (vh * frac) / (Math.max(0.1, h) * U));
    this.view.flyTo(cx, cy, k, 460);
  }

  /** 这栋楼里每件东西的【世界占地】（米）：{id: [宽, 高]}。
   *  ★ 尺寸只在美术清单里 —— 摆放的边界要按它算，不然图形会挂出墙。 */
  _itemSizes(bid) {
    const out = {};
    for (const e of this.doc.at(bid)) {
      const ent = this.assets.entry(`items/${e.type}.svg`);
      // ★ 返回【米】—— layout.js 里的 STRIDE/PAD/墙宽全是米。
      //   作者尺寸 2× 画的 → 除 2 得世界像素 → 再除 U 才是米。
      //   漏掉 /U 的话：26px 的机器被当成 26 米宽，比房子还大，
      //   于是被夹到墙角 —— 表现就是"拖不动"（用户实测）。
      if (ent) out[e.id] = [ent.w / 2 / U, ent.h / 2 / U];
    }
    return out;
  }

  /** 光标下那件东西（只在自己那栋楼里找）。 */
  hitItem(p) {
    const bid = this.placingIn();
    if (!bid) return "";
    const t = this._tol();
    let best = "", bd = t;
    for (const [id, q] of this.doc.layoutOf(bid, this._itemSizes(bid))) {
      const d = Math.hypot(q[0] - p[0], q[1] - p[1]);
      if (d < bd) { bd = d; best = id; }
    }
    return best;
  }

  /** 捡起一件。开一张撤销快照 —— "挪一件 = 一步撤销"。 */
  takeItem(id) {
    this.pick = id;
    this.pickAt = this._last;
    this.hoverItem = id;
    this._pickSnap = this.doc.snapshot();
    this.view.el.style.cursor = "grabbing";
    this.redraw();
  }

  /** 把手上的放到 p（吸屋内栅格 + 按占地夹进屋里）。 */
  dropPick(p) {
    const id = this.pick;
    if (!id) return;
    const [rx, ry] = this._relIn(this.selected, this._gridIn(p), this._itemSizes(this.selected)[id]);
    this.doc.setEntPos(id, rx, ry);
    this.pick = ""; this.pickAt = null;
    if (this._pickSnap) { this._undo.push(this._pickSnap); this._pickSnap = null; }
    this.view.el.style.cursor = "crosshair";
    this.redraw();
  }

  /** 世界坐标 → 楼内相对坐标 0~1。
   *
   *  ★ 必须按【占地】夹，不是只夹 0~1：`pos` 是脚底那个点，只夹 0~1 的话
   *    点在墙内、半个图形挂在墙外（实测："家具超出了房屋边界"）。
   *    边界算法在 layout.clampRel —— 和游戏端同一个，所见即所得。
   */
  _relIn(bid, p, size) {
    const b = this.doc.buildings[bid];
    const [cx, cy] = b.center, [w, h] = b.size;
    const rect = { x: cx - w / 2, y: cy - h / 2, w, h };
    const rx = w > 0 ? (p[0] - rect.x) / w : 0.5;
    const ry = h > 0 ? (p[1] - rect.y) / h : 0.5;
    return clampRel(rect, size, rx, ry);
  }

  /** 屋内栅格吸附（只在开着栅格吸附时）。4 米那一套是室外的，摆家具不能用。 */
  _gridIn(p) {
    const g = Math.max(0.05, +(this.doc.gridInM || 0.5));
    if (this.doc.gridSnap === false) return p;
    return [Math.round(p[0] / g) * g, Math.round(p[1] / g) * g];
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
    // ★ 摆家具【优先于一切】：家具在楼里面，先判楼的话永远拖不到它们。
    //   没点到东西就 return false → 让相机平移（拖地板 = 挪镜头，老手感）。
    if (this.placing) {
      // ★ 这套是「点起来 → 跟着鼠标 → 点击放下」，不是"按住拖"：
      //   按住拖在东西叠一起时根本选不中（用户："放置重叠不好选"）。
      if (this.pick) { this.dropPick(p); return true; }   // 手上拿着 → 这一下是放下
      const eid = this.hitItem(p);
      if (!eid) return false;                             // 空地 → 让相机平移
      this.takeItem(eid);
      return true;
    }
    // ★ 只有"拖"在这里接：房子 / 节点 / 环境物件。
    //   画路和围区域都是【点一下再点一下】，走 _click ——
    //   这样拖 = 平移、点 = 操作，两个工具同一套手感。
    if (this.tool !== "select") return false;
    const before = this.doc.snapshot();
    const bid = this.hitBuilding(p);
    if (bid) {
      const b = this.doc.buildings[bid];
      this.selected = bid;
      this._drag = { kind: "bld", id: bid, snap: before, moved: false,
                     off: [p[0] - b.center[0], p[1] - b.center[1]] };
      return true;
    }
    const nid = this.hitNode(p);
    if (nid) {
      this.selected = nid;
      this._drag = { kind: "node", id: nid, snap: before, moved: false };
      return true;
    }
    const pi = this.doc.propNear(p);
    if (pi >= 0) {                               // 拖环境物件
      this.selected = "prop:" + pi;
      this._drag = { kind: "prop", idx: pi, snap: before, moved: false };
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
    if (this._placingMove(p)) return;    // ★ 和 _hover 共用一套（见 _placingMove）
    const d = this._drag;
    if (d) d.moved = true;                                // 动过就算拖动
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
    // ★ 只是【点了一下】建筑（没拖）= 跳进建筑编辑。
    //   拖动还是要留给"挪房子"，所以必须区分这两者。
    if (d && d.kind === "bld" && !d.moved) {
      this.ui.openBuilding?.(d.id);
      return;
    }
    if (d?.moved && d?.snap) this._undo.push(d.snap);  // 拖动 = 一步撤销（记开始前那张）
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

  /** 双击一栋楼 → 直接进屋内摆放。
   *
   *  ★ 为什么是双击：单击已经给了"进建筑面板"，再双击进去摆家具是自然的下一层
   *    （点一下 = 选它，点两下 = 进去）。比在面板上放个按钮少一步、也不用先选中。
   *  退出只剩 Esc / 右键 —— 不再有「摆完了」按钮（用户砍掉的）。
   */
  _double(x, y) {
    if (this.tool !== "select") return;          // 画路/围区域时双击是"手滑"
    if (this._pending || this._areaPath.length) return;
    if (this._pick) return;                      // 人物设计器正等着选住所
    const bid = this.hitBuilding([x, y]);
    if (bid) this.enterPlacing(bid);
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
    // ★ 摆放模式里点空地【什么都不做】。以前会走到下面那句把 selected 清掉，
    //   于是"随便点击一下就出去了"（用户实测）。
    if (this.placing) return;
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
    // ★ 摆放模式下不吸路网、不亮楼 —— 那套是室外的。光标就在屋里，直接处理。
    if (this._placingMove([x, y])) {
      this.snapHint = null;                 // 屋里不吸路网：清掉残留的十字标
      this.ui.setCursor?.(null);
      return;
    }
    this._last = [x, y];
    this.snapHint = this._snapAt([x, y]);
    this.ui.setCursor?.(this.snapHint);
    // ★ 鼠标划过一栋楼也高亮（和"在名单里划"是同一个 hoverLoc）。
    //   没有它的话，只能从名单反查地图，不能从地图反查是哪一栋。
    if (!this._drag && !this._pending) {
      const bid = this.hitBuilding([x, y]);
      if (bid !== this.hoverLoc) this.hoverLoc = bid;
    }
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

  /** 摆放模式下的鼠标移动：悬停高亮 + 手上那件跟手。
   *
   *  ★★ 必须在【两条路】上都调：view.js 的 pointermove 在不按键时走
   *    `onHover`、按住时走 `onDrag`。只挂在 _move 上的话，"家具跟着鼠标走"
   *    就只在按住的时候才动（用户实测：点了没反应、不跟手）。
   *    而点起来 / 放下走的是 pointerdown，那条路是好的 —— 于是症状正好是
   *    "能拿起来，但不动"。
   */
  _placingMove(p) {
    if (!this.placingIn()) return false;
    this._last = p;
    if (this.pick) { this.pickAt = p; this.redraw(); return true; }   // 手上拿着 → 跟手
    const h = this.hitItem(p);
    if (h !== this.hoverItem) { this.hoverItem = h; this.redraw(); }
    return true;
  }

  /** 被拿走那件原来站的地方：画个虚空圈，知道"它本来在哪儿"。 */
  /** 屋内摆放：把选中那栋楼的里面画出来。
   *
   *  为什么画在【地图上】而不是右栏开个小画布：
   *  状态只有一份 —— 两套坐标系一定会出现"地图上一个地方、小图里另一个地方"。
   *  房子本来就是按真实比例画的，滚轮放大就能精确定位。
   */
  _paintPlacing(b) {
    const [cx, cy] = b.center, [w, h] = b.size;
    const x0 = (cx - w / 2) * U, y0 = (cy - h / 2) * U;
    const pw = w * U, ph = h * U;
    // ① 屋内地面：盖上底色，把屋外的路网压下去 —— 一眼看出"现在在屋里"
    this.overlay2.addChild(new Graphics().rect(x0, y0, pw, ph)
      .fill({ color: 0xfdfbf6, alpha: 0.9 })
      .stroke({ color: 0xb4552d, width: 3 }));
    // ② 屋内淡格：★ 步长用 doc.gridInM（屋内的那一套），不是 gridM。
    //    4 米的室外格摆不了家具；太密（屏幕上不到 14px）就不画 —— 画出来
    //    是一片噪声，用户看到的是"一堆不知道干嘛的线"。
    const gi = Math.max(0.05, +(this.doc.gridInM || 0.5));
    if (gi * U * this.view.cam.k >= 14) {
      const g = new Graphics();
      for (let x = gi; x < w - 1e-6; x += gi)
        g.moveTo((cx - w / 2 + x) * U, y0).lineTo((cx - w / 2 + x) * U, y0 + ph);
      for (let y = gi; y < h - 1e-6; y += gi)
        g.moveTo(x0, (cy - h / 2 + y) * U).lineTo(x0 + pw, (cy - h / 2 + y) * U);
      g.stroke({ color: 0xd9d2c4, width: 1, alpha: 0.7 });
      this.overlay2.addChild(g);
    }
    // ③ 件件东西画【真资产】，不是圆点 —— 不看到灶台就不知道自己在挪什么
    const sizes = this._itemSizes(this.selected);
    const carried = this.pick;
    for (const [id, q] of this.doc.layoutOf(this.selected, sizes)) {
      const e = (this.doc.meta.entities || []).find((x) => x.id === id);
      if (!e) continue;
      const ent = this.assets.entry(`items/${e.type}.svg`);
      const m = ent ? [ent.w / 2 / U, ent.h / 2 / U] : [1.2, 1.2];   // 米
      const px = [m[0] * U, m[1] * U];                              // 画的时候要像素
      // 手上拿着那件【不在这画】—— 它画在鼠标那儿（见下面），原位留个虚圈
      // ★ 屋里【不用标记】，一律用高亮（见 markers.js 的文件头）：
      //   普通 = 半透明；悬停 = 不透明 + 暖色。圈会盖住家具，还看不清它长什么样。
      if (id === carried) continue;        // 手上那件画在鼠标处，原位留个空位就行
      const hover = id === this.hoverItem;
      this._ghost(`items/${e.type}.svg`, q, px,
        { px: true, alpha: hover ? 1 : 0.62, tint: hover ? 0xfff0c4 : 0xffffff });
    }
    // 手上那件：画在【会落在哪儿】（吸完栅格、夹完边界的位置），
    // 不是画在鼠标原始位置 —— 不然看着落这儿、实际落那儿。
    if (carried && this.pickAt) {
      const e = (this.doc.meta.entities || []).find((x) => x.id === carried);
      const ent = e ? this.assets.entry(`items/${e.type}.svg`) : null;
      const m = ent ? [ent.w / 2 / U, ent.h / 2 / U] : [1.2, 1.2];   // ★ 米
      const px = [m[0] * U, m[1] * U];
      const [rx, ry] = this._relIn(this.selected, this._gridIn(this.pickAt), m);
      const r4 = this._rect4(this.selected);
      const halo = [r4[0] + rx * r4[2], r4[1] + ry * r4[3]];
      // 手上那件：不透明 + 选中色 —— 高亮即是"锁在这儿了"，不再另加标记
      if (e) this._ghost(`items/${e.type}.svg`, halo, px,
        { px: true, alpha: 1, tint: 0xfff0b0 });
      const from = this.doc.layoutOf(this.selected, sizes).get(carried);
      if (from) this.overlay2.addChild(new Graphics()
        .moveTo(from[0] * U, from[1] * U).lineTo(halo[0] * U, halo[1] * U)
        .stroke({ color: 0x2fbf6f, width: 1.5, alpha: 0.5 }));
    }
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

    // ★ 悬浮高亮：人物名单 / 建筑名单里划过一个，地图上亮起对应的楼。
    //   没有这个的话，名字对得上、但地图上看不到是哪一栋。
    if (this.hoverLoc && this.doc.buildings[this.hoverLoc]) {
      const hb = this.doc.buildings[this.hoverLoc];
      const [hw, hh] = hb.size;
      const g = new Graphics()
        .poly([-hw / 2 * U, -hh / 2 * U, hw / 2 * U, -hh / 2 * U,
               hw / 2 * U, hh / 2 * U, -hw / 2 * U, hh / 2 * U])
        .fill({ color: 0xffc53d, alpha: 0.32 })
        .stroke({ color: 0xffc53d, width: 3.5 });
      g.position.set(hb.center[0] * U, hb.center[1] * U);
      g.rotation = (hb.rot || 0) * Math.PI / 180;
      this.overlay2.addChild(g);
      // 名字也一起亮出来 —— 光有个框，不知道是哪栋
      this.view.paper("hover:loc", this.doc.nameOf(this.hoverLoc),
                      hb.center[0], hb.center[1] - hh / 2, "plate", -6);
    } else if (this.view._paper?.has("hover:loc")) {
      this.view.dropPaper("hover:loc");
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
      // ③b 正在摆家具 → 把屋里画出来（压在上面那个淡框之上）
      if (this.placingIn()) this._paintPlacing(b);
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
          markRing(this.overlay2, x, y, "area", { r: 5 });
      }
    }

    // ⑤ 地面区域：正在围的多边形（最后一个点连到鼠标）
    if (this.tool === "area" && this.snapHint?.kind === "road" && this._last) {
      const v = this.areaVertexPoint(this.snapHint, this._last);   // 让开后的落点
      markRing(this.overlay2, v[0], v[1], "pick", { r: 5 });
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
      // 已选顶点：第一个（点它能闭合）用 pick 色强调并"锁定"，其余用 node 色
      pts.forEach(([x, y], i) =>
        markRing(this.overlay2, x, y, i === 0 ? "pick" : "node",
                 { r: i === 0 ? 9 : 6, locked: i === 0 }));
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
      markRing(this.overlay2, px, py, "free", { r: 3 });   // 鼠标落点
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
    // 区域模式下复用同一套吸附，只是"能不能当顶点"决定语义 ——
    // bad = 这里不行（点了也白点），其余按吸附种类上色。
    const bad = this.tool === "area" && !this.areaVertexOk(s);
    const kind = bad ? "bad" : (SNAP_KIND[s.kind] || "free");
    markRing(this.overlay2, s.point[0], s.point[1], kind, { locked: opt.locked });
  }

  /** 半透明幽灵：把真资产按世界尺寸画在目标位置。 */
  /** 幽灵。size 传【世界像素】（调用方自己乘好 U）。 */
  /** 一件资产的半透明幽灵（摆放预览 / 屋内家具）。
   *
   *  ★ 返回 Sprite —— 屋内【不用标记】，靠改这个 Sprite 的 tint/alpha 做高亮。
   *    白色 tint = 原色；别的颜色是**乘上去**的（Pixi 的规矩），
   *    所以高亮色只能往暖/亮里挑，挑了深色会把图压黑。
   */
  _ghost(file, at, size, opt = {}) {
    const tex = this.assets.get(file);
    const [w, h] = size;                 // 世界像素
    if (!tex) {                          // 贴图还没到货就先画个框
      this.overlay2.addChild(new Graphics()
        .rect(at[0] * U - w / 2, at[1] * U - h / 2, w, h)
        .fill({ color: 0xf7f4ee, alpha: 0.2 }).stroke({ color: 0xf7f4ee, width: 2 }));
      return null;
    }
    const sp = new Sprite(tex);
    sp.width = w; sp.height = h;
    sp.alpha = opt.alpha ?? 0.62;
    sp.anchor.set(0.5, opt.bottomCenter ? 1 : 0.5);
    sp.position.set(at[0] * U, at[1] * U);
    if (opt.rot) sp.rotation = opt.rot * Math.PI / 180;
    if (opt.tint) sp.tint = opt.tint;
    this.overlay2.addChild(sp);
    return sp;
  }

  snapText() {
    if (!this.snapHint) return "";
    if (this.tool === "area")
      return this.areaVertexOk(this.snapHint)
        ? (this._areaPath.length ? "可以当顶点（点它）" : "起点（挂在路上）")
        : (this._areaPath.length ? "这里不能当顶点" : "起点要落在路或建筑上");
    if (this.tool === "road") return this._pending ? "再点一下定终点" : "点一下定起点";
    return SNAP_TEXT[this.snapHint.kind] || "";
  }
}

export { U };
