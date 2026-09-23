/** menu.js —— 主菜单：继续 / 新场景 / 打开 / 编辑器。 */
import { $, app, store, toast, setStatus, show, LS_LAST } from "./core.js";
import { play } from "./game.js";
import { openEditor } from "./editorui.js";

const lastGame = (() => {
  try { return JSON.parse(localStorage.getItem(LS_LAST) || "null"); } catch { return null; }
})();
$("mLast").textContent = lastGame ? `${lastGame.scenario} · ${lastGame.when}` : "还没有跑过";


$("mContinue").onclick = () => play();
$("mNew").onclick = newScene;
$("mOpen").onclick = toggleScenes;
$("mListClose").onclick = () => $("mList").classList.add("hide");
$("mEditor").onclick = openEditor;

// ── 新场景：空白地图，直接进编辑器画 ────────────────────────────────
export async function newScene() {
  const stamp = new Date().toISOString().slice(5, 10).replace("-", "");
  const name = (prompt("新场景存到 config/scenes/ —— 起个名字：",
                       `scene_${stamp}.json`) || "").trim();
  if (!name) return;
  await openEditor();
  // 空白文档：只给画布，路网和建筑都是空的，人的那份也空着
  const blank = {
    canvas: { w: 800, h: 600 }, display_name: name.replace(/\.json$/, ""),
    locations: {},
    map: { format: "citysim.map", version: 1,
           world: { unit: "m", bounds: [0, 0, 800, 600], grid: 1.0 },
           nodes: {}, edges: {}, buildings: {} },
    npcs: [], entities: [], companies: [], knowledge: [], plans: [], travel: {},
  };
  app.editor.doc.load(blank);
  app.editor.name = name;
  app.editor.view.setWorld(app.editor.doc.canvas);
  app.editor.view.fill();
  app.editor.redraw();
  app.editor.ui.setScene(name, app.editor.doc.stats());
  toast(`空白地图 —— 先画路，再摆房。Ctrl+S 保存为 ${name}`);
}

// ── 场景列表 ────────────────────────────────────────────────────────
export async function toggleScenes() {
  const box = $("mList");
  if (!box.classList.contains("hide")) return box.classList.add("hide");
  const list = await (await fetch("/api/scenes", { cache: "no-store" })).json();
  const body = $("mListBody");
  body.innerHTML = "";
  if (!list.scenes.length) { body.innerHTML = '<div class="dim" style="font-size:12px">还没有场景</div>'; }
  for (const s of list.scenes) {
    const b = document.createElement("button");
    const when = new Date(s.mtime * 1000).toLocaleString("zh-CN",
      { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    b.innerHTML = `<span>${s.name}</span><span class="meta">${(s.bytes / 1024).toFixed(1)}KB · ${when}</span>`;
    if (s.name === list.last) b.classList.add("now");
    b.onclick = () => { box.classList.add("hide"); play(s.name); };
    body.appendChild(b);
  }
  box.classList.remove("hide");
}
