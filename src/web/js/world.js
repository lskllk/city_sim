/** world.js —— 游戏里的世界。相机/输入/纸片/地图都在别处，这里只加「人」和「物件」。
 *
 *   View      相机 + 拖动缩放 + 屏幕纸片      （view.js，和编辑器共用）
 *   MapLayer  地图：地面/路/建筑             （maprender.js，和编辑器共用）
 *   Motion    【前端假模拟】：人怎么走        （motion.js，只有游戏要）
 *   本文件    人 + 物件 + 气泡 + 点人
 *
 * ★ 人的位置【不直接读后端的 position】—— 那只是"逻辑落脚点"。
 *   真正的连续位置是 motion 按目标走出来的（见 motion.js 的说明）。
 */
import { Container, Graphics, Sprite } from '../vendor/pixi.min.mjs';
import { View, U } from './view.js';
import { MapLayer } from './maprender.js';
import { Motion, artSize } from './motion.js';

/** 高亮色。★ 是【乘】在贴图上的（Pixi 的规矩），所以只能往暖/亮里挑 ——
 *  挑深色会把图压黑。悬停淡一档、选中浓一档。 */
const HILITE = 0xfff0c0;          // 悬停：淡淡一层暖
const HILITE_STRONG = 0xffc86a;   // 选中：明显的琥珀

export class World {
  constructor(canvasEl, store, hudEl, assets) {
    this.store = store;
    this.assets = assets;
    this.view = new View(canvasEl, hudEl);
    this.map = new MapLayer(assets);
    // 物件和人【没有自己的容器】—— 它们直接进 map.depthLayer，
    // 和建筑同一个父容器按 y 排深度（Pixi 的 zIndex 只在一个父容器里比）。
    this.depth = null;
    this.motion = new Motion();
    this._things = new Map();              // entity_id → Sprite
    this._people = new Map();
    // ★ 游戏里【不用圈】：指着谁、选中谁，一律靠高亮。
    //   人和物件改 tint（见 _people_ / _things_）；建筑没法 tint（贴图是
    //   屋顶+墙一整块，染色会把整栋楼染黄），就在它占地范围盖一层半透明暖色
    //   —— 和编辑器"鼠标划过一栋楼"完全同一个做法（那边也是盖一层多边形）。
    //   为什么不用圈：圈会盖住东西本身，而且"指着"和"选中"两种圈很难一眼分开。
    this.hilite = new Container();
    this._hoverAt = null;
    this._hoverHit = "";
    this.onSelect = null;
  }

  async init() {
    await this.view.init();
    this.map.root.zIndex = 0;
    this.hilite.zIndex = 3;                      // 高亮在最上面（但不管点击）
    this.view.worldLayer.addChild(this.map.root, this.hilite);
    // ★ 人和物件【直接加进建筑的深度层】，不另开容器 ——
    //   这样"人走到房子北边"会被房子挡住（真按 y 排深度）。
    //   以前人和物件各在一个容器里，外层 zIndex 一高就永远压住所有房子，
    //   看着像浮在空中（用户："建筑 物件 人会有重叠"）。
    this.depth = this.map.depthLayer;
    this.view.onView = () => this.view.syncPaper();
    // 点人；拖是平移（onDown 不接 → 相机默认接管）
    this.view.onPick = (x, y) => this.onSelect?.(this.pick(x, y), [x, y]);
    // ★ 悬停也要有反馈 —— 规矩是"光标指着什么，什么就亮"。
    //   游戏里以前只有选中才有 tint，鼠标划过什么都没有。
    this.view.onHover = (x, y) => { this._hoverAt = [x, y]; };
    this.view.onContext = () => this.onSelect?.("", [0, 0]);   // 右键 = 取消选中
    return this;
  }

  /** 场景形状和编辑器导出的一样：{canvas, locations, map} */
  scene() {
    return { canvas: this.store.canvas, locations: this.store.locations, map: this.store.map };
  }

