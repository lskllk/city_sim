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
// ★ 资源拷进 wiki/out/a/ —— 这一页（整个 wiki）要能单独打包发出去，
//   不能靠 ../../ 回指 art/out（那样 zip 一下图就全断了）。
const ART = "a";

const readJSON = p => JSON.parse(fs.readFileSync(p, "utf8"));
const listDir = (d, exts) => fs.existsSync(d)
  ? fs.readdirSync(d).filter(f => exts.some(e => f.endsWith(e))).sort().map(f => path.join(d, f))
  : [];

/* ── 读数据 ─────────────────────────────────────────────────────────────── */
const ITEMS = listDir(path.join(CFG, "items"), [".json"]).map(readJSON);
const BUILDINGS = listDir(path.join(CFG, "buildings"), [".json"]).map(readJSON);
const SCENES = listDir(path.join(CFG, "scenes"), [".json"]).map(f => ({ __file: path.basename(f), ...readJSON(f) }));

let CHARS = [];
try {
  CHARS = JSON.parse(fs.readFileSync(path.join(ROOT, "art/characters.json"), "utf8")).characters || [];
} catch { /* 还没有角色数据 */ }

let ARTMAN = null;
try { ARTMAN = readJSON(path.join(ROOT, "art/out/manifest.json")); } catch { /* 还没生成美术 */ }
const artNames = new Set((ARTMAN?.assets || []).map(a => a.name));
const ARTASSETS = ARTMAN?.assets || [];
const AT = ARTMAN?.atmosphere || { time: [] };
const BLD_TYPES = ARTMAN?.buildingTypes || {};
const BLDART = ARTMAN?.buildings || [];

