#!/usr/bin/env node
/* ============================================================================
   wiki/gen.mjs —— 从【数据】生成游戏 wiki（静态 HTML，双击即看）
   ----------------------------------------------------------------------------
   为什么要有它：玩法会长大，靠人记不住。wiki 是"这个游戏里有什么"的导航。
   为什么是【生成】的：内容全在 config/ 里。手写 wiki 三天就过期了。

   数据源：
     config/items/*.json      物品（货 / 原料 / 家具）
     config/buildings/*.json  建筑类型
     config/scenes/*.json     场景（谁产什么、谁卖什么、有哪些人）
     config/sim.toml          数值（只做索引，不解析）
     art/out/manifest.json    美术资产（缺图会标出来）

   产出：wiki/out/*.html（平铺，所有链接都是相对的，file:// 直接可看）

   用法: node wiki/gen.mjs
   ========================================================================== */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const CFG = path.join(ROOT, "config");
const OUT = path.join(ROOT, "wiki", "out");
const ART = "../../art/out";                       // wiki/out/*.html → art/out/

const readJSON = p => JSON.parse(fs.readFileSync(p, "utf8"));
const listDir = (d, exts) => fs.existsSync(d)
  ? fs.readdirSync(d).filter(f => exts.some(e => f.endsWith(e))).sort().map(f => path.join(d, f))
  : [];

/* ── 读数据 ─────────────────────────────────────────────────────────────── */
const ITEMS = listDir(path.join(CFG, "items"), [".json"]).map(readJSON);
const BUILDINGS = listDir(path.join(CFG, "buildings"), [".json"]).map(readJSON);
const SCENES = listDir(path.join(CFG, "scenes"), [".json"]).map(f => ({ __file: path.basename(f), ...readJSON(f) }));

let ARTMAN = null;
try { ARTMAN = readJSON(path.join(ROOT, "art/out/manifest.json")); } catch { /* 还没生成美术 */ }
const artNames = new Set((ARTMAN?.assets || []).map(a => a.name));

/* ── 分类：tag → 人话。顺序就是这个 wiki 的目录顺序 ── */
const CATS = [
  { tag: "staple",   name: "主食",   hint: "便宜、饱腹大、耐放，但要花时间" },
  { tag: "fresh",    name: "生鲜",   hint: "便宜、会烂 —— 逼你勤进货" },
  { tag: "ready",    name: "即食",   hint: "贵、快、保质期最短 —— 毛利与损耗的来源" },
  { tag: "snack",    name: "零食",   hint: "满足 fun 而不是 hunger" },
  { tag: "drink",    name: "饮品",   hint: "满足 energy / fun" },
  { tag: "material", name: "原料",   hint: "工厂产出、不能吃、只能出口" },
  { tag: "fixture",  name: "家具",   hint: "恒为 1、永不消耗" },
];
const isGoods = it => it.tags.includes("consumable") && !it.tags.includes("fixture");
const catOf = it => {
  for (const c of CATS) if (it.tags.includes(c.tag)) return c;
  return { tag: "other", name: "其他", hint: "" };
};
const SIGNAL_NAME = { hunger: "饥饿", energy: "精力", bladder: "膀胱", fun: "娱乐", hp: "生命" };
const money = v => v > 0 ? "¥" + (Math.round(v * 100) / 100) : "—";
const days = t => t > 0 ? (t / 1440).toFixed(t % 1440 ? 1 : 0) + " 天" : "不会坏";

/* ── 布局 ──────────────────────────────────────────────────────────────── */
const NAV = [
  ["index.html", "首页"],
  ["items.html", "物品"],
  ["buildings.html", "建筑"],
  ["scene.html", "场景"],
  ["systems.html", "机制"],
];
function page(title, body, { sub = "" } = {}) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>${title} · citysim wiki</title><link rel="stylesheet" href="wiki.css"></head><body>
<nav>${NAV.map(([h, t]) =>
    `<a href="${h}"${t === title ? ' class="on"' : ""}>${t}</a>`).join("")}</nav>
<div class="wrap">
<header><h1>${title}</h1>${sub ? `<div class="sub">${sub}</div>` : ""}
  <input id="q" placeholder="在这个页面里筛…" autocomplete="off"></header>
${body}
<footer>生成自 <code>config/</code> · <code>node wiki/gen.mjs</code> 重建 ·
  最后生成 ${new Date().toISOString().slice(0, 16).replace("T", " ")}</footer>
