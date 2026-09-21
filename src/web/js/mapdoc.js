/** mapdoc.js —— 地图文档模型。编辑器唯一的真源，视图只读写它。
 *
 * ══ 为什么是「图」而不是「线」 ══
 *
 * 一条路不是画出来的一根线，是【节点 + 边】：n_001 —e_002→ n_003。
 * 定错了这点，后面全是补丁 —— 粘连、交叉、删除、寻路，每一件都要另想办法。
 * 定对了，下面五条就是几十行：
 *
 *   ① 吸附优先级：既有节点 > 建筑门 > 道路中心线 > 栅格
 *   ② 门即节点：摆房子时把主门注册成路网节点，节点带 door_of，跟着房子走
 *   ③ 没有边的节点不存在 —— 每次改完 prune 一遍，否则攒一堆看不见的幽灵
 *   ④ 必须先有路才能摆房（规则强制，不是提示）
 *   ⑤ 建筑自动贴边：门朝最近的路 + 墙贴路沿
 *
 * 单位是米。画布默认 1280×800，可在 canvas 里改。
 */

const ROAD_SNAP = 3.0;        // 画路时吸附到既有道路中心线的距离（米）
const DOOR_SNAP = 4.0;        // 画路时吸附到建筑门的距离（米）
const AREA_PER_CAPACITY = 20; // 面积 ∝ 容量：1 capacity ≈ 20 m²

let seq = 0;
const uid = (p) => `${p}_${String(++seq).padStart(3, "0")}`;

export class MapDoc {
  constructor(scene = null) {
    this.canvas = { w: 1280, h: 800 };
    this.nodes = {}; this.edges = {}; this.buildings = {};
    this.props = [];                   // 环境物件（树/长椅/路灯/车…）：{name, xy}
    this.gridM = 4;                    // 栅格边长（米）—— 界面上可改
    this.netSnap = true; this.gridSnap = true;
    this.meta = {};                    // 场景里跟几何无关的部分（人/货/公司/认知）
    this.types = {};                   // type_id -> 类型库条目
    this.dirty = false;
    this.listeners = new Set();
    if (scene) this.load(scene);
  }

  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  _changed() { this.dirty = true; for (const fn of this.listeners) fn(this); }

  // ── 载入 / 导出 ──────────────────────────────────────────────────────
  load(scene) {
    const m = scene.map || {};
    this.canvas = { w: +(scene.canvas?.w ?? 1280), h: +(scene.canvas?.h ?? 800) };
    this.nodes = structuredClone(m.nodes || {});
    this.edges = structuredClone(m.edges || {});
    this.buildings = structuredClone(m.buildings || {});
    this.props = structuredClone(m.props || []);
    // ★ 地名要单独记下来：地图编辑【不】改名字，但 toScene() 重算 locations 时
    //   如果不带 name，就会退回自动生成的"店铺4" —— 一次保存把所有人起的名洗掉。
    this.names = Object.fromEntries(
      Object.entries(scene.locations || {}).map(([k, v]) => [k, v.name]).filter(([, v]) => v));
    // 场景里【不是地图】的部分原样留着 —— 保存时透传，不碰。
    // （地图编辑器和人物设计器是两个独立部分，各改各的字段。）
    const { map, canvas, locations, ...rest } = scene;
    this.meta = rest;
    // 续号：别和已有 id 撞
    const maxOf = (obj, p) => Math.max(0, ...Object.keys(obj)
      .filter(k => k.startsWith(p + "_")).map(k => parseInt(k.slice(p.length + 1), 10) || 0));
    seq = Math.max(seq, maxOf(this.nodes, "n"), maxOf(this.edges, "e"),
                   maxOf(this.buildings, "bld"));
    this.dirty = false;
    this._changed();
  }

