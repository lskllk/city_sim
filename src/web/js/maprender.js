/** maprender.js —— 把一份场景画成地图。**游戏和编辑器共用这一个。**
 *
 * 全部用 art/ 里的资产，不画色块：
 *   地面  ground/{grass,dirt,plaza,water}.svg        32×32 可平铺
 *   道路  road/{asphalt,sidewalk,marking_dash_h/v,crosswalk}.svg
 *   建筑  bld/{name}.svg + _shadow + _lit            ★ 按世界占地缩放
 *   杂物  props/{tree_*,bush_*,bench,lamp,bin,flowerbed,car_*}
 *
 * ★ 道路为什么用「旋转容器 + 铺图块」：
 *   路是任意角度的线段。先在【局部坐标】(长 × 宽) 里把沥青铺满、人行道贴两边、
 *   中线打虚线，然后整个容器转一个角度 —— 任何方向都是同一段代码。
 *   （没有 autotile 集，所以是"硬边"的，这一条记在 asset-list A3 缺口里。）
 *
 * ★ 增量重画：拖一栋房子不该重建整个世界。地面/路只在数据变了才重建，
 *   建筑按 loc_id 复用精灵，拖动时只改 transform。
 */
import { Container, Graphics, Matrix, Sprite, TilingSprite } from '../vendor/pixi.min.mjs';

export const U = 12;                       // 1 世界单位 = 12 px
const TILE = 32;                           // 资产网格
const SCALE = 2;                           // 资产是 2× 画的（authorScale）
const FILLET = 0.5;                        // 倒角半径 = 半路宽 × 这个系数（同 Godot 版）
const SIDEWALK = 6;                        // 人行道宽（asset: 32×6）

export class MapLayer {
  constructor(assets) {
    this.assets = assets;
    this.root = new Container();
    this.root.sortableChildren = true;
    this.ground = new Container();
    this.area = new Container();
    this.road = new Container();
    this.deco = new Container();
    this.bld = new Container();
    this.bld.sortableChildren = true;
    for (const [i, c] of [this.ground, this.area, this.road, this.deco, this.bld].entries()) {
      c.zIndex = i; this.root.addChild(c);
    }
    this.buildings = new Map();            // loc_id -> {body, lit, shadow}
    this._groundKey = ""; this._roadKey = "";
  }

  // ── 一次画全（编辑器/游戏都用这个）────────────────────────────────
  draw(scene) {
    this._ground_(scene);
    this._areas_(scene);
    this._roads_(scene);
    this._props_(scene);
    this._buildings_(scene);
  }

  // 地面：整块画布铺一张草地；地点是 public 的铺广场砖
  _ground_(scene) {
    const c = scene.canvas || { w: 1280, h: 800 };
    const key = `${c.w}x${c.h}|v${this.assets.version || 0}`;
    if (key === this._groundKey) return;
    this._groundKey = key;
    this.ground.removeChildren();
    this._tile(this.ground, "ground/grass.svg", 0, 0, c.w * U, c.h * U, 0x6d8a52);
  }

  /** 把场景里的 edges 拆成"线段"列表（支持 geom 折线）。
   *  带上两端的【节点 id】—— 路口要在节点位置画圆盘。 */
  _segs(scene) {
    const { nodes = {}, edges = {} } = scene.map || {};
    const out = [];
    for (const e of Object.values(edges)) {
      const pts = (e.geom && e.geom.length >= 2) ? e.geom
                : [nodes[e.a]?.xy, nodes[e.b]?.xy];
      if (!pts?.[0] || !pts[1]) continue;
      const w = Math.round((e.width || 4) * U);
      for (let i = 1; i < pts.length; i++)
        out.push({ a: pts[i - 1], b: pts[i], w,
                   na: i === 1 ? e.a : "", nb: i === pts.length - 1 ? e.b : "" });
    }
    return out;
  }