</div>
<script src="wiki.js"></script></body></html>`;
}

/* ── 首页 ──────────────────────────────────────────────────────────────── */
function pageIndex() {
  const byCat = CATS.map(c => ({ ...c, items: ITEMS.filter(it => it.tags.includes(c.tag)) }));
  const goods = ITEMS.filter(isGoods).length;
  const cards = byCat.map(c => `
    <a class="card" href="items.html#cat-${c.tag}">
      <b>${c.name}</b><span class="n">${c.items.length}</span>
      <span class="h">${c.hint}</span></a>`).join("");
  return page("首页", `
    <div class="stats">
      <span><b>${ITEMS.length}</b> 物品</span>
      <span><b>${goods}</b> 货</span>
      <span><b>${ITEMS.length - goods}</b> 原料/家具</span>
      <span><b>${BUILDINGS.length}</b> 建筑类型</span>
      <span><b>${SCENES.length}</b> 场景</span>
    </div>
    <h2>物品分十类</h2>
    <div class="cards">${cards}</div>
    <h2>怎么用这个 wiki</h2>
    <ul class="tipline">
      <li><b>找东西</b> —— <a href="items.html">物品</a> 页有总表，点表头排序，或用顶部的筛选框。</li>
      <li><b>看一件东西</b> —— 总表里点名字进单页，能看到它的全部字段 + 美术 + 谁产谁卖。</li>
      <li><b>看一个建筑</b> —— <a href="buildings.html">建筑</a> 页。建筑决定能开什么公司。</li>
      <li><b>看具体这一局</b> —— <a href="scene.html">场景</a> 页：有哪些公司、谁在产什么。</li>
      <li><b>看规则</b> —— <a href="systems.html">机制</a> 页，指向设计文档。</li>
    </ul>
    <div class="tip">整个 wiki 是从 <code>config/</code> 生成的 —— 改了配置跑一遍就是新的。
      手写 wiki 三天就过期。</div>`);
}

/* ── 物品总表 ──────────────────────────────────────────────────────────── */
function itemRow(it) {
  const cat = catOf(it);
  const sig = Object.entries(it.affordances || {})
    .map(([k, v]) => `${SIGNAL_NAME[k] || k} ${v}`).join(" · ") || "（不满足任何需求）";
  const art = artNames.has(it.item_type);
  return `<tr data-s="${[it.name, it.item_type, cat.name, ...it.tags].join(" ")}">
    <td class="ic">${art
      ? `<img src="${ART}/items/icon_${it.item_type}.svg" width="22" height="22" alt="">`
      : `<span class="noart" title="还没有图标资产">?</span>`}</td>
    <td><a href="item_${it.item_type}.html">${it.name}</a>
        <span class="id">${it.item_type}</span></td>
    <td><span class="tag">${cat.name}</span></td>
    <td>${sig}</td>
    <td class="num">${money(it.price)}</td>
    <td class="num">${it.price > 0 ? money(it.price * 0.8) : money(it.build_cost)}</td>
    <td class="num">${days(it.shelf_life_ticks || 0)}</td>
    <td class="num">${it.duration_ticks}t</td>
  </tr>`;
}
function pageItems() {
  const head = `<tr><th>图</th><th>名字</th><th>类别</th><th>满足</th>
    <th class="num">售价</th><th class="num">进价/造价</th>
    <th class="num">保质期</th><th class="num">耗时</th></tr>`;
  const secs = CATS.map(c => {
    const list = ITEMS.filter(it => it.tags.includes(c.tag));
    if (!list.length) return "";
    return `<h2 id="cat-${c.tag}">${c.name} <span class="cnt">${list.length}</span>
        <span class="h">${c.hint}</span></h2>
      <table class="sortable"><thead>${head}</thead><tbody>${list.map(itemRow).join("")}</tbody></table>`;
  }).join("");
  const other = ITEMS.filter(it => catOf(it).tag === "other");
  return page("物品", `
    <div class="tip">共 <b>${ITEMS.length}</b> 件。点表头排序；顶部筛选框可以打字过滤。</div>
    ${secs}
    ${other.length ? `<h2 id="cat-other">未分类 <span class="cnt">${other.length}</span></h2>
      <table class="sortable"><thead>${head}</thead><tbody>${other.map(itemRow).join("")}</tbody></table>` : ""}`);
}

/* ── 单个物品页 ────────────────────────────────────────────────────────── */
function pageItem(it) {
  const cat = catOf(it);
  const isFix = it.tags.includes("fixture");
  const hasArt = artNames.has(it.item_type);
  const sigs = Object.entries(it.affordances || {});
  const sameCat = ITEMS.filter(x => x !== it && x.tags.includes(cat.tag));
  const sameSig = ITEMS.filter(x => x !== it
    && Object.keys(x.affordances || {}).some(s => sigs.some(([k]) => k === s)));

  /* 反向链接：哪个公司在产它 / 哪个场景里用它 */
  const producers = [];
  for (const sc of SCENES)
    for (const co of sc.companies || [])
      if (co.produces_item === it.item_type)
        producers.push({ scene: sc.__file, name: co.name, kind: co.kind });

  const rows = [
    ["item_type", `<code>${it.item_type}</code>`],
    ["类别", cat.name],
    ["tags", (it.tags || []).map(t => `<span class="tag">${t}</span>`).join(" ")],
    ["满足", sigs.length
      ? sigs.map(([k, v]) => `${SIGNAL_NAME[k] || k} <b>${v}</b>`).join(" · ")
      : `<span class="dim">不满足任何需求</span>`],
    isFix ? ["造价", money(it.build_cost)] : ["售价", money(it.price)],
    isFix ? null : ["进价（批发）", money(it.price * 0.8)],
    ["保质期", days(it.shelf_life_ticks || 0)],
    ["使用耗时", `${it.duration_ticks} tick`],
    isFix ? ["stock", it.stock] : null,
    it.persist_empty ? ["持久存在", "是（容器/货架，空了也不消失）"] : null,
    Object.keys(it.attrs || {}).length
      ? ["attrs", `<code>${JSON.stringify(it.attrs)}</code>`] : null,
  ].filter(Boolean);

  const attrsNote = Object.keys(it.attrs || {}).length
    ? `<div class="warn">这个物品的 <code>attrs</code> 里带了<b>提案字段</b> ——
       它是给未来机制留的形状，内核现在还<b>不读</b>它。见
       <a href="systems.html">机制</a>。</div>` : "";

  return page(it.name, `
    <div class="itempage">
      <div class="infobox">
        ${hasArt
          ? `<img class="hero" src="${ART}/items/${it.item_type}.svg" alt="">`
          : `<div class="noart big">还没有美术</div>`}
        <table class="kv">
          <tr><th>名字</th><td>${it.name}</td></tr>
          ${rows.map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join("")}
        </table>
      </div>
      <div class="prose">
        ${it._note ? `<div class="note">${it._note.replace(/\n/g, "<br>")}</div>`
                   : `<div class="dim">（配置里没写 <code>_note</code>）</div>`}
        ${attrsNote}
        ${producers.length ? `<h2>谁在产它</h2><ul>${
          producers.map(p => `<li>${p.name}（<code>${p.kind}</code>）—— 场景 <code>${p.scene}</code></li>`)
            .join("")}</ul>` : ""}
        ${isFix ? "" : `<h2>谁需要它</h2>
          <p><span class="dim">满足</span> ${sigs.map(([k]) => SIGNAL_NAME[k] || k).join(" / ") || "—"}
          <span class="dim">的人会买它。价格与保质期决定他们囤多少。</span></p>`}
        <h2>相关</h2>
        <p><span class="dim">同类：</span>${
          sameCat.slice(0, 8).map(x => `<a href="item_${x.item_type}.html">${x.name}</a>`).join(" · ")
            || "—"}</p>
        ${sigs.length ? `<p><span class="dim">同样满足 ${sigs.map(([k]) => SIGNAL_NAME[k] || k).join("/")}：
          </span>${sameSig.slice(0, 8).map(x => `<a href="item_${x.item_type}.html">${x.name}</a>`).join(" · ")
            || "—"}</p>` : ""}
      </div>
    </div>`);
}

/* ── 建筑 ──────────────────────────────────────────────────────────────── */
const KIND_NAME = { shop: "店铺 → 零售公司", factory: "工厂 → 制造公司",
                    home: "住宅", work: "办公", public: "公共", market: "批发市场",
                    school: "学校", clinic: "诊所" };
function pageBuildings() {
  const rows = BUILDINGS.map(b => `<tr data-s="${[b.name, b.type, b.kind].join(" ")}">
    <td><a href="building_${b.type}.html">${b.name}</a>
        <span class="id">${b.type}</span></td>
    <td><span class="tag">${b.kind}</span></td>
    <td>${KIND_NAME[b.kind] || "—"}</td>
    <td class="num">${b.capacity ?? "—"}</td>
    <td>${(b.doors || []).map(d => d.side + (d.offset ? `@${Math.round(d.offset * 100)}%` : ""))
          .join(" · ")}</td></tr>`).join("");
  return page("建筑", `
    <div class="tip">建筑<b>决定能开什么公司</b>：店铺→零售，工厂→制造。这是死规矩，不是选项。</div>
    <table class="sortable"><thead><tr><th>名字</th><th>kind</th><th>能开</th>
      <th class="num">容量</th><th>门</th></tr></thead><tbody>${rows}</tbody></table>`);
}
function pageBuilding(b) {
  const used = [];
  for (const sc of SCENES)
    for (const [lid, loc] of Object.entries(sc.locations || {}))
      if (loc.kind === b.kind) used.push(`${sc.__file} · ${lid}`);
  return page(b.name, `
    <div class="itempage">
      <div class="infobox">
        <table class="kv">
          <tr><th>type</th><td><code>${b.type}</code></td></tr>
          <tr><th>kind</th><td><span class="tag">${b.kind}</span></td></tr>
          <tr><th>能开</th><td>${KIND_NAME[b.kind] || "—"}</td></tr>
          <tr><th>容量</th><td>${b.capacity ?? "—"}</td></tr>
          <tr><th>门</th><td>${(b.doors || []).map(d => d.side).join(" · ")}</td></tr>
        </table>
      </div>
      <div class="prose">
        ${used.length ? `<h2>这一局里用到的</h2><ul>${
          used.map(u => `<li><code>${u}</code></li>`).join("")}</ul>` : ""}
        <h2>相关</h2>
        <p><a href="buildings.html">← 全部建筑</a></p>
      </div>
    </div>`);
}

/* ── 场景 ──────────────────────────────────────────────────────────────── */
function pageScene() {
  const secs = SCENES.map(sc => {
    const cos = (sc.companies || []).map(c => `<tr>
      <td>${c.name} <span class="id">${c.id}</span></td>
      <td><span class="tag">${c.kind}</span></td>
      <td>${c.produces_item
        ? `<a href="item_${c.produces_item}.html">${itemName(c.produces_item)}</a>`
        : "—"}</td>
      <td class="num">${money(c.cash)}</td>
      <td class="num">${c.open}–${c.close}</td>
      <td class="num">${c.hiring_slots}</td></tr>`).join("");
    const npcs = (sc.npcs || []).map(n =>
      `<span class="chip">${n.name || n.id}</span>`).join("");
    return `<h2>${sc.display_name || sc.__file} <span class="cnt">${sc.__file}</span></h2>
      <h3>公司（谁在产什么）</h3>
      <table><thead><tr><th>公司</th><th>类型</th><th>产出</th>
        <th class="num">现金</th><th>营业</th><th class="num">招聘</th></tr></thead>
        <tbody>${cos || `<tr><td colspan="6" class="dim">没有公司</td></tr>`}</tbody></table>
      <h3>居民 <span class="cnt">${(sc.npcs || []).length}</span></h3>
      <div class="chips">${npcs}</div>`;
  }).join("");
  return page("场景", `
    <div class="tip">场景 = 这一局的地图 + 人 + 公司。它是 <code>config/scenes/*.json</code>，
      由编辑器导出。</div>${secs}`);
}
function itemName(id) { return (ITEMS.find(x => x.item_type === id) || {}).name || id; }

/* ── 机制（指向设计文档，不复制内容）──────────────────────────────────── */
function pageSystems() {
  const docs = [
    ["游戏构思", "../../docs/game-concept.md", "这个游戏是什么"],
    ["设计决定", "../../docs/decisions.md", "真源：21 条决定"],
    ["物品设计", "../../docs/item-catalog.md", "65 件 · 三个轴 · 要新增的机制"],
    ["契约", "../../docs/contracts.md", "数据源纪律 A–F · 精度档"],
    ["资产定义", "../../docs/asset-list.md", "九大类 · 命名 · 交付"],
    ["UI 实现规格", "../../docs/ui-spec.md", "布局 / 组件 / 交互 / 动效"],
    ["美术方向", "../../docs/art-direction.md", "画风 · 网格 · 交付"],
    ["Demo 计划", "../../docs/demo-plan.md", "五条线 · 分工 · 验收"],
  ];
  const attrs = ITEMS.filter(it => Object.keys(it.attrs || {}).length)
    .map(it => `<li><a href="item_${it.item_type}.html">${it.name}</a>
        —— <code>${JSON.stringify(it.attrs)}</code></li>`).join("");
  return page("机制", `
    <h2>设计文档</h2>
    <ul class="tipline">${docs.map(([n, h, d]) =>
      `<li><a href="${h}">${n}</a> —— ${d}</li>`).join("")}</ul>
    <h2>⚠ 提案字段（内核还不读）</h2>
    <div class="warn">下面这些物品的 <code>attrs</code> 里带了给<b>未来机制</b>留的形状。
      它们是数据，不是行为 —— 现在的内核会忽略它们。</div>
    <ul class="tipline">${attrs || "<li class='dim'>无</li>"}</ul>
    <h2>要新增的机制（见物品设计 §六）</h2>
    <ol class="tipline">
      <li>非需求驱动的购买（否则日用品没人买）</li>
      <li>赠礼提升关系</li>
      <li>偏好标签（甜/咸/酒/便宜/讲究）→ 把「卖什么」变成「卖给谁」</li>
      <li>冰柜：延长保质期</li>
      <li>灶台：生食 → 即食</li>
      <li>招牌：提高被发现的概率</li>
      <li>容器（货架 / 冰柜 / 货箱）</li>
      <li>多 affordance（一件物品满足多个信号）</li>
    </ol>`);
}

