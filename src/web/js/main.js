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

// ★ 版本戳：显示在编辑器顶栏。
//   起因：前端没有构建步骤，改完 JS 浏览器可能还拿着旧的模块 ——
//   于是"我这边好了、你那边没好"，来回问好几轮。
//   现在报 bug 时顺便说一句戳，就知道手上是哪一版。
//   （每次改 JS 记得把它 +1）
const BUILD = "r5";

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
        $("eStats").textContent = `${stats.nodes}节点 ${stats.edges}路 ${stats.buildings}房`;
      },
      setStats: (stats) => {
        $("eStats").textContent = `${stats.nodes}节点 ${stats.edges}路 ${stats.buildings}房`;
      },
      setDirty: (d) => { $("eDirty").textContent = d ? " •" : ""; },
      setUndo: (n) => { $("eUndo").textContent = n ? `↶${n}` : ""; },
      setCursor: (snap) => { $("eSnapLabel").textContent = editor.snapText() || "—"; },
      version: () => { $("eVer").textContent = BUILD; },
      openBuilding: (bid) => openBuilding(bid),   // 地图上点建筑 → 跳过来
      setTool: (t) => {
        for (const b of $("eTool").children) b.classList.toggle("on", b.dataset.tool === t);
        renderPalette();          // 调色盘那格的高亮跟着走
      },
    };
    editor = await new Editor($("ecanvas"), $("elabels"), a, ui).init();
    ui.version();
    await buildPalettes();
    ui.setTool("select");
    // 类别 tab
    for (const b of $("eTabs").children)
      b.onclick = () => {
        curCat = b.dataset.cat;
        for (const x of $("eTabs").children) x.classList.toggle("on", x === b);
        renderPalette();
      };
    // 吸附 / 栅格 复选框 + 栅格尺寸（整米）
    const wire = (id, fn) => {
      const lab = $(id), cb = lab.querySelector("input");
      cb.onchange = () => { lab.classList.toggle("on", cb.checked); fn(cb.checked); editor.redraw(); };
    };
    wire("eSnapNet", v => { editor.doc.netSnap = v; });
    wire("eSnapGrid", v => { editor.doc.gridSnap = v; });
    $("eGridSize").onchange = (e) => {
      editor.doc.gridM = Math.max(1, Math.round(+e.target.value || 1));
      e.target.value = editor.doc.gridM;
      editor.redraw();
    };
    editor.view.el.addEventListener("pointermove", (e) => {
      const r = editor.view.el.getBoundingClientRect();
      const [x, y] = editor.view.toWorld(e.clientX - r.left, e.clientY - r.top);
      $("eXY").textContent = `${Math.round(x)},${Math.round(y)}`;
      $("eSnapLabel").textContent = editor.snapText() || "";
    });
  }
  show("editor");
  const name = await editor.openLatest();
  toast(`打开 ${name}（最近编辑的那张）`);
}

/** 三个类别的调色盘。切 tab 就换一屏，都平铺，不滚动。
 *
 *  每一格带一个 act：
 *    width  道路宽度（点一下改画笔，接着画）
 *    bld    建筑类型（切到「摆放」）
 *    prop   环境物件（切到「摆放」）
 *  ★ 车【不算场景资产】，两边都不给 —— 它是模拟里跑出来的，不是摆上去的。
 */
let PALETTE = { bld: [], road: [], env: [], area: [] };
let curCat = "bld";

const PROP_ZH = { tree_s: "小树", tree_m: "中树", tree_l: "大树",
                  bush_1: "灌木", bush_2: "矮丛", bench: "长椅", lamp: "路灯",
                  bin: "垃圾桶", flowerbed: "花坛" };

