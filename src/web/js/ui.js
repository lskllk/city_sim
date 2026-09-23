/** ui.js —— 游戏的【详情页 + 行动队列】。样式全照 proto/ui-prototype.html。
 *
 * ══ 详情页的规矩（proto 冻结的）══
 *
 *   居中 · 不透明 · 背后虚化 · **打开即暂停**
 *
 *   为什么暂停：这些页是"翻你自己的本子"，不是实时面板。
 *   世界在背后继续跑的话，你读到一半数字就变了 —— 而且"翻本子"这件事
 *   本来就不该花游戏时间。关掉页恢复原来的档位（不是恢复成 1x）。
 *
 * ══ 为什么不用右边侧栏 ══
 *
 *   右边侧栏（上一版）把地图挤窄，而且"点一个人看穿他"是**上帝模式**的做法。
 *   现在这些页是"我的东西"：我的记忆、我的店、我的家 —— 占屏幕中间才对。
 */
import { SIGNAL_ZH } from "./zh.js";
import { esc } from "./core.js";

/** 详情页的状态。openSheet 记住进来时的档位，关了要还原。 */
let _open = null;          // { kind, tab, speed }

export function sheetOpen() { return _open; }

/** 打开一张详情页。tabs 为空就没有页签。 */
export function openSheet(shell, { title, sub = "", tabs = "", html = "", narrow = false, kind = "", tab = "" }) {
  const first = _open === null;
  if (first) _open = { kind, tab, speed: shell.speed() };
  else { _open.kind = kind; _open.tab = tab; }
  shell.pause();                                  // 打开即暂停

  document.body.classList.add("open");
  const s = shell.sheetEl;
  s.className = narrow ? "narrow" : "";
  s.innerHTML =
    '<div class="sheet-hd"><h2>' + title + '</h2>'
    + (sub ? '<span class="sub">' + sub + "</span>" : "")
    + '<button class="x" id="sheetX">关闭 ✕</button></div>'
    + (tabs ? '<div class="tabs">' + tabs + "</div>" : "")
    + '<div class="sheet-bd">' + html + "</div>";
  s.querySelector("#sheetX").onclick = () => shell.closeSheet();
}

/** 关掉详情页，恢复进来时的档位。 */
export function closeSheet(shell) {
  if (document.body.classList.contains("summary")) return;
  document.body.classList.remove("open");
  shell.sheetEl.innerHTML = "";
  const sp = _open?.speed;
  _open = null;
  if (sp != null) shell.setSpeed(sp);
}

// ══════════════════════════════════════════════════════════════════════
//  行动队列（左上角，状态下面）
//  ★ 只有"正在做"那一条有进度条 —— 一眼看出你在干什么、做到哪了。
//    队列用【序号】不是项目符号 —— 它是有顺序的计划。
// ══════════════════════════════════════════════════════════════════════

const ACT_ICON = {
  walk: '<path d="M8 2v7m0 0 3 5m-3-5-3 5M5 5h6"/>',
  eat: '<path d="M4 3v6a2 2 0 0 0 4 0V3M6 9v4M11 3c-1 2-1 4 0 6v4"/>',
  sleep: '<path d="M3 11h10M4 10V6l8 4V6"/>',
  toilet: '<path d="M5 3h6v3H5zM6 6v5a2 2 0 0 0 4 0V6"/>',
  work: '<path d="M3 6h10v6H3zM6 6V4h4v2"/>',
  buy: '<path d="M3 5h2l1.5 6h6L14 5zM7 13h.01M12 13h.01"/>',
  home: '<path d="M3 9l5-4 5 4v5H3z"/>',
  idle: '<circle cx="8" cy="8" r="3"/>',
};

