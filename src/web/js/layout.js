/** layout.js —— 建筑里的东西摆在哪。★ 这件事【前端全权负责】。
 *
 * ══ 为什么不在后端 ══
 *
 *   后端只说「这件东西在 bld_008 里」（`at`）。在里面的哪个坐标，是【怎么画】
 *   的事，不是世界状态的事 —— 内核的模拟从来不读实体坐标：走路靠路网 + 门点，
 *   用物件靠 id，库存/归属/价格都跟位置无关。
 *   所以后端原来那个「按 id 哈希撒个点」的 position 是个中间态：声明了物品有
 *   空间性，却既没被设计过、也没被用过。已经删掉了。
 *
 * ══ 两个来源，一个优先级 ══
 *
 *   ① 编辑器摆过的（场景文件 entities[].pos，相对建筑的 0~1 比值）→ 用它
 *   ② 没摆过的 / 运行中新生成的（工厂产出的堆、补货上架的）→ 自动码一排
 *
 *   自动那套【不是随机的】：按 id 排序，从左到右码一排，排满换行。
 *   同一批东西每次都在同一位置，加一件只会重排，不会乱跳。
 *
 * ══ 坐标是「图形中心」（0.5, 0.5）══
 *
 *   `[rx, ry]` 指的是图形【正中间】那个点，四周各占宽高的一半。
 *   ★ 原来用的是"脚底中点"（anchor 0.5,1）：那样贴墙确实是脚踩在离墙 X 米，
 *     但【点选】很反直觉 —— 一件高家具的中上部根本点不中（用户实测：
 *     "按家具的中间为选中 而不是中下"）。中心锚点下：看着哪儿就点哪儿，
 *     夹边界也是四周各留一半，数学还更对称。
 *   编辑器（_ghost 不传 bottomCenter）和游戏（anchor(0.5,0.5)）必须一致 ——
 *   不然"所见即所得"就是空话。
 */

/** 一格多大（米）。1.6 ≈ 一件家具的占地，摆出来不挤也不散。 */
export const STRIDE = 1.6;
/** 离墙留多少（米）。不留的话东西贴边，看着像掉出去了。 */
export const PAD = 0.6;

/** 建筑矩形（米）。locations 里就是画布坐标 = 世界坐标，没有第二套。 */
export function rectOf(locations, bid) {
  const r = locations?.[bid];
  if (!r || !(r.w > 0) || !(r.h > 0)) return null;
  return { x: r.x, y: r.y, w: r.w, h: r.h };
}

/** 统一收成 {x, y, w, h}。传数组 [x, y, w, h] 进来也认。
 *
 *  ★ 这个宽容是【有意】的：数组/对象混用出的错**静默且致命** ——
 *    rect.x 是 undefined → 算出 NaN → 东西被画到看不见的地方，
 *    而控制台一声不响、也不报错（踩过：整件家具"抓起来就消失"）。
 *    宁可在这里多转一下，也不要再出一个查半天的 NaN。
 */
function asRect(r) {
  if (!r) return null;
  return Array.isArray(r) ? { x: r[0], y: r[1], w: r[2], h: r[3] } : r;
}

/** 楼内相对坐标（0~1）→ 世界坐标（米）。★ 建筑能转，所以这里是唯一的换算口。
 *
 *  rect 用的是【未旋转】的框（toScene 写出来的 locations 就是 center±size/2），
 *  所以先按 rect 算出"相对中心"的偏移，再绕中心转 rot 度。
 */
export function relToWorld(rect0, rot, rx, ry) {
  const rect = asRect(rect0);
  const cx = rect.x + rect.w / 2, cy = rect.y + rect.h / 2;
  const lx = rx * rect.w - rect.w / 2, ly = ry * rect.h - rect.h / 2;
  if (!rot) return [cx + lx, cy + ly];
  const r = rot * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  return [cx + lx * c - ly * s, cy + lx * s + ly * c];
}

/** 世界坐标（米）→ 楼内相对坐标（0~1）。relToWorld 的逆。 */
export function worldToRel(rect0, rot, wx, wy) {
  const rect = asRect(rect0);
  const cx = rect.x + rect.w / 2, cy = rect.y + rect.h / 2;
  let dx = wx - cx, dy = wy - cy;
  if (rot) {                       // 反转回去（-rot）
    const r = -rot * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
    const nx = dx * c - dy * s, ny = dx * s + dy * c;
    dx = nx; dy = ny;
  }
  return [rect.w > 0 ? (dx + rect.w / 2) / rect.w : 0.5,
          rect.h > 0 ? (dy + rect.h / 2) / rect.h : 0.5];
}

