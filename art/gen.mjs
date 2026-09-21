#!/usr/bin/env node
/* ============================================================================
   art/gen.mjs —— 美术资产生成器（零依赖）
   ----------------------------------------------------------------------------
   画风 = style.json 里那 6 条规则。这个文件只负责【照着规则画】。
   想改画风 → 改 style.json，别改这里。
   想加人   → 加 characters.json 一行，重跑。

   用法:
     node art/gen.mjs            # 生成到 art/out/
     node art/gen.mjs --check    # 只校验角色可辨识性（两两至少 3 维不同）
   ========================================================================== */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(fileURLToPath(new URL(".", import.meta.url)));
const S = JSON.parse(fs.readFileSync(path.join(ROOT, "style.json"), "utf8"));
const C = JSON.parse(fs.readFileSync(path.join(ROOT, "characters.json"), "utf8"));

const PX = S.authorScale, G = S.grid, P = S.palette, T = S.texture;
const OUT = path.join(ROOT, "out");

/* ── 基础：坐标一律写【逻辑单位】，输出时乘 PX ───────────────────────────── */
const u = v => +(v * PX).toFixed(2);
const svg = (w, h, body) =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="${u(w)}" height="${u(h)}" ` +
  `viewBox="0 0 ${u(w)} ${u(h)}" shape-rendering="geometricPrecision">${body}</svg>`;
const rect = (x, y, w, h, fill, extra = "") =>
  `<rect x="${u(x)}" y="${u(y)}" width="${u(w)}" height="${u(h)}" fill="${fill}" ${extra}/>`;
/* path()：d 里的坐标也过 u()。
   ★ 直接写 d="..." 会绕过缩放 —— 在 16 逻辑单位的画布上画出来只有一半大，
     而且缩在左上角。这个坑吃过一次（10 个物品图标全缩了一半）。
   ★ 圆弧 a/A 的第 4、5 个参数是 large-arc-flag / sweep-flag，是布尔，不能缩放。 */
const dp = (d, extra = "") => {
  const toks = d.match(/[A-Za-z]|[+-]?(?:\d+\.?\d*|\.\d+)/g) || [];
  const out = [];
  let cmd = "M", k = 0;
  for (const tk of toks) {
    if (/[A-Za-z]/.test(tk)) { cmd = tk; k = 0; out.push(tk); continue; }
    const up = cmd.toUpperCase();
    const isFlag = up === "A" && (k === 3 || k === 4);
    out.push(isFlag ? tk : String(u(parseFloat(tk))));
    const n = up === "A" ? 7 : up === "C" ? 6 : (up === "S" || up === "Q") ? 4
            : (up === "H" || up === "V") ? 1 : 2;
    k = (k + 1) % n;
  }
  return `<path d="${out.join(" ")}" ${extra}/>`;
};
const rrect = (x, y, w, h, r, fill, extra = "") =>
  `<rect x="${u(x)}" y="${u(y)}" width="${u(w)}" height="${u(h)}" rx="${u(r)}" fill="${fill}" ${extra}/>`;
const circ = (cx, cy, r, fill, extra = "") =>
  `<circle cx="${u(cx)}" cy="${u(cy)}" r="${u(r)}" fill="${fill}" ${extra}/>`;
const ell = (cx, cy, rx, ry, fill, extra = "") =>
  `<ellipse cx="${u(cx)}" cy="${u(cy)}" rx="${u(rx)}" ry="${u(ry)}" fill="${fill}" ${extra}/>`;
const line = (x1, y1, x2, y2, stroke, w = 1, extra = "") =>
  `<line x1="${u(x1)}" y1="${u(y1)}" x2="${u(x2)}" y2="${u(y2)}" ` +
  `stroke="${stroke}" stroke-width="${u(w)}" ${extra}/>`;
const pat = (id, w, h, body) =>
  `<pattern id="${id}" width="${u(w)}" height="${u(h)}" patternUnits="userSpaceOnUse">${body}</pattern>`;

/* 确定性伪随机 —— 同一个种子永远生成一模一样的贴图（不然每次跑都在抖） */
let seed = 20260921;
const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
const reset = () => { seed = 20260921; };

const files = [];
const emit = (rel, content) => {
  const abs = path.join(OUT, rel);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, content, "utf8");
  files.push(rel);
};
const add = (name, rel, w, h, anchor, layer, tags = []) =>
  manifest.push({ name, file: rel, w, h, anchor, layer, tags });
const manifest = [];

/* ══════════════════════════════════════════════════════════════════════════
   一、地面贴图（可平铺 · 1 格）
   规则：平涂 + 1px 重复纹理 ≤22% + 全部对齐网格
   ══════════════════════════════════════════════════════════════════════════ */
function tufts(base, dark, light, n) {
  let s = "";
  for (let i = 0; i < n; i++) {
    const x = 2 + Math.floor(rnd() * (G - 4)), y = 2 + Math.floor(rnd() * (G - 4));
    const c = rnd() < 0.5 ? dark : light;
    s += rect(x, y, 2, 1, c, `opacity="0.55"`);
    s += rect(x + 1, y - 1, 1, 1, c, `opacity="0.35"`);
  }
  return s;
}
function groundTiles() {
  reset();
  // 草
  {
    let body = rect(0, 0, G, G, P.grass.base);
    body += `<defs>${pat("h", G, G, tufts(P.grass.base, P.grass.dark, P.grass.light, 9))}</defs>`;
    body += rect(0, 0, G, G, "url(#h)");
    emit("ground/grass.svg", svg(G, G, body));
    add("grass", "ground/grass.svg", G, G, "topleft", "L0", ["tileable"]);
  }
  // 土
  {
    let d = "";
    for (let i = 0; i < 14; i++)
      d += circ(3 + rnd() * (G - 6), 3 + rnd() * (G - 6), 0.6 + rnd() * 0.7,
                rnd() < 0.5 ? P.dirt.dark : P.dirt.light, `opacity="${T.speckleAlpha + 0.06}"`);
    let body = rect(0, 0, G, G, P.dirt.base);
    body += `<defs>${pat("d", G, G, d)}</defs>` + rect(0, 0, G, G, "url(#d)");
    emit("ground/dirt.svg", svg(G, G, body));
    add("dirt", "ground/dirt.svg", G, G, "topleft", "L0", ["tileable"]);
  }
  // 广场砖
  {
    const st = T.pavingStep;
    let b = "";
    for (let x = st; x < G; x += st) b += line(x, 0, x, G, P.plaza.dark, 1, `opacity="0.55"`);
    for (let y = st; y < G; y += st) b += line(0, y, G, y, P.plaza.dark, 1, `opacity="0.55"`);
    let body = rect(0, 0, G, G, P.plaza.base);
    body += `<defs>${pat("p", G, G, b)}</defs>` + rect(0, 0, G, G, "url(#p)");
    emit("ground/plaza.svg", svg(G, G, body));
    add("plaza", "ground/plaza.svg", G, G, "topleft", "L0", ["tileable"]);
  }
  // 水
  {
    let b = line(0, 8, G, 8, P.water.light, 1, `opacity="0.5"`);
    b += line(4, 20, G, 20, P.water.light, 1, `opacity="0.35"`);
    b += line(0, 27, G, 27, P.water.dark, 1, `opacity="0.4"`);
    let body = rect(0, 0, G, G, P.water.base);
    body += `<defs>${pat("w", G, G, b)}</defs>` + rect(0, 0, G, G, "url(#w)");
    emit("ground/water.svg", svg(G, G, body));
    add("water", "ground/water.svg", G, G, "topleft", "L0", ["tileable"]);
  }
  // 沥青（路面填充，可平铺）
  {
    let d = "";
    for (let i = 0; i < 22; i++)
      d += rect(2 + rnd() * (G - 4), 2 + rnd() * (G - 4), 1, 1,
                rnd() < 0.6 ? P.asphalt.light : "#3f3d3d", `opacity="${T.speckleAlpha}"`);
    let body = rect(0, 0, G, G, P.asphalt.base);
    body += `<defs>${pat("a", G, G, d)}</defs>` + rect(0, 0, G, G, "url(#a)");
    emit("ground/asphalt.svg", svg(G, G, body));
    add("asphalt", "ground/asphalt.svg", G, G, "topleft", "L1", ["tileable"]);
  }
  // 人行道（路面边框用，可平铺；缝在 16 格）
  {
    const st = T.pavingStep, h = 6;
    const b = line(st, 0, st, h, P.sidewalk.line, 1, `opacity="0.7"`);
    let body = rect(0, 0, G, h, P.sidewalk.base);
    body += `<defs>${pat("s", G, h, b)}</defs>` + rect(0, 0, G, h, "url(#s)");
    body += line(0, h - 0.5, G, h - 0.5, P.sidewalk.line, 1, `opacity="0.5"`);
    emit("ground/sidewalk.svg", svg(G, h, body));
    add("sidewalk", "ground/sidewalk.svg", G, h, "topleft", "L1", ["tileable"]);
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   二、道路标线（形状本身是平涂矩形，交给代码画；这里只给"纹理味"）
   ══════════════════════════════════════════════════════════════════════════ */
function roadBits() {
  // 中线虚线（横）
  {
    const body = rect(0, 0, 16, 2, P.marking, `opacity="0.75"`);
    emit("road/marking_dash_h.svg", svg(30, 2, body));
    add("marking_dash_h", "road/marking_dash_h.svg", 30, 2, "topleft", "L1", ["tileable"]);
  }
  // 中线虚线（竖）
  {
    const body = rect(0, 0, 2, 16, P.marking, `opacity="0.75"`);
    emit("road/marking_dash_v.svg", svg(2, 30, body));
    add("marking_dash_v", "road/marking_dash_v.svg", 2, 30, "topleft", "L1", ["tileable"]);
  }
  // 斑马线（横穿，可平铺）
  {
    const body = rect(0, 0, G, 6, P.marking, `opacity="0.7"`);
    emit("road/crosswalk.svg", svg(G, 6, body));
    add("crosswalk", "road/crosswalk.svg", G, 6, "topleft", "L1", ["tileable"]);
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   三、地块装饰（锚点在【底部中心】，因为它们"立"在地上）
   ══════════════════════════════════════════════════════════════════════════ */
/* 树：锚点在底边 = 树干尖落在地上。
   所以画布要【给树干留高度】—— 树冠只占上面 size，下面 4px 是露出来的树干。 */
function tree(size) {
  const { base, dark, light, trunk } = P.tree;
  const H = size + 4, r = size / 2, cx = size / 2, cy = r;
  const tW = r * 0.32, tTop = cy + r * 0.45;
  let b = "";
  b += rrect(cx - tW / 2, tTop, tW, H - tTop, tW * 0.45, trunk);   // 树干：从冠下缘到底边
  b += circ(cx, cy, r, dark);
  b += circ(cx - r * 0.12, cy - r * 0.12, r * 0.86, base);
  b += circ(cx - r * 0.3, cy - r * 0.3, r * 0.42, light, `opacity="0.85"`);
  return svg(size, H, b);
}
function props() {
  // 树 ×3（小/中/大）
  for (const [k, s] of [["s", 20], ["m", 27], ["l", 34]]) {
    emit(`props/tree_${k}.svg`, tree(s));
    add(`tree_${k}`, `props/tree_${k}.svg`, s, s + 4, "bottomcenter", "L2");
  }
  // 灌木 ×2
  for (const [k, s] of [["1", 15], ["2", 18]]) {
    const { base, dark, light } = P.tree, cx = s / 2, cy = s / 2 + 1, r = s / 2;
    let b = circ(cx, cy, r, dark);
    b += circ(cx - r * 0.22, cy - r * 0.2, r * 0.62, base);
    b += circ(cx - r * 0.36, cy - r * 0.36, r * 0.26, light, `opacity="0.8"`);
    emit(`props/bush_${k}.svg`, svg(s, s + 1, b));
    add(`bush_${k}`, `props/bush_${k}.svg`, s, s + 1, "bottomcenter", "L2");
  }
  // 长椅
  {
    const W = 26, H = 12, m = P.metal, w = P.wall;
    let b = rect(1, H - 4, 2, 4, m.dark) + rect(W - 3, H - 4, 2, 4, m.dark);
    b += rrect(0, 3, W, 5, 1.2, w.base) + line(0, 4, W, 4, w.dark, 1, `opacity="0.6"`);
    b += rrect(0, 0, W, 3.5, 1.2, w.dark);
    emit("props/bench.svg", svg(W, H, b));
    add("bench", "props/bench.svg", W, H, "bottomcenter", "L2");
  }
  // 路灯
  {
    const W = 10, H = 30, m = P.metal;
    let b = rect(W / 2 - 1, 6, 2, H - 8, m.base);
    b += circ(W / 2, 5, 3.4, m.dark) + circ(W / 2, 5, 2.4, "#f3e2b0");
    b += ell(W / 2, H - 1.5, 2.4, 1.4, m.dark);
    emit("props/lamp.svg", svg(W, H, b));
    add("lamp", "props/lamp.svg", W, H, "bottomcenter", "L2");
  }
  // 垃圾桶
  {
    const W = 11, H = 13, m = P.metal;
    let b = rrect(1, 3, W - 2, H - 4, 1.5, m.base);
    b += rrect(0, 1, W, 3, 1.5, m.dark);
    b += line(3, 5, 3, H - 3, m.dark, 1, `opacity="0.5"`);
    b += line(W - 3, 5, W - 3, H - 3, m.dark, 1, `opacity="0.5"`);
    emit("props/bin.svg", svg(W, H, b));
    add("bin", "props/bin.svg", W, H, "bottomcenter", "L2");
  }
  // 花坛
  {
    const W = 24, H = 14, w = P.wall;
    let b = rrect(0, 4, W, H - 4, 1.5, w.base) + line(0, 5, W, 5, w.dark, 1, `opacity="0.6"`);
    for (let i = 0; i < 5; i++) {
      const c = [P.tree.base, P.tree.light, P.accent][i % 3];
      b += circ(4 + i * 4, 5, 2.4, c, `opacity="0.9"`);
    }
    emit("props/flowerbed.svg", svg(W, H, b));
    add("flowerbed", "props/flowerbed.svg", W, H, "bottomcenter", "L2");
  }
  // 车 ×3（同一个形状，三个颜色）
  P.car.forEach((col, i) => {
    const W = 18, H = 32;
    let b = "";
    b += rrect(1, 1, W - 2, H - 2, 3, col);
    b += rrect(2.5, 5, W - 5, 8, 2, "#ffffff", `opacity="0.18"`);      // 前风挡
    b += rrect(2.5, H - 13, W - 5, 7, 2, "#ffffff", `opacity="0.13"`); // 后风挡
    b += rect(2, H / 2 - 2, 3, 4, P.marking, `opacity="0.35"`);        // 后视镜/反光
    b += rect(W - 5, H / 2 - 2, 3, 4, P.marking, `opacity="0.35"`);
    b += rrect(1, 1, W - 2, H - 2, 3, "none", `stroke="#00000033" stroke-width="${u(1)}"`);
    emit(`props/car_${i + 1}.svg`, svg(W, H, b));
    add(`car_${i + 1}`, `props/car_${i + 1}.svg`, W, H, "bottomcenter", "L2");
  });
}


/* ══════════════════════════════════════════════════════════════════════════
   三·五、物品（货 / 家具）★
   ----------------------------------------------------------------------------
   物品需要【两套语言】，这是故意的：

     世界形态 = 俯视    地图是俯视的，货摆在地上要贴地
     图标形态 = 正视    16px 的小图标，正视才认得出来 —— 俯视的苹果就是个圆

   物品清单照 config/items/*.json，不自己编：
     货·消耗品  苹果 / 梨 / 简餐       → 会卖光，所以额外给一张【空态】
     原料       简餐原料               → 工厂产、批发市场收
     家具       床 / 前台 / 工位 / 工业机器 / 马桶   → 恒为 1、永不消耗
   ══════════════════════════════════════════════════════════════════════════ */
const I = P.item;

/* 货箱：货都装在箱子里 —— 空箱 = "卖光了"（形状，不是文字） */
function crate(w, h, fill, dark, inner) {
  let b = rrect(0, 0, w, h, 2, fill);
  b += rect(0, 0, w, h, "none", `stroke="${dark}" stroke-width="${u(1)}"`);
  b += line(1, 2.2, w - 1, 2.2, dark, 1, `opacity="0.4"`);
  b += line(1, h - 2.2, w - 1, h - 2.2, dark, 1, `opacity="0.4"`);
  return b + (inner || "");
}
/* 3 颗果子（苹果/梨共用骨架，形状不同） */
function fruits(w, h, c, round) {
  let b = crate(w, h, I.crate.base, I.crate.dark);
  const r = round ? 4.1 : 4.0, cy = h / 2 + 1.2;
  [0.27, 0.5, 0.73].forEach(xr => {
    const x = w * xr;
    if (round) {
      b += circ(x, cy + 0.6, r, c.dark);
      b += circ(x, cy, r, c.base);
      b += circ(x - r * 0.32, cy - r * 0.32, r * 0.32, c.light, `opacity="0.8"`);
      b += line(x, cy - r * 0.88, x + 0.7, cy - r * 1.6, c.stem, 0.9);
    } else {
      b += ell(x, cy + 0.6, r * 0.92, r * 1.12, c.dark);
      b += ell(x, cy, r * 0.92, r * 1.12, c.base);
      b += ell(x - r * 0.3, cy - r * 0.34, r * 0.3, r * 0.36, c.light, `opacity="0.8"`);
      b += line(x, cy - r * 1.05, x + 0.6, cy - r * 1.7, c.stem, 0.9);
    }
  });
  return b;
}
/* 简餐：便当盒（俯视 = 一个盖着盖子的方盒，露出一点菜色） */
function bento(w, h, empty) {
  let b = rrect(0, 0, w, h, 2.5, I.meal.box);
  b += rect(0, 0, w, h, "none", `stroke="${I.meal.lid}" stroke-width="${u(1)}"`);
  b += rrect(3, 3, w - 6, h - 6, 1.5, I.meal.lid);
  if (!empty) {
    b += rrect(5.5, h * 0.34, w * 0.42, h * 0.42, 1.2, I.meal.food);
    b += rrect(w * 0.54, h * 0.34, w * 0.4 - 5, h * 0.42, 1.2, I.meal.green);
  }
  b += line(w * 0.5, 3, w * 0.5, h - 3, I.meal.lid, 1, `opacity="0.7"`);
  return b;
}
/* 简餐原料：麻袋（俯视 = 一坨鼓起来的袋子 + 扎口 + 撒出来的颗粒） */
function sack(w, h) {
  let b = "";
  b += ell(w / 2, h * 0.58, w * 0.44, h * 0.4, I.raw.dark);
  b += ell(w / 2, h * 0.55, w * 0.42, h * 0.38, I.raw.sack);
  b += ell(w / 2, h * 0.3, w * 0.17, h * 0.13, I.raw.tie);       // 扎口
  b += rrect(w / 2 - 1.2, h * 0.16, 2.4, h * 0.2, 1, I.raw.tie);
  b += circ(w * 0.3, h * 0.2, 0.9, I.raw.grain, `opacity="0.9"`);
  b += circ(w * 0.72, h * 0.26, 0.7, I.raw.grain, `opacity="0.8"`);
  b += ell(w * 0.36, h * 0.46, w * 0.1, h * 0.12, I.raw.grain, `opacity="0.35"`);
  return b;
}
/* 床：俯视 = 床架 + 床单 + 一端枕头 + 毯子盖住大半 */
function bed(w, h) {
  const B = I.bed;
  let b = rrect(0, 0, w, h, 3, B.frame);
  b += rect(0, 0, w, h, "none", `stroke="${B.dark}" stroke-width="${u(1)}"`);
  b += rrect(3, 3, w - 6, h - 6, 2, B.sheet);
  b += rrect(5, 5, w * 0.2, h - 10, 2.5, B.pillow);               // 枕头（头这端）
  b += rrect(w * 0.28, 3, w - 3 - w * 0.28, h - 6, 2, B.blanket);  // 毯子（右缘对齐床单）
  b += line(w * 0.28, 3, w * 0.28, h - 3, B.dark, 1, `opacity="0.5"`);
  b += line(w * 0.32, h * 0.5, w - 5, h * 0.5, B.dark, 1, `opacity="0.22"`);
  return b;
}
/* 前台/柜台：一侧是台面（浅色内嵌），一端有收银机 */
function counter(w, h) {
  const C = I.counter;
  let b = rrect(0, 0, w, h, 2, C.body);
  b += rect(0, 0, w, h, "none", `stroke="${C.dark}" stroke-width="${u(1)}"`);
  b += rrect(3, 2.5, w - 6, h - 5, 1.5, C.top);                   // 台面
  b += rrect(w - 20, h * 0.22, 13, h * 0.56, 1.5, C.reg);         // 收银机
  b += rect(w - 17, h * 0.34, 7, 3.5, "#a9c3cf", `opacity="0.85"`);
  return b;
}
/* 工位：工作台 + 台钳 + 工具痕 */
function bench(w, h) {
  const B = I.bench;
  let b = rrect(0, 0, w, h, 2, B.body);
  b += rect(0, 0, w, h, "none", `stroke="${B.dark}" stroke-width="${u(1)}"`);
  b += rrect(2.5, 2.5, w - 5, h - 5, 1.5, B.top);
  b += rrect(5, h * 0.28, 10, h * 0.44, 1.2, B.tool);             // 台钳
  b += line(w * 0.42, h * 0.3, w * 0.42, h * 0.7, B.dark, 1, `opacity="0.5"`);
  b += rrect(w * 0.55, h * 0.32, 8, 2.6, 0.8, B.tool, `opacity="0.9"`);
  b += rrect(w * 0.55, h * 0.58, 11, 2.6, 0.8, B.tool, `opacity="0.75"`);
  return b;
}
/* 工业机器：机体 + 通风格栅 + 表盘 + 出料口 */
function machine(w, h) {
  const M = I.machine;
  let b = rrect(0, 0, w, h, 2.5, M.body);
  b += rect(0, 0, w, h, "none", `stroke="${M.dark}" stroke-width="${u(1)}"`);
  b += line(2, 2.5, w - 2, 2.5, M.light, 1, `opacity="0.7"`);
  for (let i = 0; i < 4; i++)                                     // 格栅
    b += rect(5, 6 + i * 3.2, w * 0.42, 1.6, M.vent, `opacity="0.7"`);
  b += circ(w * 0.74, h * 0.3, 4.4, M.dark);                      // 表盘
  b += circ(w * 0.74, h * 0.3, 3.2, "#c9d1d5");
  b += line(w * 0.74, h * 0.3, w * 0.82, h * 0.24, M.vent, 1);
  b += rrect(w * 0.6, h * 0.56, w * 0.3, h * 0.3, 1.5, M.vent);   // 出料口
  b += circ(w * 0.12, h * 0.82, 2.2, P.accent, `opacity="0.85"`);
  return b;
}
/* 马桶：俯视 = 水箱（靠墙那端）+ 座圈 */
function toilet(w, h) {
  const T = I.toilet;
  let b = rrect(w * 0.16, 0, w * 0.68, h * 0.3, 1.5, T.body);     // 水箱
  b += rect(w * 0.16, 0, w * 0.68, h * 0.3, "none", `stroke="${T.dark}" stroke-width="${u(1)}"`);
  b += ell(w / 2, h * 0.6, w * 0.42, h * 0.34, T.dark);           // 座圈底
  b += ell(w / 2, h * 0.6, w * 0.38, h * 0.3, T.body);
  b += ell(w / 2, h * 0.62, w * 0.24, h * 0.19, T.water);         // 内圈
  b += ell(w / 2, h * 0.62, w * 0.24, h * 0.19, "none",
    `stroke="${T.seat}" stroke-width="${u(1)}"`);
  return b;
}

/* ── 图标（16×16 正视）：小图标要"一眼认得出是什么" ──────────────────── */
function iconApple() {
  return circ(8, 9.6, 5, I.apple.dark) + circ(7.6, 9.2, 4.8, I.apple.base)
       + circ(6.2, 8, 1.5, I.apple.light, `opacity="0.85"`)
       + line(8, 5.2, 8, 3.2, I.apple.stem, 1)
       + dp("M 8 4.6 Q 10.4 2.6 11.4 4.4 Q 9.6 6 8 4.6 Z", `fill="${I.apple.leaf}"`);
}
function iconPear() {
  return dp("M 8 3.4 C 9.6 5 12.6 7.4 12.6 10.2 A 4.6 4.6 0 0 1 3.4 10.2 "
            + "C 3.4 7.4 6.4 5 8 3.4 Z", `fill="${I.pear.dark}"`)
       + dp("M 8 3.9 C 9.4 5.3 12.1 7.6 12.1 10.2 A 4.1 4.1 0 0 1 3.9 10.2 "
            + "C 3.9 7.6 6.6 5.3 8 3.9 Z", `fill="${I.pear.base}"`)
       + circ(6.4, 8.6, 1.3, I.pear.light, `opacity="0.8"`)
       + line(8, 3.6, 8.6, 1.8, I.pear.stem, 1);
}
function iconMeal() {
  return rrect(2, 5, 12, 8, 1.6, I.meal.box)
       + rect(2, 5, 12, 8, "none", `stroke="${I.meal.lid}" stroke-width="${u(1)}"`)
       + rrect(3.4, 6.4, 5, 5, 1, I.meal.food)
       + rrect(9.2, 6.4, 3.4, 5, 1, I.meal.green);
}
function iconRaw() {
  return dp("M 8 2.4 C 11.6 2.4 14 5.2 14 8.8 L 14 13.6 H 2 V 8.8 C 2 5.2 4.4 2.4 8 2.4 Z",
            `fill="${I.raw.sack}"`)
       + rrect(5.4, 1, 5.2, 2.4, 1, I.raw.tie)
       + circ(6.4, 8, 0.8, I.raw.grain, `opacity="0.9"`)
       + circ(9.6, 9.6, 0.7, I.raw.grain, `opacity="0.8"`);
}
function iconBed() {
  const B = I.bed;
  return rrect(1.5, 5, 13, 7, 1.5, B.frame)
       + rrect(3, 6.4, 10, 5.2, 1, B.sheet)
       + rrect(2.6, 3.6, 10.8, 3.2, 1.2, B.pillow)
       + rrect(6.6, 6.4, 6.4, 5.2, 1, B.blanket);
}
function iconCounter() {
  const C = I.counter;
  return rrect(1, 6, 14, 6, 1.4, C.body)
       + rrect(2.4, 6.8, 11.2, 2.6, 1, C.top)
       + rrect(9.6, 2.6, 4.4, 4, 1, C.reg)
       + rect(10.4, 3.6, 2.8, 1.8, "#a9c3cf");
}
function iconMachine() {
  const M = I.machine;
  return rrect(2, 2.6, 12, 10.8, 1.6, M.body)
       + line(2.8, 3.6, 13.2, 3.6, M.light, 1, `opacity="0.7"`)
       + rect(3.6, 5.4, 5, 1.4, M.vent) + rect(3.6, 7.4, 5, 1.4, M.vent)
       + circ(11, 6.4, 2, M.dark) + circ(11, 6.4, 1.3, "#c9d1d5")
       + rrect(8, 9.6, 5.6, 2.8, 0.8, M.vent);
}
/* 米：木桶装白米（不做成布袋 —— 布袋和"简餐原料"的麻袋会撞） */
function riceTub(w, h) {
  const C = I.rice, cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.46;
  let b = circ(cx, cy, r, C.dark);
  b += circ(cx, cy, r - 1.8, C.barrel);
  b += circ(cx, cy, r - 4.6, C.grain2);
  b += circ(cx, cy, r - 6, C.grain);
  b += circ(cx - r * 0.3, cy - r * 0.26, r * 0.5, C.grain2, `opacity="0.55"`);
  [[-0.34, 0.3], [0.1, 0.42], [0.36, 0.14], [-0.05, -0.3], [0.24, -0.36]].forEach(([dx, dy]) => {
    b += ell(cx + r * dx, cy + r * dy, r * 0.1, r * 0.07, C.grain2, `opacity="0.95"`);
  });
  return b;
}
/* 面包：俯视 = 一条椭圆面包 + 三道斜切 */
function breadLoaf(w, h) {
  const C = I.bread;
  let b = "";
  b += ell(w / 2, h / 2 + 1, w * 0.47, h * 0.4, C.dark);
  b += ell(w / 2, h / 2, w * 0.46, h * 0.38, C.crust);
  b += ell(w / 2 - w * 0.06, h / 2 - h * 0.04, w * 0.34, h * 0.22, C.top, `opacity="0.7"`);
  for (let i = 0; i < 3; i++) {
    const x = w * (0.28 + i * 0.22);
    b += line(x, h * 0.26, x + w * 0.11, h * 0.6, C.cut, 1.7, `opacity="0.9"`);
  }
  return b;
}
/* 牛奶：纸盒（俯视 = 矩形 + 一端折角） */
function milkCarton(w, h) {
  const C = I.milk;
  let b = "";
  b += rrect(0, 5, w, h - 5, 1.5, C.dark);
  b += rrect(0.9, 5.8, w - 1.8, h - 7, 1.2, C.carton);
  b += rrect(0.6, 0.6, w - 1.2, 5.6, 1, C.dark);            // 顶折
  b += rrect(1.4, 1.4, w - 2.8, 4, 0.8, C.band);            // 蓝条
  b += rect(1.6, h * 0.52, w - 3.2, 2.6, C.band, `opacity="0.8"`);
  b += circ(w - 4.4, h * 0.26, 1.5, C.cap);                 // 盖
  return b;
}
/* 热菜：俯视 = 盘子 + 菜 + 筷子。热气也画（俯视里是刻意的夸张，为了表达"热"）*/
function hotDish(w, h) {
  const C = I.dish, cx = w / 2, cy = h * 0.56, r = Math.min(w * 0.47, h * 0.42);
  let b = "";
  b += line(w * 0.08, h * 0.1, w * 0.84, h * 0.22, C.stick, 1.5);
  b += line(w * 0.1, h * 0.17, w * 0.86, h * 0.29, C.stick, 1.5);
  b += circ(cx, cy, r, C.rim);
  b += circ(cx, cy, r - 1.9, C.plate);
  b += ell(cx - r * 0.1, cy - r * 0.05, r * 0.52, r * 0.44, C.food);
  b += circ(cx + r * 0.34, cy + r * 0.22, r * 0.2, C.veg, `opacity="0.9"`);
  b += circ(cx - r * 0.36, cy + r * 0.3, r * 0.16, C.veg, `opacity="0.8"`);
  [[0.32, 0.26], [0.68, 0.28]].forEach(([xr, yr], i) => {
    b += `<path d="M ${u(w * xr)} ${u(h * yr)} q ${u(2.2)} ${u(-3)} 0 ${u(-5.4)}"`
       + ` fill="none" stroke="#ffffff" stroke-width="${u(1.3)}"`
       + ` stroke-linecap="round" opacity="${i ? 0.65 : 0.9}"/>`;
  });
  return b;
}
/* 饼干：一包饼干（包装 + 露出两块） */
function biscuitPack(w, h) {
  const C = I.biscuit, br = Math.min(w, h) * 0.23;
  let b = "";
  b += rrect(0.6, 5, w - 1.2, h - 5.6, 2, C.dark);
  b += rrect(1.4, 5.6, w - 2.8, h - 6.8, 1.6, C.wrap);
  b += rrect(0.6, 0.6, w - 1.2, 4.6, 1, C.paper);           // 顶部封口
  for (let x = 2.4; x < w - 2.4; x += 4)
    b += line(x, 1, x + 1.8, 4.4, C.dark, 1, `opacity="0.5"`);
  b += circ(w * 0.37, h * 0.56, br, C.dark);
  b += circ(w * 0.37, h * 0.55, br - 0.6, C.bake);
  b += circ(w * 0.37 - 1.3, h * 0.55 - 1.6, 1.1, C.chip, `opacity="0.7"`);
  b += circ(w * 0.37 + 1.5, h * 0.55 + 1.4, 0.9, C.chip, `opacity="0.7"`);
  b += circ(w * 0.71, h * 0.56, br - 1.4, C.bake, `opacity="0.92"`);
  return b;
}
/* 汽水：罐（俯视 = 圆罐顶 + 拉环） */
function sodaCan(w, h) {
  const C = I.soda, cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.46;
  let b = "";
  b += circ(cx, cy, r, C.dark);
  b += circ(cx, cy, r - 1.1, C.metal);
  b += circ(cx, cy, r - 3.6, C.body);
  b += rrect(cx - r * 0.34, cy - r * 0.12, r * 0.68, r * 0.24, r * 0.12, C.metal);  // 拉环
  b += circ(cx, cy, r * 0.1, C.dark, `opacity="0.5"`);
  return b;
}
/* 咖啡：杯 + 碟（俯视） */
function coffeeCup(w, h) {
  const C = I.coffee, cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.36;
  let b = "";
  b += circ(cx, cy, r + 2.2, C.saucer);                      // 碟
  b += circ(cx, cy, r + 2.2, "none",
    `stroke="${C.dark}" stroke-width="${u(1)}" opacity="0.6"`);
  b += circ(cx, cy, r, C.dark);
  b += circ(cx, cy, r - 1.3, C.cup);
  b += circ(cx, cy, r - 3.4, C.liquid);
  b += circ(cx - r * 0.32, cy - r * 0.3, r * 0.36, C.foam, `opacity="0.7"`);
  return b;
}
/* 货架：容器。刻意画成【浅色层板面】—— 货要摆在上面还得看得见 */
function shelfUnit(w, h) {
  const C = I.shelf;
  let b = "";
  b += rrect(0, 0, w, h, 2, C.dark);
  b += rrect(1.8, 1.8, w - 3.6, h - 3.6, 1.4, C.deck);
  b += rect(1.8, h * 0.42, w - 3.6, 2.2, C.wood);
  b += rect(1.8, h * 0.72, w - 3.6, 2.2, C.wood);
  [[0.6, 0.6], [w - 3.4, 0.6], [0.6, h - 3.4], [w - 3.4, h - 3.4]].forEach(([x, y]) => {
    b += rect(x, y, 2.8, 2.8, C.wood);
  });
  b += rect(0, 0, w, h, "none", `stroke="${C.dark}" stroke-width="${u(1)}"`);
  return b;
}
/* 冰柜：容器。玻璃盖【半透明】—— 下面的货要透得出来 */
function freezerUnit(w, h) {
  const C = I.freezer;
  let b = "";
  b += rrect(0, 0, w, h, 3, C.trim);
  b += rrect(1.8, 1.8, w - 3.6, h - 3.6, 2.2, C.body);
  b += rrect(4.2, 4.2, w - 8.4, h - 8.4, 1.8, C.glass, `opacity="0.42"`);
  b += line(4.2, h * 0.5, w - 4.2, h * 0.5, "#ffffff", 1.2, `opacity="0.35"`);
  b += line(w * 0.5, 4.2, w * 0.5, h - 4.2, "#ffffff", 1, `opacity="0.22"`);
  b += rrect(w * 0.6, h - 7.4, w * 0.32, 3, 1.4, C.trim);      // 把手
  b += rect(0, 0, w, h, "none", `stroke="${C.dark}" stroke-width="${u(1)}"`);
  return b;
}
/* 灶台：俯视 = 台面 + 两个灶眼 */
function stoveUnit(w, h) {
  const C = I.stove, r = Math.min(w, h) * 0.19;
  let b = "";
  b += rrect(0, 0, w, h, 2, C.dark);
  b += rrect(1.4, 1.4, w - 2.8, h - 2.8, 1.6, C.body);
  b += line(1.4, 1.4, w - 1.4, 1.4, "#ffffff", 1, `opacity="0.18"`);
  [[0.34, 0.44], [0.66, 0.44]].forEach(([xr, yr], i) => {
    const cx = w * xr, cy = h * yr;
    b += circ(cx, cy, r, C.burner);
    b += circ(cx, cy, r * 0.62, C.ring, `opacity="0.55"`);
    if (i === 0) b += circ(cx, cy, r * 0.34, C.flame, `opacity="0.9"`);
  });
  b += circ(w * 0.3, h * 0.83, 2, C.ring);
  b += circ(w * 0.7, h * 0.83, 2, C.ring);
  return b;
}

/* ── 新物品的图标（16×16 正视）───────────────────────────────────────── */
function iconRice() {
  const C = I.rice;
  return dp("M 1.4 5.8 h 13.2 v 7.6 a 1.6 1.6 0 0 1 -1.6 1.6 H 3 "
            + "a 1.6 1.6 0 0 1 -1.6 -1.6 Z", `fill="${C.barrel}"`)
       + ell(8, 5.8, 6.6, 3.4, C.grain)
       + ell(8, 5.6, 5.1, 2.5, C.grain2)
       + ell(6.2, 5.4, 1.5, 0.8, C.grain)
       + ell(9.8, 6.2, 1.2, 0.65, C.grain);
}
function iconBread() {
  const C = I.bread;
  return dp("M 2 10.6 C 2 5.6 4.8 3 8 3 C 11.2 3 14 5.6 14 10.6 Z", `fill="${C.crust}"`)
       + dp("M 3.4 10.2 C 3.4 6.6 5.4 4.4 8 4.4 C 10.6 4.4 12.6 6.6 12.6 10.2 Z",
              `fill="${C.top}" opacity="0.55"`)
       + line(5.4, 5.4, 6.4, 9.4, C.cut, 1.2) + line(8, 5, 9, 9.4, C.cut, 1.2)
       + line(10.4, 5.6, 11.2, 9.4, C.cut, 1.2);
}
function iconMilk() {
  const C = I.milk;
  return dp("M 4 4.6 L 8 1.6 L 12 4.6 V 13.4 H 4 Z",
              `fill="${C.carton}" stroke="${C.dark}" stroke-width="${u(0.9)}"`)
       + dp("M 4 4.6 L 8 1.6 L 12 4.6 Z", `fill="${C.dark}"`)
       + rect(4.6, 5.4, 6.8, 2.2, C.band) + rect(4.6, 9.4, 6.8, 1.4, C.band, `opacity="0.7"`);
}
function iconHotDish() {
  const C = I.dish;
  return dp("M 2.4 8 h 11.2 a 5.6 5.6 0 0 1 -11.2 0 Z", `fill="${C.rim}"`)
       + dp("M 3.6 8 h 8.8 a 4.4 4.4 0 0 1 -8.8 0 Z", `fill="${C.plate}"`)
       + ell(8, 8, 3.2, 1, C.food)
       + line(5, 3, 5, 5, "#ffffff", 1.2, `opacity="0.9"`)
       + line(8, 2, 8, 4.6, "#ffffff", 1.2, `opacity="0.75"`)
       + line(11, 3.2, 11, 5, "#ffffff", 1.2, `opacity="0.6"`);
}
function iconBiscuit() {
  const C = I.biscuit;
  return circ(8, 8, 6.3, C.dark) + circ(8, 8, 5.7, C.bake)
       + circ(5.7, 5.7, 0.95, C.chip, `opacity="0.7"`) + circ(10.2, 6.6, 0.95, C.chip, `opacity="0.7"`)
       + circ(7, 10.6, 0.95, C.chip, `opacity="0.7"`) + circ(10.8, 10.6, 0.75, C.chip, `opacity="0.6"`);
}
function iconSoda() {
  const C = I.soda;
  return rrect(4.4, 1.6, 7.2, 12.8, 1.4, C.dark)
       + rrect(5, 2.4, 6, 11.2, 1.2, C.body)
       + rrect(5, 2.4, 6, 2.2, 1, C.metal)
       + rect(5.6, 6.4, 4.8, 2.2, C.band, `opacity="0.9"`);
}
function iconCoffee() {
  const C = I.coffee;
  return dp("M 10.6 5.6 h 1.8 a 2 2 0 0 1 0 4 h -1.8",
              `fill="none" stroke="${C.dark}" stroke-width="${u(1.1)}"`)
       + dp("M 3.4 4.6 h 7.2 v 5.2 a 3.6 3.6 0 0 1 -7.2 0 Z",
              `fill="${C.cup}" stroke="${C.dark}" stroke-width="${u(0.9)}"`)
       + ell(7, 5, 3.4, 1.3, C.liquid)
       + line(5.4, 1.2, 5.4, 3, "#ffffff", 1.1, `opacity="0.85"`)
       + line(8, 1.4, 8, 3.2, "#ffffff", 1.1, `opacity="0.65"`);
}
function iconShelf() {
  const C = I.shelf;
  return rrect(1.6, 2.4, 12.8, 11.2, 1.2, C.dark)
       + rect(2.8, 3.6, 10.4, 8.8, C.deck)
       + rect(2.8, 6.4, 10.4, 1.6, C.wood)
       + rect(2.8, 9.4, 10.4, 1.6, C.wood)
       + rect(2.8, 3.6, 1.6, 8.8, C.wood) + rect(11.6, 3.6, 1.6, 8.8, C.wood);
}
function iconFreezer() {
  const C = I.freezer;
  return rrect(1.6, 3.6, 12.8, 9.6, 1.4, C.trim)
       + rrect(2.8, 4.6, 10.4, 6.4, 1, C.body)
       + rrect(2.8, 4.6, 10.4, 3.4, 1, C.glass, `opacity="0.5"`)
       + rrect(9.6, 10.4, 3.6, 1.4, 0.6, C.trim);
}
function iconStove() {
  const C = I.stove;
  return rrect(1.6, 3.6, 12.8, 9.6, 1.4, C.dark)
       + rrect(2.6, 4.4, 10.8, 8, 1, C.body)
       + circ(6, 7.4, 2.2, C.burner) + circ(10.4, 7.4, 2.2, C.burner)
       + circ(6, 7.4, 1.2, C.ring, `opacity="0.6"`)
       + circ(10.4, 7.4, 1.2, C.ring, `opacity="0.6"`)
       + circ(5.4, 11.4, 0.9, C.ring) + circ(10.6, 11.4, 0.9, C.ring);
}

function iconBench() {
  const B = I.bench;
  return rrect(1.6, 6.4, 12.8, 5.2, 1.4, B.body)
       + rrect(2.6, 5.6, 10.8, 2.6, 1, B.top)
       + rrect(3.4, 8.4, 3.4, 2.6, 0.8, B.tool)          // 台钳
       + rect(8, 8.6, 4.4, 1.3, B.dark)                  // 工具
       + rect(8, 10.4, 3, 1.3, B.dark)
       + line(1.6, 11.6, 14.4, 11.6, B.dark, 1, `opacity="0.6"`);
}
function iconToilet() {
  const T = I.toilet;
  return rrect(4, 2, 8, 4, 1.2, T.body)
       + rect(4, 2, 8, 4, "none", `stroke="${T.dark}" stroke-width="${u(1)}"`)
       + dp("M 4.4 6.4 H 11.6 A 3.6 3.6 0 0 1 8 13.6 A 3.6 3.6 0 0 1 4.4 6.4 Z",
            `fill="${T.body}" stroke="${T.dark}" stroke-width="${u(1)}"`)
       + ell(8, 9.6, 1.8, 1.8, T.water);
}

/* 清单：物品 → 世界形态 / 空态 / 图标。尺寸是按"摆进屋里"定的（逻辑 px）。 */
/* empty: 只有【盒子会留下】的货才有空态。
   苹果筐 / 梨筐 / 米缸 / 简餐盒 —— 卖光了盒子还在。
   面包 / 牛奶 / 热菜 / 汽水 / 咖啡 卖光了就是没有了 → 不画空态。 */
const ITEMS = [
  { id: "food_apple",     name: "苹果",     w: 36, h: 26,
    empty: () => crate(36, 26, I.crate.base, I.crate.dark),
    world: () => fruits(36, 26, I.apple, true),  icon: iconApple,  tags: ["goods", "consumable", "fresh"] },
  { id: "food_pear",      name: "梨子",     w: 36, h: 26,
    empty: () => crate(36, 26, I.crate.base, I.crate.dark),
    world: () => fruits(36, 26, I.pear, false),  icon: iconPear,   tags: ["goods", "consumable", "fresh"] },
  { id: "food_rice",      name: "米",       w: 32, h: 28,
    empty: () => riceTubEmpty(32, 28),
    world: () => riceTub(32, 28),                icon: iconRice,   tags: ["goods", "consumable", "staple"] },
  { id: "food_bread",     name: "面包",     w: 30, h: 22,
    world: () => breadLoaf(30, 22),              icon: iconBread,  tags: ["goods", "consumable", "staple"] },
  { id: "food_milk",      name: "牛奶",     w: 22, h: 28,
    world: () => milkCarton(22, 28),             icon: iconMilk,   tags: ["goods", "consumable", "fresh"] },
  { id: "meal_simple",    name: "简餐",     w: 32, h: 24,
    empty: () => bento(32, 24, true),
    world: () => bento(32, 24, false),           icon: iconMeal,   tags: ["goods", "consumable", "ready"] },
  { id: "meal_hot_dish",  name: "热菜",     w: 34, h: 30,
    world: () => hotDish(34, 30),                icon: iconHotDish,tags: ["goods", "consumable", "ready"] },
  { id: "food_biscuit",   name: "饼干",     w: 26, h: 24,
    world: () => biscuitPack(26, 24),            icon: iconBiscuit,tags: ["goods", "consumable", "snack"] },
  { id: "drink_soda",     name: "汽水",     w: 20, h: 20,
    world: () => sodaCan(20, 20),                icon: iconSoda,   tags: ["goods", "consumable", "drink"] },
  { id: "drink_coffee",   name: "咖啡",     w: 26, h: 26,
    world: () => coffeeCup(26, 26),              icon: iconCoffee, tags: ["goods", "consumable", "drink"] },
  { id: "meal_simple_raw",name: "简餐原料", w: 32, h: 28,
    world: () => sack(32, 28),                   icon: iconRaw,    tags: ["goods", "material"] },
  { id: "bed_basic",      name: "床",       w: 64, h: 40,
    world: () => bed(64, 40),                    icon: iconBed,    tags: ["fixture", "sleepable"] },
  { id: "station_counter",name: "前台",     w: 76, h: 26,
    world: () => counter(76, 26),                icon: iconCounter,tags: ["fixture", "station", "retail"] },
  { id: "station_workbench", name: "工位",  w: 60, h: 26,
    world: () => bench(60, 26),                  icon: iconBench,  tags: ["fixture", "station", "manufacture"] },
  { id: "industry_machine",  name: "工业机器", w: 52, h: 40,
    world: () => machine(52, 40),                icon: iconMachine,tags: ["fixture", "machine"] },
  { id: "toilet_basic",   name: "马桶",     w: 30, h: 34,
    world: () => toilet(30, 34),                 icon: iconToilet, tags: ["fixture", "toilet"] },
  { id: "shelf_basic",    name: "货架",     w: 48, h: 26,
    world: () => shelfUnit(48, 26),              icon: iconShelf,  tags: ["fixture", "container", "retail"] },
  { id: "freezer_basic",  name: "冰柜",     w: 48, h: 32,
    world: () => freezerUnit(48, 32),            icon: iconFreezer,tags: ["fixture", "container", "retail", "cold"] },
  { id: "stove_basic",    name: "灶台",     w: 36, h: 26,
    world: () => stoveUnit(36, 26),               icon: iconStove,  tags: ["fixture", "station", "cook"] },
];

/* 米缸的空态：桶还在，米没了 */
function riceTubEmpty(w, h) {
  const C = I.rice, cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.46;
  let b = circ(cx, cy, r, C.dark);
  b += circ(cx, cy, r - 1.8, C.barrel);
  b += circ(cx, cy, r - 4.6, C.dark, `opacity="0.55"`);
  return b;
}

function items() {
  for (const it of ITEMS) {
    // 世界形态（俯视）—— 锚点在中心，因为它摆在屋里的某个点上
    emit(`items/${it.id}.svg`, svg(it.w, it.h, it.world()));
    add(it.id, `items/${it.id}.svg`, it.w, it.h, "center", "L3",
        ["item", ...it.tags, it.id]);

    // 空态：只有"会卖光"的货才需要。★ 这是"卖光了"的世界表达（不用写文字）
    if (it.empty) {
      emit(`items/${it.id}_empty.svg`, svg(it.w, it.h, it.empty()));
      add(`${it.id}_empty`, `items/${it.id}_empty.svg`, it.w, it.h, "center", "L3",
          ["item", "empty", it.id]);
    }

    // 图标形态（正视 16×16）—— 给面板用：笔记 / 账本 / 气泡
    emit(`items/icon_${it.id}.svg`, svg(16, 16, it.icon()));
    add(`icon_${it.id}`, `items/icon_${it.id}.svg`, 16, 16, "center", "L6",
        ["icon", "item", it.id]);
  }
}


/* ══════════════════════════════════════════════════════════════════════════
   三·六、头像（正面胸像）★
   判据：屏幕空间、给面板用（关系页 / 常客墙 / 打听 / 账本）。
   和世界小人是【同一份角色数据】—— 所以同一个人在两处长得一致。
   ══════════════════════════════════════════════════════════════════════════ */
function portrait(ch) {
  const W = 32, H = 32, cx = 16;
  const Q = P.portrait, skin = SKINS[ch.skin] || SKINS[0];
  const hair = C.hairStyles[ch.hair] || C.hairStyles.short;
  const hs = hair.shape || "short", top = ch.top || "#7a8f6a";
  const OL = `stroke="#00000028" stroke-width="${u(1)}"`;
  let b = "";
  // 底
  b += rrect(0, 0, W, H, 4, Q.bg);
  b += rrect(0, 0, W, H, 4, "none", `stroke="${Q.bg2}" stroke-width="${u(1)}"`);
  // 肩 / 胸（下缘出画）
  const SHOULDER = "M 3.5 32 C 3.5 24 9 20.6 16 20.6 C 23 20.6 28.5 24 28.5 32 Z";
  b += dp(SHOULDER, `fill="${top}"`);
  b += dp(SHOULDER, `fill="none" ${OL}`);
  if (ch.acc === "apron")
    b += rrect(11, 25, 10, 7, 1.4, "#f0ece2", `opacity="0.9"`);
  // 脖子
  b += rrect(12.4, 17.4, 7.2, 5.4, 1.6, skin);
  b += rrect(12.4, 17.4, 7.2, 5.4, 1.6, "none", `stroke="#00000022" stroke-width="${u(1)}"`);
  // 头 + 耳
  b += circ(cx - 8.1, 13.6, 1.7, skin) + circ(cx + 8.1, 13.6, 1.7, skin);
  b += circ(cx, 13, 8.2, skin);
  // 头发
  if (hs === "hat") {
    // 帽顶和帽檐都挂在 cx 上（头像没有侧向，所以只有这一个中心）
    b += dp("M 7.2 8.6 A 8.8 8.8 0 0 1 24.8 8.6 Z", `fill="${hair.color}"`);
    b += rrect(cx - 10.6, 8.2, 21.2, 2.4, 1.2, hair.color);
    b += rrect(cx - 10.6, 8.2, 21.2, 1, 0.5, "#00000022");
  } else if (hs === "bald") {
    b += rrect(6.8, 12.4, 2.2, 5.4, 1.1, hair.color, `opacity="0.9"`);
    b += rrect(23, 12.4, 2.2, 5.4, 1.1, hair.color, `opacity="0.9"`);
  } else {
    b += dp("M 7.5 13.4 A 8.5 8.5 0 0 1 24.5 13.4 Z", `fill="${hair.color}"`);
    if (hs === "short") {   // ★ 原来只画了左边 —— 正面像看着是一边有鬓角一边没有
      b += rrect(6.9, 9, 2.6, 5.2, 1.3, hair.color);
      b += rrect(22.5, 9, 2.6, 5.2, 1.3, hair.color);
    }
    if (hs === "bun") b += circ(cx, 3.6, 3.2, hair.color);
    if (hs === "long") {
      b += rrect(5.6, 11, 3.4, 11, 1.7, hair.color);
      b += rrect(23, 11, 3.4, 11, 1.7, hair.color);
    }
    b += dp("M 7.5 13.4 A 8.5 8.5 0 0 1 24.5 13.4 Z", `fill="none" ${OL}`);
  }
  // 眉 / 眼 / 嘴
  b += line(11, 12.2, 14, 11.7, "#3a3128", 0.9, `opacity="0.8"`);
  b += line(21, 12.2, 18, 11.7, "#3a3128", 0.9, `opacity="0.8"`);
  b += ell(13, 14.6, 1.5, 1.7, "#ffffff");
  b += ell(19, 14.6, 1.5, 1.7, "#ffffff");
  b += circ(13.1, 14.7, 0.95, "#2b2620");
  b += circ(19.1, 14.7, 0.95, "#2b2620");
  b += dp("M 13.6 19 Q 16 20.6 18.4 19",
           `fill="none" stroke="#8a5a4a" stroke-width="${u(1)}" stroke-linecap="round"`);
  if (ch.acc === "glasses") {
    b += rrect(10.4, 13.2, 5.4, 3, 1, "none", `stroke="#3a3128" stroke-width="${u(1)}"`);
    b += rrect(16.2, 13.2, 5.4, 3, 1, "none", `stroke="#3a3128" stroke-width="${u(1)}"`);
    b += line(15.8, 14.2, 16.2, 14.2, "#3a3128", 1);
  }
  return b;
}
function portraits() {
  for (const ch of C.characters) {
    emit(`portraits/${ch.id}.svg`, svg(32, 32, portrait(ch)));
    add(`pt_${ch.id}`, `portraits/${ch.id}.svg`, 32, 32, "topleft", "UI",
        ["portrait", ch.id]);
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   三·七、建筑附件 ★ 复用到任意建筑上（招牌底 / 雨棚 / 烟囱 / 空调外机）
   招牌上的【字不进贴图】—— 这里只给底，字由代码画（编辑器能改名）。
   招牌按【九宫格】交付：middle 可横向拉伸适应任意宽度。
   ══════════════════════════════════════════════════════════════════════════ */
const SIGNS = [
  { id: "wood",  w: 48, h: 16, slice: { l: 7, r: 7, t: 5, b: 5 } },
  { id: "metal", w: 48, h: 14, slice: { l: 6, r: 6, t: 4, b: 4 } },
  { id: "neon",  w: 48, h: 16, slice: { l: 9, r: 9, t: 5, b: 5 } },
  { id: "cloth", w: 48, h: 18, slice: { l: 5, r: 5, t: 6, b: 5 } },
  { id: "light", w: 48, h: 16, slice: { l: 8, r: 8, t: 5, b: 5 } },
  { id: "hand",  w: 48, h: 14, slice: { l: 5, r: 5, t: 4, b: 4 } },
];
function signBody(s) {
  const A = P.attach["sign_" + s.id], W = s.w, H = s.h;
  const inner = { x: 3, y: 3, w: W - 6, h: H - 6 };   // ★ 留白区：字画在这里
  let b = "";
  if (s.id === "wood") {
    b += rrect(0, 0, W, H, 2, A.base);
    b += line(0, 0, W, 0, A.dark, 1.4);
    b += line(0, H - 1, W, H - 1, A.dark, 1.4);
    for (let x = 8; x < W - 6; x += 9) b += line(x, 1.5, x, H - 1.5, A.dark, 1, `opacity="0.35"`);
    b += circ(3.6, 3.6, 0.9, A.nail) + circ(W - 3.6, H - 3.6, 0.9, A.nail);
  } else if (s.id === "metal") {
    b += rrect(0, 0, W, H, 1.5, A.base);
    b += rrect(0.7, 0.7, W - 1.4, H - 1.4, 1, "none", `stroke="${A.dark}" stroke-width="${u(1)}"`);
    [3.4, W - 3.4].forEach(x => [3.4, H - 3.4].forEach(y => { b += circ(x, y, 0.8, A.rivet); }));
  } else if (s.id === "neon") {
    b += rrect(0, 0, W, H, 2.5, A.base);
    b += rrect(2.4, 2.4, W - 4.8, H - 4.8, 2, "none",
               `stroke="${A.glow}" stroke-width="${u(1.6)}" opacity="0.9"`);
    b += rrect(4.6, 4.2, W - 9.2, H - 8.4, 1.5, "none",
               `stroke="${A.glow}" stroke-width="${u(0.8)}" opacity="0.35"`);
  } else if (s.id === "cloth") {
    b += rrect(0, 3, W, H - 3, 1, A.base);
    b += rect(0, 3, W, H - 3, "none", `stroke="${A.dark}" stroke-width="${u(1)}"`);
    b += rrect(0, 0, W, 3.4, 1.4, A.rod);
    b += `<path d="M 0 ${u(H)} q ${u(3)} ${u(-3)} ${u(6)} 0 q ${u(3)} ${u(-3)} ${u(6)} 0
         q ${u(3)} ${u(-3)} ${u(6)} 0 q ${u(3)} ${u(-3)} ${u(6)} 0 q ${u(3)} ${u(-3)} ${u(6)} 0
         q ${u(3)} ${u(-3)} ${u(6)} 0 q ${u(3)} ${u(-3)} ${u(6)} 0 q ${u(3)} ${u(-3)} ${u(6)} 0
         L ${u(W)} ${u(H - 3)} L 0 ${u(H - 3)} Z" fill="${A.base}"/>`;
  } else if (s.id === "light") {
    b += rrect(0, 0, W, H, 2, A.dark);
    b += rrect(2, 2, W - 4, H - 4, 1.5, A.base);
    b += rrect(2, 2, W - 4, 2.4, 1, A.glow, `opacity="0.8"`);
  } else {
    b += rrect(0.6, 0.6, W - 1.2, H - 1.2, 1.5, A.base);
    b += rrect(0.6, 0.6, W - 1.2, H - 1.2, 1.5, "none",
               `stroke="${A.dark}" stroke-width="${u(1.2)}"`);
    b += line(5, H - 2.6, W - 4, H - 2.2, A.ink, 0.9, `opacity="0.5"`);
  }
  return { body: b, inner };
}
function attachments() {
  for (const s of SIGNS) {
    const { body, inner } = signBody(s);
    emit(`attach/sign_${s.id}.svg`, svg(s.w, s.h, body));
    // 九宫格：把 slice 写进清单，前端拉伸 middle 就能适配任意宽度
    const a = { name: `sign_${s.id}`, file: `attach/sign_${s.id}.svg`,
                w: s.w, h: s.h, anchor: "center", layer: "L3",
                tags: ["attach", "sign"], slice: s.slice,
                text: { x: inner.x, y: inner.y, w: inner.w, h: inner.h } };
    manifest.push(a);
  }
  // 雨棚 ×3（挂在门上沿）
  P.attach.awning.forEach((col, i) => {
    const W = 46, H = 16;
    let b = "";
    b += rrect(1, 0, W - 2, 9, 1.5, col);
    for (let x = 5; x < W - 4; x += 7) b += rect(x, 0, 3.4, 9, "#ffffff", `opacity="0.22"`);
    b += `<path d="M 1 ${u(9)} q ${u(3.8)} ${u(4)} ${u(7.6)} 0 q ${u(3.8)} ${u(4)} ${u(7.6)} 0
         q ${u(3.8)} ${u(4)} ${u(7.6)} 0 q ${u(3.8)} ${u(4)} ${u(7.6)} 0 q ${u(3.8)} ${u(4)} ${u(7.6)} 0
         q ${u(3.8)} ${u(4)} ${u(7.6)} 0 L ${u(W - 1)} ${u(9)} Z" fill="${col}"/>`;
    b += rect(1, 0, W - 2, 9.6, "none", `stroke="#00000030" stroke-width="${u(1)}"`);
    b += line(5, 12.6, 5, 15.4, "#00000033", 1.2) + line(W - 5, 12.6, W - 5, 15.4, "#00000033", 1.2);
    emit(`attach/awning_${i + 1}.svg`, svg(W, H, b));
    add(`awning_${i + 1}`, `attach/awning_${i + 1}.svg`, W, H, "bottomcenter", "L3",
        ["attach", "awning"]);
  });
  // 烟囱 ×2
  [["1", 15, 15], ["2", 18, 13]].forEach(([k, W, H]) => {
    const Cc = P.attach.chimney;
    let b = rrect(0, 0, W, H, 1.5, Cc.base);
    b += rect(0, 0, W, H, "none", `stroke="${Cc.dark}" stroke-width="${u(1)}"`);
    b += rrect(W * 0.22, H * 0.22, W * 0.56, H * 0.56, 1, Cc.flue);
    b += line(0, H - 1.5, W, H - 1.5, Cc.dark, 1.2, `opacity="0.7"`);
    emit(`attach/chimney_${k}.svg`, svg(W, H, b));
    add(`chimney_${k}`, `attach/chimney_${k}.svg`, W, H, "center", "L3",
        ["attach", "chimney"]);
  });
  // 空调外机 ×2
  [["1", 22, 18], ["2", 18, 15]].forEach(([k, W, H]) => {
    const A = P.attach.ac;
    let b = rrect(0, 0, W, H, 1.5, A.base);
    b += rect(0, 0, W, H, "none", `stroke="${A.dark}" stroke-width="${u(1)}"`);
    b += circ(W * 0.34, H * 0.5, Math.min(W, H) * 0.26, A.dark);
    b += circ(W * 0.34, H * 0.5, Math.min(W, H) * 0.19, A.fan);
    for (let i = 0; i < 3; i++)
      b += line(W * 0.62, H * (0.3 + i * 0.2), W - 2.5, H * (0.3 + i * 0.2), A.dark, 1.2,
                `opacity="0.7"`);
    emit(`attach/ac_${k}.svg`, svg(W, H, b));
    add(`ac_${k}`, `attach/ac_${k}.svg`, W, H, "center", "L3", ["attach", "ac"]);
  });
}