/** 一条任务 → 一行 HTML。now = 正在做（带进度条）。 */
export function taskRow(t, now = false) {
  const icon = ACT_ICON[t.icon] || ACT_ICON.idle;
  const svg = '<svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor"'
    + ' stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">' + icon + "</svg>";
  if (now) {
    const pct = t.total > 0 ? Math.max(0, Math.min(100, (t.prog / t.total) * 100)) : 0;
    return '<div class="now">' + svg + '<span class="lb">' + esc(t.label) + "</span>"
      + '<button class="x" data-cancel="1" title="取消">×</button></div>'
      + '<div class="prog"><i style="width:' + pct.toFixed(1) + '%"></i></div>';
  }
  return '<div class="qi' + (t.done ? " done" : "") + (t.next ? " next" : "") + '">'
    + '<span class="no">' + esc(t.no ?? "·") + "</span>" + svg
    + '<span class="lb">' + esc(t.label) + "</span>"
    + '<button class="x" data-drop="' + esc(t.id) + '" title="取消这条">×</button></div>';
}

/** 把队列画进 #paneMe 的 .actwrap。返回要挂事件的元素。 */
export function renderQueue(host, { act, queue = [], hint = "" }) {
  if (!act && !queue.length) {
    host.innerHTML = '<div class="none">' + esc(hint || "没在做什么 —— 点地图走过去") + "</div>";
    return;
  }
  let h = "";
  if (act) h += taskRow(act, true);
  const rest = queue.slice(0, 7);
  if (rest.length) {
    h += '<div class="queue"><div class="qh">接下来</div>'
      + rest.map((t, i) => taskRow({ ...t, no: i + 1, next: i === 0 })).join("") + "</div>";
  }
  host.innerHTML = h;
}

// ══════════════════════════════════════════════════════════════════════
//  四张详情页
// ══════════════════════════════════════════════════════════════════════

/** 我知道的信息：情报 / 账本 / 人，三个页签。
 *  ★ 这一页的魂是"我的记忆是旧的"—— 每条都带来源和时间，旧了褪色。 */
export function infoTabs(tab) {
  const t = (k, l) => '<button class="' + (tab === k ? "on" : "") + '" data-tab="' + k + '">' + l + "</button>";
  return t("nb", "情报") + t("ld", "账本") + t("pp", "人");
}

export function infoPage(tab, me, store) {
  if (tab === "ld") return ledgerHTML(me, store);
  if (tab === "pp") return peopleHTML(me, store);
  return notebookHTML(me, store);
}

export function infoSub(tab) {
  return { nb: "你自己的记忆。世界在变，它不会跟着变",
           ld: "你自己经手的事实，精确",
           pp: "你记得谁 —— 名字是从账本里长出来的" }[tab] || "";
}

/** 情报：一条一块，越旧的越褪色。 */
function notebookHTML(me, store) {
  const rows = [...(me.notebook || [])].sort((a, b) => b.age - a.age);
  if (!rows.length) return '<div class="dim">还没有任何情报。走过去看看，或者问问人。</div>';
  const ageCls = (d) => (d <= 0 ? "age1" : d <= 1 ? "age2" : d <= 3 ? "age3" : "age4");
  return '<div class="dim" style="font-size:12px;margin-bottom:12px">'
    + "这是你自己的记忆。世界在变，它不会跟着变 —— 想更新，就得去看或去问。</div>"
    + rows.map((n) => '<div class="nb ' + (n.chain ? "hearsay " : "") + ageCls(n.age) + '">'
      + '<div class="top"><span class="subj">' + esc(n.item) + " · " + esc(n.placeName)
      + '</span><span class="when">' + (n.age === 0 ? "今天" : n.age + " 天前") + "</span></div>"
      + '<div class="val">' + priceViz(n.value, n.prec) + "</div>"
      + '<div class="src">' + srcTag(n.source) + (n.by ? " " + esc(n.by) : "") + "</div>"
      + (n.chain ? '<div class="chain">~ 他也是听来的（传了 ' + n.chain + " 手）</div>" : "")
      + "</div>").join("");
}