  /** ★ 路口【倒圆角】—— 每个节点，相邻两条入射路之间的缺口填一段切线圆弧。
   *
   *  算法照归档的 Godot 版（shared/building_style.gd: build_junctions）：
   *    r    = half × FILLET
   *    cc   = pos + rot(d0, φ/2) × (half+r)/sin(φ/2)      ← 圆心
   *    t1   = pos + d0×tang + rot(d0, +90°)×half           ← 切点
   *    t2   = pos + d1×tang + rot(d1, −90°)×half
   *    多边形 = [节点, t1, …弧…, t2]
   *
   *  ★ 这不是"在节点上放个圆盘"。圆盘补不了缺口 —— 缺口要的是【与两条边都相切】的弧。
   *    90° 时：t1=(1.5h, h) · t2=(h, 1.5h) · 圆心=(1.5h, 1.5h)，
   *    |cc−t1| = 0.5h = r ✓ 相切。圆盘做不到这一点。
   *
   *  近直行（φ≈π）和近同向（φ≈0）跳过 —— 那两种情况本来就没有缺口。
   */
  /** 路口倒角块 —— 相邻两条入射路之间填一段【与两条边都相切】的圆弧。
   *
   *  ★ 大路接小路：每条边用【自己的半宽】，不能统一取最宽的。
   *    统一取最宽的话，小路那侧的切点对不上，接缝就是个台阶
   *    （用户："大路和小路的融合问题"）。
   *
   *  切线圆与两条偏移线都相切 →
   *      C·u0 = P·u0 + h0 + r
   *      C·u1 = P·u1 + h1 + r        u = 指向缺口那一侧的法线
   *  解两元一次方程组得圆心 C，切点 T = C − r·u。
   *  h0 = h1 时它自动退化成"半宽 + 半径"那个简单式。
   *
   *  r = FILLET × max(h0, h1)：倒角的"分量"跟着那条大路走。
   */
  _fillets(nodes, segs, grow) {
    const inc = new Map();
    const add = (nid, d, half) => {
      const L = Math.hypot(d[0], d[1]);
      if (L < 1e-6 || !nodes[nid]) return;
      if (!inc.has(nid)) inc.set(nid, []);
      inc.get(nid).push({ dir: [d[0] / L, d[1] / L], half });
    };
    for (const s of segs) {
      const d = [s.b[0] - s.a[0], s.b[1] - s.a[1]];
      const half = (s.w + grow) / U / 2;      // ★ 单位统一：都先化成米
      if (s.na) add(s.na, d, half);
      if (s.nb) add(s.nb, [-d[0], -d[1]], half);
    }
    const rot90 = (v, sign) => [sign * -v[1], sign * v[0]];   // 屏幕 y 向下
    const out = [];
    for (const [nid, list] of inc) {
      if (list.length < 2) continue;                            // 尽头没有缺口
      const pos = nodes[nid].xy;
      // 按角度排序：只有相邻两个方向之间才构成缺口
      const dirs = list.slice().sort((a, b) =>
        Math.atan2(a.dir[1], a.dir[0]) - Math.atan2(b.dir[1], b.dir[0]));
      for (let i = 0; i < dirs.length; i++) {
        const A = dirs[i], B = dirs[(i + 1) % dirs.length];
        const d0 = A.dir, d1 = B.dir, h0 = A.half, h1 = B.half;
        let phi = Math.atan2(d1[1], d1[0]) - Math.atan2(d0[1], d0[0]);
        while (phi <= 0) phi += Math.PI * 2;
        if (phi < 0.15 || phi > Math.PI - 0.05) continue;        // 近平行 / 直行
        // 指向缺口那一侧的法线：d0 的法线里，和 d1 同向的那条
        const n0a = rot90(d0, +1), n0b = rot90(d0, -1);
        const u0 = (n0a[0] * d1[0] + n0a[1] * d1[1]) > 0 ? n0a : n0b;
        const n1a = rot90(d1, +1), n1b = rot90(d1, -1);
        const u1 = (n1a[0] * d0[0] + n1a[1] * d0[1]) > 0 ? n1a : n1b;

        const r = FILLET * Math.max(h0, h1);
        // 解 C：u0·C = u0·P + h0 + r 且 u1·C = u1·P + h1 + r
        const b0 = u0[0] * pos[0] + u0[1] * pos[1] + h0 + r;
        const b1 = u1[0] * pos[0] + u1[1] * pos[1] + h1 + r;
        const det = u0[0] * u1[1] - u0[1] * u1[0];
        if (Math.abs(det) < 1e-6) continue;                      // 两法线平行，没缺口
        const cc = [(b0 * u1[1] - u0[1] * b1) / det,
                    (u0[0] * b1 - b0 * u1[0]) / det];
        const t1 = [cc[0] - r * u0[0], cc[1] - r * u0[1]];
        const t2 = [cc[0] - r * u1[0], cc[1] - r * u1[1]];

        // 弧从 t1 到 t2，走短的那边
        let a0 = Math.atan2(t1[1] - cc[1], t1[0] - cc[0]);
        let a1 = Math.atan2(t2[1] - cc[1], t2[0] - cc[0]);
        let sweep = a1 - a0;
        while (sweep > Math.PI) sweep -= Math.PI * 2;
        while (sweep < -Math.PI) sweep += Math.PI * 2;
        const steps = Math.max(2, Math.ceil(Math.abs(sweep) / 0.18));
        const poly = [pos[0] * U, pos[1] * U, t1[0] * U, t1[1] * U];
        for (let k = 1; k < steps; k++) {
          const th = a0 + sweep * k / steps;
          poly.push((cc[0] + Math.cos(th) * r) * U, (cc[1] + Math.sin(th) * r) * U);
        }
        poly.push(t2[0] * U, t2[1] * U);
        out.push(poly);
      }
    }
    return out;
  }

