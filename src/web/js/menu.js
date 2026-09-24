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
$("mListClose").onclick = () => hideList();
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
/** 关掉「开始新场景」那个悬浮窗（✕ / 蒙布 / 选完 / 再点一次，都走这里）。 */
function hideList() {
  $("mList").classList.add("hide");
  $("mListVeil").classList.add("hide");
}

// ── 开始新场景：居中悬浮窗，只列名字 ──────────────────────────────────
export async function toggleScenes() {
  const box = $("mList");
  if (!box.classList.contains("hide")) return hideList();
  const list = await (await fetch("/api/scenes", { cache: "no-store" })).json();
  const body = $("mListBody");
  body.innerHTML = "";
  if (!list.scenes.length)
    body.innerHTML = '<div class="dim" style="font-size:12px;padding:10px">还没有场景</div>';
  for (const s of list.scenes) {
    const b = document.createElement("button");
    // ★ 只要名字。大小 / 修改时间不显示 —— 选场景时没人看那个，
    //   它们只会把名字淹掉（用户："只要名字不要脏"）。
    b.textContent = s.name;
    if (s.name === list.last) b.classList.add("now");   // 当前这个只加重，不写字
    b.onclick = () => { hideList(); play(s.name); };
    body.appendChild(b);
  }
  $("mListVeil").onclick = hideList;                 // 点蒙布 = 关掉
  $("mListVeil").classList.remove("hide");
  box.classList.remove("hide");
}
