/** markers.js —— 世界上的【圈】。全项目只有这一份实现、一张语义表。
 *
 * ══ 为什么要有这个文件 ══
 *
 *   以前每种状态各自现画：室外吸附一套"十字 + 小环"，屋里摆放一套橘色十字，
 *   游戏侧干脆没有。三套语言、三种含义，用户一眼看不出"现在指着什么、锁没锁住"。
 *   现在收口：**形状只有圆环，颜色按语义查表**。
 *
 * ══ 形状：只有圆环（十字已废除）══
 *
 *   圈的大小表示"多大一块"：
 *     · 没有尺寸的（吸附点）= 固定小圈
 *     · 有尺寸的（人 / 建筑 / 东西）= **圈住它的占地**
 *   ★ 曾经的"十字 + 圆"是两种形状混用，还容易和"选中"看混 —— 已删。
 *     现在"指着"和"选中"靠【颜色 + 大小】区分，形状永远是圈。
 *
 * ══ 颜色语义 ══
 *
 *   绿 node/item   = 路网节点 / 屋里的一件东西    （"这是个可以接上的实体"）
 *   橙 door/area   = 建筑门 / 地面区域            （"这是有归属的结构"）
 *   琥珀 road/pick = 路中线 / 选中                （"候选、将要"）
 *   青 drop        = 将要落在这里（摆放）          （"确定会发生"）
 *   灰 bad         = 不行（点了也白点）            （"这里不行"）
 *   白 free        = 什么都没吸到，自由落点
 *
 * ══ 屋里为什么【不用】标记 ══
 *
 *   屋里画标记是多余的：家具本来就在那儿，而且很小 —— 圈住它反而看不清它长什么样。
 *   屋里统一用【高亮】（见 editor.js 的 _ghost：tint + 透明度）：
 *     普通 = 半透明 / 悬停 = 不透明 + 暖色 / 拿在手上 = 不透明 + 选中色
 *   圈只用在屋外那种"地是空的、只有个点"的场合。
 *
 * ══ 手势语义（编辑器 / 游戏，一样）══
 *
 *   移动   → 悬停：告诉你"现在指着什么"
 *   点     → 对这个东西做事（不是拖出来的）
 *   拖     → 平移镜头（永远）
 *   右键   → 放下手上的 / 取消当前手势
 *   滚轮   → 缩放（锚点在光标）
 *   Esc    → 取消当前手势；没有手势就退出当前模式
 *
 *   ★ 一条铁律：点 = 操作，拖 = 平移。任何"按住拖才有反应"的设计都是错的。
 */
import { Graphics } from '../vendor/pixi.min.mjs';
import { U } from './view.js';

export const MARK = {
  node: 0x2fbf6f,     // 路网节点
  item: 0x2fbf6f,     // 一件东西
  door: 0xff6b3d,     // 建筑门 / 建筑
  area: 0xff6b3d,     // 地面区域
  road: 0xffc53d,     // 路中线
  pick: 0xffc53d,     // 被选中
  drop: 0x21b3a6,     // 将要落在这里
  bad: 0x8a8779,      // 不行
  free: 0xffffff,     // 自由落点
};

const OUTLINE = 0x141414;          // 深色描边：亮色在白墙 / 土地上都看得见
const R_FREE = 5;                  // 没有尺寸的东西（吸附点）固定这么大
const R_MIN = 6;

/** 画一个圈。
 *
 *  @param host  画到哪个 Pixi 容器（世界像素坐标系的都行）
 *  @param xm,ym 世界坐标（米）—— 内部 ×U
 *  @param kind  MARK 里的键
 *  @param opt   {
 *                 size  占地 [宽,高] 米 —— 给了就【圈住它】，不给就用固定小圈
 *                 r     直接指定半径（像素），优先级最高
 *                 locked 已经定住 → 圈外套一道深边
 *               }
 */
export function markRing(host, xm, ym, kind = "free", opt = {}) {
  const col = MARK[kind] ?? MARK.free;
  const x = xm * U, y = ym * U;
  const r = opt.r ?? (opt.size
    ? Math.max(R_MIN, (Math.max(opt.size[0], opt.size[1]) * U) / 2 + 3)
    : R_FREE);
  const g = new Graphics();
  g.circle(x, y, r).stroke({ color: OUTLINE, width: 4.5, alpha: 0.5 });   // 深色底
  g.circle(x, y, r).stroke({ color: col, width: 2.6 });
  if (opt.locked) g.circle(x, y, r + 4).stroke({ color: OUTLINE, width: 3, alpha: 0.8 });
  host.addChild(g);
  return g;
}