/* ══════════════════════════════════════════════════════════════════════════
   三·八、存量刻度条 ★
   决定 ③：货的存量用【一条刻度】表示，不用数字。
   和"精度区间条 / 常客热度条"共用同一套视觉语言（轨道是资产，填充是代码）。
   ══════════════════════════════════════════════════════════════════════════ */
function bars() {
  [["lg", 46, 6, 4], ["sm", 28, 4, 3]].forEach(([k, W, H, r]) => {
    let b = rrect(0, 0, W, H, r, "#00000012");
    b += rrect(0, 0, W, H, r, "none", `stroke="#00000014" stroke-width="${u(1)}"`);
    emit(`fx/bar_track_${k}.svg`, svg(W, H, b));
    add(`bar_track_${k}`, `fx/bar_track_${k}.svg`, W, H, "topleft", "L6",
        ["bar", "track", k]);
  });
}

/* ══════════════════════════════════════════════════════════════════════════
   三·九、雨（时间色调是参数，不是贴图 —— 见 manifest.atmosphere）
   ══════════════════════════════════════════════════════════════════════════ */
function rain() {
  [["light", 5, 0.30], ["heavy", 9, 0.44]].forEach(([k, step, alpha]) => {
    let d = "";
    for (let x = -30; x < 64; x += step)
      d += line(x, 0, x + 22, 64, "#dfeaf5", 1, `opacity="${alpha}"`);
    let body = rect(0, 0, 64, 64, "#00000000");
    body += `<defs>${pat("r" + k, 64, 64, d)}</defs>` + rect(0, 0, 64, 64, "url(#r" + k + ")");
    emit(`atm/rain_${k}.svg`, svg(64, 64, body));
    add(`rain_${k}`, `atm/rain_${k}.svg`, 64, 64, "topleft", "L5",
        ["atmosphere", "weather", "rain"]);
  });
}

