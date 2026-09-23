/** motion.js —— 【前端假模拟】人的连续移动 + 走路动画。
 *
 * ══ 为什么要这一层 ══
 *
 * 后端只有【逻辑位置】：谁在哪个地点、或者"在路上，0→40 tick 从 A 到 B"。
 * 它没有地图 —— 不知道门在哪、柜台在哪、路上有没有树。所以它给不出
 * "视觉上这个人在哪一米"，也不该给。
 *
 * 于是前端编：**拿后端的逻辑状态当目标，自己按速度走过去。**
 *   · 后端说他在用 meal_simple_041  → 前端让他走到那个物件旁边
 *   · 后端说他在 travel bld_008→bld_004 → 前端跟着后端那条沿路网的点走
 *   · 后端说他在 bld_008 闲着         → 前端让他就地站住
 *
 * ★ 不追求和后端同步。用户的话："移动过去看起来像真的过去吃饭就行"。
 *   这条很关键 —— 想做"精确同步"就得让后端有地图，那是另一场战争。
 *
 * ══ 三条规矩 ══
 *
 * ① 速度跟着【游戏时间】走，不跟墙钟。
 *    所以 1x 是散步、100x 是一闪而过 —— 快进时人就该糊成一片，那是对的。
 *    1 tick = 1 游戏分钟（config/sim.toml），SPEED_TPS["1x"] = 1 → 1x 下
 *    1 墙钟秒 = 1 游戏分钟。
 *
 * ② 走到哪由【目标】决定，不是插值出来的。
 *    目标会跳（后端说"他改用马桶了"），人就转身走过去 —— 这才是"像真的"。
 *
 * ③ 贴图朝向只有三向（up/down/side），side 资产面朝右，往左走就翻过来。
 *    朝向取【位移的主轴】：横着走的多就是 side。
 */
import { U } from './view.js';

/** 每【游戏分钟】走几米。和内核的 move_m_per_tick 一致（config/sim.toml [motion]）。
 *  ★ 前端拿不到这个值（snapshot 里没有），所以硬编码在这里。
 *    改内核那个值时要一起改这里 —— 目前 10 米/游戏分钟 = 0.6 公里/小时，
 *    在 1x 下是 10 米/秒（画面上的快走），很小但看得清。 */
export const WALK_M_PER_TICK = 10;

/** 视觉上每走这么多米换一帧（4 帧一轮）。 */
const STEP_M = 1.1;

/** 离目标多近算"到了"（米）。太小会原地抖，太大看着像没走到。 */
const ARRIVE_M = 0.18;

/** 落太远就加速追（切标签页回来 / 掉帧）。乘这个系数，最多 3 倍。 */
const CATCHUP_M = 6;

export class Motion {
  constructor() {
    /** id → {x, y, dir, face, frame, phase, walk} */
    this.byId = new Map();
  }

  /** 推进一帧。dt = 墙钟秒（不是游戏时间）。 */
  step(store, dt) {
    // ★ 夹住 tps/dt：只要有一个是 undefined，位置就会变成 NaN，
    //   而 NaN 是不可逆的（+= NaN 之后永远是 NaN）→ 人从此隐形（踩过）。
    const dgm = Math.max(0, Number(store.tps) || 0) * Math.max(0, Number(dt) || 0);
    const maxStep = WALK_M_PER_TICK * dgm;

    for (const [id, npc] of store.npcs) {
      let a = this.byId.get(id);
      if (!a) { this.byId.set(id, a = this._spawn(npc)); }
      if (!Number.isFinite(a.x) || !Number.isFinite(a.y))
        Object.assign(a, this._spawn(npc));        // 兜底：NaN 一次就再也回不来了
      const [gx, gy] = this.goalOf(npc, store);
      const dx = gx - a.x, dy = gy - a.y;
      const d = Math.hypot(dx, dy);

      if (d <= ARRIVE_M || maxStep <= 0) {
        a.walk = false;                            // 到了 / 暂停 → 站着
      } else {
        // 距离越远走得越快（最多 3 倍）—— 掉帧后不至于永远落在后面
        const boost = d > CATCHUP_M ? Math.min(3, d / CATCHUP_M) : 1;
        const step = Math.min(d, maxStep * boost);
        a.x += (dx / d) * step;
        a.y += (dy / d) * step;
        a.walk = true;
        a.phase = (a.phase + step) % (STEP_M * 4);
        a.frame = Math.floor(a.phase / STEP_M) % 4;
        // 朝向取主轴；相等时算横着走（人比房子宽，横着更常见）
        if (Math.abs(dx) >= Math.abs(dy)) { a.dir = "side"; a.face = dx < 0 ? -1 : 1; }
        else { a.dir = dy < 0 ? "up" : "down"; a.face = 1; }
      }
    }
    // 不在场上的人（死了 / 走了）清掉，免得 Map 越攒越大
    for (const id of [...this.byId.keys()])
      if (!store.npcs.has(id)) this.byId.delete(id);
  }

  /** 这个人现在【该站在哪】（世界坐标，米）。
   *
   *  越具体的越优先 —— 后端说"他正在用那个马桶"，就比"他在 bld_009"具体：
   *    ① 正在用一个物件 → 走到那个物件【旁边】
   *    ② 其它            → 用后端的逻辑位置（在路上时它沿路网在动，跟得上）
   */
  goalOf(npc, store) {
    const act = npc.active;
    if (act && act.entity) {
      const e = store.entities.get(act.entity);
      // ★ 物件的坐标【前端自己算】（store.placeOf），后端不发 —— 实体没有坐标。
      const p = e && store.placeOf(e.loc).get(act.entity);
      if (p) {
        // 站到【旁边】而不是叠在上面：物件锚点在中心，人锚点在脚底，
        // 不偏一下的话人就站在马桶上了。偏的量和方向都是编的，看着像就行。
        return [p[0] + 0.5, p[1] + 0.45];
      }
    }
    // 人的位置还是后端给的（逻辑落脚点 / 路上插值）—— 这一份没动。
    return npc.position || [0, 0];
  }

  /** 第一次见到这个人：直接放到位，别让他从 (0,0) 横穿整张地图走过来。 */
  _spawn(npc) {
    const p = npc.position || [0, 0];
    return { x: p[0], y: p[1], dir: "down", face: 1, frame: 0, phase: 0, walk: false };
  }

  /** 拿某个人的视觉状态（world.js 画人用）。 */
  get(id) { return this.byId.get(id); }

  /** 贴图文件名。look 是美术 id（art 里的 8 个之一）。 */
  static frameOf(a, look) {
    return a.walk
      ? `people/${look}_${a.dir}_walk${a.frame}.svg`
      : `people/${look}_${a.dir}_idle.svg`;
  }
}

/** 一件物件在世界里的显示尺寸（像素）。
 *  manifest 的 w/h 是【作者尺寸】（authorScale = 2 倍画的），
 *  所以实际像素 = w / 2，再按 U 换算就是米。 */
export function artSize(a, authorScale = 2) {
  const w = (a?.w || 16) / authorScale;
  const h = (a?.h || 16) / authorScale;
  return [w, h];
}
