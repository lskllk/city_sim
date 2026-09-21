/** main.js —— 壳。
 *
 *   主菜单 ─┬─ 继续（最近一次的场景）
 *           ├─ 选择场景
 *           └─ 编辑器 ── 默认打开【最近编辑的那张】地图
 *
 * 游戏和编辑器共用 View（相机/输入/纸片）和 MapLayer（地图渲染）——
 * 所以两边看到的是同一份画面，编辑器只是多画了几个手柄。
 */
import { Net } from "./net.js";
import { Store } from "./store.js";
import { World } from "./world.js";
import { Editor } from "./editor.js";
import { Assets2, fetchManifest } from "./assets.js";
import { renderPanel } from "./panel.js";

const LS_LAST = "citysim.last";
const SPEEDS = [["pause", "停"], ["1x", "1×"], ["10x", "10×"],
                ["100x", "100×"], ["1000x", "1000×"]];
const $ = (id) => document.getElementById(id);

let assets = null, net = null, world = null, editor = null, store = new Store();
let selected = "";

function toast(text) {
  const el = $("hint");
  el.textContent = text; el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 1600);
}
function setStatus(text, cls = "") {
  const el = $("mStatus"); el.textContent = text; el.className = "status " + cls;
}
function show(which) {
  for (const s of ["menu", "game", "editor"]) $(s).classList.toggle("hide", s !== which);
}

const lastGame = (() => { try { return JSON.parse(localStorage.getItem(LS_LAST) || "null"); } catch { return null; } })();
$("mLast").textContent = lastGame ? `${lastGame.scenario} · ${lastGame.when}` : "还没有跑过";

// ── 贴图仓库（游戏和编辑器共用一份）──────────────────────────────────
async function ensureAssets() {
  if (!assets) assets = new Assets2(await fetchManifest());
  return assets;
}