/* ══════════════════════════════════════════════════════════════════════════
   四、建筑（屋顶 + 立面揭示 + 门口 + 招牌位）
   规则②：底部留 facadeReveal 的立面 = 假厚度。这是"看着立体"的全部秘密。
   规则③：落影单独一层。
   ══════════════════════════════════════════════════════════════════════════ */
/* types[] = 这栋美术【覆盖 config 的哪种建筑类型】。
   ★ 名字不该指望能对上（美术叫 shop_a，config 叫 shop_small），
     所以由资产【自己声明】—— 清单里会汇成 buildingTypes 映射给前端和 wiki。 */
const BUILDINGS = [
  { id: "shop_a",  kind: "shop",    g: [8, 5],  v: 0, types: ["shop_small"] },
  { id: "shop_b",  kind: "shop",    g: [6, 4],  v: 1, types: ["shop_supermarket"] },
  { id: "home_a",  kind: "home",    g: [5, 4],  v: 0, types: ["home_small"] },
  { id: "home_b",  kind: "home",    g: [6, 4],  v: 1, types: ["home_standard"] },
  { id: "home_c",  kind: "home",    g: [4, 3],  v: 2, types: ["home_large"] },
  { id: "factory", kind: "factory", g: [10, 6], v: 0, types: ["factory_plant"] },
  { id: "market",  kind: "shop",    g: [9, 5],  v: 2, types: ["market_hall"] },
  // ↓ 这五种原来没有美术
  { id: "clinic",  kind: "clinic",  g: [6, 5],  v: 0, types: ["clinic_basic"],
    deco: "cross", _note: "屋顶画个十字 —— 不用看名字就知道是诊所" },
  { id: "school",  kind: "school",  g: [9, 6],  v: 0, types: ["school_basic"],
    deco: "flag",  _note: "屋顶一根旗杆" },
  { id: "office",  kind: "work",    g: [7, 5],  v: 0, types: ["work_office"] },
  { id: "site",    kind: "work",    g: [7, 5],  v: 1, types: ["work_site"],
    roof: "site",  _note: "同 kind，靠屋顶色和门位区分（工地土一点）" },
  { id: "plaza",   kind: "public",  g: [8, 6],  v: 0, types: ["public_plaza"],
    open: true,    _note: "广场不是房子：不画屋顶/立面/门，画成铺装 + 花坛" },
];
function building(b) {
  const W = b.g[0] * G, H = b.g[1] * G;
  const r = P.roof[b.roof || b.kind] || P.roof.home, wall = P.wall, B = S.building;
  const rev = B.facadeReveal;
  const doorW = b.kind === "factory" ? 20 : 13, doorH = 8;
  const doorX = W * (b.v === 1 ? 0.3 : 0.46);

  let body = "";
  // ★ 广场：不是房子。不画屋顶/立面/门口，画成铺装 + 花坛
  if (b.open) {
    body += rect(0, 0, W, H, P.plaza.base);
    body += rect(0, 0, W, H, "none", `stroke="${P.plaza.dark}" stroke-width="${u(1)}"`);
    const st = T.pavingStep;
    for (let x = st; x < W; x += st)
      body += line(x, 0, x, H, P.plaza.dark, 1, `opacity="0.4"`);
    for (let y = st; y < H; y += st)
      body += line(0, y, W, y, P.plaza.dark, 1, `opacity="0.4"`);
    [[0.16, 0.2], [0.84, 0.2], [0.16, 0.8], [0.84, 0.8], [0.5, 0.5]].forEach(([rx, ry]) => {
      const bx = W * rx, by = H * ry, br = Math.min(W, H) * 0.07;
      body += circ(bx, by, br, P.tree.dark);
      body += circ(bx - br * 0.2, by - br * 0.2, br * 0.72, P.tree.base);
      body += circ(bx - br * 0.35, by - br * 0.35, br * 0.3, P.tree.light, `opacity="0.85"`);
    });
    emit(`bld/${b.id}.svg`, svg(W, H, body));
    add(b.id, `bld/${b.id}.svg`, W, H, "topleft", "L3",
        ["building", b.kind, `variant${b.v}`, "open"]);
    const so2 = svg(W + 4, H + 5, rect(0, 0, W, H, "#000", `opacity="0"`));
    emit(`bld/${b.id}_shadow.svg`, so2);
    add(`${b.id}_shadow`, `bld/${b.id}_shadow.svg`, W + 4, H + 5, "topleft", "L3",
        ["building", "shadow", "oversize"]);
    emit(`bld/${b.id}_lit.svg`, svg(W, H, ""));
    add(`${b.id}_lit`, `bld/${b.id}_lit.svg`, W, H, "topleft", "L5",
        ["building", "night"]);
    return { id: b.id, doors: [], sign: { x: 0, y: 0, w: 0, h: 0 },
             types: b.types || [] };
  }
  // 屋顶主体
  body += rect(0, 0, W, H, r.base);
  // 屋顶纹理：1px 平行线 ≤22%（v 决定竖纹还是横纹）
  {
    const step = T.roofStripeStep;
    let d = "";
    if (b.v % 2 === 0) for (let x = step; x < W; x += step) d += line(x, 0, x, H, r.dark, 1);
    else               for (let y = step; y < H; y += step) d += line(0, y, W, y, r.dark, 1);
    body += `<defs>${pat("rf", W, H, d)}</defs>`
          + rect(0, 0, W, H, "url(#rf)", `opacity="${T.roofStripeAlpha}"`);
  }
  // 屋脊高光（上边缘 1px 亮）+ 描边
  body += line(0.5, 0.5, W - 0.5, 0.5, r.light, 1, `opacity="0.8"`);
  body += rect(0, 0, W, H, "none",
    `stroke="#00000044" stroke-width="${u(1)}"`);
  // 底部立面揭示（假厚度）
  body += rect(0, H - rev, W, rev, wall.base);
  body += line(0, H - rev, W, H - rev, wall.dark, 1, `opacity="0.9"`);
  body += rect(0, H - rev, W, rev, "none", `stroke="#00000033" stroke-width="${u(1)}"`);
  // 门口（贴在南墙的立面里）
  body += rrect(doorX, H - rev - 1, doorW, rev + 1, 1, P.door.base);
  body += rect(doorX, H - rev - 1, doorW, rev + 1, "none",
    `stroke="${P.door.dark}" stroke-width="${u(1)}"`);
  // ★ 屋顶记号：不用看名字就知道这是什么楼
  if (b.deco === "cross") {
    const cx2 = W * 0.72, cy2 = H * 0.34, L = Math.min(W, H) * 0.16, T = L * 0.38;
    body += rect(cx2 - L / 2, cy2 - T / 2, L, T, "#e8e2d4", `opacity="0.92"`);
    body += rect(cx2 - T / 2, cy2 - L / 2, T, L, "#e8e2d4", `opacity="0.92"`);
    body += rect(cx2 - L / 2, cy2 - T / 2, L, T, "none",
                 `stroke="#a85a3c" stroke-width="${u(0.8)}" opacity="0.7"`);
    body += rect(cx2 - T / 2, cy2 - L / 2, T, L, "none",
                 `stroke="#a85a3c" stroke-width="${u(0.8)}" opacity="0.7"`);
  }
  if (b.deco === "flag") {
    const fx = W * 0.16, fy = H * 0.16;
    body += rect(fx, fy, 1.6, Math.min(W, H) * 0.22, P.metal.dark);
    body += `<path d="M ${u(fx + 1.6)} ${u(fy)} L ${u(fx + 13)} ${u(fy + 4)} L `
          + `${u(fx + 1.6)} ${u(fy + 8)} Z" fill="${P.accent}"/>`;
  }
  // 招牌底（**留白** —— 字由代码画，因为编辑器能改名）
  const sg = B.signInset;
  body += rrect(sg.x, sg.y, W - sg.x * 2, sg.h, 1.5, wall.base, `opacity="0.92"`);
  body += rect(sg.x, sg.y, W - sg.x * 2, sg.h, "none",
    `stroke="${wall.dark}" stroke-width="${u(1)}"`);
  emit(`bld/${b.id}.svg`, svg(W, H, body));
  add(b.id, `bld/${b.id}.svg`, W, H, "topleft", "L3",
      ["building", b.kind, `variant${b.v}`]);

  // 落影（单独一层，方便夜/雨复用、也方便关掉）
  {
    const sh = S.building.shadow;
    // 落影画布【故意比建筑大】—— 多的那圈是偏移的余量。
    // 画的时候仍然是"画布左上角对齐建筑左上角"：影子的剪影在画布内偏移了 (dx,dy)。
    const sw = W + sh.dx + 2, shh = H + sh.dy + 2;
    const so = svg(sw, shh, rect(sh.dx, sh.dy, W, H, "#000", `opacity="${sh.alpha}"`));
    emit(`bld/${b.id}_shadow.svg`, so);
    add(`${b.id}_shadow`, `bld/${b.id}_shadow.svg`, sw, shh, "topleft", "L3",
        ["building", "shadow", "oversize"]);
  }
  // 夜里亮起的窗格（和屋顶同一套坐标，所以一定对得上）
  {
    let lit = "";
    const cols = Math.max(2, Math.floor((W - 20) / 16));
    const rows = Math.max(1, Math.floor((H - rev - 24) / 14));
    for (let i = 0; i < cols; i++)
      for (let j = 0; j < rows; j++) {
        if (rnd() < 0.35) continue;                    // 有的窗不亮
        lit += rect(12 + i * 16, 24 + j * 14, 7, 6, P.window.night, `opacity="0.9"`);
      }
    emit(`bld/${b.id}_lit.svg`, svg(W, H, lit));
    add(`${b.id}_lit`, `bld/${b.id}_lit.svg`, W, H, "topleft", "L5",
        ["building", "night"]);
  }
  return { id: b.id, doors: [{ side: "south", offset: +(doorX / W).toFixed(3) }],
           sign: { x: sg.x, y: sg.y, w: W - sg.x * 2, h: sg.h },
           types: b.types || [] };
}

