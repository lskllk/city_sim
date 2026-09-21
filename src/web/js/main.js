/** main.js —— 壳。
 *
 *  主菜单  →  游戏
 *  菜单里三个入口：继续（最近一次的场景）/ 选择场景 / 编辑器（还没做）
 *
 * "最近一次的场景"存在 localStorage，键里带 mtime —— 场景文件变了就当成新的。
 * （真正的场景文件服务还没做，这一步先记名字。）
 */
import { Net } from "./net.js";
import { Store } from "./store.js";
import { World } from "./world.js";
import { renderPanel } from "./panel.js";

const LS_LAST = "citysim.last";
const SPEEDS = [["pause", "停"], ["1x", "1×"], ["10x", "10×"],
                ["100x", "100×"], ["1000", "1000×"]];

const $ = (id) => document.getElementById(id);
const store = new Store();
let net = null, world = null, selected = "";

// ── 主菜单 ────────────────────────────────────────────────────────────
const last = (() => { try { return JSON.parse(localStorage.getItem(LS_LAST) || "null"); } catch { return null; } })();

function setStatus(text, cls = "") {
  const el = $("mStatus");
  el.textContent = text;
  el.className = "status " + cls;
}

$("mLast").textContent = last ? `${last.scenario} · ${last.when}` : "还没有跑过";

async function boot() {
  setStatus("正在连后端…");
  net = new Net(onMessage);
  try {
    const hello = await net.connect();
    store.applyHello(hello);
    await startGame(hello);
    setStatus(`后端已连上 · 场景 ${hello.scenario ?? "?"} · ${hello.n_npc ?? "?"} 人`, "ok");
  } catch (e) {
    setStatus(String(e.message || e), "bad");
    $("mContinue").disabled = false;         // 允许重试
  }
}

async function startGame(hello) {
  if (!world) {
    const manifest = await (await fetch("/art/manifest.json")).json();
    world = await new World($("stage"), store, document.createElement("div")).init();
    world.hud = document.createElement("div");
    world.hud.style.cssText = "position:absolute;inset:0;pointer-events:none";
    $("stage").parentElement.appendChild(world.hud);
    await world.preload(manifest);
    world.onPick = onPick;
    world.fit();
    const shop = store.myShop();
    if (shop) world.centerOn(shop.x + shop.w / 2, shop.y + shop.h / 2, 1.6);
    tickLoop();
  }
  $("menu").classList.add("hide");
  $("game").classList.remove("hide");
  // 用最近的场景名记住它（"继续"下次直接进来）
  const when = new Date().toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  localStorage.setItem(LS_LAST, JSON.stringify({ scenario: hello.scenario ?? "scene", when }));
  $("mLast").textContent = `${hello.scenario ?? "scene"} · ${when}`;
  syncSpeed();
}

let _panelAt = 0;
function onMessage(msg) {
  if (msg.type === "snapshot") {
    store.applySnapshot(msg);
    // 面板 60Hz 重建会把滚动位置和选中状态撞掉，限到 8Hz。
    // （记忆本来也只 10Hz 才带一次 —— 后端 rich_every=6）
    if (selected && performance.now() - _panelAt > 120) {
      _panelAt = performance.now();
      renderPanel($("panel"), store.npcs.get(selected) || null, store, clearSel);
    }
    $("gClock").textContent = msg.clock || "--:--";
    $("gDay").textContent = `第 ${msg.day} 天`;
    if (msg.speed && msg.speed !== store.speed) syncSpeed();
  } else if (msg.type === "__closed") {
    setStatus("后端断开了", "bad");
    $("menu").classList.remove("hide");
  }
}

function clearSel() {
  selected = "";
  store.focus = "";
  net.send("select", { npc: "" });
  renderPanel($("panel"), null, store, clearSel);
}

function onPick(hit) {
  if (!hit) { clearSel(); return; }
  if (hit.startsWith("loc:")) { toast(store.locations[hit.slice(4)]?.name || hit.slice(4)); return; }
  selected = hit;
  store.focus = hit;
  net.send("select", { npc: hit });
  renderPanel($("panel"), store.npcs.get(hit) || null, store, clearSel);
}

// ── 帧循环：Pixi 只画"看到的这一屏"，数据来多少都只是合并 ──
function tickLoop() {
  world.frame();
  requestAnimationFrame(tickLoop);
}

function syncSpeed() {
  const host = $("gSpeed");
  host.innerHTML = "";
  for (const [code, label] of SPEEDS) {
    const b = document.createElement("button");
    b.textContent = label;
    if (code === store.speed) b.classList.add("on");
    b.onclick = async () => { await net.send("set_speed", { speed: code }); store.speed = code; syncSpeed(); };
    host.appendChild(b);
  }
}

let toastTimer = 0;
function toast(text) {
  const el = $("hint");
  el.textContent = text; el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 1400);
}

// ── 顶上那排按钮 ─────────────────────────────────────────────────────
$("gMenu").onclick = () => {
  $("game").classList.add("hide");
  $("menu").classList.remove("hide");
};
$("gHome").onclick = () => {
  const shop = store.myShop();
  if (shop) world.centerOn(shop.x + shop.w / 2, shop.y + shop.h / 2, 1.6);
  else world.fit();
};
$("mContinue").onclick = boot;
$("mPick").onclick = () => { toast("场景列表还没做 —— 现在只有 config/scenes/scene.json"); // 调试句柄：控制台里能直接捅（前端没有花哨的 devtools，这个够用）
window.citysim = { store, net: () => net, world: () => world,
                   pick: onPick, get selected() { return selected; } };

boot(); };

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") clearSel();
  if (e.key === "f" && world) world.fit();
});
window.addEventListener("resize", () => { if (world) world._apply(); });

boot();