async function buildPalettes() {
  const cat = await (await fetch("/api/catalog", { cache: "no-store" })).json();
  const m = await fetchManifest();
  const prop = (a) => ({ act: "prop", key: a.name,
                         label: PROP_ZH[a.name] || a.name, sub: `${a.w}×${a.h}`,
                         hint: `props/${a.name}.svg` });
  // 车不进调色盘：车是模拟里跑的，不是摆上去的场景资产
  const props = m.assets.filter(a => a.sub === "props" && !/^car_/.test(a.name));

  PALETTE.bld = cat.buildings.map(b => ({
    act: "bld", key: b.type, label: b.name, sub: b.kind,
    hint: `${b.type} · 容量 ${b.capacity} · 默认 ${b.size[0].toFixed(1)}×${b.size[1].toFixed(1)} m`,
  }));
  PALETTE.road = [3, 4, 6, 8].map(w => ({
    act: "width", key: String(w), label: `${w} 米`,
    sub: w <= 3 ? "小巷" : w <= 4 ? "标准" : w <= 6 ? "大路" : "主干道",
    hint: "画路用的宽度；改完接着画",
  }));
  PALETTE.env = props.map(prop);
  // 地面区域：玩法后面再说，先把这几个用途预留出来
  PALETTE.area = [
    { act: "area", key: "farm", label: "农田", sub: "借 dirt",
      hint: "点节点围出闭合多边形；点回第一个节点闭合" },
    { act: "area", key: "concrete", label: "水泥地", sub: "借 plaza",
      hint: "同上" },
    { act: "area", key: "tile", label: "地砖", sub: "借 plaza",
      hint: "同上" },
  ];
  renderPalette();
}

function renderPalette() {
  const host = $("ePalette");
  host.innerHTML = "";

  for (const it of (PALETTE[curCat] || [])) {
    const b = document.createElement("button");
    b.dataset.key = it.key;
    b.title = it.hint || "";
    b.innerHTML = `${it.label}<span class="k">${it.sub || ""}</span>`;
    const on = (it.act === "bld" && editor.buildType === it.key)
            || (it.act === "width" && String(editor.roadWidth) === it.key)
            || (it.act === "prop" && editor.propName === it.key)
            || (it.act === "area" && editor.areaKind === it.key && editor.tool === "area");
    if (on) b.classList.add("on");
    b.onclick = () => {
      // 点调色盘 = 进那个状态。再点一次同一格 = 退回「选择」。
      const same = (it.act === "bld" && editor.buildType === it.key)
                || (it.act === "prop" && editor.propName === it.key)
                || (it.act === "area" && editor.areaKind === it.key && editor.tool === "area")
                || (it.act === "width" && String(editor.roadWidth) === it.key && editor.tool === "road");
      if (same) { editor.buildType = ""; editor.propName = ""; editor.setTool("select"); }
      else if (it.act === "bld") { editor.propName = ""; editor.buildType = it.key; editor.setTool("place", it.key); }
      else if (it.act === "prop") { editor.buildType = ""; editor.propName = it.key; editor.setTool("place"); }
      else if (it.act === "area") { editor.areaKind = it.key; editor.setTool("area"); }
      else { editor.roadWidth = +it.key; editor.setTool("road"); }
      renderPalette();
    };
    host.appendChild(b);
  }
}


// ══ 接线 ══════════════════════════════════════════════════════════════
// 模式切换
for (const b of $("eModes").children)
  b.onclick = () => {
    const m = b.dataset.mode;
    closePeople(); closeBuilding();
    if (m === "people") openPeople();
    else if (m === "building") openBuilding();
    else closePeople();
  };
$("pAdd").onclick = newNpc;

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
// ★ 不传第二个参数！传 editor.buildType 的话：setTool("select") 先清空，
//   紧接着 `if (buildType)` 又把它塞回来 —— 点「选择」调色盘不取消高亮。
for (const b of $("eTool").children)
  b.onclick = () => editor.setTool(b.dataset.tool);