/* ══════════════════════════════════════════════════════════════════════════
   五、人物（3 向 × 5 帧 × N 人；side 靠镜像出左右 → 省一半文件）
   锚点在【脚底中心】。腿摆幅 legSwing，身体浮动 bob。
   ══════════════════════════════════════════════════════════════════════════ */
const SKINS = P.skin;
function person(ch, dir, frame) {
  const Pc = S.person, B = Pc.bodies[ch.body];
  const W = Pc.canvas.w, H = Pc.canvas.h;
  const cx = W / 2, skin = SKINS[ch.skin] || SKINS[0];
  const hair = C.hairStyles[ch.hair] || C.hairStyles.short;
  const swing = frame < 0 ? 0 : [1, 0.15, -1, 0.15][frame] * Pc.legSwing;
  const bob = frame < 0 ? 0 : [0, 0.8, 0, 0.8][frame];
  const gy = H - 1;                                    // 脚底

  let b = "";
  const dirEyes = dir === "down" ? 1 : dir === "side" ? 1 : 0;
  // ★ 头只有【一个】中心。原来头用 cx+shift、发盖用 cx-headR*0.55、
  //   帽子和长发又用回 cx —— 三个中心，侧向时帽子/长发明显歪在头旁边。
  const headShift = dir === "side" ? 0.8 : 0;
  const headX = cx + headShift;

  // 腿（两条，前后错开 = 走路）
  const lw = B.legW, lh = 4.6;
  b += rrect(cx - B.shoulderRx * 0.5 - lw / 2 + swing * 0.6, gy - lh + bob, lw, lh, lw / 2, "#4a4038");
  b += rrect(cx + B.shoulderRx * 0.5 - lw / 2 - swing * 0.6, gy - lh + bob, lw, lh, lw / 2, "#4a4038");

  // 身体中心：从【脚底】往上量。★ 不能再减 shoulderRy —— 减两次头就顶出画布了。
  const by = gy - 7.8 + bob * 0.4;
  b += ell(cx, by, B.shoulderRx, B.shoulderRy, ch.top || "#7a8f6a");
  b += ell(cx, by, B.shoulderRx, B.shoulderRy, "none",
    `stroke="#00000030" stroke-width="${u(1)}"`);

  // 围裙 / 包（在躯干上）
  if (ch.acc === "apron") b += rrect(cx - 3, by - 1, 6, 7, 1.2, "#f0ece2", `opacity="0.9"`);
  if (ch.acc === "bag")   b += rrect(cx + B.shoulderRx - 1.5, by - 1, 4.5, 6, 1.2, "#6b5138");

  // 头
  // 头中心：压在肩膀上方一点点（用比例，别用绝对差 —— 三种体型都要放得下）
  const hy = by - B.shoulderRy * 0.55 - B.headR * 0.9;
  b += circ(headX, hy, B.headR, skin);
  // 头发：down = 帽子形；up = 整个后脑勺；side = 往后偏
  // 头发：shape 决定形状、color 决定颜色（"白发"是 shape=short + 白）
  const hs = hair.shape || "short";
  // 头发的锚点：侧向只往后偏 0.32（0.55 会让发盖整个滑到脑后、前面露光头）
  const hairX = dir === "side" ? headX - B.headR * 0.32 : headX;
  if (dir === "up") {
    b += circ(headX, hy, B.headR + 0.35, hair.color);
  } else {
    const hx = hairX;
    if (hs !== "bald")
      b += `<path d="M ${u(hx - B.headR - 0.35)} ${u(hy + 0.6)} `
         + `A ${u(B.headR + 0.35)} ${u(B.headR + 0.35)} 0 0 1 `
         + `${u(hx + B.headR + 0.35)} ${u(hy + 0.6)} Z" fill="${hair.color}"/>`;
    if (hs === "long")
      b += rrect(hx - B.headR - 1, hy - 0.5, (B.headR + 1) * 2, B.headR * 1.5, 1.4,
                 hair.color, `opacity="0.95"`);
    if (hs === "bun")
      b += circ(hx, hy - B.headR - 1.1, 1.9, hair.color);
    if (hs === "hat")
      b += rrect(hx - B.headR - 1.6, hy - B.headR - 0.6, (B.headR + 1.6) * 2, 2.2, 1,
                 hair.color);
    if (hs === "bald") {
      b += rrect(hx - B.headR - 0.4, hy + B.headR * 0.2, 1.6, B.headR * 0.7, 0.7,
                 hair.color, `opacity="0.85"`);
      b += rrect(hx + B.headR - 1.2, hy + B.headR * 0.2, 1.6, B.headR * 0.7, 0.7,
                 hair.color, `opacity="0.85"`);
    }
  }
  // 眼睛
  if (dirEyes) {
    if (dir === "down") {
      b += circ(cx - B.headR * 0.42, hy + 0.5, 0.5, "#2b2620");
      b += circ(cx + B.headR * 0.42, hy + 0.5, 0.5, "#2b2620");
    } else {
      // ★ 侧向：眼在【头中心往后偏一点】的位置。ex 是相对偏移量，别再自己加 cx。
      b += circ(headX + B.headR * 0.45, hy + 0.5, 0.5, "#2b2620");
    }
  }
  // 眼镜 / 拐杖
  if (ch.acc === "glasses" && dirEyes) {
    const gw = dir === "side" ? B.headR * 0.8 : B.headR * 1.7;
    const gx = dir === "side" ? headX + B.headR * 0.2 : headX;
    b += line(gx - gw / 2, hy + 0.5, gx + gw / 2, hy + 0.5,
              "#2b2620", 0.7, `opacity="0.85"`);
  }
  if (ch.acc === "cane")
    b += line(cx + B.shoulderRx + 1, by + 1, cx + B.shoulderRx + 1, gy, "#6b5138", 1.1);
  return svg(W, H, b);
}
function people() {
  const out = [];
  for (const ch of C.characters) {
    for (const dir of S.person.directions) {
      for (let f = 0; f < S.person.walkFrames; f++) {
        const rel = `people/${ch.id}_${dir}_walk${f}.svg`;
        emit(rel, person(ch, dir, f));
        add(`${ch.id}_${dir}_walk${f}`, rel, S.person.canvas.w, S.person.canvas.h,
            "bottomcenter", "L4", ["person", ch.id, dir, "walk", `f${f}`]);
      }
      const rel = `people/${ch.id}_${dir}_idle.svg`;
      emit(rel, person(ch, dir, -1));
      add(`${ch.id}_${dir}_idle`, rel, S.person.canvas.w, S.person.canvas.h,
          "bottomcenter", "L4", ["person", ch.id, dir, "idle"]);
    }
    out.push(ch.id);
  }
  return out;
}

