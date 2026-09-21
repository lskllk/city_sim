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
   四、建筑（屋顶 + 立面揭示 + 门口 + 招牌位）
   规则②：底部留 facadeReveal 的立面 = 假厚度。这是"看着立体"的全部秘密。
   规则③：落影单独一层。
   ══════════════════════════════════════════════════════════════════════════ */
const BUILDINGS = [
  { id: "shop_a",  kind: "shop",    g: [8, 5], v: 0 },
  { id: "shop_b",  kind: "shop",    g: [6, 4], v: 1 },
  { id: "home_a",  kind: "home",    g: [5, 4], v: 0 },
  { id: "home_b",  kind: "home",    g: [6, 4], v: 1 },
  { id: "home_c",  kind: "home",    g: [4, 3], v: 2 },
  { id: "factory", kind: "factory", g: [10, 6], v: 0 },
  { id: "market",  kind: "shop",    g: [9, 5], v: 2 },
];
function building(b) {
  const W = b.g[0] * G, H = b.g[1] * G;
  const r = P.roof[b.kind], wall = P.wall, B = S.building;
  const rev = B.facadeReveal;
  const doorW = b.kind === "factory" ? 20 : 13, doorH = 8;
  const doorX = W * (b.v === 1 ? 0.3 : 0.46);

  let body = "";
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
           sign: { x: sg.x, y: sg.y, w: W - sg.x * 2, h: sg.h } };
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
  const headShift = dir === "side" ? 0.8 : 0;

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
  b += circ(cx + headShift, hy, B.headR, skin);
  // 头发：down = 帽子形；up = 整个后脑勺；side = 往后偏
  if (dir === "up") {
    b += circ(cx, hy, B.headR + 0.35, hair.color);
  } else {
    const hx = dir === "side" ? cx - B.headR * 0.55 : cx;
    b += `<path d="M ${u(hx - B.headR - 0.35)} ${u(hy + 0.6)} `
       + `A ${u(B.headR + 0.35)} ${u(B.headR + 0.35)} 0 0 1 `
       + `${u(hx + B.headR + 0.35)} ${u(hy + 0.6)} Z" fill="${hair.color}"/>`;
    if (ch.hair === "long")
      b += rrect(cx - B.headR - 1, hy - 0.5, (B.headR + 1) * 2, B.headR * 1.5, 1.4,
                 hair.color, `opacity="0.95"`);
    if (ch.hair === "hat")
      b += rrect(cx - B.headR - 1.6, hy - B.headR - 0.6, (B.headR + 1.6) * 2, 2.2, 1,
                 hair.color);
  }
  // 眼睛
  if (dirEyes) {
    if (dir === "down") {
      b += circ(cx - B.headR * 0.42, hy + 0.5, 0.5, "#2b2620");
      b += circ(cx + B.headR * 0.42, hy + 0.5, 0.5, "#2b2620");
    } else {
      // ★ 侧向：眼在【头中心往后偏一点】的位置。ex 是相对偏移量，别再自己加 cx。
      b += circ(cx + headShift + B.headR * 0.45, hy + 0.5, 0.5, "#2b2620");
    }
  }
  // 眼镜 / 拐杖
  if (ch.acc === "glasses" && dirEyes) {
    const gw = dir === "side" ? B.headR * 0.8 : B.headR * 1.7;
    b += line(cx - gw / 2 + (dir === "side" ? B.headR * 0.2 : 0), hy + 0.5,
              cx + gw / 2 + (dir === "side" ? B.headR * 0.2 : 0), hy + 0.5,
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
  badge("hunger", `<path d="M3.6 7.4h8.8a4.4 4.4 0 0 1-8.8 0z" fill="${P.accent}"/>`
                + `<rect x="3.6" y="6.4" width="8.8" height="1.1" fill="#7a7264"/>`);
  badge("energy", `<path d="M8.6 2.4 4.8 8.2h2.7L6.6 13l4.8-6.2H8.5z" fill="#6b7f9a"/>`);
  badge("bladder", `<path d="M8 2.2c2.5 3.4 3.5 5 3.5 6.3a3.5 3.5 0 0 1-7 0c0-1.3 1-2.9 3.5-6.3z" fill="#5a7f96"/>`);
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
const bldJson = BUILDINGS.map(building);
const who = people();
fx();
checkCharacters();

fs.writeFileSync(path.join(OUT, "manifest.json"),
  JSON.stringify({ style: "art/style.json", grid: G, authorScale: PX,
                   logicalSize: true, buildings: bldJson, assets: manifest }, null, 1));

const byLayer = {};
for (const a of manifest) byLayer[a.layer] = (byLayer[a.layer] || 0) + 1;
console.log(`\n生成 ${manifest.length} 个资产 → art/out/`);
console.log("  按图层:", Object.entries(byLayer).sort().map(([k, v]) => `${k}:${v}`).join("  "));
console.log(`  人物 ${who.length} 人 × ${S.person.directions.length} 向 × ${S.person.walkFrames + 1} 帧`);
console.log(`  manifest.json 给了每个资产的 name / file / 逻辑尺寸 / 锚点 / 图层`);
