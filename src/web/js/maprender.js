/** maprender.js —— 把一份场景画成地图。
 *
 * ★ 游戏和编辑器【共用这一个】。编辑器和游戏看到的必须一模一样 ——
 *   否则"编辑器里看着对，进游戏不对"，而那种问题只有玩到才发现。
 *   编辑器只是在这之上多画了几个编辑手柄。
 *
 * 输入是一份【场景】({canvas, locations, map})，两边形状相同：
 *   游戏   ← 后端 hello 下发的 locations + map
 *   编辑器 ← MapDoc.toScene()（实时重算，所以所见即所存）
 */
import { Container, Graphics, Sprite, TilingSprite } from '../vendor/pixi.min.mjs';

export const U = 12;                       // 1 世界单位 = 12 px
const ROAD = 0x4c4a4a, ROAD_EDGE = 0x3a3838;
const NO_ART = 0x8c5b48, NO_ART_EDGE = 0x5a3a2e;

export class MapLayer {
  /** @param assets Assets2 实例 · @param onSign (loc, {x,y}) => void 给 DOM 标签用 */
  constructor(assets, onSign) {
    this.assets = assets;
    this.onSign = onSign;
    this.root = new Container();
    this.root.sortableChildren = true;
    this.ground = new Container();
    this.road = new Container();
    this.bld = new Container();
    this.bld.sortableChildren = true;
    for (const [i, c] of [this.ground, this.road, this.bld].entries()) {
      c.zIndex = i; this.root.addChild(c);
    }
    this._key = "";
    this.buildings = new Map();            // loc_id -> Sprite（编辑器要拿它做命中/选中）
  }

  /** 变了才重画。每帧重画 = 60Hz 建几千个对象。 */
  draw(scene) {
    const key = JSON.stringify([
      scene.canvas,
      Object.entries(scene.locations || {}).map(([k, v]) =>
        [k, v.x, v.y, v.w, v.h]).sort(),
      Object.keys(scene.map?.buildings || {}).sort(),
    ]);
    if (key === this._key) return false;
    this._key = key;
    this._ground(scene); this._roads(scene); this._buildings(scene);
    return true;
  }

  _tile(layer, file, x, y, w, h, color) {
    const t = this.assets.get(file);
    layer.addChild(t ? new TilingSprite({ texture: t, x, y, width: w, height: h })
                     : new Graphics().rect(x, y, w, h).fill(color));
  }

  _ground(scene) {
    this.ground.removeChildren();
    const { w, h } = scene.canvas || { w: 1280, h: 800 };
    this._tile(this.ground, "ground/grass.svg", 0, 0, w * U, h * U, 0x6d8a52);
  }

  /** 路是【图】：nodes/edges 是数据，路面是画出来的。 */
  _roads(scene) {
    this.road.removeChildren();
    const { nodes = {}, edges = {} } = scene.map || {};
    for (const e of Object.values(edges)) {
      const a = nodes[e.a]?.xy, b = nodes[e.b]?.xy;
      if (!a || !b) continue;
      const pts = (e.geom && e.geom.length >= 2) ? e.geom : [a, b];
      const w = (e.width || 4) * U;
      const g = new Graphics();
      g.moveTo(pts[0][0] * U, pts[0][1] * U);
      for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0] * U, pts[i][1] * U);
      g.stroke({ color: ROAD_EDGE, width: w + 3, cap: "round", join: "round" });
      g.stroke({ color: ROAD, width: w, cap: "round", join: "round" });
      this.road.addChild(g);
    }
  }

  /** 建筑：美术按【世界占地】缩放。占地是真值，美术是贴上去的。 */
  _buildings(scene) {
    this.bld.removeChildren();
    this.buildings.clear();
    const types = scene.map?.buildings || {};
    const map = this.assets.buildingTypes();
    for (const [lid, loc] of Object.entries(scene.locations || {})) {
      const x = loc.x * U, y = loc.y * U, w = loc.w * U, h = loc.h * U;
      if (loc.kind === "public" && !types[lid]) {        // 广场不是房子
        this._tile(this.bld, "ground/plaza.svg", x, y, w, h, 0xc9c2b1);
        this._sign(loc, x, y, h);
        continue;
      }
      const name = map[types[lid]?.type] || KIND_ART[loc.kind] || "home_a";
      const sh = this.assets.get(`bld/${name}_shadow.svg`);
      if (sh) {
        const s = new Sprite(sh);
        s.x = x - 3; s.y = y + 3; s.width = w + 6; s.height = h + 7;
        s.zIndex = 1; this.bld.addChild(s);
      }
      const t = this.assets.get(`bld/${name}.svg`);
      if (t) {
        const s = new Sprite(t);
        s.x = x; s.y = y; s.width = w; s.height = h; s.zIndex = 2;
        this.bld.addChild(s);
        this.buildings.set(lid, s);
      } else {
        this.bld.addChild(new Graphics().rect(x, y, w, h)
          .fill(NO_ART).stroke({ color: NO_ART_EDGE, width: 2 }));
      }
      this._sign(loc, x, y, h);
    }
  }

  _sign(loc, x, y, h) {
    if (!loc.name || !this.onSign) return;
    this.onSign(loc, { x: x / U, y: (y + h) / U + 0.8 });
  }
}

const KIND_ART = {
  home: "home_a", shop: "shop_a", market: "market", factory: "factory",
  clinic: "clinic", school: "school", work: "office", public: "plaza",
};
