/** store.js —— 世界状态（hello + 增量 snapshot 合并）。
 *
 * 后端契约（见 gateway/snapshot.py）：
 *   · npcs/entities 是**增量**：只推渲染状态变了的那些 → 本地按 id 合并
 *   · `gone` 里的 id 必须删掉，否则会留下幽灵
 *   · 被选中的人（focus）额外带 memory/intent/events —— 10Hz 才来一次
 *   · 每个 NPC 带 `bubble {text, until}`：过期由前端自己判，后端不会再推空帧
 *
 * ★ 位置不由后端管：实体没有坐标（后端只说"在哪个 region 里"），
 *   摆在楼里的哪里由 layout.js 算。见 store.placeOf()。
 */
import { placeIn, rectOf, sortIds } from "./layout.js";

export class Store {
  constructor() {
    this.hello = null;
    // ★ 每次刷新（applyHello/applySnapshot）都会长新东西 → 位置缓存必须清掉，
    //   否则会拿上一个场景那份算出来的坐标。
    this._placeCache = new Map();
    this.canvas = { w: 800, h: 600 };
    this.locations = {};
    this.map = {};
    this.companies = [];
    this.npcs = new Map();
    this.entities = new Map();
    this.tick = 0; this.day = 1; this.clock = "--:--"; this.speed = "pause";
    this.focus = "";
    this.listeners = new Set();
    // —— 前端自己维护的 ——
    // looks: npc_id → 美术 id（art 里的 8 个之一）。
    //   ★ 后端不发这个（它不知道美术），由前端自己去 /api/scene 拿。
    this.looks = {};
    // entPos: entity_id → [rx, ry]（相对建筑的 0~1 比值），编辑器摆的。
    //   ★ 和 looks 同一条路：后端【不认也不发】位置，前端自己读场景文件。
    //     没摆过的（或运行中新生成的：工厂产出的堆、补货上架的）不在表里
    //     → 由 layout.js 自动码一排。
    this.entPos = {};
    // entSize: item_type → [宽, 高]（米）。★ 只用来算边界和步长 ——
    //   不按占地夹的话，脚底那个点虽然在墙内，半个身子照样挂在墙外。
    //   由 game.js 从美术清单里填（尺寸是美术的属性，不是世界的属性）。
    this.entSize = {};
    // tps: 当前档位每秒推进几个 tick（= 几个游戏分钟）。前端拿它外推本地时钟。
    this.tps = 0;
    // gameMin: 本地外推的【游戏分钟】。帧间靠 tps 长，收到快照时对齐回真值。
    this.gameMin = 0;
    // player: 我操控的是谁（hello.player）。接管之前是空的。
    this.player = "";
    // me: 我的笔记本 + 账本 + 行动队列。
    //   ★ 现在是 null —— 【不放假数据】。用户："不要演示数据"。
    //     界面必须能面对"什么都没有"：显示空态，而不是塞一堆假条目蒙混。
    this.me = null;
  }


  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  _emit(what) { for (const fn of this.listeners) fn(what, this); }

  applyHello(h) {
    this.hello = h;
    this.canvas = h.locations?.canvas || this.canvas;
    this.locations = h.locations?.locations || {};
    this.map = h.map || {};
    this.companies = h.companies || [];
    this.player = h.player || "";
    this._emit("hello");
  }

  applySnapshot(s) {
    this.tick = s.tick; this.day = s.day; this.clock = s.clock; this.speed = s.speed;
    if (s.player != null) this.player = s.player;
    // ★ 本地时钟对齐回真值，并把档位换算成 tps
    //   1x = 1 tick/秒，1 tick = 1 游戏分钟（见 game/clock.py）
    this.gameMin = s.tick;
    this.tps = s.tps != null ? s.tps
      : ({ pause: 0, "1x": 1, "10x": 10, "100x": 100, "1000x": 1000 }[s.speed] ?? 0);
    for (const n of s.npcs || []) this.npcs.set(n.id, { ...this.npcs.get(n.id), ...n });
    for (const e of s.entities || []) this.entities.set(e.id, { ...this.entities.get(e.id), ...e });
    const gone = s.gone || {};
    for (const id of gone.npcs || []) this.npcs.delete(id);
    for (const id of gone.entities || []) this.entities.delete(id);
    this._emit("snapshot");
  }

  /** 帧间外推本地时钟。dt = 墙钟秒。
   *  ★ 为什么要外推：快照 60Hz 到，但 tick 只在 1x 下每秒才长 1 ——
   *    直接跟着 tick 画，人就一卡一卡地跳。外推后动画是连续的。 */
  advanceClock(dt) {
    if (this.tps > 0) this.gameMin += this.tps * dt;
  }

  /** 美术 id。场景里没填 look 的人（现在大部分没填）按 id 稳定分配一个 ——
   *  稳定很要紧：每帧换一张脸人就抽风了。 */
  lookOf(npc) {
    const set = this._lookSet || (this._lookSet =
      ["me", "n_li", "n_lin", "n_sun", "n_wang", "n_zhang", "n_zhao", "n_zhou"]);
    const want = this.looks[npc.id] || npc.look;
    if (want && set.includes(want)) return want;
    let h = 0;                                  // 稳定散列（乘法散列，不是随机）
    for (let i = 0; i < npc.id.length; i++) h = (h * 31 + npc.id.charCodeAt(i)) >>> 0;
    return set[h % set.length];
  }

  /** 地图的指纹 —— 变了才重画地面/路/建筑（每帧重画 = 60Hz 建几万个对象）。 */
  builtKey() {
    return Object.keys(this.locations).sort()
      .map(id => `${id}:${this.locations[id].x},${this.locations[id].y}`).join("|");
  }

  /** 这一帧里带着完整记忆的那个人（没在看谁时是 undefined）。 */
  focused() { return this.focus ? this.npcs.get(this.focus) : undefined; }

  /** 老板自己的店 —— 开局镜头对准它。 */
  myShop() {
    for (const c of this.companies)
      for (const id of c.shops || []) if (this.locations[id]) return this.locations[id];
    return null;
  }

  /** 还没过期的气泡（前端自己算过期，后端不再补空帧）。 */
  bubbleOf(npc) {
    const b = npc.bubble;
    if (!b) return null;
    if (b.until != null && b.until <= this.tick) return null;
    return b.text || null;
  }

  /** 某栋楼里东西的位置表：Map<id, [x, y]>（世界坐标，米）。
   *
   *  ★ 缓存键只跟「这栋楼有哪几件东西」有关 —— 库存/价格变了不影响位置，
   *    所以别把整个实体对象塞进去当键。
   */
  placeOf(bid) {
    const ents = this.entitiesAt(bid);
    const key = bid + "|" + ents.join(",");
    const hit = this._placeCache.get(key);
    if (hit) return hit;
    // 按类型查占地，摊成 id → 尺寸给 layout 用
    const sizes = {};
    for (const id of ents) {
      const s = this.entSize[this.entities.get(id)?.item_type];
      if (s) sizes[id] = s;
    }
    const out = placeIn(rectOf(this.locations, bid), ents, this.entPos, sizes);
    if (this._placeCache.size > 64) this._placeCache.clear();   // 跑一整天的场景别把内存长成山
    this._placeCache.set(key, out);
    return out;
  }

  /** 这栋楼里所有东西的 id（已排序 —— 不排的话每次刷新都在换位置）。 */
  entitiesAt(bid) {
    const out = [];
    for (const [id, e] of this.entities) if (e.loc === bid) out.push(id);
    return sortIds(out);
  }
}