  /** 导出成场景 JSON：`map` 是编辑的结果，`locations` 由它派生，其余透传。 */
  toScene() {
    const locations = {};
    for (const [bid, b] of Object.entries(this.buildings)) {
      const [x, y] = b.center, [w, h] = b.size;
      locations[bid] = {
        type: b.type, name: this.nameOf(bid),
        x: +(x - w / 2).toFixed(3), y: +(y - h / 2).toFixed(3),
        w: +w.toFixed(3), h: +h.toFixed(3),
      };
      if (b.floors > 1) locations[bid].floors = b.floors;
    }
    return {
      ...this.meta,
      canvas: { ...this.canvas },
      locations,
      map: {
        format: "citysim.map", version: 1,
        world: { unit: "m", bounds: [0, 0, this.canvas.w, this.canvas.h], grid: 1.0 },
        nodes: this.nodes, edges: this.edges, buildings: this.buildings,
        ...(this.props.length ? { props: this.props } : {}),
      },
    };
  }

  nameOf(bid) { return this.names[bid] || this._plate(bid); }

  _plate(bid) {
    const n = parseInt((bid.match(/(\d+)$/) || [])[1] || "0", 10);
    const t = this.types[this.buildings[bid]?.type];
    return t ? `${t.name}${n || ""}` : bid;
  }

  // ── 类型库 ──────────────────────────────────────────────────────────
  setTypes(catalog) {
    this.types = Object.fromEntries((catalog.buildings || []).map(b => [b.type, b]));
  }

  /** 默认占地：面积 ∝ 容量。加楼层不改占地 —— 密度上升，城市不铺开。 */
  sizeFor(typeId) {
    const t = this.types[typeId];
    const cap = Math.max(1, t?.capacity ?? 12), asp = Math.max(0.25, t?.aspect ?? 1);
    const area = cap * AREA_PER_CAPACITY;
    const w = Math.sqrt(area * asp);
    return [w, w / asp];
  }

  // ── 几何 ────────────────────────────────────────────────────────────
  /** 门定义(side/offset) + 尺寸 → 世界门点与朝外法线。 */
  doorWorlds(b) {
    const t = this.types[b.type];
    const defs = (t?.doors?.length ? t.doors : [{ side: "south", offset: 0 }]);
    const [w, h] = b.size, [cx, cy] = b.center;
    const rot = (b.rot || 0) * Math.PI / 180;
    const cos = Math.cos(rot), sin = Math.sin(rot);
    return defs.map(d => {
      const off = (d.offset || 0) * (d.side === "north" || d.side === "south" ? w : h);
      let lx = 0, ly = 0, nx = 0, ny = 0;
      if (d.side === "south") { lx = off; ly = h / 2; ny = 1; }
      else if (d.side === "north") { lx = off; ly = -h / 2; ny = -1; }
      else if (d.side === "east") { lx = w / 2; ly = off; nx = 1; }
      else { lx = -w / 2; ly = off; nx = -1; }
      return { pos: [cx + lx * cos - ly * sin, cy + lx * sin + ly * cos],
               normal: [nx * cos - ny * sin, nx * sin + ny * cos] };
    });
  }

  /** 最近的道路段 {point, dir, normal, edge, width, dist}；没路返回 {dist: Infinity}。
   *  ★ 一定要带【方向】和【法线】：光有"最近点"没法决定房子往哪边推 ——
   *    当点正好落在路上时，最近点 = 它自己，往哪推都是猜的（踩过：推到了路的延长线上）。 */
  nearestRoad(p) {
    let best = { dist: Infinity };
    for (const [eid, e] of Object.entries(this.edges)) {
      const pts = this._poly(e);
      for (let i = 1; i < pts.length; i++) {
        const q = this._closest(p, pts[i - 1], pts[i]);
        const d = Math.hypot(q[0] - p[0], q[1] - p[1]);
        if (d < best.dist) {
          const vx = pts[i][0] - pts[i - 1][0], vy = pts[i][1] - pts[i - 1][1];
          const L = Math.hypot(vx, vy) || 1;
          best = { dist: d, point: q, edge: eid, width: e.width || 4,
                   dir: [vx / L, vy / L],
                   normal: [-vy / L, vx / L] };     // 屏幕坐标 y 向下，+90° = (-dy, dx)
        }
      }
    }
    return best;
  }

