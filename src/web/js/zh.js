/** zh.js —— 内核的英文键 → 界面上的中文。**只有这一份。**
 *
 * 抽出来的原因：main.js / ui.js / panel 都要用，各写一份迟早对不上
 * （一边叫"饿"、一边叫"饥饿"，同一份数据两个说法）。
 *
 * ★ 这里只放【翻译】，不放业务。要加一个信号，先在内核加，再加这一行。
 */

/** 生理信号。内核的 SIGNALS 是 energy/hunger/bladder/hp/fun。 */
export const SIGNAL_ZH = {
  energy: "精力", hunger: "饿", bladder: "憋", hp: "健康", fun: "想玩",
};

/** 时间档位 → 界面文案。键必须和 game/clock.py 的 SPEED_TPS 一致。 */
export const SPEED_ZH = {
  pause: "停", "1x": "1×", "10x": "10×", "100x": "100×", "1000x": "1000×",
};

/** 键盘提示里显示的顺序（和上面同一批档位）。 */
export const SPEEDS = [
  ["pause", "停"], ["1x", "1×"], ["10x", "10×"], ["100x", "100×"],
];

/** 公司类型。 */
export const COMPANY_KIND_ZH = { retail: "零售", manufacture: "制造" };