  /** ★ 道路分三层画：路段 / 节点圆盘 / 路口倒角。
   *
   *  ⚠ 端头【不能】用 cap:"round"：大路接小路时，大路的端帽半径是它自己的
   *    半宽（4 米），而小路半宽只有 1.5 米 —— 那个半圆直接拱到小路外面，
   *    路口多出一个"圆圆的屁股"（用户报的）。
   *
   *  改成：路段 butt 头（不拱），另在【每个节点】补一个圆盘，
   *  半径取该节点上【最窄】那条路的半宽：
   *    · L 形同宽      盘半径 = h        → 外角仍然是圆的
   *    · 大路接小路    盘半径 = 小路半宽  → 大路那侧不拱出去
   *    · 尽头（度数 1）盘半径 = 自己半宽  → 圆头照旧
   *
   *  一条路径而不是一段一张图：逐段各画会在接缝上叠两层抗锯齿，出现白线。
   *  贴图要走 texture + matrix，注意 Pixi 会【把贴图乘上 color】——
   *  用贴图时 color 给白，否则颜色被平方（0x4c×0x4c = #171515，路变近黑）。
   */
  /** 地面区域：nodes 围成的闭合多边形，铺对应的地面贴图。
   *  ★ 美术里现在只有 grass/dirt/plaza/water 四种地面 ——
   *    农田/水泥/地砖是【缺口】，这里先用最接近的贴图 + 色调区分。 */
  _areas_(scene) {
    const list = scene.map?.areas || [];
    const key = JSON.stringify(list.map(a => [a.kind, a.nodes]))
      + "|" + list.map(a => a.nodes.map(id => scene.map.nodes[id]?.xy || 0).join()).join()
      + "|v" + (this.assets.version || 0);
    if (key === this._areaKey) return;
    this._areaKey = key;
    this.area.removeChildren();
    const M = new Matrix().scale(1 / SCALE);
    for (const a of list) {
      const poly = (a.nodes || []).map(id => scene.map.nodes[id]?.xy).filter(Boolean);
      if (poly.length < 3) continue;
      const spec = AREA_KIND[a.kind] || AREA_KIND.concrete;
      // ★ 半透明【磨砂覆盖】，不是把地面换掉 —— 底下的草地要透得出来。
      //   纹理打底（弱） + 一层提亮（磨砂感），最后描边分界。
      const tex = this.assets.get(spec.file);
      const pts = poly.flatMap(([x, y]) => [x * U, y * U]);
      const g = new Graphics();
      g.poly(pts);
      g.fill({ color: spec.tint, alpha: 0.5, ...(tex ? { texture: tex, matrix: M } : {}) });
      g.poly(pts);
      g.fill({ color: 0xffffff, alpha: 0.10 });          // 磨砂的"雾面"
      g.poly(pts);
      g.stroke({ color: 0xffffff, width: 2, alpha: 0.5 });// 内描边
      g.poly(pts);
      g.stroke({ color: 0x000000, width: 1, alpha: 0.2 }); // 外描边（分界清楚）
      this.area.addChild(g);
    }
  }

