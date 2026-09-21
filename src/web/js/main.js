/** main.js —— 壳。
 *
 *   主菜单 ─┬─ 继续（最近一次的场景）
 *           └─ 编辑器 ── 默认打开【最近编辑的那张】地图
 *
 * 游戏和编辑器共用 View（相机/输入/纸片）和 MapLayer（地图渲染），
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

let assets = null, net = null, world = null, editor = null;
const store = new Store();
let selected = "";

function toast(text) {
  const el = $("hint");
  el.textContent = text; el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 1800);
}
function setStatus(t, cls = "") { const el = $("mStatus"); el.textContent = t; el.className = "status " + cls; }
function show(which) {
  $("menu").classList.toggle("hide", which !== "menu");
  $("hud").classList.toggle("hide", which !== "game");
  $("viewport").classList.toggle("hide", which !== "game");
  $("labels").classList.toggle("hide", which !== "game");
  $("panel").classList.toggle("hide", which !== "game" || !selected);
  $("editor").classList.toggle("hide", which !== "editor");
  setTimeout(() => { world?.view.resize(); editor?.view.resize(); }, 0);
}

const lastGame = (() => { try { return JSON.parse(localStorage.getItem(LS_LAST) || "null"); } catch { return null; } })();
$("mLast").textContent = lastGame ? `${lastGame.scenario} · ${lastGame.when}` : "还没有跑过";

async function ensureAssets() {
  if (!assets) assets = new Assets2(await fetchManifest());
  return assets;
}

// ══ 游戏 ══════════════════════════════════════════════════════════════
async function play(sceneName) {
  setStatus(sceneName ? `正在打开 ${sceneName}…` : "正在连后端…");
  net = new Net(onMessage);
  try {
    const hello = await net.connect();
    if (sceneName && hello.scenario !== sceneName) {
      // 换场景 = 重置 runner 到那个场景（reset 会重新 build 并回一份新的 hello）
      await net.send("reset", { scenario: sceneName });
    }
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
    world = await new World($("stage"), store, $("labels"), a).init();
    world.onSelect = onPick;
    world.view.setWorld(store.canvas);
    startLoop();
  }
  show("game");
  world.view.fill();                       // ★ 铺满窗口，不留边距
  syncSpeed();
}

let _looping = false;
function startLoop() {
  if (_looping) return;
  _looping = true;
  const step = () => {
    if (!$("hud").classList.contains("hide")) world?.frame();
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

let _panelAt = 0;
function onMessage(msg) {
  if (msg.type === "snapshot") {
    store.applySnapshot(msg);
    $("gDay").textContent = `第 ${msg.day} 天`;
    $("gClock").textContent = msg.clock || "--:--";
    // 面板 8Hz 重建 —— 60Hz 会把滚动位置撞掉（记忆本来也只 10Hz 带一次）
    if (selected && performance.now() - _panelAt > 120) {
      _panelAt = performance.now();
      renderPanel($("panel"), store.npcs.get(selected) || null, store, clearSel);
    }
    paintMe();
    if (msg.speed && msg.speed !== store.speed) syncSpeed();
  } else if (msg.type === "__closed") {
    setStatus("后端断开了", "bad"); show("menu");
  }
}

/** 左上角那张纸：看着谁就显示谁，没看就显示我的店。 */
function paintMe() {
  const npc = store.focused();
  if (npc) {
    $("meName").textContent = `${npc.name} · ${npc.role || "—"}`;
    $("meMoney").innerHTML = `${npc.money ?? "—"}<span class="d">元</span>`;
    $("meAct").textContent = npc.active
      ? `正在 ${npc.active.verb || "?"} ${npc.active.item || ""}`
      : `在 ${store.locations[npc.loc]?.name || npc.loc || "路上"}`;
    $("meBars").innerHTML = bars(npc.signals);
  } else {
    $("meName").textContent = "镇上的小店";
    $("meMoney").innerHTML = `—<span class="d">元</span>`;
    $("meAct").textContent = "点一个人看看";
    $("meBars").innerHTML = "";
  }
}
const SIGNALS = [["energy", "精力"], ["hunger", "饿"], ["bladder", "憋"], ["fun", "想玩"]];
function bars(sig = {}) {
  return SIGNALS.map(([k, label]) => {
    const v = Math.max(0, Math.min(1, Number(sig[k] ?? 0)));
    return `<div class="bar${v < 0.3 ? " low" : ""}"><span>${label}</span>
      <span class="t"><i style="width:${(v * 100).toFixed(0)}%"></i></span>
      <span class="v">${(v * 100).toFixed(0)}</span></div>`;
  }).join("");
}