/** 把一条相对坐标夹到「整个图形都在屋里」的范围里。
 *
 *  ★ 只夹 0~1 是不够的：那保证的是【那个点】在墙内，半个图形照样挂在墙外
 *    （实测："家具超出了房屋边界"）。真正的边界按每件东西的占地算 ——
 *    锚点是图形中心，所以【四周各留一半】：
 *      x ∈ [w/2, 1 - w/2]，y ∈ [h/2, 1 - h/2]
 *
 *  @param size [宽, 高] 米；缺省当成一个小方块（总比不夹强）
 *  @return [rx, ry] 已夹
 */
export function clampRel(rect, size, rx, ry) {
  const c = (v) => Math.min(1, Math.max(0, v));
  rx = c(rx); ry = c(ry);
  if (!rect || !(rect.w > 0) || !(rect.h > 0)) return [rx, ry];
  const mx = ((size?.[0] || STRIDE * 0.5) / 2 + PAD * 0.5) / rect.w;
  const my = ((size?.[1] || STRIDE * 0.5) / 2 + PAD * 0.5) / rect.h;
  // ★ 东西比屋子还大 → 上下界会反过来。这时只能摆正中，
  //   硬夹的话会算出"上界 < 下界"的乱值。
  const cl = (v, m) => (m > 0.5 ? 0.5 : Math.min(1 - m, Math.max(m, v)));
  return [cl(rx, mx), cl(ry, my)];
}

/** 摆完的位置表：Map<id, [x, y]>（世界坐标，米）。
 *
 *  @param rect     建筑矩形；没有就返回空（不画，比画到 (0,0) 好）
 *  @param ids      这栋楼里所有东西的 id（**调用方先排序**，见 sortIds）
 *  @param authored {id: [rx, ry]} 编辑器摆过的相对位置（0~1，可缺省）
 *  @param sizes    {id: [宽, 高]} 米。只用来算边界 / 步长；可缺省
 *  @param rot      建筑旋转（度，顺时针）。★ 不传的话转过的楼里东西会摆歪
 *                  —— 相对坐标是"楼内"的，落到世界必须带上这个角度。
 */
export function placeIn(rect, ids, authored = {}, sizes = {}, rot = 0) {
  const out = new Map();
  if (!rect || !ids.length) return out;

  // ① 摆过的先落位 —— 按各自占地夹进屋里（改小楼 / 换大家具也不会挂出去）
  for (const id of ids) {
    const a = authored[id];
    if (!a) continue;
    const [rx, ry] = clampRel(rect, sizes[id], +a[0], +a[1]);
    out.set(id, relToWorld(rect, rot, rx, ry));
  }

  // ② 剩下的自动码一排
  const rest = ids.filter((id) => !out.has(id));
  if (!rest.length) return out;

  // ★ 步长跟着【最大的那件】走，不然大件会互相压住
  let maxW = 0, maxH = 0;
  for (const id of rest) {
    const s = sizes[id];
    if (s) { maxW = Math.max(maxW, s[0]); maxH = Math.max(maxH, s[1]); }
  }
  const stride = Math.max(STRIDE, maxW + 0.4);
  const padX = Math.max(PAD, maxW / 2 + PAD * 0.5);
  const padY = Math.max(PAD, maxH / 2 + PAD * 0.5);   // 中心锚点：上下各留半个高

  const innerW = rect.w - 2 * padX;
  const innerH = rect.h - 2 * padY;
  // ★ 屋子装不下一格 → 全摆正中（分格会算出负数）
  if (innerW < 0 || innerH < 0) {
    const c = relToWorld(rect, rot, 0.5, 0.5);
    for (const id of rest) out.set(id, c.slice());
    return out;
  }
  const cols = Math.max(1, Math.floor(innerW / stride) + 1);
  const rows = Math.max(1, Math.floor(innerH / stride) + 1);
  rest.forEach((id, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols) % rows;
    const tx = cols > 1 ? col / (cols - 1) : 0.5;    // 只有一列时别除零
    const ty = rows > 1 ? row / (rows - 1) : 0.5;
    // 算出来的是【楼内】坐标 → 交给 relToWorld 统一带旋转落到世界
    out.set(id, relToWorld(rect, rot, (padX + tx * innerW) / rect.w,
                                       (padY + ty * innerH) / rect.h));
  });
  return out;
}

/** id 排序。★ 一定要排：Map/快照的顺序不保证，不排的话同一批东西
 *  每次刷新都在换位置（"货架在跳舞"）。 */
export function sortIds(ids) {
  return [...ids].sort();
}