  _roads_(scene) {
    const segs = this._segs(scene);
    const key = JSON.stringify(segs) + "|v" + (this.assets.version || 0);
    if (key === this._roadKey) return;
    this._roadKey = key;
    this.road.removeChildren();
    if (!segs.length) return;

    const { nodes = {} } = scene.map || {};
    const byW = new Map();
    for (const s of segs) {
      if (!byW.has(s.w)) byW.set(s.w, []);
      byW.get(s.w).push(s);
    }
    const M = new Matrix().scale(1 / SCALE);
    const asphalt = this.assets.get("road/asphalt.svg");
    const sidewalk = this.assets.get("road/sidewalk.svg");
    const WALK = SIDEWALK * 2;

    for (const layer of ["walk", "road"]) {
      const grow = layer === "walk" ? WALK : 0;
      const tex = layer === "walk" ? sidewalk : asphalt;
      const paint = { color: tex ? 0xffffff : (layer === "walk" ? 0xb8b3a6 : 0x4c4a4a),
                      ...(tex ? { texture: tex, matrix: M } : {}) };

      // ① 路段：butt 头（不拱），折线内部节点仍是圆接头
      for (const [w, list] of byW) {
        const g = new Graphics();
        for (const s of list)
          g.moveTo(s.a[0] * U, s.a[1] * U).lineTo(s.b[0] * U, s.b[1] * U);
        g.stroke({ width: w + grow, cap: "butt", join: "round", ...paint });
        this.road.addChild(g);
      }

      // ② 节点圆盘：半径 = 该节点上【最窄】那条路的半宽
      const narrow = new Map();
      for (const s of segs) {
        const half = (s.w + grow) / U / 2;
        for (const nid of [s.na, s.nb]) {
          if (!nid || !nodes[nid]) continue;
          const cur = narrow.get(nid);
          if (cur === undefined || half < cur) narrow.set(nid, half);
        }
      }
      const disc = new Graphics();
      for (const [nid, half] of narrow) {
        const xy = nodes[nid].xy;
        disc.circle(xy[0] * U, xy[1] * U, half * U);
      }
      disc.fill(paint);
      this.road.addChild(disc);

      // ③ 路口倒角：填相邻两条路之间的缺口（每条边用【自己的半宽】）
      const fil = new Graphics();
      for (const poly of this._fillets(nodes, segs, grow)) fil.poly(poly);
      fil.fill(paint);
      this.road.addChild(fil);
    }
    this._dashes(segs);
  }

  /** 中线虚线 —— 这是美术"道路风格"的一部分（road/marking_dash_h），
   *  不是噪声。两头留出路口，免得糊成一团。
   *  （我一度以为用户说的"不知道干嘛的虚线"是它，把它删了 —— 错。
   *   那句话说的是 4 米栅格：整图视角下只有 7 屏幕像素，一片噪声。） */
  _dashes(segs) {
    const tex = this.assets.get("road/marking_dash_h.svg");
    if (!tex) return;
    for (const s of segs) {
      const dx = (s.b[0] - s.a[0]) * U, dy = (s.b[1] - s.a[1]) * U;
      const len = Math.hypot(dx, dy), ang = Math.atan2(dy, dx);
      const x0 = s.a[0] * U, y0 = s.a[1] * U;
      const skip = s.w / 2 + 6;
      if (len - skip * 2 < 18) continue;
      for (let d = skip; d + 30 <= len - skip; d += 44) {
        const sp = new Sprite(tex);
        sp.anchor.set(0.5); sp.width = 30; sp.height = 2; sp.rotation = ang;
        sp.position.set(x0 + Math.cos(ang) * (d + 15), y0 + Math.sin(ang) * (d + 15));
        sp.alpha = 0.55;
        this.road.addChild(sp);
      }
    }
  }

  /** 杂物。场景里现在没有 props 段 —— 有就画（编辑器以后能摆）。 */
  _props_(scene) {
    const list = scene.map?.props || [];
    const key = JSON.stringify(list);
    if (key === this._propsKey) return;
    this._propsKey = key;
    this.deco.removeChildren();
    const SIZE = { tree_s: [20, 24], tree_m: [27, 31], tree_l: [34, 38],
                   bush_1: [15, 16], bush_2: [18, 19], bench: [26, 12],
                   lamp: [10, 30], bin: [11, 13], flowerbed: [24, 14] };
    for (const p of list) {
      const nm = p.name || p.type;
      const [w, h] = SIZE[nm] || p.size || [20, 20];
      const t = this.assets.get(`props/${nm}.svg`);
      const s = new Sprite(t || undefined);
      s.anchor.set(0.5, 1);                       // 锚点在脚底：立在地上
      s.position.set(p.xy[0] * U, p.xy[1] * U);
      s.width = w; s.height = h;
      s.zIndex = Math.round(p.xy[1]);
      this.deco.addChild(s);
    }
  }

  /** 需要按 y【深度排序】的东西都加到这里：建筑、人、物件。
   *
   *  ★ 必须放同一个容器 —— Pixi 的 zIndex 只在同一个父容器里比。
   *    分开三个容器的话，"人在房子北边"永远画在房子上面，看着像浮在空中；
   *    实际是两个容器在比最外层 zIndex，不是真的按深度排。
   *  本层里的排序键：建筑 = 下边缘 y，人和物件 = 脚底 / 中心 y。
   */
  get depthLayer() { return this.bld; }