window.addEventListener("keydown", (e) => {
  const inEditor = !$("editor").classList.contains("hide");
  if (e.key === "Escape") {
    // Esc = 同一个 cancelGesture（和右键一样），不只是清选中
    if (inEditor) editor.deselect(); else clearSel();
  }
  if (e.key === "f" && world) world.view.fill();
  if (e.ctrlKey && e.key === "s" && inEditor) { e.preventDefault(); editor.save(); }
  if ((e.key === "Delete" || e.key === "Backspace") && inEditor) {
    if (editor.deleteSelected()) e.preventDefault();
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && inEditor) {
    e.preventDefault(); editor.undo();
  }
  if (inEditor) {
    const map = { "1": "select", "2": "erase" };
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

// ══ 人物设计 ══════════════════════════════════════════════════════════
//  ★ 人物数据本来就在场景里（scene.npcs），所以它是【场景编辑器的一个模式】，
//    不是另开一个地方。保存场景 = 保存这份名单。
//    右边编辑栏里所有「可选项」都来自 /api/npc-parts（内核侧的配置 + 美术），
//    前端不硬编码任何一份 —— 改 config/ 或 art/ 这里就跟着变。
let PARTS = null;            // /api/npc-parts
let npcSel = "";             // 选中的人 id
let draft = null;            // 正在编辑的草稿（没保存前不动场景）

async function openPeople() {
  if (!PARTS) {
    PARTS = await (await fetch("/api/npc-parts", { cache: "no-store" })).json();
    // ★ 在这里就把「有哪些长相」记下来。
    //   原来是 renderNpcForm() 里才赋值，而 renderPeople() 是【先建列表、后调表单】——
    //   建列表时 PARTS_LOOK 还是空的，于是每个人的头像都回退成默认那个（踩过）。
    PARTS_LOOK = new Set((PARTS.looks || []).map((l) => l.id));
  }
  for (const b of $("eModes").children) b.classList.toggle("on", b.dataset.mode === "people");
  $("eplace").classList.add("hide");
  $("ePeople").classList.remove("hide");
  editor.view.el.style.cursor = "default";
  npcSel = ""; draft = null;
  renderPeople();
}

function closePeople() {
  $("ePeople").classList.add("hide");
  $("eplace").classList.remove("hide");
  editor.hoverLoc = "";
  editor.view.el.style.cursor = "crosshair";
  for (const b of $("eModes").children) b.classList.toggle("on", b.dataset.mode === "map");
}

function renderPeople() {
  const list = editor.doc.npcs;
  $("pCount").textContent = list.length + " 人";
  const host = $("pList");
  host.innerHTML = "";
  if (!list.length) host.innerHTML = '<div class="none">还没有人</div>';
  for (const n of list) {
    const b = document.createElement("button");
    const face = PARTS_LOOK.has(n.look) ? n.look : "me";
    b.innerHTML = '<img src="/art/portraits/' + face + '.svg">'
      + '<span class="nm">' + esc(n.name || "(无名)") + "</span>"
      + '<span class="tag2">' + (n.gender === "female" ? "女" : "男") + "</span>";
    if (n.id === npcSel) b.classList.add("on");
    b.onclick = () => { npcSel = n.id; draft = null; renderPeople(); };
    // ★ 悬浮 → 在地图上高亮他的住处
    b.onmouseenter = () => { editor.hoverLoc = n.home || ""; editor.redraw(); };
    b.onmouseleave = () => { editor.hoverLoc = ""; editor.redraw(); };
    host.appendChild(b);
  }
  renderNpcForm();
}

let PARTS_LOOK = new Set();
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function newNpc() {
  npcSel = "";
  draft = { name: "", gender: "female", birthday: "", home: "", role: "",
            money: 100, personality: {}, traits: {}, look: "me" };
  renderPeople();
}

function renderNpcForm() {
  const host = $("pForm");
  const cur = draft || (npcSel ? editor.doc.npcs.find((n) => n.id === npcSel) : null);
  if (!cur) {
    host.innerHTML = '<div class="none" style="color:var(--ink2);font-size:13px;'
      + 'padding:60px 0;text-align:center">点左边选一个人，或者点「+ 新增」</div>';
    return;
  }
  const isNew = !!draft;
  const tags = new Set(Array.isArray(cur.traits?.tags) ? cur.traits.tags : []);
  const per = cur.personality || {};
  const looks = PARTS?.looks || [];
  PARTS_LOOK = new Set(looks.map((l) => l.id));

  const curLook = (cur.look || "me");
  // ★ 只要图，不要名字 —— 头像就是头像
  const faceRow = looks.map((l) =>
    '<button data-look="' + l.id + '" title="' + esc(l.name) + '" class="'
    + (curLook === l.id ? "on" : "") + '">'
    + '<img src="/art/portraits/' + l.id + '.svg"></button>').join("");

  // 住所：只显示"现在住哪"，改地址靠【在地图上点】
  const homeNow = cur.home
    ? esc(editor.doc.nameOf(cur.home) || cur.home)
      + "　" + (editor.doc.residents(cur.home) - 1) + "/" + editor.doc.homeCapacity(cur.home)
    : "（没有住处）";

  const perRow = (PARTS?.signals || []).map((s) =>
    '<div class="row"><label>' + (SIGNAL_ZH[s] || s) + '</label>'
    + '<input type="number" step="0.1" min="0" data-per="' + s + '" value="'
    + (per[s] ?? 1) + '"></div>').join("");

  const traitRow = (PARTS?.traits || []).map((x) =>
    '<button data-trait="' + x + '" class="' + (tags.has(x) ? "on" : "") + '">' + x + "</button>").join("");

  host.innerHTML =
    "<h2>" + (isNew ? "新增" : esc(cur.name || "(无名)")) + "</h2>"

    + '<div class="row"><label>头像</label><div class="inline">'
    + '<img class="faceNow" id="pFaceNow" src="/art/portraits/' + curLook + '.svg">'
    + '<button class="ghost" id="pFaceEdit">编辑头像</button></div></div>'
    + (faceRow ? '<div class="row"><label></label>'
        + '<div class="facepop hide" id="pFacePop">' + faceRow + "</div></div>" : "")

    + '<div class="row"><label>姓名</label><div class="inline">'
    + '<input id="pName" type="text" value="' + esc(cur.name || "") + '"'
    + (isNew ? "" : " disabled") + ">"
    + (isNew ? '<button class="ghost" id="pRollName">骰</button>' : "")
    + "</div></div>"

    + '<div class="row"><label>生日</label><div class="inline">'
    + '<input id="pBirth" type="date" value="' + esc(cur.birthday || "") + '"'
    + (isNew ? "" : " disabled") + ">"
    + (isNew ? '<button class="ghost" id="pRollBirth">骰</button>' : "")
    + "</div></div>"

    + '<div class="row"><label>性别</label><div class="inline">'
    + '<select id="pGender"' + (isNew ? "" : " disabled") + ">"
    + (PARTS?.genders || []).map((g) => '<option value="' + g + '"'
        + (cur.gender === g ? " selected" : "") + ">"
        + (g === "female" ? "女" : "男") + "</option>").join("")
    + "</select></div></div>"

    + '<div class="row"><label>住所</label><div class="inline">'
    + '<span id="pHomeNow" class="hn">' + homeNow + "</span>"
    + '<button class="ghost" id="pPickHome">地图点选</button>'
    + (cur.home ? '<button class="ghost" id="pClearHome">×</button>' : "")
    + "</div></div>"

    + '<div class="row"><label>角色</label><input id="pRole" type="text" value="'
    + esc(cur.role || "") + '"></div>'
    + '<div class="row"><label>初始钱</label><input id="pMoney" type="number" step="1" value="'
    + (cur.money ?? 100) + '"></div>'

    + '<div class="sec">性格</div>' + perRow
    + '<div class="sec">特性</div><div class="chips" id="pTraits">' + traitRow + "</div>"

    + '<div class="bar2"><button class="primary" id="pSave">'
    + (isNew ? "存进场景" : "保存修改") + "</button>"
    + '<button class="ghost" id="pRandom">随机</button><span class="sp"></span>'
    + (isNew ? "" : '<button class="danger" id="pDel">删掉</button>') + "</div>";

  const pop = $("pFacePop");
  const fe = $("pFaceEdit");
  if (fe) fe.onclick = (e) => {
    e.stopPropagation();
    pop?.classList.toggle("hide");
  };
  for (const b of host.querySelectorAll("#pFacePop button"))
    b.onclick = () => { cur.look = b.dataset.look; renderNpcForm(); };
  for (const b of host.querySelectorAll("#pTraits button"))
    b.onclick = () => {
      const s = new Set(Array.isArray(cur.traits?.tags) ? cur.traits.tags : []);
      if (s.has(b.dataset.trait)) s.delete(b.dataset.trait); else s.add(b.dataset.trait);
      cur.traits = { ...(cur.traits || {}), tags: [...s] };
      renderNpcForm();
    };
  const on = (id, fn) => { const e = $(id); if (e) e.onclick = fn; };
  on("pRollName", () => { cur.name = randName($("pGender").value); renderNpcForm(); });
  on("pRollBirth", () => { cur.birthday = randBirthday(); renderNpcForm(); });
  on("pRandom", () => {
    cur.name = randName($("pGender").value);
    cur.birthday = randBirthday();
    cur.traits = { ...(cur.traits || {}), tags: randTraits() };
    renderNpcForm();
  });
  on("pSave", async () => {
    const spec = {
      name: ($("pName")?.value || cur.name || "").trim(),
      gender: $("pGender").value,
      birthday: ($("pBirth")?.value || cur.birthday || "").trim(),
      home: cur.home || "",
      role: $("pRole").value.trim(),
      money: Number($("pMoney").value) || 0,
      personality: Object.fromEntries([...host.querySelectorAll("[data-per]")]
        .map((e) => [e.dataset.per, Number(e.value) || 1]).filter(([, v]) => v !== 1)),
      traits: cur.traits || {},
      look: cur.look || "me",
      tell_bias: cur.tell_bias ?? 1,
      init: cur.init || {},
    };
    if (isNew && !spec.name) return toast("先填个姓名");
    if (!spec.birthday) spec.birthday = randBirthday();
    editor.pushUndo();
    npcSel = editor.doc.upsertNpc(spec, isNew ? "" : npcSel);
    draft = null;
    editor.doc.dirty = true;
    editor.ui.setDirty?.(true);
    renderPeople();
    await editor.save();          // ★ 写盘，不然刷新就没了（同建筑面板）
    toast(isNew ? "加上了 " + spec.name : "已保存到 " + (editor.name || "场景"));
  });
  on("pPickHome", () => {
    // ★ 在地图上点一个住宅。满了就当场拒绝。
    toast("在地图上点一栋住宅");
    editor.pickBuilding((bid) => {
      if (!bid) return toast("那儿没有建筑");
      const r = editor.doc.canMoveIn(bid, npcSel || "");
      if (!r.ok) return toast(r.why);
      cur.home = bid;
      renderNpcForm();
      toast("住址 → " + (editor.doc.nameOf(bid) || bid) + "（" + (r.used + 1) + "/" + r.cap + "）");
    });
  });
  on("pClearHome", () => { cur.home = ""; renderNpcForm(); });
  on("pDel", () => {
    if (!confirm("真的删掉 " + cur.name + "？")) return;
    editor.pushUndo();
    editor.doc.removeNpc(npcSel);
    npcSel = ""; draft = null;
    editor.ui.setDirty?.(true);
    renderPeople();
  });
}

const SIGNAL_ZH = { energy: "精力", hunger: "饿", bladder: "憋", hp: "健康", fun: "想玩" };
const randPick = (a) => a[Math.floor(Math.random() * a.length)];
function randName(g) {
  const pool = (PARTS?.given || {})[g === "male" ? "male" : "female"] || [];
  return randPick(PARTS?.surnames?.length ? PARTS.surnames : ["王"])
       + randPick(pool.length ? pool : ["明"]);
}
function randBirthday() {
  const y = 1955 + Math.floor(Math.random() * 45);
  const m = 1 + Math.floor(Math.random() * 12);
  const d = 1 + Math.floor(Math.random() * 28);
  return y + "-" + String(m).padStart(2, "0") + "-" + String(d).padStart(2, "0");
}
function randTraits() {
  const pool = [...(PARTS?.traits || [])];
  const out = [];
  for (let i = 0; i < 2 && pool.length; i++)
    out.push(...pool.splice(Math.floor(Math.random() * pool.length), 1));
  return out;
}

// ══ 建筑编辑 ══════════════════════════════════════════════════════════
//  ★ 建筑【没有"新增"】—— 房子是在地图上摆的（画路 → 摆房），这里只编辑。
//    右边能改的是"这栋楼是什么、归谁、里面摆了什么"。
let BPARTS = null;          // /api/building-parts
let bldSel = "";            // 选中的建筑 id

async function openBuilding(pick) {
  if (!BPARTS) BPARTS = await (await fetch("/api/building-parts", { cache: "no-store" })).json();
  for (const b of $("eModes").children) b.classList.toggle("on", b.dataset.mode === "building");
  $("eplace").classList.add("hide");
  $("ePeople").classList.add("hide");
  $("eBld").classList.remove("hide");
  editor.hoverLoc = "";
  bldSel = pick || "";
  $("popVeil")?.remove();
  renderBuildings();
}

function closeBuilding() {
  $("eBld").classList.add("hide");
  $("eplace").classList.remove("hide");
  editor.hoverLoc = "";
}

function renderBuildings() {
  const D = editor.doc;
  const ids = Object.keys(D.buildings).sort((a, b) => D.nameOf(a).localeCompare(D.nameOf(b), "zh"));
  $("bCount").textContent = ids.length + " 栋";
  const host = $("bList");
  host.innerHTML = "";
  for (const bid of ids) {
    const b = D.buildings[bid];
    const t2 = D.types[b.type] || {};
    const el = document.createElement("button");
    el.innerHTML = '<span class="nm">' + esc(D.nameOf(bid) || bid) + "</span>"
      + '<span class="tag2">' + esc(t2.kind || "") + "</span>";
    if (bid === bldSel) el.classList.add("on");
    el.onclick = () => { bldSel = bid; renderBuildings(); };
    // ★ 悬浮 → 在地图上高亮整栋楼
    // ★ 改完 hoverLoc 要重绘 —— 不然地图上什么都不亮（踩过）
    el.onmouseenter = () => { editor.hoverLoc = bid; editor.redraw(); };
    el.onmouseleave = () => { editor.hoverLoc = ""; editor.redraw(); };
    host.appendChild(el);
  }
  renderBldForm();
}

function renderBldForm() {
  const host = $("bForm");
  const D = editor.doc;
  if (!bldSel || !D.buildings[bldSel]) {
    host.innerHTML = '<div class="none2" style="text-align:center;padding:60px 0">'
      + "点左边选一栋楼</div>";
    return;
  }
  const bid = bldSel, b = D.buildings[bid], tp = D.types[b.type] || {};
  const inside = (D.meta.entities || []).filter((e) => e.at === bid);
  const mine = (D.meta.companies || []).find((c) => (c.shop_list || c.shops || []).includes(bid));
  const items = BPARTS?.items || [];
  const iconOf = (ty) => (items.find((x) => x.type === ty)?.icon)
    ? "/art/items/icon_" + ty + ".svg" : "";
  const isFix = (ty) => (items.find((x) => x.type === ty)?.tags || []).includes("fixture");

  const opt = (v, label, on) =>
    '<option value="' + v + '"' + (on ? " selected" : "") + ">" + label + "</option>";
  const typeOpts = (BPARTS?.types || []).map((x) =>
    opt(x.type, esc(x.name) + "（" + esc(x.kind) + " " + x.capacity + "）", b.type === x.type)).join("");
  // ★ 权限是【读出来】的，不是选出来的 —— 由建筑类型定，public 只是
  //   「谁都能进」这个更强的例外。
  //   以前靠一个 public 开关算：非住宅 + 没标公开 = 「仅内部人员」
  //   —— 于是店铺也被写成仅内部，显然不对。
  const dwellers = D.npcs.filter((n) => n.home === bid);
  const cap = tp.capacity || 0;
  const BY_KIND = {
    home: () => (dwellers.length
      ? "只住客能进 —— " + dwellers.map((n) => n.name).join("、")
        + "（" + dwellers.length + "/" + cap + "）"
      : "只住客能进 —— 还没人住（0/" + cap + "）"),
    shop: () => "顾客能进" + (mine && mine.open != null
      ? "（" + String(mine.open).slice(0, 5) + "–" + String(mine.close).slice(0, 5) + "）"
      : "（营业时）"),
    market: () => "谁都能进",
    public: () => "谁都能进",
    clinic: () => "病人能进",
    school: () => "学生和老师能进",
    work: () => "仅员工",
    factory: () => "仅员工",
  };
  const access = D.isPublic(bid) ? "谁都能进"
    : ((BY_KIND[tp.kind] || (() => "仅内部人员"))());
  const companyName = mine ? (mine.name || mine.id) : "无";

  // 一行一件，只有【图标 + 名字】+ 右边一个数量提示 —— 点它才弹详情。
  const things = inside.length ? inside.map((e, i) => {
    const it = items.find((x) => x.type === e.type) || {};
    const fix = isFix(e.type);
    const ic = iconOf(e.type);
    const qt = fix ? "" : "×" + (e.stock ?? it.stock ?? 0);
    return '<button class="th" data-open="' + i + '" title="点开改详情">'
      + (ic ? '<img class="ic" src="' + ic + '">' : '<span class="ic"></span>')
      + '<span class="nm3">' + esc(it.name || e.type) + "</span>"
      + '<span class="qt">' + qt + "</span></button>";
  }).join("") : '<div class="none2">空着</div>';

  // 候选（和头像那个一样：点「放一件」才弹）
  const cand = items.map((x) =>
    '<button data-put="' + x.type + '" title="' + esc(x.name) + '">'
    + (x.icon ? '<img src="/art/items/icon_' + x.type + '.svg">' : '<span class="ic"></span>')
    + '<span class="nm4">' + esc(x.name) + "</span></button>").join("");

  host.innerHTML =
    "<h2>" + esc(D.nameOf(bid) || bid) + "</h2>"
    + '<div class="row"><label>类型</label><select id="bType">' + typeOpts + "</select></div>"
    + '<div class="row"><label>名字</label><input id="bName" type="text" value="'
    + esc(D.nameOf(bid) || "") + '"></div>'
    + '<div class="row"><label>占地</label><span class="hn">'
    + b.size[0].toFixed(1) + " × " + b.size[1].toFixed(1) + " m</span></div>"
    + '<div class="row"><label>权限</label><span class="hn">' + esc(access) + "</span></div>"
    + '<div class="row"><label>公司</label><span class="hn">' + esc(companyName) + "</span></div>"

    + '<div class="sec">里面的东西 <span class="dim">' + inside.length + " 件</span></div>"
    + '<div class="things">' + things + "</div>"
    + '<div class="addrow"><button id="bAdd">+ 放一件</button></div>'

    + '<div class="bar2"><button class="primary" id="bSave">保存</button>'
    + '<span class="sp"></span>'
    + '<button class="danger" id="bDel">拆掉这栋楼</button></div>';

  const on = (id, fn) => { const e2 = $(id); if (e2) e2.onclick = fn; };

  // 两个弹框住在 body 顶层（见 index.html 的注释），内容由这里填。
  $("bItemPop").innerHTML = cand;
  $("bItemPop").classList.add("hide");
  $("thingPop").classList.add("hide");
  for (const el2 of $("bItemPop").querySelectorAll("[data-put]"))
    el2.onclick = () => putItem(el2.dataset.put);

  // 「放一件」→ 弹出候选（和头像一样），点一个就放进去
  on("bAdd", () => {
    $("thingPop").classList.add("hide");          // 和"物品详情"互斥
    const pop = $("bItemPop");
    const open = pop.classList.contains("hide");
    pop.classList.toggle("hide", !open);
    let veil = $("popVeil");
    if (open) {
      if (!veil) { veil = document.createElement("div"); veil.id = "popVeil";
                   document.body.appendChild(veil); }
      veil.onclick = () => { pop.classList.add("hide"); veil.remove(); };
    } else veil?.remove();
  });
  function putItem(ty) {
    const it = items.find((x) => x.type === ty) || {};
    const fix = (it.tags || []).includes("fixture");
    editor.pushUndo();
    (D.meta.entities ||= []).push(fix
      ? { id: ty + "_" + String(Date.now()).slice(-5), at: bid, type: ty,
          owner: mine ? mine.id : undefined }
      : { id: ty + "_" + String(Date.now()).slice(-5), at: bid, type: ty,
          owner: mine ? mine.id : undefined, stock: it.stock ?? 1, price: it.price ?? 0 });
    D.dirty = true; editor.ui.setDirty?.(true);
    $("popVeil")?.remove();
    renderBldForm();
  }

  // ★ 点一行 → 弹详情框（存量 / 售价 / 删掉）。
  //   行里只放图标和名字 —— 296px 的栏塞不下"图标+名字+两个数字框+删除"。
  for (const el2 of host.querySelectorAll("[data-open]"))
    el2.onclick = () => openThing(inside[+el2.dataset.open]);

  /** 一件东西的详情框：存量 / 售价 / 删掉。家具类只有名字和"删掉"。 */
  function openThing(ent) {
    const it = items.find((x) => x.type === ent.type) || {};
    const fix = isFix(ent.type);
    const ic = iconOf(ent.type);
    const pop = $("thingPop");
    pop.innerHTML =
      '<div class="th2">' + (ic ? '<img src="' + ic + '">' : "")
      + "<div><b>" + esc(it.name || ent.type) + "</b>"
      + '<div class="id">' + esc(it.tags ? it.tags.join(" · ") : "") + "</div></div></div>"
      + (fix
        ? '<div class="row"><label>说明</label><span class="hn">家具 —— 不买卖、没有存量</span></div>'
        : '<div class="row"><label>存量</label><input id="tStock" type="number" value="'
          + (ent.stock ?? it.stock ?? 0) + '"></div>'
          + '<div class="row"><label>售价</label><input id="tPrice" type="number" step="0.5" value="'
          + (ent.price ?? it.price ?? 0) + '"></div>')
      + '<div class="bar3"><button class="primary" id="tSave">保存</button>'
      + '<span class="sp"></span><button class="danger" id="tDel">删掉</button></div>';
    pop.classList.remove("hide");
    let veil = $("popVeil");
    if (!veil) { veil = document.createElement("div"); veil.id = "popVeil";
                 document.body.appendChild(veil); }
    veil.onclick = () => { pop.classList.add("hide"); veil.remove(); };
    const close = () => { pop.classList.add("hide"); veil.remove(); };
  $("bItemPop").classList.add("hide");            // 和"放一件"的候选框互斥
    on("tSave", () => {
      editor.pushUndo();
      if (!fix) {
        ent.stock = Number($("tStock").value) || 0;
        ent.price = Number($("tPrice").value) || 0;
      }
      D.dirty = true; editor.ui.setDirty?.(true);
      close();
      renderBldForm();
    });
    on("tDel", () => {
      editor.pushUndo();
      const arr = D.meta.entities || [];
      const k = arr.indexOf(ent);
      if (k >= 0) arr.splice(k, 1);
      D.dirty = true; editor.ui.setDirty?.(true);
      close();
      renderBldForm();
    });
  }

  on("bSave", async () => {
    const name = $("bName").value.trim();
    const newType = $("bType").value;
    editor.pushUndo();
    if (name) D.names[bid] = name;
    if (D.meta.locations?.[bid]) D.meta.locations[bid].name = name || bid;
    if (newType !== b.type) {                      // 换类型：占地按新类型重算，中心不动
      const sz = D.sizeFor(newType);
      b.type = newType; b.size = sz;
      if (D.meta.locations?.[bid]) {
        D.meta.locations[bid].type = newType;
        D.meta.locations[bid].w = sz[0]; D.meta.locations[bid].h = sz[1];
        D.meta.locations[bid].x = +(b.center[0] - sz[0] / 2).toFixed(3);
        D.meta.locations[bid].y = +(b.center[1] - sz[1] / 2).toFixed(3);
      }
    }
    // ★ 权限 / 公司 不在这里写 —— 它们是读出来的（权限由类型 + public 决定，
    //   公司由 companies[].shops 决定）。以前这里会重写 public 和 shops，
    //   对着"只读"的值瞎改，反而把数据弄坏。
    D.dirty = true; editor.ui.setDirty?.(true);
    renderBuildings();
    // ★ 必须写盘。原来只改内存 —— 编辑完刷新一下改动全没了，
    //   看着就是"编辑失败"（顶栏那个「保存」才真写盘，两个按钮同名很容易混）。
    await editor.save();
    toast("已保存到 " + (editor.name || "场景"));
  });
  on("bDel", () => {
    if (!confirm("拆掉 " + (D.nameOf(bid) || bid) + "？")) return;
    editor.pushUndo();
    D.removeBuilding(bid);
    bldSel = "";
    D.dirty = true; editor.ui.setDirty?.(true);
    renderBuildings();
  });
}

// ── 真菜单：进来不自动开游戏，等玩家选 ──────────────────────────────
// ★ 以前是无条件 play() —— 菜单只是一闪而过，等于没有菜单。
//   （#play / #editor 两个 hash 仍然直达，截图和演示要用。）
//
// ★ 一定要 show("menu")：HUD 在 HTML 里默认是显示的，
//   不主动收起来，主菜单右上角就会露出游戏那排按钮（"返回菜单""我的店"）。
show("menu");
if (location.hash === "#editor") openEditor();
else if (location.hash === "#play") play();
