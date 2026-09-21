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
const ARTGRID = ARTMAN?.grid || 32;

/* 美术资产的九大类（判据是玩法属性 —— 见 docs/asset-list.md §二）。
   gap = 该子类还没有资产：wiki 上会显示成虚线框，**所以这一页同时是缺口报告**。 */
const ARTCATS = [
  { k: "A", n: "环境", hint: "铺在地上 / 立在地上但不交互", subs: [
    { k: "A1", n: "地面", s: "ground", hint: "可平铺 32px" },
    { k: "A2", n: "道路", s: "road", hint: "路面形状是平涂，这里给纹理味" },
    { k: "A3", n: "过渡与拼接", s: "autotile",
      gap: "autotile 集（草↔泥 / 草↔水 / 铺装↔草 / 路肩）。只有地面没有过渡 → 地图到处是硬边，这是「业余 vs 专业」最大的分水岭" },
    { k: "A4", n: "地块装饰", s: "props", hint: "锚点在底部中心，所以「立」在地上" },
    { k: "A5", n: "围栏与院子", s: "fence", gap: "木栅栏 / 矮砖墙 / 树篱（各 4 段：直/角/端/门）" },
  ]},
  { k: "B", n: "建筑", hint: "有门口、能走进去、有名字", subs: [
    { k: "B1", n: "本体", s: "body", hint: "屋顶 + 立面揭示 + 门口" },
    { k: "B2", n: "落影", s: "shadow", hint: "单独一层：夜/雨可复用，也能整个关掉" },
    { k: "B3", n: "夜间窗光", s: "lit", hint: "和屋顶同一套坐标，所以一定对得上" },
    { k: "B4", n: "附件", s: "attach", hint: "招牌底 6 种是【九宫格】，中段可拉伸；招牌留白，字由代码画" },
    { k: "B5", n: "状态", s: "bstate", gap: "关门挂牌（休息中/打烊）· 装修中 · 出售/出租牌" },
    { k: "B6", n: "室内结构", s: "binter", gap: "室内墙 / 室内门 / 室内窗 / 楼梯 / 地板贴图" },
  ]},
  { k: "C", n: "角色", hint: "会走动、有需求、有记忆", subs: [
    { k: "C1", n: "世界小人", s: "world", anim: true,
      hint: "走 4 帧 + 站 1 帧，循环播放；锚点在脚底；左右靠水平镜像" },
    { k: "C2", n: "头像", s: "portrait", hint: "32×32 正面胸像，给面板用；和世界小人同一份角色数据" },
    { k: "C3", n: "动作", s: "cemote", gap: "待机小动作（换重心/看表）· 坐 · 用东西（吃/睡/如厕）" },
  ]},
  { k: "D", n: "物件", hint: "玩家能点 / 能买卖 / 能用 —— 判据是玩法属性，不是外观", subs: [
    { k: "D1", n: "世界形态", s: "iworld", hint: "俯视，摆在屋里要贴地" },
    { k: "D2", n: "空态", s: "iempty", hint: "「卖光了」用形状说，不写字" },
    { k: "D3", n: "图标", s: "iicon", hint: "正视 16×16 —— 俯视的苹果就是个圆" },
    { k: "D4", n: "容器", s: "icont", gap: "货架 / 冰柜 / 展示柜 —— 容器与内容必须是两个资产" },
  ]},
  { k: "E", n: "界面", hint: "屏幕空间，不随地图缩放", subs: [
    { k: "E1", n: "需求徽章", s: "badge", hint: "饿 / 困 / 憋 / 犹豫 / 睡" },
    { k: "E2", n: "标记", s: "marker", hint: "队列编号点" },
    { k: "E3", n: "刻度条", s: "bar", hint: "轨道是资产、填充是代码" },
    { k: "E4", n: "图标系统", s: "uicon", gap: "一套统一线性图标（时间/经济/需求/社交/功能/地图）。现在混了 emoji + 手写 SVG + 纯字符" },
  ]},
  { k: "F", n: "特效", hint: "一次性、短命、不占位置", subs: [
    { k: "F1", n: "落影与环", s: "fx", hint: "人物落影小/中/大 + 选中环" },
    { k: "F2", n: "点击与反馈", s: "fback", gap: "点击涟漪 · 完成打勾 · 气泡底/尾 · 交易成功" },
  ]},
  { k: "G", n: "氛围", hint: "覆盖全屏、影响观感、不改任何逻辑", subs: [
    { k: "G1", n: "天气", s: "rain", hint: "可平铺。时间色调是【参数】不是贴图，见本页顶部的「时间」" },
    { k: "G2", n: "光与色", s: "glight", gap: "窗光遮罩 · 灯光光斑 · 雪/雾/落叶" },
  ]},
  { k: "H", n: "认知", hint: "表达「我记的多旧 / 多准 / 从哪来」—— 这个游戏特有", subs: [
    { k: "H1", n: "来源记号", s: "csrc", gap: "亲眼 / 打听 / 传闻 / 雇员 / 经手 —— 现在是字符，要重做成一套" },
    { k: "H2", n: "精度档", s: "cprec", gap: "5 档的区间条元件 —— 现在还是代码画的 div" },
    { k: "H3", n: "知识等级", s: "cknow", gap: "3 档（没进去过 / 旧了 / 新鲜）—— 现在是 filter: saturate()" },
    { k: "H4", n: "事件反馈", s: "cev", gap: "惊讶 / 刚确认 / 已过时 / 待确认" },
  ]},
];
const artBy = (cat, sub2) => ARTASSETS.filter(a => a.cat === cat && a.sub === sub2);

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
function artCell(a, k) {
  k = (k || 1.3) * 1.6;
  const slice = a.slice ? " ▣九宫格" : "";
  const over = a.tags.includes("oversize") ? " ⚠画布比建筑大" : "";
  return `<div class="acell">
    <div class="abox" data-w="${a.w}" data-h="${a.h}" data-k="${k}">
      <img src="${ART}/${a.file}" style="width:${Math.round(a.w * k)}px;
        height:${Math.round(a.h * k)}px"></div>
    <div class="alb">${a.name}</div>
    <div class="adm">${a.w}×${a.h} ${a.anchor}${slice}${over}</div></div>`;
}
function pageArt() {
  const scenes = `
    <div class="scenes">
      <div><div class="scene" id="scene"></div>
        <div class="hint">地图一角（含招牌与雨棚）</div></div>
    </div>
    <div class="scenes" id="scenes2"></div>
    <div class="hint">★ 物品必须和人摆在一起才看得出大小 —— 床边那个人是 18×24</div>`;
  const secs = ARTCATS.map(C => {
    const list = ARTASSETS.filter(a => a.cat === C.k);
    const subs = C.subs.map(SB => {
      const items = artBy(C.k, SB.s);
      if (!items.length) {
        return SB.gap
          ? `<h4>${SB.k} ${SB.n} <span class="cnt">0</span></h4>
             <div class="gapbox"><b>缺</b> —— ${SB.gap}</div>` : "";
      }
      if (SB.anim) {
        return `<h4>${SB.k} ${SB.n} <span class="cnt">${items.length}</span></h4>
          <div class="hint">${SB.hint}</div><div class="arow" id="people"></div>
          ${SB.gap ? `<div class="gapbox"><b>还缺</b> —— ${SB.gap}</div>` : ""}`;
      }
      const k = (SB.s === "iicon" || SB.s === "badge" || SB.s === "marker") ? 2.2 : 1.3;
      return `<h4>${SB.k} ${SB.n} <span class="cnt">${items.length}</span></h4>
        ${SB.hint ? `<div class="hint">${SB.hint}</div>` : ""}
        <div class="arow">${items.map(a => artCell(a, k)).join("")}</div>
        ${SB.gap ? `<div class="gapbox"><b>还缺</b> —— ${SB.gap}</div>` : ""}`;
    }).join("");
    return `<h2>${C.k} ${C.n} <span class="cnt">${list.length}</span>
      <span class="h">${C.hint}</span></h2>${subs}`;
  }).join("");
  return page("美术", `
    <div class="tip">从 <code>art/</code> 生成。改画风改 <code>art/style.json</code>，
      加人改 <code>art/characters.json</code>，然后 <code>bash art/build.sh</code>。
      <b>虚线框是「还缺什么」</b> —— 这一页同时是缺口报告。</div>
    <div class="stats">
      <span><b>${ARTASSETS.length}</b> 资产</span>
      <span><b>${ARTGRID}</b> px 网格</span>
      <span><b>2×</b> 绘制</span>
      <span class="dim">缩放</span>
      <span class="zoom">
        <button data-z="0.6">0.6×</button><button data-z="1" class="on">1×</button>
        <button data-z="2">2×</button><button data-z="3">3×</button></span>
      <span class="dim">时间</span><span id="tones" class="zoom"></span>
      <button id="bGrid">格子</button>
      <button id="bNorm">统一大小</button>
    </div>
    <h2>建筑类型覆盖 <span class="cnt">${Object.keys(BLD_TYPES).length}/${BUILDINGS.length}</span>
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
        </tr>`; }).join("")}</tbody></table>

    <h2>组合场景 <span class="h">资产放在一起才知道搭不搭</span></h2>
    ${scenes}
    ${secs}`);
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

/* 美术页 */
.arow{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 14px}
.acell{display:flex;flex-direction:column;align-items:center;gap:4px;
  border:1px solid var(--line);border-radius:8px;background:#fff;padding:8px}
.abox{display:flex;align-items:center;justify-content:center;background:#e9e6da;
  border-radius:5px;overflow:hidden}
.alb{font:10px ui-monospace,Consolas,monospace;color:var(--dim)}
.adm{font:9px ui-monospace,Consolas,monospace;color:#a49c8d}
h4{margin:14px 0 4px;font-size:13px;color:var(--dim);
  display:flex;align-items:baseline;gap:8px}
h4 .cnt{font:11px ui-monospace,Consolas,monospace;color:#a49c8d}
.gapbox{margin:4px 0 12px;padding:8px 12px;border:1px dashed #cfc7b6;border-radius:7px;
  color:#9a8f7c;font-size:12px;background:#00000004}
.gapbox b{color:var(--hi)}
/* 统一大小：把每个格子拉到一样大，按比例缩放（world 资产本来就是各自的世界尺寸，
   验收图标一致性时才开这个）。 */
body.norm .abox{width:78px!important;height:78px!important}
body.norm .abox img{width:auto!important;height:auto!important;
  max-width:100%;max-height:100%;object-fit:contain}
body.norm .acell{min-width:96px}
.zoom{display:inline-flex;gap:3px}
.zoom button{font:inherit;font-size:11px;padding:2px 9px;border:1px solid var(--line);
  border-radius:999px;background:#fff;cursor:pointer}
.zoom button.on{background:#26221c;color:#f7f5f0;border-color:#26221c}
body.grid .abox{background-image:
  linear-gradient(#00000012 1px,transparent 1px),
  linear-gradient(90deg,#00000012 1px,transparent 1px);background-size:32px 32px}
/* 组合场景 */
.scenes{display:flex;gap:16px;padding:2px 0 8px;flex-wrap:wrap}
.scene{position:relative;width:640px;height:352px;border:1px solid var(--line);
  border-radius:8px;overflow:hidden;background-color:#6d8a52;
  background-image:url(../../art/out/ground/grass.svg);background-size:32px 32px}
.scene .g{position:absolute;background-image:url(../../art/out/ground/asphalt.svg);
  background-size:32px 32px}
.scene .sw{position:absolute;background-image:url(../../art/out/ground/sidewalk.svg);
  background-size:32px 6px}
.scene img,.room img{position:absolute}
.roomwrap{border:1px solid var(--line);border-radius:8px;background:#fff;padding:8px}
.roomwrap .cap{font-size:11px;color:var(--dim);padding-top:5px}
.room{position:relative;background:#e8dfc9;border-radius:5px;overflow:hidden;
  box-shadow:inset 0 0 0 1px #00000018}
.tone{position:absolute;inset:0;pointer-events:none}
body.grid .scene{background-image:
  linear-gradient(#00000026 1px,transparent 1px),
  linear-gradient(90deg,#00000026 1px,transparent 1px),
  url(../../art/out/ground/grass.svg);
  background-size:32px 32px,32px 32px,32px 32px}
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
  /* 组合场景：地图一角 */
  var sc = document.getElementById("scene");
  if (sc){
    function box(cls, x, y, w, h){ var d = el("div", cls);
      d.style.cssText = "left:" + x + "px;top:" + y + "px;width:" + w + "px;height:" + h + "px";
      sc.appendChild(d); return d; }
    box("g", 0, 150, 640, 64); box("sw", 0, 144, 640, 6); box("sw", 0, 214, 640, 6);
    function bld(name, x, y, w, h){
      im(sc, "bld/" + name + "_shadow.svg", x, y, w + 6, h + 7);
      im(sc, "bld/" + name + ".svg", x, y, w, h);
      im(sc, "bld/" + name + "_lit.svg", x, y, w, h, "lit");
      im(sc, "attach/awning_1.svg", x + 96, y + 134, 46, 16);
      im(sc, "attach/sign_wood.svg", x + 72, y + 18, 112, 16);
    }
    bld("shop_a", 40, 30, 256, 160); bld("home_b", 330, 40, 192, 128);
    [[150,118,27],[470,108,20],[556,238,34],[92,248,20],[300,258,27]].forEach(function(t){
      im(sc, "props/tree_" + (t[2]>=30?"l":t[2]>=24?"m":"s") + ".svg", t[0], t[1], t[2], t[2]+4); });
    im(sc, "props/car_1.svg", 250, 152, 18, 32); im(sc, "props/car_3.svg", 420, 168, 18, 32);
    im(sc, "props/lamp.svg", 500, 118, 10, 30); im(sc, "props/bench.svg", 200, 226, 26, 12);
    im(sc, "people/n_wang_down_idle.svg", 140, 232, 18, 24);
    im(sc, "people/n_li_down_idle.svg", 228, 236, 18, 24);
    im(sc, "people/n_sun_side_idle.svg", 180, 228, 18, 24);
    im(sc, "people/me_down_idle.svg", 330, 258, 18, 24);
    sc.appendChild(el("div", "tone"));
  }
  /* 三间室内 */
  var s2 = document.getElementById("scenes2");
  if (s2){
    function room(title, W, H, place){
      var wrap = el("div", "roomwrap"); var r = el("div", "room");
      r.style.cssText += "width:" + W + "px;height:" + H + "px";
      function rIM(src, x, y, w, h){ return im(r, src, x, y, w, h); }
      var P = function(cid, dir, x, y){ return rIM("people/" + cid + "_" + dir + "_idle.svg", x, y, 18, 24); };
      place(rIM, P); r.appendChild(el("div", "tone"));
      wrap.appendChild(r); wrap.appendChild(el("div", "cap", title)); s2.appendChild(wrap);
    }
    var IT = ${JSON.stringify(
      ARTASSETS.filter(a => a.cat === "D" && a.sub === "iworld")
        .reduce((o, a) => { o[a.name] = [a.w, a.h]; return o; }, {}))};
    room("店里（前台 + 货 + 店员）", 340, 190, function(im2, P){
      im2("items/station_counter.svg", 244, 40, IT["station_counter"][0], IT["station_counter"][1]);
      im2("items/food_apple.svg", 30, 34, IT["food_apple"][0], IT["food_apple"][1]);
      im2("items/food_pear.svg", 30, 68, IT["food_pear"][0], IT["food_pear"][1]);
      im2("items/meal_simple.svg", 30, 102, IT["meal_simple"][0], IT["meal_simple"][1]);
      im2("items/food_apple_empty.svg", 96, 34, IT["food_apple"][0], IT["food_apple"][1]);
      P("n_sun","down",226,118); P("n_wang","down",150,122); });
    room("加工厂（工位 + 机器 + 工人）", 340, 190, function(im2, P){
      im2("items/station_workbench.svg", 30, 40, IT["station_workbench"][0], IT["station_workbench"][1]);
      im2("items/industry_machine.svg", 26, 90, IT["industry_machine"][0], IT["industry_machine"][1]);
      im2("items/meal_simple_raw.svg", 110, 96, IT["meal_simple_raw"][0], IT["meal_simple_raw"][1]);
      P("n_zhou","down",130,130); P("n_li","side",200,134); });
    room("家里（床 + 马桶）", 340, 190, function(im2, P){
      im2("items/bed_basic.svg", 40, 34, IT["bed_basic"][0], IT["bed_basic"][1]);
      im2("items/toilet_basic.svg", 250, 30, IT["toilet_basic"][0], IT["toilet_basic"][1]);
      P("me","up",160,100); P("n_zhang","side",190,104); });
  }
  /* 时间色调 */
  var host = document.getElementById("tones");
  function apply(i){
    var tn = tones[i];
    document.querySelectorAll(".tone").forEach(function(e){
      e.style.background = tn.tint;
      e.style.mixBlendMode = tn.blend === "normal" ? "normal" : tn.blend;
      e.style.opacity = tn.alpha;
    });
    document.querySelectorAll(".lit").forEach(function(e){
      e.style.visibility = tn.window > 0.3 ? "visible" : "hidden";
      e.style.opacity = tn.window;
    });
  }
  if (host) tones.forEach(function(tn, i){
    var b = el("button", "", tn.label);
    b.onclick = function(){
      host.querySelectorAll("button").forEach(function(x){ x.classList.remove("on"); });
      b.classList.add("on"); apply(i);
    };
    host.appendChild(b);
    if (tn.name === "day"){ b.classList.add("on"); apply(i); }
  });
  /* 缩放 */
  document.querySelectorAll("[data-z]").forEach(function(b){
    b.onclick = function(){
      var Z = parseFloat(b.dataset.z);
      document.querySelectorAll("[data-z]").forEach(function(x){ x.classList.remove("on"); });
      b.classList.add("on");
      if (document.body.classList.contains("norm")) return;   /* 统一大小时交给 CSS */
      document.querySelectorAll(".abox").forEach(function(bx){
        var W = parseFloat(bx.dataset.w), H = parseFloat(bx.dataset.h),
            k = parseFloat(bx.dataset.k);
        bx.style.width = Math.round(W*Z*k) + "px"; bx.style.height = Math.round(H*Z*k) + "px";
        var img = bx.querySelector("img");
        if (img){ img.style.width = Math.round(W*Z*k) + "px";
                  img.style.height = Math.round(H*Z*k) + "px"; }
      });
    };
  });
  /* 统一大小 */
  var nb = document.getElementById("bNorm");
  if (nb) nb.onclick = function(){ this.classList.toggle("on");
    document.body.classList.toggle("norm"); };
  /* 格子 */
  var g = document.getElementById("bGrid");
  if (g) g.onclick = function(){ this.classList.toggle("on");
    document.body.classList.toggle("grid"); };
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