/** 账本：不用表格。人 → 常客墙；每一笔 → 一张小票。 */
function ledgerHTML(me, store) {
  const by = new Map();
  for (const e of me.ledger || []) {
    if (e.npc === "me") continue;
    const v = by.get(e.npc) || { n: 0, last: -Infinity, spent: 0 };
    v.n++; v.last = Math.max(v.last, e.day); v.spent += e.qty * e.price;
    by.set(e.npc, v);
  }
  const regs = [...by.entries()].map(([id, v]) => ({ id, ...v, ago: (me.today ?? 0) - v.last }))
    .sort((a, b) => a.ago - b.ago);
  let h = '<h4 class="sec">常客墙 <span class="dim" style="font-weight:400">· 越靠右越久没来</span></h4>';
  if (!regs.length) h += '<div class="empty-row"></div>';
  else h += '<div class="regs">' + regs.map((r) => {
    const n = store.npcs.get(r.id) || {};
    const lvl = r.ago <= 0 ? 0 : r.ago <= 2 ? 1 : r.ago <= 6 ? 2 : 3;
    const heat = Math.max(6, Math.round(100 * (1 - Math.min(1, r.ago / 14))));
    return '<div class="reg" data-lvl="' + lvl + '" data-npc="' + esc(r.id) + '" title="'
      + esc(n.name || "某居民") + " · 来过 " + r.n + " 次 · 共 ¥" + r.spent.toFixed(0) + '">'
      + (r.ago === 0 ? '<span class="today"></span>' : "")
      + '<div class="face">' + miniFace(store.lookOf(n)) + "</div>"
      + '<div class="nm">' + esc(n.name || "某居民") + "</div>"
      + '<div class="heat"><i style="width:' + heat + '%"></i></div>'
      + '<div class="n">' + r.n + "<span>次</span></div></div>";
  }).join("") + "</div>";
  return h;
}

function peopleHTML(me, store) {
  return '<div class="people-grid">' + [...store.npcs.values()].map((n) =>
    '<div class="pcard" data-npc="' + esc(n.id) + '"><div class="nm">' + esc(n.name)
    + "</div><small>" + (n.role ? esc(n.role) : "居民") + "</small></div>").join("") + "</div>";
}

/** 一个人的页：只给"我认识的"。没打过交道的只给"某居民"。
 *  ★ 这就是"不是上帝模式"最直接的体现。 */
export function personPage(npc, me, store) {
  const known = !!npc.name;
  let h = '<div style="margin-bottom:14px"><div style="font-size:16px;font-weight:700">'
    + esc(known ? npc.name : "某居民") + "</div>"
    + '<div class="dim" style="font-size:11px">' + esc(npc.role || "居民")
    + " · " + esc(store.locations[npc.loc]?.name || npc.loc || "路上") + "</div></div>";
  if (!known) {
    h += '<div class="card dim">你还不认识这个人。</div>';
    return h;
  }
  h += '<h4 class="sec">现在</h4><div class="card">'
    + (npc.active ? "正在 " + esc(npc.activity || "做事")
                  : esc(npc.activity || "站着"))
    + "</div>";
  h += '<h4 class="sec">状态</h4><div class="card">'
    + Object.entries(npc.signals || {}).filter(([k]) => SIGNAL_ZH[k])
      .map(([k, v]) => '<div class="row"><span class="lab">' + SIGNAL_ZH[k]
        + '</span><span class="mono">' + Math.round(v * 100) + "</span></div>").join("")
    + "</div>";
  return h;
}

