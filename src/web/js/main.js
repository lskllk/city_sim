/** main.js —— 引导。就三件事：
 *   ① import 三块界面（import 本身就完成了事件注册）
 *   ② 全局键盘
 *   ③ 调试句柄 */
import { $, app, store, show } from "./core.js";
import { play, startGame, startLoop, clearSel, onPick } from "./game.js";
import { newScene, toggleScenes } from "./menu.js";
import { openEditor } from "./editorui.js";
import { U } from "./view.js";


window.addEventListener("keydown", (e) => {
  const inEditor = !$("editor").classList.contains("hide");
  if (e.key === "Escape") {
    // Esc = 同一个 cancelGesture（和右键一样），不只是清选中
    if (inEditor) app.editor.deselect(); else clearSel();
  }
  if (e.key === "f" && !inEditor && app.world) { e.preventDefault(); app.world.view.fill(); }
  if (e.ctrlKey && e.key === "s" && inEditor) { e.preventDefault(); app.editor.save(); }
  if ((e.key === "Delete" || e.key === "Backspace") && inEditor) {
    if (app.editor.deleteSelected()) e.preventDefault();
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && inEditor) {
    e.preventDefault(); app.editor.undo();
  }
  if (inEditor) {
    const map = { "1": "select", "2": "erase" };
    if (map[e.key]) app.editor.setTool(map[e.key], app.editor.buildType);
  }
});

// 调试句柄（tools/*.mjs 的回归脚本靠它）
window.citysim = {
  store, app, pick: onPick, newScene, toggleScenes, play, startGame, startLoop,
  U,                       // 1 米 = 多少像素（工具和回归脚本要用；也省得测试里猜）
  get net() { return app.net; }, get world() { return app.world; },
  get editor() { return app.editor; }, get assets() { return app.assets; },
  get selected() { return app.selected; },
};

// ★ 以前是无条件 play() —— 菜单只是一闪而过，等于没有菜单。
//   （#play / #editor 两个 hash 仍然直达，截图和演示要用。）
//
// ★ 一定要 show("menu")：HUD 在 HTML 里默认是显示的，
//   不主动收起来，主菜单右上角就会露出游戏那排按钮（"返回菜单""我的店"）。
show("menu");
if (location.hash === "#editor") openEditor();
else if (location.hash === "#play") play();
