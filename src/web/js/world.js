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
import { Container, Sprite } from '../vendor/pixi.min.mjs';
import { View, U } from './view.js';
import { MapLayer } from './maprender.js';
import { markRing } from "./markers.js";
import { Motion, artSize } from './motion.js';

export class World {
  constructor(canvasEl, store, hudEl, assets) {
    this.store = store;
    this.assets = assets;
    this.view = new View(canvasEl, hudEl);
    this.map = new MapLayer(assets);
    this.thing = new Container();          // 物件（货/家具）
    this.thing.sortableChildren = true;
    this.npc = new Container();
    this.npc.sortableChildren = true;
    this.motion = new Motion();
    this._things = new Map();              // entity_id → Sprite
    this._people = new Map();
    // 光标标记（悬停 / 选中）—— ★ 和编辑器【同一套符号】，见 markers.js。
    // 单独一层、每帧重建：标记是"这一瞬间指着什么"，不该攒着。
    this.marks = new Container();
    this._hoverAt = null;
    this.onSelect = null;
  }

  async init() {
    await this.view.init();
    this.map.root.zIndex = 0; this.thing.zIndex = 1; this.npc.zIndex = 2;
    this.marks.zIndex = 3;                       // 标记在最上面（但不挡点击）
    this.view.worldLayer.addChild(this.map.root, this.thing, this.npc, this.marks);
    this.view.onView = () => this.view.syncPaper();
    // 点人；拖是平移（onDown 不接 → 相机默认接管）
    this.view.onPick = (x, y) => this.onSelect?.(this.pick(x, y), [x, y]);
    // ★ 悬停也要有反馈 —— 编辑器的规矩是"光标指着什么就标什么"，
    //   游戏里以前只有 tint 变色（选中才有），鼠标划过什么都没有。
    this.view.onHover = (x, y) => { this._hoverAt = [x, y]; };
    this.view.onContext = () => this.onSelect?.("", [0, 0]);   // 右键 = 取消选中
    return this;
  }

  /** 场景形状和编辑器导出的一样：{canvas, locations, map} */
  scene() {
    return { canvas: this.store.canvas, locations: this.store.locations, map: this.store.map };
  }

  /** 点到谁了。人优先（他们很小，但最该点得中），其次物件，最后建筑。 */
  pick(wx, wy) {
    const r = 26 / this.view.cam.k;
    let best = "", bestD = r;
    for (const [id, p] of this._people) {
      const d = Math.hypot(p.spr.x / U - wx, p.spr.y / U - wy);
      if (d < bestD) { bestD = d; best = id; }
    }
    if (best) return best;
    bestD = r * 0.7;                        // 物件比人小一圈，点选半径也收一点
    for (const [id, s] of this._things) {
      const d = Math.hypot(s.x / U - wx, s.y / U - wy);
      if (d < bestD) { bestD = d; best = "ent:" + id; }
    }
    if (best) return best;
    for (const [lid, loc] of Object.entries(this.store.locations))
      if (wx >= loc.x && wx <= loc.x + loc.w && wy >= loc.y && wy <= loc.y + loc.h)
        return "loc:" + lid;
    return "";
  }

  /** dt = 距上一帧的墙钟秒。main 的帧循环传进来。 */
  frame(dt) {
    this.store.advanceClock(dt);            // 本地游戏时钟外推（帧间动画要连续）
    this.view.step();
    this.map.draw(this.scene());
    this._things_();
    this.motion.step(this.store, dt);
    this._people_();
    this._marks_();
    this.view.syncPaper();
  }

  // ── 物件：货 / 家具 ────────────────────────────────────────────────
  /** 后端只给 item_type + 世界坐标；贴图名照 art 的约定推：
   *  items/{item_type}.svg 是"有货"，items/{item_type}_empty.svg 是空态。
   *  ★ 空态是有意义的信息（"这筐苹果空了" ≠ "这儿没有筐"），所以 stock=0
   *    且 persist_empty 时要用空态那张 —— 没有空态资产就退回有货那张。 */
  /** 光标标记：一律是【圈】—— 悬停一个小的，选中一个圈住它的。
   *  ★ 和编辑器同一套符号/颜色（见 markers.js）—— 不然两边各一套语言，用户认不过来。
   *  人在 world 坐标里是 a.x/a.y（米），物件在 placeOf 表里。
   */
  _marks_() {
    this.marks.removeChildren();
    // ① 选中的那个人：环（不是十字 —— 十字是"指着的点"，环是"选中的东西"）
    const f = this._people.get(this.store.focus);
    if (f) markRing(this.marks, f.spr.x / U, f.spr.y / U, "pick",
                    { size: [f.spr.width / U, f.spr.height / U] });
    // ② 光标底下：十字 + 小环
    if (!this._hoverAt) return;
    const hit = this.pick(this._hoverAt[0], this._hoverAt[1]);
    if (!hit) return;
    if (hit.startsWith("ent:")) {
      const s = this._things.get(hit.slice(4));
      if (s) markRing(this.marks, s.x / U, s.y / U, "item", { size: [s.width / U, s.height / U] });
    } else if (hit.startsWith("loc:")) {
      const r = this.store.locations[hit.slice(4)];
      if (r) markRing(this.marks, r.x + r.w / 2, r.y + r.h / 2, "door", { size: [r.w, r.h] });
    } else {
      const p = this._people.get(hit);
      if (p) markRing(this.marks, p.spr.x / U, p.spr.y / U, "node",
                      { size: [p.spr.width / U, p.spr.height / U] });
    }
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
        this.thing.addChild(s);
        this._things.set(id, s);
      }
      const empty = e.stock === 0 && e.persist_empty;
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
      p.spr.tint = this.store.focus === id ? 0xffd9a0 : 0xffffff;
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
    this.npc.addChild(spr);
    const p = { spr, baseX, baseY };
    this._people.set(id, p);
    return p;
  }

  _bubble(id, npc, wx, wy) {
    const txt = this.store.bubbleOf(npc);
    this.view.paper("npc:" + id, txt, wx, wy - 1.6);
  }
}
