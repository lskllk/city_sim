/** core.js —— 三块界面共用的地基。 */
import { Store } from "./store.js";
import { Assets2, fetchManifest } from "./assets.js";

const BUILD = "r24";
/** 我最近跑过哪一个场景（主菜单「继续」用）。 */
const LS_LAST = "citysim.last";

export const $ = (id) => document.getElementById(id);
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/** ★ 唯一的【可变】共享状态都放这里。
 *
 *  为什么不是 `export let app.net` —— ES module 的 `let` 导出是「快照」式的，
 *  别人改了我看不见、我改了别人也看不见。共享一个对象，大家改属性。
 */
export const app = { assets: null, net: null, world: null, editor: null, selected: "" };

/** 世界状态（前端这一份）。名字就叫 store，全项目不换。 */
export const store = new Store();

export function toast(text) {
  const el = $("hint"); el.textContent = text; el.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove("show"), 1800);
}
export function setStatus(t, cls = "") {
  const el = $("mStatus"); el.textContent = t; el.className = "status " + cls;
}

/** 决定「现在在哪一屏」。★ 唯一一处。 */
export function show(which) {
  $("menu").classList.toggle("hide", which !== "menu");
  $("hud").classList.toggle("hide", which !== "game");
  $("viewport").classList.toggle("hide", which !== "game");
  $("labels").classList.toggle("hide", which !== "game");
  $("editor").classList.toggle("hide", which !== "editor");
  setTimeout(() => { app.world?.view.resize(); app.editor?.view.resize(); }, 0);
}

/** 记一笔「最后跑的场景」。★ 放 core 不放 menu：game.js 要用它，
 *  而 menu.js 已经 import 了 game.js —— 放 menu 就是循环依赖。 */
export function rememberLast(scenario, when) {
  localStorage.setItem(LS_LAST, JSON.stringify({ scenario, when }));
  const el = $("mLast");
  if (el) el.textContent = scenario + " · " + when;
}

export async function ensureAssets() {
  if (!app.assets) app.assets = new Assets2(await fetchManifest());
  return app.assets;
}

export { BUILD, LS_LAST };