function clearSel() {
  selected = ""; store.focus = "";
  net?.send("select", { npc: "" });
  $("panel").classList.add("hide");
  paintMe();
}
function onPick(hit) {
  if (!hit) return clearSel();
  if (hit.startsWith("loc:")) return toast(store.locations[hit.slice(4)]?.name || hit.slice(4));
  selected = hit; store.focus = hit;
  net?.send("select", { npc: hit });
  renderPanel($("panel"), store.npcs.get(hit) || null, store, clearSel);
  paintMe();
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
    const ui = {
      toast,
      setScene: (name, stats, saved) => {
        $("eName").textContent = name;
        $("eDirty").textContent = saved ? "" : " •";
        $("eStats").textContent = `${stats.nodes} 节点 · ${stats.edges} 路段 · ${stats.buildings} 建筑`;
      },
      setStats: (stats) => {
        $("eStats").textContent = `${stats.nodes} 节点 · ${stats.edges} 路段 · ${stats.buildings} 建筑`;
      },
      setDirty: (d) => { $("eDirty").textContent = d ? " •" : ""; },
      setCursor: (snap) => { $("eSnapLabel").textContent = editor.snapText() || "—"; },
      setTool: (t, type) => {
        for (const b of $("eTool").children) b.classList.toggle("on", b.dataset.tool === t);
        $("ePickHint").textContent = t === "build" ? "挑一个" : "切到「摆房」才能选";
        for (const b of $("ePalette").children) b.classList.toggle("on", b.dataset.type === type);
      },
    };
    editor = await new Editor($("ecanvas"), $("elabels"), a, ui).init();
    buildPalette();
    ui.setTool("select", "");
    editor.view.el.addEventListener("pointermove", (e) => {
      const r = editor.view.el.getBoundingClientRect();
      const [x, y] = editor.view.toWorld(e.clientX - r.left, e.clientY - r.top);
      $("eXY").textContent = `${x.toFixed(0)}, ${y.toFixed(0)} m`;
      $("eSnapLabel").textContent = editor.snapText() || "—";
    });
  }
  show("editor");
  const name = await editor.openLatest();
  toast(`打开 ${name}（最近编辑的那张）`);
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
}

// ══ 接线 ══════════════════════════════════════════════════════════════
$("mContinue").onclick = () => play();
$("mNew").onclick = newScene;
$("mOpen").onclick = toggleScenes;
$("mListClose").onclick = () => $("mList").classList.add("hide");
$("mEditor").onclick = openEditor;
$("gMenu").onclick = () => { net?.send("select", { npc: "" }); selected = ""; show("menu"); };
$("gHome").onclick = () => {
  const shop = store.myShop();
  if (shop) world.view.centerOn(shop.x + shop.w / 2, shop.y + shop.h / 2, 1.6);
  else world.view.fill();
};
$("eMenu").onclick = () => show("menu");
$("eSave").onclick = () => editor?.save();
$("eSaveAs").onclick = () => {
  const name = prompt("另存为（写到 config/scenes/）：", editor?.name || "scene.json");
  if (name) editor.save(name.trim().replace(/[^\w.-]/g, "") || "scene.json");
};
for (const b of $("eTool").children)
  b.onclick = () => editor.setTool(b.dataset.tool, editor.buildType);

/** 吸附开关：网络（节点/门/路中线）和栅格，各自独立。 */
for (const b of $("eSnapToggles").children)
  b.onclick = () => {
    const on = !b.classList.contains("on");
    b.classList.toggle("on", on);
    if (b.dataset.snap === "net") editor.doc.netSnap = on;
    else editor.doc.gridSnap = on;
    editor.redraw();
  };

window.addEventListener("keydown", (e) => {
  const inEditor = !$("editor").classList.contains("hide");
  if (e.key === "Escape") {
    if (inEditor) { editor.selected = ""; editor.redraw(); } else clearSel();
  }
  if (e.key === "f" && world) world.view.fill();
  if (e.ctrlKey && e.key === "s" && inEditor) { e.preventDefault(); editor.save(); }
  if (inEditor) {
    const map = { "1": "select", "2": "road", "3": "build", "4": "erase" };
    if (map[e.key]) editor.setTool(map[e.key], editor.buildType);
  }
});

// 调试句柄
window.citysim = {
  store, get net() { return net; }, get world() { return world; },
  get editor() { return editor; }, get assets() { return assets; },
  pick: onPick, get selected() { return selected; },
};

// ── 新场景：空白地图，直接进编辑器画 ────────────────────────────────
async function newScene() {
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
  editor.doc.load(blank);
  editor.name = name;
  editor.view.setWorld(editor.doc.canvas);
  editor.view.fill();
  editor.redraw();
  editor.ui.setScene(name, editor.doc.stats());
  toast(`空白地图 —— 先画路，再摆房。Ctrl+S 保存为 ${name}`);
}

// ── 场景列表 ────────────────────────────────────────────────────────
async function toggleScenes() {
  const box = $("mList");
  if (!box.classList.contains("hide")) return box.classList.add("hide");
  const list = await (await fetch("/api/scenes")).json();
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

// ── 真菜单：进来不自动开游戏，等玩家选 ──────────────────────────────
// ★ 以前是无条件 play() —— 菜单只是一闪而过，等于没有菜单。
//   （#play / #editor 两个 hash 仍然直达，截图和演示要用。）
if (location.hash === "#editor") openEditor();
else if (location.hash === "#play") play();
// 否则就停在菜单上