/* ══════════════════════════════════════════════════════════════════════════
   六、特效与标记（阴影 / 选中环 / 需求徽章 / 队列编号）
   ══════════════════════════════════════════════════════════════════════════ */
function fx() {
  // 落影
  for (const [k, r] of [["s", 5], ["m", 7], ["l", 9]]) {
    const s = r * 2 + 4;
    emit(`fx/shadow_${k}.svg`, svg(s, r + 3,
      ell(s / 2, r / 2 + 1, r, r * 0.52, "#000", `opacity="0.16"`)));
    add(`shadow_${k}`, `fx/shadow_${k}.svg`, s, r + 3, "bottomcenter", "L4");
  }
  // 选中环
  emit("fx/ring.svg",
    svg(22, 22, circ(11, 11, 9.5, "none", `stroke="${P.accent}" stroke-width="${u(2)}"`)));
  add("ring", "fx/ring.svg", 22, 22, "center", "L6");
  // 需求徽章（碗 / 闪电 / 水滴 / 犹豫）
  const badge = (id, inner) => {
    let b = circ(8, 8, 7.4, "#ffffff") + circ(8, 8, 7.4, "none",
      `stroke="#00000014" stroke-width="${u(1)}"`);
    emit(`fx/badge_${id}.svg`, svg(16, 16, b + inner));
    add(`badge_${id}`, `fx/badge_${id}.svg`, 16, 16, "center", "L6", ["badge"]);
  };
  badge("hunger", dp("M3.6 7.4h8.8a4.4 4.4 0 0 1-8.8 0z", `fill="${P.accent}"`)
                + rect(3.6, 6.4, 8.8, 1.1, "#7a7264"));
  badge("energy", dp("M8.6 2.4 4.8 8.2h2.7L6.6 13l4.8-6.2H8.5z", `fill="#6b7f9a"`));
  badge("bladder", dp("M8 2.2c2.5 3.4 3.5 5 3.5 6.3a3.5 3.5 0 0 1-7 0c0-1.3 1-2.9 3.5-6.3z",
    `fill="#5a7f96"`));
  badge("hesit", `<text x="8" y="11.4" text-anchor="middle" font-size="10" `
               + `font-family="system-ui,sans-serif" font-weight="700" fill="#a8761c">?</text>`);
  badge("sleep", `<text x="8" y="11" text-anchor="middle" font-size="9" `
               + `font-family="system-ui,sans-serif" font-weight="700" fill="#6b7f9a">z</text>`);
  // 队列编号点
  const qm = (id, fill, stroke) => {
    let b = circ(9, 9, 8, fill) + circ(9, 9, 8, "none",
      `stroke="${stroke}" stroke-width="${u(1.4)}"`);
    emit(`fx/qmark_${id}.svg`, svg(18, 18, b));
    add(`qmark_${id}`, `fx/qmark_${id}.svg`, 18, 18, "center", "L6", ["qmark"]);
  };
  qm("next", "#f7f4ee", P.ok);
  qm("now", "#f7f4ee", P.accent);
}