/* ── CSS / JS ──────────────────────────────────────────────────────────── */
const CSS = `
:root{--bg:#f7f5f0;--fg:#26221c;--dim:#7a7264;--line:#ded7c8;--hi:#b4552d;--ok:#4a7358}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.65 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
nav{position:sticky;top:0;z-index:9;background:#26221c;padding:9px 20px;display:flex;gap:6px}
nav a{color:#cfc7b6;text-decoration:none;padding:4px 12px;border-radius:999px;font-size:13px}
nav a:hover{background:#ffffff1a;color:#fff}
nav a.on{background:#f7f5f0;color:#26221c;font-weight:600}
.wrap{max-width:1000px;margin:0 auto;padding:0 20px 60px}
header{padding:22px 0 10px}
h1{margin:0;font-size:26px}
h2{margin:30px 0 8px;font-size:17px;border-bottom:1px solid var(--line);padding-bottom:5px}
h3{margin:18px 0 6px;font-size:14px;color:var(--dim)}
h2 .cnt{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--dim);
  font-weight:400;margin-left:6px}
h2 .h{font-size:12px;color:var(--dim);font-weight:400}
.sub{color:var(--dim);font-size:13px;margin-top:3px}
#q{margin-top:12px;width:100%;max-width:340px;padding:6px 12px;font:inherit;font-size:13px;
  border:1px solid var(--line);border-radius:999px;background:#fff}
a{color:var(--hi)}
code{background:#00000008;padding:1px 5px;border-radius:3px;
  font:12px ui-monospace,Consolas,monospace}
table{border-collapse:collapse;width:100%;font-size:13px;background:#fff;
  border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}
th{background:#efebe1;font-size:12px;color:var(--dim);font-weight:600}
th.sortable{cursor:pointer;user-select:none}
th.sortable:hover{color:var(--fg)}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:#00000004}
td.num{text-align:right;font-family:ui-monospace,Consolas,monospace}
td.ic{width:34px}
.id{color:var(--dim);font:11px ui-monospace,Consolas,monospace;margin-left:6px}
.tag{display:inline-block;padding:0 6px;border:1px solid var(--line);border-radius:4px;
  font-size:11px;color:var(--dim);background:#fff}
.dim{color:var(--dim)}
.warn{margin:12px 0;padding:10px 14px;border:1px solid #e0cfa0;background:#fdf8ec;
  border-radius:8px;font-size:13px}
.note{margin:12px 0;padding:12px 15px;border-left:3px solid var(--ok);background:#fff;
  border-radius:0 8px 8px 0}
.tip{margin:12px 0;padding:10px 14px;border:1px dashed var(--line);border-radius:8px;
  font-size:13px;color:var(--dim);background:#00000003}
.stats{display:flex;gap:20px;flex-wrap:wrap;margin:6px 0 4px;font-size:13px;color:var(--dim)}
.stats b{font-size:19px;color:var(--fg);font-family:ui-monospace,Consolas,monospace;
  margin-right:3px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.card{display:block;padding:12px 14px;border:1px solid var(--line);border-radius:9px;
  background:#fff;text-decoration:none;color:var(--fg)}
.card:hover{border-color:var(--hi)}
.card b{font-size:15px}
.card .n{float:right;font-family:ui-monospace,Consolas,monospace;color:var(--dim)}
.card .h{display:block;font-size:12px;color:var(--dim);margin-top:4px}
.tipline{font-size:14px;padding-left:20px}
.tipline li{margin:5px 0}
.itempage{display:grid;grid-template-columns:280px 1fr;gap:26px;align-items:start;
  margin-top:14px}
.infobox{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px;
  position:sticky;top:60px}
.infobox .hero{display:block;width:100%;background:#e9e6da;border-radius:7px;
  padding:14px 0;margin-bottom:10px}
table.kv{font-size:12px;border:none;background:none}
table.kv th{background:none;width:78px;padding:4px 0;border:none;
  font-family:ui-monospace,Consolas,monospace;font-size:11px}
table.kv td{padding:4px 0;border:none;vertical-align:top}
.noart{display:inline-block;width:20px;height:20px;line-height:18px;text-align:center;
  border:1px dashed var(--line);border-radius:4px;color:var(--dim);font-size:11px}
.noart.big{width:100%;height:76px;line-height:76px;margin-bottom:10px;border-radius:7px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:3px 10px;border:1px solid var(--line);border-radius:999px;background:#fff;
  font-size:12px}
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);
  color:var(--dim);font-size:12px}
@media(max-width:760px){.itempage{grid-template-columns:1fr}.infobox{position:static}}
`;