  /** 最近的建筑门 {pos, building, index, dist}。 */
  nearestDoor(p) {
    let best = { dist: Infinity };
    for (const [bid, b] of Object.entries(this.buildings)) {
      this.doorWorlds(b).forEach((d, i) => {
        const dist = Math.hypot(d.pos[0] - p[0], d.pos[1] - p[1]);
        if (dist < best.dist) best = { dist, pos: d.pos, building: bid, index: i };
      });
    }
    return best;
  }

  /** ★ ① 统一吸附。画路和预览共用一套，否则"看到的位置"和"落下的位置"会不一样。 */
  snap(p, nodeHit = "") {
    const free = { kind: "free", point: this.grid(p), id: "",
                   building: "", doorIndex: -1 };
    if (this.netSnap === false) return free;      // 网络吸附关掉 → 只吸栅格

    // ★ 节点和门之间【比距离】，不无条件让节点赢。
    //   踩过：门就在鼠标下 1.2m，却被 11m 外的一个既有节点抢走 ——
    //   而节点命中的容差是按【屏幕像素】算的，缩放越小它覆盖的世界范围越大。
    const nodeDist = nodeHit && this.nodes[nodeHit]
      ? Math.hypot(this.nodes[nodeHit].xy[0] - p[0], this.nodes[nodeHit].xy[1] - p[1])
      : Infinity;
    const dw = this.nearestDoor(p);
    const doorOk = dw.dist <= DOOR_SNAP;
    if (nodeDist <= Math.min(doorOk ? dw.dist : Infinity, Infinity) && nodeHit
        && this.nodes[nodeHit]) {
      return { kind: "node", point: this.nodes[nodeHit].xy, id: nodeHit,
               building: this.nodes[nodeHit].door_of || "", doorIndex: -1 };
    }
    if (doorOk)
      return { kind: "door", point: dw.pos, id: "", building: dw.building, doorIndex: dw.index };
    const rd = this.nearestRoad(p);
    if (rd.dist <= ROAD_SNAP)
      return { kind: "road", point: rd.point, id: "", building: "",
               doorIndex: -1, edge: rd.edge };
    return free;
  }

  /** 栅格吸附。边长按【米】设（gridM，默认 4），关掉就贴着鼠标走。 */
  grid(p) {
    const g = this.gridSnap === false ? 0 : Math.max(1, Math.round(this.gridM || 4));
    return g ? [Math.round(p[0] / g) * g, Math.round(p[1] / g) * g] : [...p];
  }

  // ── 环境物件 ────────────────────────────────────────────────────────
  addProp(name, xy) {
    this.props.push({ name, xy: [+xy[0].toFixed(2), +xy[1].toFixed(2)] });
    this._changed();
  }
  propNear(p, tol = 2.5) {
    return this.props.findIndex(q => Math.hypot(q.xy[0] - p[0], q.xy[1] - p[1]) < tol);
  }
  removePropNear(p, tol = 2.5) {
    const i = this.propNear(p, tol);
    if (i < 0) return "";
    const [g] = this.props.splice(i, 1);
    this._changed();
    return g.name;
  }

  // ── 改（只改数据，渲染是结果）──────────────────────────────────────
  /** 点一个点：有节点就复用，否则新建。返回节点 id。 */
  addNode(p, extra = {}) {
    for (const [nid, n] of Object.entries(this.nodes))
      if (Math.hypot(n.xy[0] - p[0], n.xy[1] - p[1]) < 0.4) return nid;
    const id = uid("n");
    this.nodes[id] = { xy: [+p[0].toFixed(3), +p[1].toFixed(3)], kind: "junction", ...extra };
    return id;
  }

  /** 把一条边从中间拆开：a—b → a—n + n—b。新节点成为那个路口。
   *  ★ 用户规则 3：起点落在既有路的中段时，那条路要变成【三条路四个节点】——
   *    拆出来的两条 + 新画的这条 = 三条边，a / n / b / 另一端 = 四个节点。 */
  splitEdgeAt(eid, nid) {
    const e = this.edges[eid];
    if (!e || nid === e.a || nid === e.b) return false;
    const { a, b } = e;
    const rest = { ...e };
    delete rest.a; delete rest.b; delete rest.geom;
    delete this.edges[eid];
    for (const [x, y] of [[a, nid], [nid, b]]) {
      this.edges[uid("e")] = { ...rest, a: x, b: y,
        geom: [this.nodes[x].xy.map(Number), this.nodes[y].xy.map(Number)] };
    }
    this._changed();
    return true;
  }

