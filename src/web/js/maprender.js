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
  constructor(assets, onSign) {
    this.assets = assets;
    this.onSign = onSign;
    this.root = new Container();
    this.root.sortableChildren = true;
    this.ground = new Container();
    this.road = new Container();
    this.deco = new Container();
    this.bld = new Container();
    this.bld.sortableChildren = true;
    for (const [i, c] of [this.ground, this.road, this.deco, this.bld].entries()) {
      c.zIndex = i; this.root.addChild(c);
    }
    this.buildings = new Map();            // loc_id -> {body, lit, shadow}
    this._groundKey = ""; this._roadKey = "";
  }

  // ── 一次画全（编辑器/游戏都用这个）────────────────────────────────
  draw(scene) {
    this._ground_(scene);
    this._roads_(scene);
    this._props_(scene);
    this._buildings_(scene);
  }

  // 地面：整块画布铺一张草地；地点是 public 的铺广场砖
  _ground_(scene) {
    const c = scene.canvas || { w: 1280, h: 800 };
    const key = `${c.w}x${c.h}`;
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
  _fillets(nodes, segs, half) {
    const inc = new Map();
    const add = (nid, d) => {
      const L = Math.hypot(d[0], d[1]);
      if (L < 1e-6 || !nodes[nid]) return;
      if (!inc.has(nid)) inc.set(nid, []);
      inc.get(nid).push([d[0] / L, d[1] / L]);
    };
    for (const s of segs) {
      const d = [s.b[0] - s.a[0], s.b[1] - s.a[1]];
      if (s.na) add(s.na, d);
      if (s.nb) add(s.nb, [-d[0], -d[1]]);
    }
    const r = half * FILLET;
    const reach = half + r;
    const out = [];
    for (const [nid, list] of inc) {
      if (list.length < 2) continue;                 // 尽头：没有缺口
      const pos = nodes[nid].xy;
      const sorted = [...list].sort((a, b) => Math.atan2(a[1], a[0]) - Math.atan2(b[1], b[0]));
      for (let i = 0; i < sorted.length; i++) {
        const d0 = sorted[i], d1 = sorted[(i + 1) % sorted.length];
        let phi = Math.atan2(d1[1], d1[0]) - Math.atan2(d0[1], d0[0]);
        while (phi <= 0) phi += Math.PI * 2;
        if (phi < 0.15 || phi > Math.PI - 0.05) continue;   // 近平行 / 直行
        const hp = phi / 2;
        const cot = 1 / Math.tan(hp);
        const tang = reach * cot;
        const ca = Math.cos(hp), sa = Math.sin(hp);
        const cc = [pos[0] + (d0[0] * ca - d0[1] * sa) * reach / Math.sin(hp),
                    pos[1] + (d0[0] * sa + d0[1] * ca) * reach / Math.sin(hp)];
        const t1 = [pos[0] + d0[0] * tang - d0[1] * half,
                    pos[1] + d0[1] * tang + d0[0] * half];
        const t2 = [pos[0] + d1[0] * tang + d1[1] * half,
                    pos[1] + d1[1] * tang - d1[0] * half];
        const a0 = Math.atan2(t1[1] - cc[1], t1[0] - cc[0]);
        const sweep = -(Math.PI - phi);
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

  /** ★ 道路：每个宽度一组 = 一条路径 + 顶点圆盘 + 路口倒角。
   *
   *  两层各司其职：
   *    一条路径 + 圆帽/圆接头   外角（凸角）自然就是圆的，接缝也不会发白
   *    路口【倒角】多边形        填相邻两条路之间的缺口 —— 这才是"倒圆角"的本体
   *
   *  ★ 没有顶点圆盘。
   *    Godot 版有（draw_road 在每个顶点补一个半径=半宽的实心圆），那是为了
   *    补 draw_line 逐段画留下的接缝。Pixi 这边一条路径 + join:"round" 本来
   *    就接得上，再补圆盘就是【多余的一个圆】—— 用户一眼就看出来了：
   *    "还是圆盘"。
   */
  _roads_(scene) {
    const segs = this._segs(scene);
    const key = JSON.stringify(segs);
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
    const asphalt = this.assets.get("ground/asphalt.svg");
    const sidewalk = this.assets.get("ground/sidewalk.svg");
    const WALK = SIDEWALK * 2;

    // 每层画一遍：人行道（宽一圈）→ 路面
    for (const [layer, grow] of [["walk", WALK], ["road", 0]]) {
      for (const [w, list] of byW) {
        const width = w + grow;
        const halfW = width / U / 2;                    // 世界单位
        const tex = layer === "walk" ? sidewalk : asphalt;
        const g = new Graphics();
        for (const s of list)
          g.moveTo(s.a[0] * U, s.a[1] * U).lineTo(s.b[0] * U, s.b[1] * U);
        g.stroke({ width, cap: "round", join: "round",
                   color: layer === "walk" ? 0xb8b3a6 : 0x4c4a4a,
                   ...(tex ? { texture: tex, matrix: M } : {}) });
        this.road.addChild(g);
        // 倒角：填在路段之后，同色叠加
        const fil = new Graphics();
        for (const poly of this._fillets(nodes, list, halfW)) fil.poly(poly);
        fil.fill({ color: layer === "walk" ? 0xb8b3a6 : 0x4c4a4a,
                   ...(tex ? { texture: tex, matrix: M } : {}) });
        this.road.addChild(fil);
      }
    }
    this._dashes(segs);
  }

  /** 中线虚线：只给够宽的路画（窄弄堂摆一条只是噪声），两头留出路口。 */
  _dashes(segs) {
    const tex = this.assets.get("road/marking_dash_h.svg");
    if (!tex) return;
    for (const s of segs) {
      if (s.w < 6 * U) continue;
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
      e.box.position.set(x, y);
      e.box.zIndex = Math.round(loc.y + loc.h);
      this.onSign?.(lid, loc, { x, y: y + h });
    }
    for (const [lid, e] of [...this.buildings])
      if (!seen.has(lid)) { e.box.destroy({ children: true }); this.buildings.delete(lid); }
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

const KIND_ART = {
  home: "home_a", shop: "shop_a", market: "market", factory: "factory",
  clinic: "clinic", school: "school", work: "office", public: "plaza",
};