const JS = `
/* 筛选：顶部输入框按行过滤（匹配 data-s 或整行文字） */
(function(){
  var q = document.getElementById("q");
  if (!q) return;
  q.addEventListener("input", function(){
    var v = q.value.trim().toLowerCase();
    document.querySelectorAll("table tbody tr").forEach(function(tr){
      var s = (tr.dataset.s || tr.textContent).toLowerCase();
      tr.style.display = (!v || s.indexOf(v) >= 0) ? "" : "none";
    });
    document.querySelectorAll("table").forEach(function(t){
      var any = Array.prototype.some.call(t.tBodies[0].rows, function(r){
        return r.style.display !== "none"; });
      t.style.display = any ? "" : "none";
      var h = t.previousElementSibling;
      if (h && h.tagName === "H2") h.style.display = any ? "" : "none";
    });
  });
})();
/* 表头点击排序 */
document.querySelectorAll("table.sortable").forEach(function(t){
  var ths = t.tHead.rows[0].cells;
  Array.prototype.forEach.call(ths, function(th, i){
    th.classList.add("sortable");
    var dir = 1;
    th.addEventListener("click", function(){
      var rows = Array.prototype.slice.call(t.tBodies[0].rows);
      rows.sort(function(a, b){
        var x = a.cells[i].textContent.trim(), y = b.cells[i].textContent.trim();
        var nx = parseFloat(x.replace(/[^\\d.-]/g, "")), ny = parseFloat(y.replace(/[^\\d.-]/g, ""));
        if (!isNaN(nx) && !isNaN(ny)) return (nx - ny) * dir;
        return x.localeCompare(y, "zh") * dir;
      });
      dir = -dir;
      rows.forEach(function(r){ t.tBodies[0].appendChild(r); });
    });
  });
});
/* 表格里的行整行可点（除了链接和表头）*/
document.querySelectorAll("table tbody tr").forEach(function(tr){
  var a = tr.querySelector("td a");
  if (!a) return;
  tr.style.cursor = "pointer";
  tr.addEventListener("click", function(e){
    if (e.target.tagName === "A") return;
    location.href = a.getAttribute("href");
  });
});
`;

/* ── 写出 ──────────────────────────────────────────────────────────────── */
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });
const write = (name, html) => fs.writeFileSync(path.join(OUT, name), html, "utf8");

fs.writeFileSync(path.join(OUT, "wiki.css"), CSS, "utf8");
fs.writeFileSync(path.join(OUT, "wiki.js"), JS, "utf8");
write("index.html", pageIndex());
write("items.html", pageItems());
write("buildings.html", pageBuildings());
write("scene.html", pageScene());
write("systems.html", pageSystems());
for (const it of ITEMS) write(`item_${it.item_type}.html`, pageItem(it));
for (const b of BUILDINGS) write(`building_${b.type}.html`, pageBuilding(b));

const noArt = ITEMS.filter(it => !artNames.has(it.item_type)).map(it => it.name);
console.log(`wiki → wiki/out/（${ITEMS.length} 物品 · ${BUILDINGS.length} 建筑 · ${SCENES.length} 场景）`);
console.log(`  打开 wiki/out/index.html`);
if (noArt.length) console.log(`  ⚠ 还没有美术的：${noArt.join("、")}`);