/* ══════════════════════════════════════════════════════════════════════════
   七、角色可辨识性自检（契约要求：任意两人至少 3 维不同）
   ══════════════════════════════════════════════════════════════════════════ */
function checkCharacters() {
  const cs = C.characters, bad = [];
  const dims = c => ({ body: c.body, hair: c.hair, top: c.top, acc: c.acc, skin: c.skin });
  for (let i = 0; i < cs.length; i++)
    for (let j = i + 1; j < cs.length; j++) {
      const a = dims(cs[i]), b = dims(cs[j]);
      const diff = Object.keys(a).filter(k => a[k] !== b[k]);
      if (diff.length < 3)
        bad.push(`${cs[i].id}(${cs[i].name}) vs ${cs[j].id}(${cs[j].name})：只差 ${diff.length} 维 [${diff}]`);
    }
  console.log(`\n角色可辨识性：${cs.length} 人，两两 ${cs.length * (cs.length - 1) / 2} 对`);
  if (bad.length) { console.log(bad.map(s => "  ✗ " + s).join("\n")); return false; }
  console.log("  ✓ 任意两人至少 3 维不同（身体/头发/上衣/配饰/肤色）");
  return true;
}

/* ══════════════════════════════════════════════════════════════════════════
   主流程
   ══════════════════════════════════════════════════════════════════════════ */