  /** 点到谁了。
   *
   *  ★ 判定是【鼠标在不在它的范围里】，不是"离得多近"。
   *    距离阈值那套（`26/k` 米）的毛病：缩远了阈值涨到几百米，
   *    指哪都算指着东西；缩近了又极难点中；而且圆和"看起来那个形状"
   *    根本对不上（人是瘦高条、机器是扁方块、房子是能转的矩形）。
   *    矩形包含就是所见即所得：鼠标压到谁身上，才算谁。
   *
   *  ★ 多个都包含时取【最小的那个】：房子的框包含屋里的人和家具，
   *    但你伸手要点的是人/柜子，不是这栋楼。面积最小 = 最具体。
   *    面积一样时取画得靠上的（zIndex 大 = 更靠前）。
   */
  pick(wx, wy) {
    let best = "", bestArea = Infinity, bestZ = -Infinity;
    const take = (id, x0, y0, x1, y1, z = 0) => {
      if (wx < x0 || wx > x1 || wy < y0 || wy > y1) return;
      const area = (x1 - x0) * (y1 - y0);
      if (area < bestArea - 1e-6 || (Math.abs(area - bestArea) < 1e-6 && z > bestZ)) {
        bestArea = area; bestZ = z; best = id;
      }
    };

    // 人：锚点在脚底（anchor 0.5,1），贴图比人本身大一圈（头顶有余量）
    //     → 收一收，别让"头顶那片空气"也能点中。
    //     宽度要取绝对值：朝左走时 scale.x 是负的。
    for (const [id, p] of this._people) {
      const w = Math.abs(p.spr.width) / U, h = Math.abs(p.spr.height) / U;
      const hw = w * 0.35, hh = h * 0.42;
      const x = p.spr.x / U, y = p.spr.y / U;
      take(id, x - hw, y - hh * 2, x + hw, y, p.spr.zIndex);
    }

    // 物件：锚点在图形正中 → 就是它自己那圈
    for (const [id, s] of this._things) {
      const hw = Math.abs(s.width) / U / 2, hh = Math.abs(s.height) / U / 2;
      const x = s.x / U, y = s.y / U;
      take("ent:" + id, x - hw, y - hh, x + hw, y + hh, s.zIndex);
    }

    // 建筑：能转 → 把光标转进它的【局部坐标】再比（和编辑器 hitBuilding 同一套）
    for (const [lid, b] of Object.entries(this.store.map?.buildings || {})) {
      if (!b.center || !b.size) continue;
      const r = -(b.rot || 0) * Math.PI / 180;
      const dx = wx - b.center[0], dy = wy - b.center[1];
      const lx = dx * Math.cos(r) - dy * Math.sin(r);
      const ly = dx * Math.sin(r) + dy * Math.cos(r);
      const [bw, bh] = b.size;
      if (Math.abs(lx) > bw / 2 || Math.abs(ly) > bh / 2) continue;
      const area = bw * bh;
      if (area < bestArea - 1e-6) { bestArea = area; best = "loc:" + lid; }
    }
    return best;
  }

  /** dt = 距上一帧的墙钟秒。main 的帧循环传进来。 */
  frame(dt) {
    this.store.advanceClock(dt);            // 本地游戏时钟外推（帧间动画要连续）
    this.view.step();
    this.map.draw(this.scene());
    this._roofs_();
    // ★ 先算一次"现在指着谁" —— 人和物件的 tint 要靠它，而它们是下面画的。
    this._hoverHit = this._hoverAt ? this.pick(this._hoverAt[0], this._hoverAt[1]) : "";
    this._things_();
    this.motion.step(this.store, dt);
    this._people_();
    this._hilite_();
    this.view.syncPaper();
  }

  // ── 物件：货 / 家具 ────────────────────────────────────────────────
  /** 后端只给 item_type + 世界坐标；贴图名照 art 的约定推：
   *  items/{item_type}.svg 是"有货"，items/{item_type}_empty.svg 是空态。
   *  ★ 空态是有意义的信息（"这筐苹果空了" ≠ "这儿没有筐"），所以 stock=0
   *    且 persist_empty 时要用空态那张 —— 没有空态资产就退回有货那张。 */
  /** 屋顶淡出：有人站在里面的楼 → 半透明，能隔着屋顶看见人和家具。
   *
   *  ★ 为什么是必需品，不是锦上添花：视角是【正俯视】——
   *    你看到的就是屋顶本身。不淡出的话，进屋的人等于从画面上消失了。
   *    （美术方向文档 L216 那个未决问题："只看到屋顶？但'屋子里长什么样'
   *      是交互的一部分" —— 这里就是那个问题的答案。）
   *
   *  ★ 缩放越大越透：放大说明你在看这栋楼，就该看清里面；
   *    缩得很远时半透明只会糊成一团，不如实心 —— 而且"哪几栋有人"
   *    在缩略视角下反而更该一眼看出。
   *
   *  只改 body（屋顶本体）。lit（窗户灯）归日夜系统管，别抢。
   */
  _roofs_() {
    const inside = new Set();
    for (const [, npc] of this.store.npcs) {
      // 在路上的人不算"在屋里"
      if (npc.travel && (npc.travel.waypoints || []).length >= 2) continue;
      if (npc.loc) inside.add(npc.loc);
    }
    const k = this.view.cam.k;
    const t2 = Math.min(1, Math.max(0, (k - 0.6) / 1.4));   // k≤0.6 → 0；k≥2 → 1
    const open = 0.75 - 0.57 * t2;                          // 0.75 → 0.18
    for (const [lid, e] of this.map.buildings || []) {
      if (!e.body) continue;                                // 广场没有 body
      const want = inside.has(lid) ? open : 1;
      if (Math.abs(e.body.alpha - want) > 0.01) e.body.alpha = want;
    }
  }

