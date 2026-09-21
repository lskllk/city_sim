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
import { Container, Graphics, Sprite, TilingSprite } from '../vendor/pixi.min.mjs';

export const U = 12;                       // 1 世界单位 = 12 px
const TILE = 32;                           // 资产网格
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

  /** 一段路 = 旋转容器里铺图块。返回容器。 */
  _segment(a, b, width) {
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]) * U;
    const w = width * U;
    const box = new Container();
    box.position.set(a[0] * U, a[1] * U);
    box.rotation = Math.atan2(b[1] - a[1], b[0] - a[0]);
    // 沥青
    this._tile(box, "road/asphalt.svg", 0, -w / 2, len, w, 0x4c4a4a);
    // 人行道贴两条长边（图块是 32×6 的横条，竖边用同一张即可 —— 它是可平铺的）
    this._tile(box, "road/sidewalk.svg", 0, -w / 2 - SIDEWALK, len, SIDEWALK, 0xb8b3a6);
    this._tile(box, "road/sidewalk.svg", 0, w / 2, len, SIDEWALK, 0xb8b3a6);
    // 中线虚线：asset 有横向/纵向两种，按角度取
    const horiz = Math.abs(Math.cos(box.rotation)) > 0.7;
    const dash = horiz ? "road/marking_dash_h.svg" : "road/marking_dash_v.svg";
    if (horiz) this._tile(box, dash, 0, -1, len, 2, 0xe9e5da);
    else this._tile(box, dash, -1, -len / 2, 2, len, 0xe9e5da);
    return box;
  }

  _roads_(scene) {
    const { nodes = {}, edges = {} } = scene.map || {};
    // 只在地图数据变了才重建；拖房子不动路
    const key = Object.entries(edges)
      .map(([id, e]) => `${id}:${e.a}-${e.b}:${e.width}`).join("|")
      + "#" + Object.entries(nodes).map(([id, n]) => `${id}:${n.xy}`).join("|");
    if (key === this._roadKey) return;
    this._roadKey = key;
    this.road.removeChildren();
    for (const e of Object.values(edges)) {
      const a = nodes[e.a]?.xy, b = nodes[e.b]?.xy;
      if (!a || !b) continue;
      const pts = (e.geom && e.geom.length >= 2) ? e.geom : [a, b];
      for (let i = 1; i < pts.length; i++)
        this.road.addChild(this._segment(pts[i - 1], pts[i], e.width || 4));
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