// ══ 游戏 ══════════════════════════════════════════════════════════════
async function play() {
  setStatus("正在连后端…");
  net = new Net(onMessage);
  try {
    const hello = await net.connect();
    store.applyHello(hello);
    await startGame(hello);
    const when = new Date().toLocaleString("zh-CN",
      { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    localStorage.setItem(LS_LAST, JSON.stringify({ scenario: hello.scenario || "scene", when }));
    $("mLast").textContent = `${hello.scenario || "scene"} · ${when}`;
    setStatus(`后端已连上 · ${hello.n_npc ?? "?"} 人`, "ok");
  } catch (e) {
    setStatus(String(e.message || e), "bad");
  }
}

async function startGame() {
  if (!world) {
    const a = await ensureAssets();
    await a.preloadMap();
    world = await new World($("stage"), store, $("ghud"), a).init();
    world.onSelect = onPick;
  }
  world.view.fit(store.canvas);
  const shop = store.myShop();
  if (shop) world.view.centerOn(shop.x + shop.w / 2, shop.y + shop.h / 2, 1.6);
  show("game");
  syncSpeed();
  if (!startGame._loop) { startGame._loop = true; tickLoop(); }
}

function tickLoop() {
  if (!world) return;
  if (!$("game").classList.contains("hide")) world.frame();
  requestAnimationFrame(tickLoop);
}

let _panelAt = 0;
function onMessage(msg) {
  if (msg.type === "snapshot") {
    store.applySnapshot(msg);
    // 面板 60Hz 重建会把滚动位置撞掉，限到 8Hz（记忆本来也只 10Hz 带一次）
    if (selected && performance.now() - _panelAt > 120) {
      _panelAt = performance.now();
      renderPanel($("panel"), store.npcs.get(selected) || null, store, clearSel);
    }
    $("gClock").textContent = msg.clock || "--:--";
    $("gDay").textContent = `第 ${msg.day} 天`;
    if (msg.speed && msg.speed !== store.speed) syncSpeed();
  } else if (msg.type === "__closed") {
    setStatus("后端断开了", "bad"); show("menu");
  }
}

function clearSel() {
  selected = ""; store.focus = "";
  net?.send("select", { npc: "" });
  renderPanel($("panel"), null, store, clearSel);
}
function onPick(hit) {
  if (!hit) return clearSel();
  if (hit.startsWith("loc:")) return toast(store.locations[hit.slice(4)]?.name || hit.slice(4));
  selected = hit; store.focus = hit;
  net?.send("select", { npc: hit });
  renderPanel($("panel"), store.npcs.get(hit) || null, store, clearSel);
}
function syncSpeed() {
  const host = $("gSpeed"); host.innerHTML = "";
  for (const [code, label] of SPEEDS) {
    const b = document.createElement("button");
    b.textContent = label;
    if (code === store.speed) b.classList.add("on");
    b.onclick = async () => { await net.send("set_speed", { speed: code }); store.speed = code; syncSpeed(); };
    host.appendChild(b);
  }
}

// ══ 编辑器 ════════════════════════════════════════════════════════════
async function openEditor() {
  if (!editor) {
    const a = await ensureAssets();
    await a.preloadMap();
    editor = await new Editor($("ecanvas"), $("ehud"), a, {
      toast,
      setScene: (name, stats, saved) => {
        $("eName").textContent = name;
        $("eDirty").textContent = saved ? "" : "•";
        $("eStats").textContent = `${stats.nodes} 节点 · ${stats.edges} 路段 · ${stats.buildings} 建筑`;
      },
      setStats: (stats) => {
        $("eStats").textContent = `${stats.nodes} 节点 · ${stats.edges} 路段 · ${stats.buildings} 建筑`;
      },
      setDirty: (d) => { $("eDirty").textContent = d ? "•" : ""; },
      setTool: (t, type) => {
        for (const b of $("eTool").children) b.classList.toggle("on", b.dataset.tool === t);
        $("ePaletteGrp").style.opacity = t === "build" ? "1" : "0.55";
        $("ePickHint").textContent = t === "build" ? "挑一个，然后在地图上点" : "切到「摆房」才能选";
        for (const b of $("ePalette").children) b.classList.toggle("on", b.dataset.type === type);
      },
    }).init();
    buildPalette();
    // 坐标读数的唯一刷新点（每帧刷 DOM 没必要，跟着鼠标走就够）
    editor.view.el.addEventListener("pointermove", (e) => {
      const r = editor.view.el.getBoundingClientRect();
      const [x, y] = editor.view.toWorld(e.clientX - r.left, e.clientY - r.top);
      $("eXY").textContent = `${x.toFixed(0)}, ${y.toFixed(0)} m`;
      const s = editor.snapHint;
      $("eSnap").textContent = s ? { node: "吸到节点", door: "吸到门", road: "吸到路中线", free: "自由" }[s.kind] : "";
      $("eSnap").className = "snap " + (s?.kind || "");
    });
  }
  show("editor");
  const name = await editor.openLatest();
  toast(`打开 ${name}（最近编辑的一张）`);
}

async function buildPalette() {
  const cat = await (await fetch("/api/catalog")).json();
  const host = $("ePalette");
  host.innerHTML = "";
  for (const b of cat.buildings) {
    const el = document.createElement("button");
    el.dataset.type = b.type;
    el.innerHTML = `${b.name}<span class="k">${b.kind}</span>`;
    el.title = `${b.type} · 容量 ${b.capacity} · 默认 ${b.size[0].toFixed(1)}×${b.size[1].toFixed(1)} m`;
    el.onclick = () => editor.setTool("build", b.type);
    host.appendChild(el);
  }
  editor.ui.setTool("select", "");
}

// ══ 顶上那排 ══════════════════════════════════════════════════════════
$("mContinue").onclick = play;
$("mPick").onclick = () => { toast("场景列表还没做 —— 现在只有 config/scenes/scene.json"); play(); };
$("mEditor").onclick = openEditor;

$("gMenu").onclick = () => { show("menu"); net?.send("select", { npc: "" }); selected = ""; };
$("gHome").onclick = () => {
  const shop = store.myShop();
  if (shop) world.view.centerOn(shop.x + shop.w / 2, shop.y + shop.h / 2, 1.6);
  else world.view.fit(store.canvas);
};

$("eMenu").onclick = () => show("menu");
$("eSave").onclick = () => editor?.save();
$("eSaveAs").onclick = () => {
  const name = prompt("另存为（只写到 config/scenes/）：", editor.name);
  if (name) editor.save(name.trim().replace(/[^\w.-]/g, "") || "scene.json");
};
for (const b of $("eTool").children)
  b.onclick = () => editor.setTool(b.dataset.tool, editor.buildType);

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { clearSel(); editor && (editor.selected = "", editor.redraw()); }
  if (e.key === "f" && world) world.view.fit(store.canvas);
  if (e.ctrlKey && e.key === "s" && editor && !$("editor").classList.contains("hide")) {
    e.preventDefault(); editor.save();
  }
  if (!$("editor").classList.contains("hide") && editor) {
    const map = { "1": "select", "2": "road", "3": "build", "4": "erase" };
    if (map[e.key]) editor.setTool(map[e.key], editor.buildType);
  }
});
window.addEventListener("resize", () => { world?.view.apply(); editor?.view.apply(); });

// 调试句柄：控制台里能直接捅
window.citysim = {
  store, get net() { return net; }, get world() { return world; },
  get editor() { return editor; }, get assets() { return assets; },
  pick: onPick, get selected() { return selected; },
};

// 直达：#editor 直接进编辑器（测起来方便，平时也好用）
if (location.hash === "#editor") openEditor();
else play();
