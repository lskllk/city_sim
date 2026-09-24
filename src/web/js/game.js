/** game.js —— 游戏这一侧的全部接线。
 *
 *   连后端 → 铺世界 → 四角 HUD → 详情页 → 点击 → 每帧推进 */
import { $, esc, app, store, toast, show, ensureAssets,
         setStatus, rememberLast } from "./core.js";
import { SPEEDS } from "./zh.js";
import { U } from "./view.js";
import { Net } from "./net.js";
import { World } from "./world.js";
import { openSheet, closeSheet, renderQueue, infoTabs, infoPage,
         infoSub, personPage, shopPage, homePage } from "./ui.js";

export async function play(sceneName) {
  // ★ 打开哪个场景，必须【说得出名字】。
  //   以前"继续"不带名字 → 不 reset → 后端那个进程从早跑到晚，
  //   于是"打开的场景和我编辑的不是同一个，而且从第 50 天开始"（用户实测）。
  //   这里定死：能拿到名字就一定重新加载它；拿不到才交给后端挑默认的。
  const last = (() => {
    try { return JSON.parse(localStorage.getItem(LS_LAST) || "null")?.scenario || ""; }
    catch { return ""; }
  })();
  const target = sceneName || last || "";
  setStatus(target ? `正在打开 ${target}…` : "正在连后端…");
  app.net = new Net(onMessage);
  try {
    const hello = await app.net.connect();

    // ★ 一律 reset，不再"名字一样就跳过"。
    //   理由：编辑器存盘之后，后端内存里那份还是旧的 ——
    //   世界（第几天、谁在哪）也只有 reset 才会从场景文件重建。
    //   hello.scenario 发的是【原始参数】（默认空串），拿它和文件名比
    //   本来也不可靠（比不出来 → 该重置的没重置）。
    if (target) await app.net.send("reset", { scenario: target });

    // reset 之后后端会再推一份 hello；store 里那份是最新的。
    const h = store.hello || hello;
    store.applyHello(h);
    await loadLooks(h);            // 美术 id（后端不发，前端自己读场景）
    await startGame(h);

    // 到底开了哪一个 —— 状态栏里写清楚，不然"是不是同一个"没法判断
    const got = h.scenario || target || "默认场景";
    const when = new Date().toLocaleString("zh-CN",
      { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    rememberLast(target || "默认场景", when);
    setStatus(`已打开 ${target || "默认场景"} · ${h.n_npc ?? "?"} 人 · 第 ${h.day ?? 1} 天`, "ok");
  } catch (e) {
    setStatus(String(e.message || e), "bad");
  }
}

export async function startGame() {
  if (!app.world) {
    const a = await ensureAssets();
    await a.preloadMap();
    fillEntSizes(a);        // 摆位要用占地尺寸（见 layout.js）—— 先填再建世界
    app.world = await new World($("stage"), store, $("labels"), a).init();
    app.world.onSelect = onPick;
    app.world.view.setWorld(store.canvas);
    startLoop();
  }
  show("game");
  // ★ 进场看【一个街区】，不是整座城。
  //   铺满整城（fill）的时候 k≈0.1：一个人才 1.5 米宽 → 屏幕上 1.5 像素 ✗
  //   高亮/名牌全在，但你看不见；悬停也等于瞎指（判定半径会涨到 260 米）。
  //   这里让【短边】看到 ~80 米 —— 人 15 像素、房子看得清门在哪。
  const vv = app.world.view, [vw2, vh2] = vv.viewport();
  const shop = store.myShop();
  const c = shop ? [shop.x + shop.w / 2, shop.y + shop.h / 2]
                 : [store.canvas.w / 2, store.canvas.h / 2];
  vv.centerOn(c[0], c[1], Math.min(vw2, vh2) / (STREET_M * U));
  syncSpeed();
}

/** 进场时短边看到多少米。80 米 ≈ 一个街区：人看得清、房子看得清门。
 *  ★ 改这个数就是改默认缩放。调小 = 更近（看得细），调大 = 更远（看得广）。 */
const STREET_M = 80;

/** 把物品的【世界占地尺寸】填进 store（单位米）。
 *
 *  ★ 为什么必须要有：`pos` 是「脚底那个点」，只夹 0~1 的话点在墙内、
 *    半个图形挂在墙外（实测："家具超出了房屋边界"）。
 *    真正的边界要按每件东西的占地算 —— 尺寸只在美术清单里，所以这一步
 *    是"读美术"，不是"读世界"。
 *
 *  清单里物品世界贴图是 sub="iworld"；空态是 iempty（同尺寸，跳过）。
 *  作者尺寸是 2× 画的 → 除 2 才是实际米数（和 artSize 同一套规矩）。
 */
function fillEntSizes(a) {
  const out = {};
  for (const it of a?.manifest?.assets || []) {
    if (it.sub !== "iworld" || !it.file) continue;
    const ty = it.file.replace(/^.*\//, "").replace(/\.svg$/, "");
    // ★ 要【米】：作者尺寸 2× 画的 → 除 2 得世界像素 → 再除 U 才是米。
    //   layout.js 的 STRIDE/PAD/墙宽全是米，喂像素进去等于把东西放大 12 倍。
    out[ty] = [(it.w || 16) / 2 / U, (it.h || 16) / 2 / U];
  }
  store.entSize = out;
}

/** 拿每个人的【美术 id】（art 里的 8 个之一）。
 *
 *  ★ 后端的快照【不发 look】—— 它不知道美术，也不该知道。
 *    但这是前端的事，前端自己就能拿到：直接读场景文件（GET /api/scene 就是
 *    编辑器存的那份原文件），里面有 npcs[].look。
 *    不改后端、不加接口，走已有的一条路。
 *
 *  场景里没填 look 的人（现在大部分没填）由 store.lookOf 稳定分配一个。
 */
async function loadLooks(hello) {
  try {
    const list = await (await fetch("/api/scenes", { cache: "no-store" })).json();
    const name = String(hello?.scenario || "").split("/").pop() || list.last;
    if (!name) return;
    const scene = await (await fetch("/api/scene?name=" + encodeURIComponent(name),
                                   { cache: "no-store" })).json();
    store.looks = Object.fromEntries((scene.npcs || [])
      .filter(n => n.id && n.look).map(n => [n.id, n.look]));
    // 家具的【相对位置】（编辑器摆的，0~1 比值）。后端读到也不认 —— 这是前端
    // 的事，和 look 同一条路：自己读场景文件。没摆过的由 layout.js 自动码一排。
    store.entPos = Object.fromEntries((scene.entities || [])
      .filter(e => e.id && Array.isArray(e.pos) && e.pos.length >= 2)
      .map(e => [e.id, [+e.pos[0], +e.pos[1]]]));
  } catch { /* 拿不到就用兜底分配，不至于黑屏 */ }
}

/** 详情页的壳：元素 + 暂停/恢复 + 关掉。
 *  ★ 全部经这一处 —— 免得每个页面自己记"进来时的档位"，漏一处就变成
 *    "关掉之后世界还停着"（那种 bug 很难看出来）。
 */
const shell = {
  get sheetEl() { return $("sheet"); },
  speed: () => store.speed,
  setSpeed(s) { setSpeed(s); },
  pause() { if (store.speed !== "pause") this.setSpeed("pause"); },
  closeSheet() { closeSheet(shell); },
};
$("veil").onclick = () => shell.closeSheet();

let _looping = false;
export function startLoop() {
  if (_looping) return;
  _looping = true;
  let last = performance.now();
  const step = () => {
    const now = performance.now();
    // 夹一下 dt：切标签页回来时它可能是几十秒，不夹的话人会瞬间冲出去
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    if (!$("hud").classList.contains("hide")) app.world?.frame(dt);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

let _hudAt = 0;
function onMessage(msg) {
  // ★ 处理 hello。以前这里只认 snapshot / __closed，
  //   于是 reset 之后后端推的那份新 hello 被【丢掉】——
  //   store 里还是上一个场景的 locations/map/companies，
  //   症状就是「打开的场景和我编辑的不是同一个」（几何是旧的）。
  if (msg.type === "hello") { store.applyHello(msg); return; }
  if (msg.type === "snapshot") {
    store.applySnapshot(msg);
    $("gDay").textContent = `第 ${msg.day} 天`;
    $("gClock").textContent = msg.clock || "--:--";
    // HUD 8Hz 重建 —— 60Hz 会把滚动位置撞掉（队列的 DOM 也不该每帧重建）
    if (performance.now() - _hudAt > 120) {
      _hudAt = performance.now();
      paintMe();
      paintQueue();
    }
    if (msg.speed && msg.speed !== store.speed) syncSpeed();
  } else if (msg.type === "__closed") {
    setStatus("后端断开了", "bad"); show("menu");
  }
}

/** 左上角那张纸 —— **永远是我**，不是"我正在看谁"。
 *
 *  ★ 这是"从上帝变成一个人"最直接的一处：上帝模式里左上角跟着选中的
 *    NPC 变；一个人只有自己这一张纸。
 *    接管之前的兜底：没接管任何人时退化成"老板视角"，显示我的店。
 */
function paintMe() {
  const me = store.npcs.get(store.player);
  if (me) {
    $("meName").textContent = me.name + (me.role ? " · " + me.role : "");
    $("meMoney").innerHTML = `${me.money ?? "—"}<span class="d">元</span>`;
    $("meBars").innerHTML = bars(me.signals);
    $("meAuto").textContent = "";
  } else {
    const shop = store.myShop();
    $("meName").textContent = shop ? (store.locations[shop.id]?.name || "我的店")
                                   : "还没接管任何人";
    $("meMoney").innerHTML = `—<span class="d">元</span>`;
    $("meBars").innerHTML = "";
    $("meAuto").textContent = "先看世界跑起来";
  }
  $("nCount").textContent = (store.me?.notebook || []).length;
}

/** 行动队列。数据源是 runner 的队列（现在还没有 → 先给空态）。 */
function paintQueue() {
  const q = store.me?.queue || [];
  renderQueue($("meAct"), {
    act: store.me?.act || null,
    queue: q,
    hint: store.player ? "没在做什么 —— 点地图走过去" : "还没接管任何人",
  });
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

export function clearSel() { app.selected = ""; store.focus = ""; closeSheet(shell); }

/** 点地图：人 → 看那个人；建筑 → 走过去；空地 → 走过去。
 *  ★ "走过去"这一步【现在先不发指令】—— 用户说了先做界面，后端接线放后面。
 *    所以现在只 toast 一句，让人知道点中了什么。 */
export function onPick(hit) {
  if (!hit) return clearSel();
  if (hit.startsWith("ent:")) {
    const e = store.entities.get(hit.slice(4));
    return toast((e?.name || e?.item_type || "东西") + " ¥" + (e?.price ?? 0));
  }
  if (hit.startsWith("loc:")) {
    const id = hit.slice(4);
    return toast("走去 " + (store.locations[id]?.name || id) + "（导航还没接）");
  }
  openPerson(hit);
}

/** 开一个人的页 —— 只能看到"我认识的"。 */
function openPerson(id) {
  const npc = store.npcs.get(id);
  if (!npc) return;
  store.focus = id; app.selected = id;
  app.net?.send("select", { npc: id });            // 让后端把记忆带过来
  openSheet(shell, { kind: "person", title: esc(npc.name || "某居民"),
                       sub: "你记得他什么", html: personPage(npc, store.me || {}, store) });
}
/** 改档位。
 *
 *  ★ 先把界面改掉，再去告诉后端 —— 不要 await。
 *
 *  原来是 `await net.send(...)` 之后才改界面：而 net.send 要等后端带着同一个
 *  req_id 回一条消息，等不到就 4 秒超时兜底（net.js）。后端的帧又是
 *  「状态没变就不推」的 —— 档位改了它不觉得该推帧，那个确认要等到下一次
 *  别的变化才搭车过来：点一下 1×，界面要等三秒才亮。
 *
 *  档位是【界面自己就该立刻知道】的事（按下就是按下了），后端只是执行方。
 *  真要是没生效，onMessage 里那条 `msg.speed !== store.speed` 会把界面拉回真值。
 */
function setSpeed(code) {
  store.speed = code;
  syncSpeed();
  app.net?.send("set_speed", { speed: code });
}

function syncSpeed() {
  const host = $("gSpeed"); host.innerHTML = "";
  for (const [code, label] of SPEEDS) {
    const b = document.createElement("button");
    b.textContent = label;
    if (code === store.speed) b.classList.add("on");
    b.onclick = () => setSpeed(code);
    host.appendChild(b);
  }
}

/** 我知道的信息 —— 情报 / 账本 / 人。三个页签共用一张详情页。 */
function openInfo(tab) {
  const tabs = infoTabs(tab);
  openSheet(shell, { kind: "info", tab, title: "我知道的信息", sub: infoSub(tab),
                     tabs, html: infoPage(tab, store.me || {}, store) });
  for (const b of $("sheet").querySelectorAll("[data-tab]"))
    b.onclick = () => openInfo(b.dataset.tab);
  // 点常客墙/人列表里的人 → 开那个人的页
  for (const el of $("sheet").querySelectorAll("[data-npc]"))
    el.onclick = () => openPerson(el.dataset.npc);
}

function openMyShop() {
  openSheet(shell, { kind: "shop", title: "公司管理", sub: "你的店",
                     html: shopPage(store) });
}
function openMyHome() {
  openSheet(shell, { kind: "home", title: "我的家", sub: "吃 / 睡 / 上",
                     html: homePage(store) });
  for (const el of $("sheet").querySelectorAll("[data-use]"))
    el.onclick = () => toast("用它（还没接）");
}

$("gInfo").onclick = () => openInfo("nb");
$("gShop").onclick = openMyShop;
$("gHome2").onclick = openMyHome;
$("gSave").onclick = () => toast("存档还没做");
$("gSet").onclick = () => openSheet(shell, { kind: "set", title: "设置", narrow: true,
  html: '<h4 class="sec">显示</h4><div class="card">'
      + '<div class="row"><span class="lab">界面缩放</span><span class="mono">'
      + Math.round((parseFloat(getComputedStyle(document.documentElement)
          .getPropertyValue('--ui')) || 1) * 100) + '%</span></div></div>'
      + '<h4 class="sec">游戏</h4><div class="card">'
      + '<div class="row"><span class="lab">自动生理</span>'
      + '<span class="dim" style="font-size:11px">很饿会自己吃饭</span></div></div>' });

$("gMenu").onclick = () => { app.selected = ""; store.focus = ""; show("menu"); };