  /** ★ 吸附结果 → 节点 id。按需要【新建节点】或【拆边】。
   *  ★ 只在【提交时】调用 —— 手势过程中一律不碰数据，
   *    所以"没画成"就真的什么都没留下（用户规则 1：不该有孤儿节点）。 */
  resolve(s) {
    if (!s) return "";
    if (s.kind === "node") return s.id;
    const nid = this.addNode(s.point);
    if (s.kind === "road" && s.edge && nid !== s.edge) {
      const e = this.edges[s.edge];
      if (e && nid !== e.a && nid !== e.b) this.splitEdgeAt(s.edge, nid);
    }
    if (s.kind === "door" && s.building) {
      const n = this.nodes[nid];
      if (n) { n.door_of = s.building; n.door_index = s.doorIndex; }
    }
    return nid;
  }

  /** 连一条路：两端各自 resolve（可能建节点 / 拆边），然后连边。
   *  任何一端无效 → 什么都不做，返回 ""。 */
  connect(sa, sb, opts = {}) {
    if (!sa || !sb) return "";
    // ★ 先比点，再动数据。否则 resolve(sa) 已经建了节点，才发现两端是同一个点 ——
    //   地图上就留下一个孤儿节点（而且可能顺手把一条路拆了）。用户规则 1。
    const [ax, ay] = sa.point, [bx, by] = sb.point;
    if (Math.hypot(ax - bx, ay - by) < 0.5) return "";
    const a = this.resolve(sa), b = this.resolve(sb);
    if (!a || !b || a === b) return "";
    return this.addEdge(a, b, opts);
  }

  /** 离 p 最近、且在 tol 之内的节点 id（没有返回 ""）。 */
  nearestNodeWithin(p, tol) {
    let best = "", bd = tol;
    for (const [id, n] of Object.entries(this.nodes)) {
      const d = Math.hypot(n.xy[0] - p[0], n.xy[1] - p[1]);
      if (d < bd) { bd = d; best = id; }
    }
    return best;
  }

  /** ★ 房子贴好之后，把它的门【接进路网】：
   *  门上已经站着一颗节点 → 认领它（门即节点）；没有 → 新建一颗。
   *  不做这一步的话，"房子压在路边"只是画面上挨着，图上根本没连起来。 */
  attachDoorNodes(id) {
    const b = this.buildings[id];
    if (!b) return;
    for (const [i, w] of this.doorWorlds(b).entries()) {
      const owns = Object.entries(this.nodes)
        .find(([, n]) => n.door_of === id && n.door_index === i);
      if (owns) continue;
      const near = this.nearestNodeWithin(w.pos, 1.6);
      const nid = near || this.nodeAtDoor(id, i);
      const n = this.nodes[nid];
      if (n && !n.door_of) { n.door_of = id; n.door_index = i; }
    }
  }

  /** ★ ② 把建筑的第 i 个门变成路网节点（已有就复用）。节点带 door_of，跟着房子走。 */
  nodeAtDoor(bid, di) {
    for (const [nid, n] of Object.entries(this.nodes))
      if (n.door_of === bid && n.door_index === di) return nid;
    const b = this.buildings[bid];
    if (!b) return "";
    const ws = this.doorWorlds(b);
    if (di < 0 || di >= ws.length) return "";
    const id = uid("n");
    this.nodes[id] = { xy: [...ws[di].pos], kind: "junction", door_of: bid, door_index: di };
    return id;
  }

  /** 连一条边。两点重合 / 已经有边 → 返回 ""。 */
  addEdge(a, b, opts = {}) {
    if (!a || !b || a === b) return "";
    for (const e of Object.values(this.edges))
      if ((e.a === a && e.b === b) || (e.a === b && e.b === a)) return "";
    const id = uid("e");
    this.edges[id] = {
      a, b, class: opts.class || "local", width: opts.width || 4.0,
      speed: opts.speed || 1.3, oneway: false,
      geom: [this.nodes[a].xy.map(Number), this.nodes[b].xy.map(Number)],
    };
    this._changed();
    return id;
  }