/** 公司管理：我的店。改价/补货/看销量以后接后端，现在先给个真实的只读视图。 */
export function shopPage(store) {
  const c = store.companies[0];
  if (!c) return '<div class="card dim">这个场景里还没有公司。</div>';
  const shop = c.shops?.[0];
  const items = [...store.entities.values()].filter((e) => e.loc === shop);
  return '<h4 class="sec">' + esc(c.name) + " <span class=\"dim\" style=\"font-weight:400\">"
    + esc(shop ? store.locations[shop]?.name || shop : "没占建筑") + "</span></h4>"
    + '<div class="card">'
    + '<div class="kv"><span class="k">现金</span><span class="mono">¥'
    + (c.cash ?? 0).toFixed(0) + "</span></div>"
    + '<div class="kv"><span class="k">类型</span><span>' + esc(c.kind || "—") + "</span></div>"
    + '<div class="kv"><span class="k">营业</span><span class="mono">'
    + esc(c.open || "") + " – " + esc(c.close || "") + "</span></div>"
    + '<div class="kv"><span class="k">时薪</span><span class="mono">¥'
    + (c.wage_per_hour ?? 0) + "/时</span></div></div>"
    + '<h4 class="sec">店里的东西 <span class="dim" style="font-weight:400">'
    + items.length + " 件</span></h4>"
    + (items.length ? '<div class="card">' + items.map((e) =>
        '<div class="row"><span class="lab">' + esc(e.name || e.item_type)
        + '</span><span class="mono">×' + (e.stock ?? 0)
        + (e.price ? "  ¥" + e.price : "") + "</span></div>").join("") + "</div>"
      : '<div class="empty-row"></div>');
}

/** 我的家：三样东西（吃/睡/上厕所）。不在家时点它们 = 先回家再用。 */
export function homePage(store, onUse) {
  const me = store.npcs.get(store.player) || {};
  const home = me.home || me.loc;
  const items = [...store.entities.values()].filter((e) => e.loc === home);
  const inside = me.loc === home;
  const AFF = { energy: "回精力", hunger: "填肚子", bladder: "松快" };
  let h = '<div class="homebar' + (inside ? "" : " out") + '">'
    + '<span class="ic">⌂</span><span class="t">'
    + esc(store.locations[home]?.name || "还没有家") + "</span>"
    + (store.player ? "" : '<span class="dim" style="font-size:11px">（还没接管任何人）</span>')
    + "</div>";
  if (!items.length) return h + '<div class="empty-row"></div>';
  h += '<h4 class="sec">能用的东西</h4><div class="hgrid">' + items.map((e) => {
    const aff = Object.keys(e.affordances || {})[0];
    return '<div class="hitem' + (inside ? "" : " far") + '" data-use="' + esc(e.id) + '">'
      + '<span class="hi">' + ITEM_GLYPH[e.item_type] || "▪" + "</span>"
      + '<span class="hn">' + esc(e.name || e.item_type) + "</span>"
      + '<span class="hd">' + (AFF[aff] || "") + "</span></div>";
  }).join("") + "</div>";
}

const ITEM_GLYPH = { bed_basic: "🛏", toilet_basic: "🚽", stove_basic: "🍳",
                     freezer_basic: "❄", shelf_basic: "▤", station_counter: "▬",
                     meal_simple: "🍚", food_apple: "🍎", food_rice: "🌾" };

/** 价格按精度显示 —— 记的是个大概还是精确，得看得出来。 */
function priceViz(v, prec) {
  if (v == null) return "?";
  if (prec >= 5) return "¥" + (+v).toFixed(1);
  if (prec >= 3) return "¥" + Math.round(v);
  return "「" + Math.round(v / 5) * 5 + " 上下」";
}
function srcTag(s) {
  const t = { A: "亲眼", B: "听说", C: "传闻" }[s] || s || "?";
  return '<span class="tag' + (s === "B" ? " b" : s === "C" ? " c" : "") + '">' + t + "</span>";
}
function miniFace(look) {
  const top = "#9a9488", hair = "#3a3128";
  return '<svg width="100%" height="100%" viewBox="0 0 18 24">'
    + '<ellipse cx="9" cy="16.5" rx="6" ry="7" fill="' + top + '"/>'
    + '<circle cx="9" cy="7.5" r="5.4" fill="' + hair + '"/>'
    + '<circle cx="9" cy="9" r="4.2" fill="#e6c9a8"/>'
    + '<path d="M3.6 7.6a5.4 5.4 0 0 1 10.8 0z" fill="' + hair + '"/></svg>';
}