if (process.argv.includes("--check")) {
  process.exit(checkCharacters() ? 0 : 1);
}

fs.rmSync(OUT, { recursive: true, force: true });
reset();
groundTiles();
roadBits();
props();
items();
attachments();
bars();
rain();
const bldJson = BUILDINGS.map(building);
const who = people();
portraits();
fx();
checkCharacters();

/* ══════════════════════════════════════════════════════════════════════════
   九、归到资产的【标准类别】（docs/asset-list.md 的九大类）
   ----------------------------------------------------------------------------
   判据是玩法属性，不是文件放哪儿：
     A 环境  铺在地上、不交互        B 建筑  有门口、能走进去
     C 角色  会走动、有需求          D 物件  玩家能点 / 能买卖 / 能用
     E 界面  屏幕空间                F 特效  一次性、短命
     G 氛围  覆盖全屏                H 认知  表达"我记的多旧 / 多准 / 从哪来"
   ══════════════════════════════════════════════════════════════════════════ */
function categorize(a) {
  const T = a.tags;
  const has = (...x) => x.some(k => T.indexOf(k) >= 0);
  if (has("person")) return ["C", "world"];
  if (has("portrait")) return ["C", "portrait"];
  if (has("icon")) return ["D", "iicon"];            // 物品图标 = 物品的第二套语言
  if (has("empty")) return ["D", "iempty"];
  if (has("item")) return ["D", "iworld"];
  if (has("attach")) return ["B", "attach"];
  if (has("building")) return has("shadow") ? ["B", "shadow"]
                       : has("night") ? ["B", "lit"] : ["B", "body"];
  if (has("atmosphere")) return ["G", "rain"];
  if (a.layer === "L0") return ["A", "ground"];
  if (a.layer === "L1") return ["A", "road"];
  if (a.layer === "L2") return ["A", "props"];
  if (has("bar")) return ["E", "bar"];
  if (has("badge")) return ["E", "badge"];
  if (has("qmark")) return ["E", "marker"];
  if (a.layer === "UI") return ["E", "ui"];
  return ["F", "fx"];
}
for (const a of manifest) { const cs = categorize(a); a.cat = cs[0]; a.sub = cs[1]; }
const byCat = {};
for (const a of manifest) byCat[a.cat] = (byCat[a.cat] || 0) + 1;

fs.writeFileSync(path.join(OUT, "manifest.json"),
  JSON.stringify({ style: "art/style.json", grid: G, authorScale: PX,
                   logicalSize: true, buildings: bldJson,
                   atmosphere: S.atmosphere,
                   buildingTypes: bldJson.reduce((o, b) => {
                     for (const t2 of (b.types || [])) o[t2] = b.id;
                     return o; }, {}),
                   assets: manifest }, null, 1));

console.log(`\n生成 ${manifest.length} 个资产 → art/out/`);
console.log("  按类别:", ["A", "B", "C", "D", "E", "F", "G", "H"]
  .map(c => `${c}:${byCat[c] || 0}`).join("  ") + "   ← H 认知是最缺的");
console.log(`  人物 ${who.length} 人 × ${S.person.directions.length} 向 × ${S.person.walkFrames + 1} 帧`);
console.log(`  manifest.json 给了每个资产的 name / file / 逻辑尺寸 / 锚点 / 图层`);