  /** ★ ④ 摆建筑：必须先有路。没有 → 返回 ""，调用方去提示"先画条路"。 */
  addBuilding(typeId, p) {
    if (!Object.keys(this.edges).length) return "";
    const id = uid("bld");
    this.buildings[id] = {
      type: typeId, center: [+p[0].toFixed(3), +p[1].toFixed(3)],
      size: this.sizeFor(typeId), rot: 0, doors: [], floors: 1,
    };
    this.alignBuilding(id);
    this._changed();
    return id;
  }

  /** 拖动中的自由移动（不吸附）。松手后调 alignBuilding 归位。 */
  moveBuilding(id, p) {
    const b = this.buildings[id];
    if (!b) return;
    b.center = [+p[0].toFixed(3), +p[1].toFixed(3)];
    this._syncDoorNodes(id);
    this._changed();
  }

  /** 纯计算版：给一栋建筑算出"贴到路边"后的中心和朝向。不改数据。
   *  预览要用它 —— 否则幽灵框画在鼠标处，实际落点在别处，看着对、放下就错。 */
  computeAlign(b) {
    const rd = this.nearestRoad(b.center);
    if (!isFinite(rd.dist)) return null;
    const [cx, cy] = b.center, [qx, qy] = rd.point;
    // 从"路 → 房子"的方向：优先用实际偏离方向；偏离太小（正好压在路上）
    // 就用路的【法线】—— 这才保证是"推到路边"而不是"推到路的延长线上"。
    let dx = cx - qx, dy = cy - qy;
    if (Math.hypot(dx, dy) < 0.01) { dx = rd.normal[0]; dy = rd.normal[1]; }
    const d = Math.hypot(dx, dy) || 1;
    const t = this.types[b.type];
    const side = (t?.doors?.[0]?.side) || "south";
    const base = { south: 90, north: -90, east: 0, west: 180 }[side] ?? 90;
    const want = Math.atan2(-dy / d, -dx / d) * 180 / Math.PI;   // 门朝【路】，所以反向
    // ★ 退开的是【墙到路的距离】，所以还要加上半个【自身进深】。
    //   只退半个路宽的话，退的是"中心"—— 小房子整个压在路里，
    //   大房子更夸张（21.9m 的店会盖住路 10m）。用户："被吸附在中心而不是门口"。
    const side0 = (this.types[b.type]?.doors?.[0]?.side) || "south";
    const depth = (side0 === "north" || side0 === "south") ? b.size[1] : b.size[0];
    const back = (rd.width || 4) / 2 + depth / 2 + 0.3;
    return {
      center: [+(qx + dx / d * back).toFixed(3), +(qy + dy / d * back).toFixed(3)],
      rot: +(((want - base + 540) % 360) - 180).toFixed(1),
      road: rd,
    };
  }

  /** ★ ⑤ 贴边：主门朝最近的路 + 墙贴路沿。无路返回 false。 */
  alignBuilding(id) {
    const b = this.buildings[id];
    if (!b) return false;
    const a = this.computeAlign(b);
    if (!a) return false;
    b.center = a.center;
    b.rot = a.rot;
    this._syncDoorNodes(id);
    this.attachDoorNodes(id);       // 门接进路网
    this._changed();
    return true;
  }