  /** 高亮：人和物件走 tint（在各自的绘制里），这里只补【建筑】那一种。
   *
   *  ★ 建筑没法 tint —— 贴图是"屋顶 + 墙"整块资产，染色会把整栋楼染黄。
   *    所以盖一层半透明暖色（和编辑器"鼠标划过一栋楼"完全一样）。
   *    选中的人/东西不用在这里画：tint 在 _people_/_things_ 里已经处理了。
   */
  _hilite_() {
    this.hilite.removeChildren();
    const hit = this._hoverHit;
    // ① 建筑：盖一层半透明暖色（理由见上）
    //
    //   ★ 必须用 scene.map.buildings 而不是 locations ——
    //     locations 里只有轴对齐的矩形（x/y/w/h），**没有 rot**；
    //     建筑是可以转的（编辑器里能转），照着 locations 画框就会
    //     "楼是斜的、框是正的"（用户："建筑的高亮框无旋转"）。
    //     map.buildings 里有 center / size / rot，和地图渲染用的是同一份。
    if (hit && hit.startsWith("loc:")) {
      const lid = hit.slice(4);
      const b = (this.store.map?.buildings || {})[lid];
      const loc = this.store.locations[lid];
      if (b && b.center && b.size) {
        const [w, h] = b.size;
        const g = new Graphics()
          .rect(-w / 2 * U, -h / 2 * U, w * U, h * U)
          .fill({ color: HILITE, alpha: 0.22 })
          .stroke({ color: HILITE, width: 2.5, alpha: 0.75 });
        g.position.set(b.center[0] * U, b.center[1] * U);
        g.rotation = (b.rot || 0) * Math.PI / 180;
        this.hilite.addChild(g);
      } else if (loc && loc.w > 0) {
        // 兜底：没进 map 的（老场景）就照轴对齐矩形画
        this.hilite.addChild(new Graphics()
          .rect(loc.x * U, loc.y * U, loc.w * U, loc.h * U)
          .fill({ color: HILITE, alpha: 0.22 })
          .stroke({ color: HILITE, width: 2.5, alpha: 0.75 }));
      }
    }
    // ② 名牌：悬浮谁、选中谁，都显示名字（用户要的）。
    //
    //   ★ 位置给的是【世界坐标】不是屏幕偏移 —— 纸片的 dy 是屏幕像素，
    //     拿它抬到头顶的话，一缩放就跑偏了。这里直接算"头顶之上多少米"。
    //   ★ 同一时刻只有一个名牌（一个 paper id 反复用）——
    //     不这样的话鼠标扫一圈会攒下一堆 div。
    const lab = this._label_();
    this.view.paper("hover:name", lab ? lab.text : null,
                    lab ? lab.x : 0, lab ? lab.y : 0, "plate");
  }

  /** 现在该给谁挂名牌：光标底下的优先，没有就看【选中的那个人】。 */
  _label_() {
    const up = (spr) => spr.y / U - spr.height / U - 0.35;   // 站在"头顶之上"
    let hit = this._hoverHit;
    if (!hit && this.store.focus) hit = this.store.focus;
    if (!hit) return null;
    if (hit.startsWith("ent:")) {
      const id = hit.slice(4), s = this._things.get(id);
      const e = this.store.entities.get(id);
      if (!s || !e) return null;
      return { text: e.name || e.item_type || id, x: s.x / U, y: up(s) };
    }
    if (hit.startsWith("loc:")) {
      const r = this.store.locations[hit.slice(4)];
      if (!r) return null;
      return { text: r.name || hit.slice(4), x: r.x + r.w / 2, y: r.y - 0.6 };
    }
    const p = this._people.get(hit);
    if (!p) return null;
    return { text: this.store.npcs.get(hit)?.name || "某居民", x: p.spr.x / U, y: up(p.spr) };
  }