  /** 建筑：按 loc_id 复用精灵，拖动时只改 transform。 */
  _buildings_(scene) {
    const types = scene.map?.buildings || {};
    const map = this.assets.buildingTypes();
    const seen = new Set();
    for (const [lid, loc] of Object.entries(scene.locations || {})) {
      seen.add(lid);
      const x = loc.x * U, y = loc.y * U, w = loc.w * U, h = loc.h * U;
      const isPlaza = loc.kind === "public" && !types[lid];
      const name = isPlaza ? null : (map[types[lid]?.type] || KIND_ART[loc.kind] || "home_a");
      let e = this.buildings.get(lid);
      if (!e) {
        e = { box: new Container(), body: null, lit: null, shadow: null, key: "" };
        this.bld.addChild(e.box);
        this.buildings.set(lid, e);
      }
      // 外观变了才重建精灵（换类型 / 广场 ↔ 房子）
      const key = (isPlaza ? "plaza" : name) + `:${Math.round(w)}x${Math.round(h)}`;
      if (e.key !== key) {
        e.key = key;
        e.box.removeChildren();
        if (isPlaza) {
          const g = new Container();
          this._tile(g, "ground/plaza.svg", 0, 0, w, h, 0xc9c2b1);
          e.box.addChild(g);
          e.body = e.lit = e.shadow = null;
        } else {
          const st = this.assets.get(`bld/${name}_shadow.svg`);
          if (st) {
            e.shadow = new Sprite(st); e.shadow.position.set(-3, 3);
            e.shadow.width = w + 6; e.shadow.height = h + 7;
            e.shadow.zIndex = 0; e.box.addChild(e.shadow);
          }
          const bt = this.assets.get(`bld/${name}.svg`);
          if (bt) {
            e.body = new Sprite(bt); e.body.width = w; e.body.height = h;
            e.body.zIndex = 1; e.box.addChild(e.body);
          } else {
            e.body = new Graphics().rect(0, 0, w, h)
              .fill(0x8c5b48).stroke({ color: 0x5a3a2e, width: 2 });
            e.body.zIndex = 1; e.box.addChild(e.body);
          }
          const lt = this.assets.get(`bld/${name}_lit.svg`);
          e.lit = lt ? new Sprite(lt) : null;
          if (e.lit) {
            e.lit.width = w; e.lit.height = h; e.lit.zIndex = 2;
            e.lit.alpha = 0; e.box.addChild(e.lit);
          }
        }
      }
      // ★ 建筑要能转。rot 来自左边的编辑器地图（scene.map.buildings[lid].rot）——
      //   编辑器和游戏共用这一段，所以两边转得一样。
      //   pivot 放在【中心】：box 里的小精灵是按左上角摆的，
      //   不给 pivot 就得绕左上角转，房子会飞出去。
      const rot = (types[lid]?.rot || 0) * Math.PI / 180;
      e.box.pivot.set(w / 2, h / 2);
      e.box.position.set(x + w / 2, y + h / 2);
      e.box.rotation = rot;
      e.box.zIndex = Math.round(loc.y + loc.h);
      // ★ 地图上【默认不显示建筑名称】（用户要的）。
      //   名字只在"我正指着这栋"时出现 —— 见 editor 的 hoverLoc 高亮。
      //   理由：地图是彩色的、有质感的；名字一多就变成一张表格。
      //   （游戏那边要名字的话，同样是"看/选中才给"，不是默认铺满）
    }
    // ★ 拆掉的建筑，名牌也要撤 —— 否则地图上留一个没有房子的名字。
    for (const [lid, e] of [...this.buildings]) {
      if (seen.has(lid)) continue;
      e.box.destroy({ children: true });
      this.buildings.delete(lid);
    }
  }

  /** 夜里点亮窗户（时间色调由调用方给，见 atmosphere） */
  setNight(windowAlpha) {
    for (const e of this.buildings.values())
      if (e.lit) e.lit.alpha = windowAlpha;
  }

  _tile(parent, file, x, y, w, h, color) {
    const t = this.assets.get(file);
    if (t) { parent.addChild(new TilingSprite({ texture: t, x, y, width: w, height: h })); return; }
    parent.addChild(new Graphics().rect(x, y, w, h).fill(color));
  }
}

// 地面区域的用途 → 贴图 + 色调。★ 农田/水泥/地砖的专用贴图是美术缺口，
//   现在借用 dirt / plaza，用色调拉开（见 docs/asset-list.md 的 A 类）。
const AREA_KIND = {
  farm:     { file: "ground/dirt.svg",  tint: 0xffffff, label: "农田" },
  concrete: { file: "ground/plaza.svg", tint: 0xd8d8d2, label: "水泥地" },
  tile:     { file: "ground/plaza.svg", tint: 0xffffff, label: "地砖" },
};

const KIND_ART = {
  home: "home_a", shop: "shop_a", market: "market", factory: "factory",
  clinic: "clinic", school: "school", work: "office", public: "plaza",
};