  _alignBuildingOld(id) {
    const b = this.buildings[id];
    if (!b) return false;
    const rd = this.nearestRoad(b.center);
    if (!isFinite(rd.dist)) return false;
    const [cx, cy] = b.center, [qx, qy] = rd.point;
    // 从"路 → 房子"的方向：优先用实际的偏离方向；偏离太小（正好压在路上）
    // 就用路的【法线】—— 这才保证是"推到路边"而不是"推到路的延长线上"。
    let dx = cx - qx, dy = cy - qy;
    if (Math.hypot(dx, dy) < 0.01) { dx = rd.normal[0]; dy = rd.normal[1]; }
    const d = Math.hypot(dx, dy) || 1;
    // 门朝路：门的朝外法线 = 指向路的方向 → 反推 rot
    const t = this.types[b.type];
    const side = (t?.doors?.[0]?.side) || "south";
    const base = { south: 90, north: -90, east: 0, west: 180 }[side] ?? 90;
    const want = Math.atan2(-dy / d, -dx / d) * 180 / Math.PI;   // 门朝【路】，所以反向
    b.rot = +(((want - base + 540) % 360) - 180).toFixed(1);
    // 墙贴路沿：从路中心线沿法线退开半个路宽 + 一点余量
    const back = (rd.width || 4) / 2 + 0.6;
    b.center = [+(qx + dx / d * back).toFixed(3), +(qy + dy / d * back).toFixed(3)];
    this._syncDoorNodes(id);
    this._changed();
    return true;
  }

  /** 建筑的门移动了，挂在它身上的节点跟着走。 */
  _syncDoorNodes(id) {
    const b = this.buildings[id];
    if (!b) return;
    const ws = this.doorWorlds(b);
    for (const n of Object.values(this.nodes))
      if (n.door_of === id && n.door_index < ws.length) n.xy = [...ws[n.door_index].pos];
  }

  /** 同理：移动节点带着建筑走（拖门口 = 挪房子）。 */
  moveNode(nid, p) {
    const n = this.nodes[nid];
    if (!n) return;
    n.xy = [+p[0].toFixed(3), +p[1].toFixed(3)];
    if (n.door_of && this.buildings[n.door_of]) {
      const b = this.buildings[n.door_of];
      const ws = this.doorWorlds(b);
      const w = ws[n.door_index];
      if (w) {
        const dx = p[0] - w.pos[0], dy = p[1] - w.pos[1];
        b.center = [+(b.center[0] + dx).toFixed(3), +(b.center[1] + dy).toFixed(3)];
      }
    }
    for (const e of Object.values(this.edges))
      if (e.a === nid || e.b === nid) e.geom = this._poly(e, true);
    this._changed();
  }

  removeNode(nid) {
    delete this.nodes[nid];
    for (const [eid, e] of Object.entries(this.edges))
      if (e.a === nid || e.b === nid) delete this.edges[eid];
    this.pruneOrphans();
  }

  removeEdge(eid) { delete this.edges[eid]; this.pruneOrphans(); }

  /** 删建筑：挂在它门上的节点也一起走（不然留下一堆孤儿）。 */
  removeBuilding(bid) {
    delete this.buildings[bid];
    for (const [nid, n] of Object.entries(this.nodes))
      if (n.door_of === bid) delete this.nodes[nid];
    for (const [eid, e] of Object.entries(this.edges))
      if (!this.nodes[e.a] || !this.nodes[e.b]) delete this.edges[eid];
    this.pruneOrphans();
  }

  /** ★ ③ 没有边的节点不存在。 */
  pruneOrphans() {
    const used = new Set();
    for (const e of Object.values(this.edges)) { used.add(e.a); used.add(e.b); }
    let n = 0;
    for (const nid of Object.keys(this.nodes))
      // 挂着建筑门的节点先留着 —— 房子还在，门就不该消失
      if (!used.has(nid) && !this.nodes[nid].door_of) { delete this.nodes[nid]; n++; }
    this._changed();
    return n;
  }

  // ── 小工具 ──────────────────────────────────────────────────────────
  _poly(e, refresh = false) {
    if (refresh || !e.geom || e.geom.length < 2) {
      const a = this.nodes[e.a]?.xy, b = this.nodes[e.b]?.xy;
      e.geom = a && b ? [[...a], [...b]] : (e.geom || []);
    }
    return e.geom;
  }

  _closest(p, a, b) {
    const vx = b[0] - a[0], vy = b[1] - a[1];
    const len2 = vx * vx + vy * vy;
    const t = len2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / len2)) : 0;
    return [a[0] + vx * t, a[1] + vy * t];
  }

  stats() {
    return { nodes: Object.keys(this.nodes).length, edges: Object.keys(this.edges).length,
             buildings: Object.keys(this.buildings).length };
  }
}