/* 美术资产的九大类（判据是玩法属性 —— 见 docs/asset-list.md §二）。
   gap = 该子类还没有资产：wiki 上会显示成虚线框，**所以这一页同时是缺口报告**。 */

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
  ["art.html", "美术"],
  ["chars.html", "人物"],
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
  const cov = `
    <h2>美术覆盖 <span class="cnt">${Object.keys(BLD_TYPES).length}/${BUILDINGS.length}</span>
      <span class="h">config 的类型名和美术资产名【不该指望能对上】—— 所以由资产自己声明覆盖谁</span></h2>
    <table class="dt"><thead><tr><th>config 类型</th><th>kind</th><th>美术资产</th>
      <th>尺寸</th><th></th></tr></thead><tbody>
      ${BUILDINGS.map(b => {
        const base = BLD_TYPES[b.type];
        const bj = BLDART.find(x => x.id === base) || {};
        return `<tr><td><a href="building_${b.type}.html"><code>${b.type}</code></a></td>
          <td><span class="tag">${b.kind}</span></td>
          <td>${base ? `<code>${base}</code>` : `<span class="bad">缺</span>`}</td>
          <td>${bj.g ? `${bj.g[0]}×${bj.g[1]} 格` : "—"}</td>
          <td>${base ? `<img src="${ART}/bld/${base}.svg" style="height:30px">` : ""}</td>
        </tr>`; }).join("")}</tbody></table>`;
  return page("建筑", `
    <div class="tip">建筑<b>决定能开什么公司</b>：店铺→零售，工厂→制造。这是死规矩，不是选项。</div>
    ${cov}
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
        ${(() => {
          // ★ 精确取图：靠资产自己声明的 types[]（清单汇成 buildingTypes）。
          //   原来是"找一个同 kind 的来示意"——那会把未覆盖的类型也画成有图。
          const base = BLD_TYPES[b.type];
          if (!base) return `<h2>美术</h2>
            <div class="gapbox"><b>缺</b> —— <code>${b.type}</code> 还没有美术。
            在 <code>art/gen.mjs</code> 的 <code>BUILDINGS</code> 里加一行并写上
            <code>types: ["${b.type}"]</code>（见 <a href="art.html">美术</a>）</div>`;
          const bj = BLDART.find(x => x.id === base) || {};
          const own = (bj.types || []).filter(x => x !== b.type);
          return `<h2>美术 <span class="id">art/bld/${base}*</span></h2>
            <div class="arow">${[["", "本体"], ["_shadow", "落影"], ["_lit", "夜间窗光"]]
              .filter(([sfx]) => artNames.has(base + sfx)).map(([sfx, lb]) =>
              `<div class="acell"><div class="abox"><img src="${ART}/bld/${base}${sfx}.svg"
                 style="width:${base === "plaza" ? 200 : 190}px"></div>
               <div class="alb">${lb}<br><span class="id">${base}${sfx}.svg</span></div></div>`
              ).join("")}</div>
            <div class="hint">每栋三张：本体 / 落影 / 夜间窗光。
              这栋美术叫 <code>${base}</code>，覆盖 <code>${b.type}</code>${own.length
                ? `（还覆盖 ${own.map(x => `<code>${x}</code>`).join(" · ")}）` : ""}。
              ${bj._note ? `<br>★ ${bj._note}` : ""}</div>`;
        })()}
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

/* ── 美术总览（★ 从这里验收资产，不再另开联络表）────────────────────── */
function pageArt() {
  return page("美术", `
    <div class="tip">这一页只做一件事：<b>看它们摆在一起协不协调</b>。<br>
      单个资产的<b>对错</b>由 <code>art/verify.py</code> 机械地查（文件/尺寸/颜色/填充率/锚点），
      代码能查的都查完了 —— 剩下只有这一个问题，只有眼睛能答。</div>
    <div class="knobs">
      <span class="kn"><b>场景</b><span id="kScene" class="zoom"></span></span>
      <span class="kn"><b>时间</b><span id="kTone" class="zoom"></span></span>
      <span class="kn"><b>天气</b><span id="kRain" class="zoom"></span></span>
      <span class="kn"><b>缩放</b><span id="kZoom" class="zoom"></span></span>
      <span class="kn"><b>图层</b><span id="kLayer" class="zoom"></span></span>
      <button id="kGrid">格子</button>
    </div>
    <div class="stage"><div class="scene" id="scene"></div></div>`);
}
function pageChars() {
  const rows = CHARS.map(c => `<div class="chcard">
    <div class="chhead"><img src="${ART}/portraits/${c.id}.svg" alt="">
      <div><b>${c.name}</b><div class="id">${c.id}</div></div></div>
    <div class="chbody">${["down", "up", "side"].map(d =>
      `<div class="cbox"><img data-cid="${c.id}" data-dir="${d}"></div>`).join("")}</div>
    <div class="chmeta">${(c.note || "")}</div></div>`).join("");
  return page("人物", `
    <div class="tip">左：头像（面板用）· 右：三个方向的走路循环。
      <b>同一份角色数据</b> —— 同一个人在世界里和面板里长得一致。</div>
    <div class="chgrid">${rows}</div>
    <h2>可辨识性 <span class="h">契约要求：任意两人至少 3 维不同</span></h2>
    <table><thead><tr><th>名字</th><th>体型</th><th>头发</th><th>上衣</th><th>配饰</th></tr></thead>
      <tbody>${CHARS.map(c => `<tr><td><a href="chars.html">${c.name}</a></td>
        <td>${c.body}</td><td>${c.hair}</td>
        <td><span class="swatch" style="background:${c.top}"></span> ${c.top}</td>
        <td>${c.acc}</td></tr>`).join("")}</tbody></table>
    <div class="tip">跑 <code>node art/gen.mjs --check</code> 会校验任意两人至少 3 维不同 ——
      这正是 Demo 验收第①条「我认得他们」。</div>`);
}

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

/* 美术页 = 场景预览 + 旋钮 —— 只回答「摆一起协不协调」 */
.knobs{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin:6px 0 12px}
.kn{display:inline-flex;align-items:center;gap:6px}
.kn>b{font:11px ui-monospace,Consolas,monospace;color:var(--dim);font-weight:600}
.stage{position:relative;overflow:auto;border:1px solid var(--line);border-radius:9px;
  background:#e3dfd3;padding:5px}
.scene{position:relative;transform-origin:top left;overflow:hidden;border-radius:6px;
  background:#6d8a52}
.scene .L{position:absolute}
.scene .tone,.scene .raing{position:absolute;pointer-events:none}
.scene .raing{background-repeat:repeat;background-size:64px 64px}
.scene.gridon::after{content:"";position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(#00000030 1px,transparent 1px),
    linear-gradient(90deg,#00000030 1px,transparent 1px);
  background-size:32px 32px}
.overwarn{margin:8px 0 0;padding:8px 12px;border-radius:7px;font-size:12px;
  background:#a8761c18;border:1px solid #a8761c40;color:#8a5f10}
.zoom{display:inline-flex;gap:3px}
.zoom button{font:inherit;font-size:11px;padding:2px 9px;border:1px solid var(--line);
  border-radius:999px;background:#fff;cursor:pointer}
.zoom button.on{background:#26221c;color:#f7f5f0;border-color:#26221c}
.arow{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 14px}
.acell{display:flex;flex-direction:column;align-items:center;gap:4px;
  border:1px solid var(--line);border-radius:8px;background:#fff;padding:8px}
.abox{display:flex;align-items:center;justify-content:center;background:#e9e6da;
  border-radius:5px;overflow:hidden}
.alb{font:10px ui-monospace,Consolas,monospace;color:var(--dim)}
/* 人物页 */
.chgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.chcard{border:1px solid var(--line);border-radius:9px;background:#fff;padding:10px}
.chhead{display:flex;gap:9px;align-items:center;margin-bottom:8px}
.chhead img{width:40px;height:40px;border-radius:7px;background:#e9e6da}
.chhead b{font-size:14px}
.chbody{display:flex;gap:8px;justify-content:center}
.cbox{background:#e9e6da;border-radius:6px;width:42px;height:52px;
  display:flex;align-items:center;justify-content:center}
.cbox img{width:34px;height:45px}
.chmeta{font-size:11px;color:var(--dim);margin-top:8px}
.swatch{display:inline-block;width:11px;height:11px;border-radius:3px;
  vertical-align:-1px;box-shadow:inset 0 0 0 1px #00000022}
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
/* ★ 把美术产物拷进 wiki/out/a/ —— 让 wiki 自足。
   这样 wiki/out 可以整个 zip 出去发人看，图不会断。 */
const ART_SRC = path.join(ROOT, "art", "out");
const ART_DST = path.join(OUT, "a");
if (fs.existsSync(ART_SRC)) {
  fs.rmSync(ART_DST, { recursive: true, force: true });
  fs.cpSync(ART_SRC, ART_DST, { recursive: true });
  const n = fs.readdirSync(ART_DST, { recursive: true })
    .filter(f => String(f).endsWith(".svg")).length;
  console.log(`  资源 → wiki/out/a/（${n} 个 SVG）`);
}

const write = (name, html) => fs.writeFileSync(path.join(OUT, name), html, "utf8");

fs.writeFileSync(path.join(OUT, "wiki.css"), CSS, "utf8");
fs.writeFileSync(path.join(OUT, "wiki.js"), JS + ARTJSFn(), "utf8");
write("index.html", pageIndex());
write("items.html", pageItems());
write("buildings.html", pageBuildings());
write("art.html", pageArt());
write("chars.html", pageChars());
write("scene.html", pageScene());
write("systems.html", pageSystems());
for (const it of ITEMS) write(`item_${it.item_type}.html`, pageItem(it));
for (const b of BUILDINGS) write(`building_${b.type}.html`, pageBuilding(b));

const noArt = ITEMS.filter(it => !artNames.has(it.item_type)).map(it => it.name);
console.log(`wiki → wiki/out/（${ITEMS.length} 物品 · ${BUILDINGS.length} 建筑 · ${SCENES.length} 场景）`);
console.log(`  打开 wiki/out/index.html`);
if (noArt.length) console.log(`  ⚠ 还没有美术的：${noArt.join("、")}`);

/* ── 美术页：组合场景 + 时间色调 + 缩放 + 人物动画（从 art/preview.mjs 搬来）── */
function ARTJSFn(){ return `
(function(){
  var ART = "${ART}";
  var tones = ${JSON.stringify(AT.time || [])};
  var man = ${JSON.stringify(ARTASSETS.map(a => [a.file, a.w, a.h]))};
  var chars = ${JSON.stringify(CHARS.map(c => c.id))};
  function el(t, c, h){ var e = document.createElement(t); if (c) e.className = c;
    if (h) e.innerHTML = h; return e; }
  function im(host, src, x, y, w, h, cls){ var m = el("img"); m.src = ART + "/" + src;
    m.style.cssText = "left:" + x + "px;top:" + y + "px;width:" + w + "px;height:" + h + "px";
    if (cls) m.className = cls; host.appendChild(m); return m; }
  /* ══ 场景预览 ══════════════════════════════════════════════════════
     这一页只干这一件事。摆得对不对，代码查不出来。 ═══════════════════ */
  var stage = document.getElementById("scene");
  var zoom = 1, rain = 0, toneIdx = 1;

  function put(host, src, x, y, w, h, layer){
    var m = el("img");
    m.src = ART + "/" + src;
    m.className = "L " + (layer || "");
    m.style.cssText = "left:" + x + "px;top:" + y + "px;"
                    + "width:" + w + "px;height:" + h + "px";
    host.appendChild(m); return m;
  }
  function fill(host, src, x, y, w, h, tw, th, layer){
    for (var yy = 0; yy < h; yy += th)
      for (var xx = 0; xx < w; xx += tw)
        put(host, src, x + xx, y + yy,
            Math.min(tw, w - xx), Math.min(th, h - yy), layer);
  }
  /* 建筑 = 落影 + 本体 + 夜光 + 招牌（招牌底留白，字由代码画）*/
  function bld(host, name, x, y, w, h, sign){
    put(host, "bld/" + name + "_shadow.svg", x - 3, y + 3, w + 6, h + 6, "shadow");
    put(host, "bld/" + name + ".svg", x, y, w, h, "bld");
    put(host, "bld/" + name + "_lit.svg", x, y, w, h, "bld lit");
    if (sign){
      var sh = Math.round(sign[1]);
      put(host, "attach/" + sign[0] + ".svg", x + (w - sign[2]) / 2, y + 8, sign[2], sh, "attach");
    }
  }
  function man(host, cid, dir, x, y){
    return put(host, "people/" + cid + "_" + dir + "_idle.svg", x, y, 18, 24, "person");
  }

  /* ── 场景定义 ── */
  var SCN = [
    { id: "corner", n: "街角", w: 640, h: 440, build: function(h){
        fill(h, "ground/grass.svg", 0, 0, 640, 440, 32, 32, "ground");
        // 一排店：左边两家大店 + 右边一栋小住宅
        bld(h, "shop_a",  24, 12, 256, 160, ["sign_wood", 16, 104]);
        bld(h, "clinic", 306, 12, 192, 160, ["sign_metal", 14, 88]);
        bld(h, "home_c", 500, 76, 128,  96);
        put(h, "attach/awning_1.svg",  84, 158, 112, 16, "attach");
        put(h, "attach/chimney_1.svg", 560, 70, 15, 15, "attach");
        fill(h, "ground/sidewalk.svg", 0, 172, 640, 6, 32, 6, "road");
        fill(h, "ground/asphalt.svg",  0, 178, 640, 64, 32, 32, "road");
        fill(h, "ground/sidewalk.svg", 0, 242, 640, 6, 32, 6, "road");
        fill(h, "road/marking_dash_h.svg", 14, 208, 612, 2, 30, 2, "road");
        put(h, "road/crosswalk.svg", 280, 178, 32, 6, "road");
        put(h, "road/crosswalk.svg", 280, 236, 32, 6, "road");
        // 车（车是竖的，路上横着跑 → 转 90°）
        [140, 420].forEach(function(cx){
          var c = put(h, "props/car_" + (cx === 140 ? 1 : 3) + ".svg",
                      cx, 201 - 16, 18, 32, "deco");
          c.style.transform = "rotate(90deg)"; c.style.transformOrigin = "9px 16px";
        });
        // 街边
        [["tree_l",  20, 258, 34], ["tree_m",  60, 300, 27], ["tree_s", 118, 268, 20],
         ["tree_m", 566, 262, 27], ["tree_l", 520, 306, 34]].forEach(function(t2){
          put(h, "props/" + t2[0] + ".svg", t2[1], t2[2], t2[3], t2[3] + 4, "deco");
        });
        put(h, "props/lamp.svg", 272, 244, 10, 30, "deco");
        put(h, "props/bench.svg", 40, 390, 26, 12, "deco");
        put(h, "props/bin.svg", 76, 390, 11, 13, "deco");
        put(h, "props/flowerbed.svg", 110, 392, 24, 14, "deco");
        // 街上的人
        man(h, "n_wang", "down", 150, 224); man(h, "me", "down", 190, 226);
        man(h, "n_sun",  "side", 400, 226); man(h, "n_li", "down", 330, 148);
        man(h, "n_zhou", "down", 96, 148);  man(h, "n_zhao", "side", 470, 224);
      }},
    { id: "shop", n: "店里", w: 440, h: 300, build: function(h){
        fill(h, "ground/plaza.svg", 0, 0, 440, 300, 32, 32, "ground");
        // 货架区：三个货架并排，货摆在上面（容器和内容是两层）
        [30, 84, 138].forEach(function(x, i){
          put(h, "items/shelf_basic.svg", x, 46, 48, 26, "bld");
          put(h, "items/" + ["food_apple", "food_pear", "food_bread"][i] + ".svg",
              x + 6, 38, [36, 36, 30][i], [26, 26, 22][i], "item");
        });
        // 冰柜区
        [30, 84].forEach(function(x, i){
          put(h, "items/freezer_basic.svg", x, 120, 48, 32, "bld");
          put(h, "items/" + ["food_milk", "drink_soda"][i] + ".svg",
              x + 12, 116, [22, 20][i], [28, 20][i], "item");
        });
        // 灶台 + 热菜
        put(h, "items/stove_basic.svg", 138, 122, 36, 26, "bld");
        put(h, "items/meal_hot_dish.svg", 139, 118, 34, 30, "item");
        // 柜台 + 售罄的空筐
        put(h, "items/station_counter.svg", 300, 60, 76, 26, "bld");
        put(h, "items/food_apple_empty.svg", 34, 196, 36, 26, "item");
        put(h, "items/food_rice_empty.svg", 84, 194, 32, 28, "item");
        man(h, "n_sun",  "up",   326, 100);
        man(h, "n_wang", "down", 232, 118);
        man(h, "n_me",   "down", 214, 118);
      }},
    { id: "factory", n: "加工厂", w: 440, h: 300, build: function(h){
        fill(h, "ground/dirt.svg", 0, 0, 440, 300, 32, 32, "ground");
        put(h, "items/station_workbench.svg", 40, 52, 60, 26, "bld");
        put(h, "items/industry_machine.svg", 40, 120, 52, 40, "bld");
        put(h, "items/meal_simple_raw.svg", 120, 128, 32, 28, "item");
        put(h, "items/meal_simple.svg", 300, 60, 32, 24, "item");
        put(h, "items/meal_simple.svg", 340, 60, 32, 24, "item");
        put(h, "items/meal_simple_empty.svg", 380, 60, 32, 24, "item");
        man(h, "n_zhou", "down", 148, 92);
        man(h, "n_li",   "side", 190, 200);
        man(h, "me",     "down", 300, 210);
      }},
    { id: "home", n: "家里", w: 440, h: 300, build: function(h){
        fill(h, "ground/plaza.svg", 0, 0, 440, 300, 32, 32, "ground");
        put(h, "items/bed_basic.svg", 40, 40, 64, 40, "bld");
        put(h, "items/station_counter.svg", 150, 46, 76, 26, "bld");
        put(h, "items/meal_hot_dish.svg", 162, 42, 34, 30, "item");
        put(h, "items/stove_basic.svg", 250, 46, 36, 26, "bld");
        put(h, "items/toilet_basic.svg", 350, 44, 30, 34, "bld");
        put(h, "items/food_milk.svg", 60, 160, 22, 28, "item");
        put(h, "items/drink_coffee.svg", 100, 162, 26, 26, "item");
        man(h, "me",     "up",   120, 120);
        man(h, "n_zhang","side", 240, 170);
      }},
  ];

  var CUR = -1;
  function draw(i){
    if (!stage) return;
    CUR = i;
    var s = SCN[i];
    stage.innerHTML = "";
    stage.style.width = s.w + "px";
    stage.style.height = s.h + "px";
    s.build(stage);
    // ★ 摆到画布外的元素在代码里看不出来，肉眼也容易漏 —— 让场景自己报。
    var over = [];
    stage.querySelectorAll(".L").forEach(function(e){
      var r = e.getBoundingClientRect(), b = stage.getBoundingClientRect();
      var sc = zoom || 1;
      if (r.right - b.left > s.w * sc + 1 || r.bottom - b.top > s.h * sc + 1){
        over.push(e.src.split("/").pop());
      }
    });
    if (over.length){
      var w = el("div", "overwarn");
      w.textContent = "⚠ " + over.length + " 个元素摆到了画布外：" + over.slice(0, 4).join(" · ");
      stage.parentNode.parentNode.insertBefore(w, stage.parentNode.nextSibling);
    }
    var tn = el("div", "L tone");
    tn.style.cssText = "left:0;top:0;width:" + s.w + "px;height:" + s.h + "px";
    stage.appendChild(tn);
    var rn = el("div", "L raing");
    rn.style.cssText = "left:0;top:0;width:" + s.w + "px;height:" + s.h + "px";
    stage.appendChild(rn);
    apply();
  }

  /* ── 旋钮 ── */
  function group(hostId, items, cur, onPick){
    var host = document.getElementById(hostId);
    if (!host) return;
    items.forEach(function(it, i){
      var b = el("button", i === cur ? "on" : "", it);
      b.onclick = function(){
        Array.prototype.forEach.call(host.querySelectorAll("button"),
          function(x){ x.classList.remove("on"); });
        b.classList.add("on");
        onPick(i);
      };
      host.appendChild(b);
    });
  }
  group("kScene", SCN.map(function(s){ return s.n; }), 0, draw);

  var tones = ${JSON.stringify(AT.time || [])};
  group("kTone", tones.map(function(t){ return t.label; }), 1,
    function(i){ toneIdx = i; apply(); });
  group("kRain", ["晴", "小雨", "大雨"], 0, function(i){ rain = i; apply(); });
  group("kZoom", ["0.5×", "1×", "2×", "3×"], 1, function(i){ zoom = [0.5, 1, 2, 3][i]; apply(); });

  var LAYERS = [["落影", "shadow"], ["夜光", "lit"], ["招牌", "attach"],
                ["装潢", "deco"], ["人物", "person"], ["货", "item"]];
  var off = {};
  var lh = document.getElementById("kLayer");
  if (lh) LAYERS.forEach(function(L){
    var b = el("button", "on", L[0]);
    b.onclick = function(){
      off[L[1]] = !off[L[1]];
      this.classList.toggle("on", !off[L[1]]);
      apply();
    };
    lh.appendChild(b);
  });

  function apply(){
    if (!stage) return;
    var tn = tones[toneIdx] || {};
    stage.querySelectorAll(".tone").forEach(function(e){
      e.style.background = tn.tint;
      e.style.mixBlendMode = tn.blend === "normal" ? "normal" : tn.blend;
      e.style.opacity = tn.alpha;
    });
    stage.querySelectorAll(".lit").forEach(function(e){
      e.style.visibility = (tn.window > 0.3 && !off.lit) ? "visible" : "hidden";
      e.style.opacity = tn.window;
    });
    Object.keys(off).forEach(function(k){
      stage.querySelectorAll("." + k).forEach(function(e){
        e.style.display = off[k] ? "none" : "";
      });
    });
    stage.querySelectorAll(".raing").forEach(function(e){
      e.style.display = rain ? "block" : "none";
      if (rain){
        e.style.backgroundImage = "url(" + ART + "/atm/rain_" +
          (rain > 1 ? "heavy" : "light") + ".svg)";
        e.style.opacity = rain > 1 ? 0.5 : 0.32;
      }
    });
    if (stage){ stage.style.transform = "scale(" + zoom + ")"; }
    stage.parentNode.style.height = (SCN[CUR].h * zoom + 4) + "px";
  }

  var gb = document.getElementById("kGrid");
  if (gb) gb.onclick = function(){ this.classList.toggle("on");
    stage.classList.toggle("gridon"); };

  if (stage) draw(0);

  /* 人物动画 */
  var peopleHost = document.getElementById("people");
  if (peopleHost) chars.forEach(function(cid){
    var wrap = el("div", "chcard");
    wrap.appendChild(el("div", "chhead", "<b>" + cid + "</b>"));
    var body = el("div", "chbody");
    ["down","up","side"].forEach(function(dir){
      var b = el("div", "cbox"); var img = el("img");
      img.style.width = "34px"; img.style.height = "45px";
      b.appendChild(img); body.appendChild(b);
      var f = 0;
      setInterval(function(){
        img.src = ART + "/people/" + cid + "_" + dir + "_" +
          (f % 7 === 6 ? "idle" : "walk" + (f % 4)) + ".svg";
        f++;
      }, 140);
    });
    wrap.appendChild(body); peopleHost.appendChild(wrap);
  });
  /* 人物页的动画 */
  document.querySelectorAll("[data-cid]").forEach(function(img){
    var cid = img.dataset.cid, dir = img.dataset.dir, f = 0;
    setInterval(function(){
      img.src = ART + "/people/" + cid + "_" + dir + "_" +
        (f % 7 === 6 ? "idle" : "walk" + (f % 4)) + ".svg";
      f++;
    }, 140);
  });
})();
`; }