  _things_() {
    const alive = new Set();
    // 先按楼把位置表展开成一个 id→坐标 的大表（每栋楼只算一次，有缓存）
    const place = new Map();
    for (const [id, e] of this.store.entities) {
      if (!e.loc || place.has(id)) continue;
      for (const [k, v] of this.store.placeOf(e.loc)) place.set(k, v);
    }
    for (const [id, e] of this.store.entities) {
      if (!e.loc) continue;
      alive.add(id);
      let s = this._things.get(id);
      if (!s) {
        // ★ 锚点 = 图形【正中】，不是脚底 —— 和编辑器的 _ghost 一致。
        //   两边不一致的话"编辑器里看到的位置"和"游戏里画出来的位置"会差
        //   半个身位，"所见即所得"就成了空话。
        //   选中心还有别的好处：点选时看着哪儿就点哪儿（脚底锚点下，
        //   高家具的中上部点不中）。
        s = new Sprite(); s.anchor.set(0.5, 0.5);
        this.depth.addChild(s);
        this._things.set(id, s);
      }
      const empty = e.stock === 0 && e.persist_empty;
      // 悬停同样是高亮（见 _people_ 的注释）；选中目前没有物件态，留白 = 原色
      s.tint = this._hoverHit === ("ent:" + id) ? HILITE : 0xffffff;
      const file = `items/${e.item_type}${empty ? "_empty" : ""}.svg`;
      const ent = this.assets.entry(file) || this.assets.entry(`items/${e.item_type}.svg`);
      const t = this.assets.get(ent ? ent.file : file);
      if (t && s.texture !== t) {
        s.texture = t;
        const [w, h] = artSize(ent);
        s.width = w; s.height = h;           // 作者尺寸是 2× 画的，artSize 已经除了
      }
      if (!s.texture) {                      // 缺图 → 画个色块，看得见"这儿少东西"
        s.texture = null;
        s.width = 0; s.height = 0;
      }
      // ★ 位置由前端自己摆（store.placeOf → layout.js）。同一栋楼算一次，
      //   所以这里先把整栋楼的位置表拿出来，别一件一件去要。
      const p = place.get(id);
      if (!p) continue;
      s.position.set(p[0] * U, p[1] * U);
      s.zIndex = Math.round(p[1]);
      // ★ 家具朝向跟着楼转（和编辑器 / 建筑贴图同一个 rot）。
      //   不转的话：斜楼里的床和柜台全是正的，看着像浮在屋顶上。
      s.rotation = ((this.store.map?.buildings?.[e.loc]?.rot || 0)) * Math.PI / 180;
    }
    for (const [id, s] of [...this._things])
      if (!alive.has(id)) { s.destroy(); this._things.delete(id); this.view.dropPaper("ent:" + id); }
  }

  // ── 人 ────────────────────────────────────────────────────────────
  _people_() {
    const alive = new Set();
    for (const [id, npc] of this.store.npcs) {
      alive.add(id);
      const p = this._people.get(id) || this._spawn(id);
      const a = this.motion.get(id);
      if (!a) continue;
      const look = this.store.lookOf(npc);
      const file = Motion.frameOf(a, look);
      const t = this.assets.get(file);
      if (t && p.spr.texture !== t) p.spr.texture = t;
      p.spr.x = a.x * U; p.spr.y = a.y * U;
      p.spr.zIndex = Math.round(a.y);
      // ★ 朝向用 scale 翻，不能用 width：给 width 会覆盖掉 scale.x。
      //   side 资产【面朝右】（art 里眼睛偏在头中心右边），往左走就翻过来。
      p.spr.scale.set(p.baseX * (a.face < 0 ? -1 : 1), p.baseY);
      // ★ 指着谁、选中谁 —— 全靠高亮，不画圈（用户定的规矩）。
      //   选中比悬停浓一档，两种状态一眼分得开。
      p.spr.tint = this.store.focus === id ? HILITE_STRONG
                 : (this._hoverHit === id ? HILITE : 0xffffff);
      this._bubble(id, npc, a.x, a.y);
    }
    for (const [id, p] of [...this._people])
      if (!alive.has(id)) { p.spr.destroy(); this._people.delete(id); this.view.dropPaper("npc:" + id); }
  }

  _spawn(id) {
    const spr = new Sprite(this.assets.get("people/me_down_idle.svg") || undefined);
    spr.anchor.set(0.5, 1);                 // 锚点在脚底：人站在地上
    const baseX = 18 / (spr.texture?.width || 36);   // 36×48 是作者尺寸（2×）
    const baseY = 24 / (spr.texture?.height || 48);
    spr.scale.set(baseX, baseY);
    spr.eventMode = "static";
    this.depth.addChild(spr);
    const p = { spr, baseX, baseY };
    this._people.set(id, p);
    return p;
  }

  _bubble(id, npc, wx, wy) {
    const txt = this.store.bubbleOf(npc);
    this.view.paper("npc:" + id, txt, wx, wy - 1.6);
  }
}
