#!/usr/bin/env node
/* ============================================================================
   art/preview.mjs —— 生成联络表 out/preview.html（按【资产类别】组织）
   ----------------------------------------------------------------------------
   组织方式跟 docs/asset-list.md 的九大类一致：
     A 环境 · B 建筑 · C 角色 · D 物件 · E 界面 · F 特效 · G 氛围 · H 认知
   每个子类下面标了【缺什么】—— 所以这张表同时是缺口报告。

   清单内联进 HTML，双击就能开，不需要起服务器。
   用法: node art/preview.mjs   （先跑 gen.mjs）
   ========================================================================== */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(fileURLToPath(new URL(".", import.meta.url)));
const S = JSON.parse(fs.readFileSync(path.join(ROOT, "style.json"), "utf8"));
const C = JSON.parse(fs.readFileSync(path.join(ROOT, "characters.json"), "utf8"));
const M = JSON.parse(fs.readFileSync(path.join(ROOT, "out/manifest.json"), "utf8"));
const G = S.grid, PX = S.authorScale, SH = S.building.shadow;
const AT = M.atmosphere || { time: [] };
const charIds = C.characters.map(c => c.id);
const charName = Object.fromEntries(C.characters.map(c => [c.id, c.name]));
/* 物品 id → 逻辑尺寸。★ 按 id 不按中文名 —— 中文名属于内核的 config/items，
   不在美术清单里（清单的 name 是资产 id） */
const ITEMS_BY_NAME = M.assets
  .filter(a => a.cat === "D" && a.sub === "iworld")
  .reduce((o, a) => { o[a.name] = [a.w, a.h]; return o; }, {});

/* 类别结构 = asset-list.md 的目录。gap = 该子类还没有资产（会显示成缺口）。 */
const CATS = [
  { k: "A", n: "环境", hint: "铺在地上 / 立在地上但不交互", subs: [
    { k: "A1", n: "地面",     s: "ground", hint: "可平铺 32px" },
    { k: "A2", n: "道路",     s: "road",   hint: "路面形状是平涂，这里给纹理味" },
    { k: "A3", n: "过渡与拼接", s: "autotile",
      gap: "autotile 集（草↔泥 / 草↔水 / 铺装↔草 / 路肩）。只有地面没有过渡 → 地图到处是硬边，这是「业余 vs 专业」最大的分水岭" },
    { k: "A4", n: "地块装饰", s: "props",  hint: "锚点在底部中心，所以「立」在地上" },
    { k: "A5", n: "围栏与院子", s: "fence", gap: "木栅栏 / 矮砖墙 / 树篱（各 4 段：直/角/端/门）" },
  ]},
  { k: "B", n: "建筑", hint: "有门口、能走进去、有名字", subs: [
    { k: "B1", n: "本体",     s: "body",   hint: "屋顶 + 立面揭示 + 门口" },
    { k: "B2", n: "落影",     s: "shadow", hint: "单独一层：夜 / 雨可复用，也能整个关掉" },
    { k: "B3", n: "夜间窗光", s: "lit",    hint: "和屋顶同一套坐标，所以一定对得上" },
    { k: "B4", n: "附件",     s: "attach", hint: "招牌底 6 种是【九宫格】，中段可拉伸；招牌留白，字由代码画" },
    { k: "B5", n: "状态",     s: "bstate", gap: "关门挂牌（休息中/打烊）· 装修中（脚手架/围挡）· 出售/出租牌" },
    { k: "B6", n: "室内结构", s: "binter", gap: "室内墙 / 室内门 / 室内窗 / 楼梯 / 地板贴图" },
  ]},
  { k: "C", n: "角色", hint: "会走动、有需求、有记忆", subs: [
    { k: "C1", n: "世界小人", s: "world",  anim: true,
      hint: "走 4 帧 + 站 1 帧，循环播放；锚点在脚底；左右靠水平镜像" },
    { k: "C2", n: "头像",     s: "portrait", hint: "32×32 正面胸像，给面板用；和世界小人同一份角色数据" },
    { k: "C3", n: "动作",     s: "cemote", gap: "待机小动作（换重心/看表）· 坐 2 帧 · 用东西 3 帧（吃/睡/如厕）" },
  ]},
  { k: "D", n: "物件", hint: "玩家能点 / 能买卖 / 能用 —— 判据是玩法属性，不是外观", subs: [
    { k: "D1", n: "世界形态", s: "iworld", hint: "俯视，摆在屋里要贴地" },
    { k: "D2", n: "空态",     s: "iempty", hint: "「卖光了」用形状说，不写字" },
    { k: "D3", n: "图标",     s: "iicon",  hint: "正视 16×16，给小图标用 —— 俯视的苹果就是个圆" },
    { k: "D4", n: "容器",     s: "icont",  gap: "★ 货架 / 冰柜 / 展示柜 —— 容器与内容必须是两个资产，「卖光了」= 容器还在、内容没了" },
  ]},
  { k: "E", n: "界面", hint: "屏幕空间，不随地图缩放", subs: [
    { k: "E1", n: "需求徽章", s: "badge",  hint: "饿 / 困 / 憋 / 犹豫 / 睡" },
    { k: "E2", n: "标记",     s: "marker", hint: "队列编号点" },
    { k: "E3", n: "刻度条",   s: "bar",    hint: "轨道是资产、填充是代码；和精度条 / 热度条共用一套语言" },
    { k: "E4", n: "图标系统", s: "uicon",  gap: "★ 一套统一线性图标（时间/经济/需求/社交/功能/地图）。现在混了 emoji + 手写 SVG + 纯字符" },
  ]},
  { k: "F", n: "特效", hint: "一次性、短命、不占位置", subs: [
    { k: "F1", n: "落影与环", s: "fx", hint: "人物落影小/中/大 + 选中环" },
    { k: "F2", n: "点击与反馈", s: "fback", gap: "点击涟漪 · 完成打勾 · 气泡底/尾 · 交易成功" },
  ]},
  { k: "G", n: "氛围", hint: "覆盖全屏、影响观感、不改任何逻辑", subs: [
    { k: "G1", n: "天气",     s: "rain", hint: "可平铺。时间色调是【参数】不是贴图，见顶栏「时间」" },
    { k: "G2", n: "光与色",   s: "glight", gap: "窗光遮罩 · 灯光光斑 · 雪/雾/落叶（留 T2）" },
  ]},
  { k: "H", n: "认知", hint: "表达「我记的多旧 / 多准 / 从哪来」—— 这个游戏特有，别的游戏不需要", subs: [
    { k: "H1", n: "来源记号", s: "csrc",  gap: "亲眼 / 打听 / 传闻 / 雇员 / 经手 —— 现在是字符 ●❞∿◐▮，要重做成一套" },
    { k: "H2", n: "精度档",   s: "cprec", gap: "5 档的区间条元件 —— 现在还是代码画的 div" },
    { k: "H3", n: "知识等级", s: "cknow", gap: "3 档（没进去过 / 旧了 / 新鲜）—— 现在是 filter: saturate()" },
    { k: "H4", n: "事件反馈", s: "cev",   gap: "惊讶 / 刚确认 / 已过时 / 待确认" },
  ]},
];

const CSS = `
body{margin:0;background:#efece4;color:#26221c;
  font:13px/1.5 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:9;background:#f7f4ee;border-bottom:1px solid #ded7c8;
  padding:9px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
h2{margin:30px 0 0;font-size:15px;padding:8px 16px;background:#e6e0d2;border-top:1px solid #ded7c8;
  display:flex;align-items:baseline;gap:10px}
h2 .hint{color:#7a7264;font-weight:400;font-size:12px}
h2 .cnt{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#7a7264;margin-left:auto}
h3{margin:16px 0 6px;font-size:12px;color:#7a7264;padding:0 16px;
  display:flex;align-items:baseline;gap:8px}
h3 .cnt{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#a49c8d}
.hint{padding:2px 16px 8px;color:#7a7264;font-size:12px}
.gap{margin:2px 16px 8px;padding:9px 12px;border:1px dashed #cfc7b6;border-radius:8px;
  color:#9a8f7c;font-size:12px;background:#00000004}
.gap b{color:#a8761c}
button{font:inherit;padding:3px 10px;border:1px solid #ded7c8;border-radius:999px;
  background:#fff;cursor:pointer}
button.on{background:#26221c;color:#f7f4ee;border-color:#26221c}
.row{display:flex;flex-wrap:wrap;gap:10px;padding:0 16px}
.scenes{display:flex;gap:16px;padding:0 16px;flex-wrap:wrap}
.cell{border:1px solid #ded7c8;border-radius:8px;background:#fff;padding:8px;
  display:flex;flex-direction:column;align-items:center;gap:5px}
.cell .box{display:flex;align-items:center;justify-content:center;
  background:#e9e6da;border-radius:5px;overflow:hidden}
.cell .lb{font-size:10px;color:#7a7264;font-family:ui-monospace,Consolas,monospace}
.cell .dim{font-size:9px;color:#a49c8d;font-family:ui-monospace,Consolas,monospace}
.cells{display:flex;gap:8px;margin-top:4px}
.ch{border:1px solid #ded7c8;border-radius:8px;background:#fff;padding:8px 10px}
.ch b{font-size:12px}
.ch .meta{font-size:10px;color:#7a7264;font-family:ui-monospace,Consolas,monospace}
.roomwrap{border:1px solid #ded7c8;border-radius:8px;background:#fff;padding:8px}
.roomwrap .cap{font-size:11px;color:#7a7264;padding-top:5px}
.room{position:relative;background:#e8dfc9;border-radius:5px;overflow:hidden;
  box-shadow:inset 0 0 0 1px #00000018}
.room img{position:absolute}
.scene{position:relative;width:640px;height:352px;border:1px solid #ded7c8;
  border-radius:8px;overflow:hidden;background-color:#6d8a52;
  background-image:url(ground/grass.svg);background-size:${G}px ${G}px}
.scene .g{position:absolute;background-image:url(ground/asphalt.svg);background-size:${G}px ${G}px}
.scene .sw{position:absolute;background-image:url(ground/sidewalk.svg);background-size:${G}px 6px}
.scene img{position:absolute}
.tone{position:absolute;inset:0;pointer-events:none}
body.grid .cell .box{background-image:
  linear-gradient(#00000012 1px,transparent 1px),
  linear-gradient(90deg,#00000012 1px,transparent 1px);background-size:${G}px ${G}px}
body.grid .scene{background-image:
  linear-gradient(#00000026 1px,transparent 1px),
  linear-gradient(90deg,#00000026 1px,transparent 1px),url(ground/grass.svg);
  background-size:${G}px ${G}px,${G}px ${G}px,${G}px ${G}px}
body.grid .room{background-image:
  linear-gradient(#00000018 1px,transparent 1px),
  linear-gradient(90deg,#00000018 1px,transparent 1px);background-size:${G}px ${G}px}
`;

const SCRIPT = `
var M = ${JSON.stringify({ assets: M.assets, grid: G })};
var CATS = ${JSON.stringify(CATS)};
var Z = 1;
function el(t,c,h){ var e=document.createElement(t); if(c)e.className=c; if(h)e.innerHTML=h; return e; }
function cell(a, k){
  k = (k||1) * 1.6;
  var c = el("div","cell");
  var b = el("div","box");
  b.style.width = Math.round(a.w*Z*k)+"px"; b.style.height = Math.round(a.h*Z*k)+"px";
  var img = el("img"); img.src = a.file;
  img.style.width = (a.w*Z*k)+"px"; img.style.height = (a.h*Z*k)+"px";
  img.dataset.w = a.w; img.dataset.h = a.h; img.dataset.k = k;
  b.appendChild(img); c.appendChild(b);
  c.appendChild(el("div","lb", a.name));
  var extra = a.tags.indexOf("oversize")>=0 ? " ⚠画布比建筑大" : "";
  var slice = a.slice ? " ▣九宫格" : "";
  c.appendChild(el("div","dim", a.w+"×"+a.h+" "+a.anchor+extra+slice));
  return c;
}
function byCatSub(cat, sub){ return M.assets.filter(function(a){
  return a.cat===cat && a.sub===sub; }); }
function place(host, a, k){ host.appendChild(cell(a, k)); }
function renderAll(){
  var root = document.getElementById("cats");
  CATS.forEach(function(C){
    var list = M.assets.filter(function(a){ return a.cat===C.k; });
    var h2 = el("h2","", C.k+" "+C.n+" <span class='hint'>"+C.hint+"</span>");
    h2.appendChild(el("span","cnt", list.length+" 个"));
    root.appendChild(h2);
    C.subs.forEach(function(SB){
      var items = byCatSub(C.k, SB.s);
      var h3 = el("h3","", SB.k+" "+SB.n);
      h3.appendChild(el("span","cnt", items.length+" 个"));
      root.appendChild(h3);
      if (!items.length){
        if (SB.gap) root.appendChild(el("div","gap","<b>缺</b> — "+SB.gap));
        return;
      }
      if (SB.anim){ renderPeople(root); return; }
      if (SB.hint) root.appendChild(el("div","hint", SB.hint));
      var row = el("div","row");
      var k = (SB.s==="iicon"||SB.s==="badge"||SB.s==="marker") ? 2.2 : 1.4;
      items.forEach(function(a){ place(row, a, k); });
      root.appendChild(row);
      if (SB.gap) root.appendChild(el("div","gap","<b>还缺</b> — "+SB.gap));
    });
  });
}
function renderPeople(root){
  var host = el("div","row");
  ${JSON.stringify(charIds)}.forEach(function(cid){
    var wrap = el("div","ch");
    wrap.appendChild(el("div","", "<b>"+${JSON.stringify(charName)}[cid]+"</b>"));
    wrap.appendChild(el("div","meta", cid));
    var cells = el("div","cells");
    ${JSON.stringify(S.person.directions)}.forEach(function(dir){
      var w = 18*Z*1.6, h = 24*Z*1.6;
      var b = el("div","box");
      b.style.cssText = "display:flex;align-items:center;justify-content:center;"
        +"background:#e9e6da;border-radius:5px;width:"+w+"px;height:"+h+"px";
      var img = el("img"); img.style.width=w+"px"; img.style.height=h+"px";
      b.appendChild(img); cells.appendChild(b);
      var f = 0;
      setInterval(function(){
        img.src = (f%7===6) ? "people/"+cid+"_"+dir+"_idle.svg"
                            : "people/"+cid+"_"+dir+"_walk"+(f%4)+".svg";
        f++;
      }, 140);
    });
    wrap.appendChild(cells); host.appendChild(wrap);
  });
  root.appendChild(host);
}

/* 组合场景 */
function scenes(){
  (function(){
    var s = document.getElementById("scene");
    function box(cls,x,y,w,h){ var d=el("div",cls);
      d.style.cssText="left:"+x+"px;top:"+y+"px;width:"+w+"px;height:"+h+"px"; s.appendChild(d); return d; }
    function im(src,x,y,w,h,cls){ var m=el("img"); m.src=src;
      m.style.cssText="left:"+x+"px;top:"+y+"px;width:"+w+"px;height:"+h+"px";
      if(cls)m.className=cls; s.appendChild(m); return m; }
    box("g",0,150,640,64); box("sw",0,144,640,6); box("sw",0,214,640,6);
    function bld(name,x,y,w,h){
      im("bld/"+name+"_shadow.svg", x, y, w+${SH.dx + 2}, h+${SH.dy + 2});
      im("bld/"+name+".svg", x, y, w, h);
      im("bld/"+name+"_lit.svg", x, y, w, h, "lit");
      im("attach/awning_1.svg", x+96, y+134, 46, 16);
      im("attach/sign_wood.svg", x+72, y+18, 112, 16);
    }
    bld("shop_a", 40, 30, 256, 160);
    bld("home_b", 330, 40, 192, 128);
    [[150,118,27],[470,108,20],[556,238,34],[92,248,20],[300,258,27]].forEach(function(t){
      im("props/tree_"+(t[2]>=30?"l":t[2]>=24?"m":"s")+".svg", t[0], t[1], t[2], t[2]+4);
    });
    im("props/car_1.svg", 250, 152, 18, 32);
    im("props/car_3.svg", 420, 168, 18, 32);
    im("props/lamp.svg", 500, 118, 10, 30);
    im("props/bench.svg", 200, 226, 26, 12);
    im("people/n_wang_down_idle.svg", 140, 232, 18, 24);
    im("people/n_li_down_idle.svg",   228, 236, 18, 24);
    im("people/n_sun_side_idle.svg",  180, 228, 18, 24);
    im("people/me_down_idle.svg",     330, 258, 18, 24);
    s.appendChild(el("div","tone"));
  })();
  var host = document.getElementById("scenes2");
  function room(title, W, H, place2){
    var wrap = el("div","roomwrap");
    var r = el("div","room");
    r.style.cssText += "width:"+W+"px;height:"+H+"px";
    function im(src,x,y,w,h){ var m=el("img"); m.src=src;
      m.style.cssText="left:"+x+"px;top:"+y+"px;width:"+w+"px;height:"+h+"px"; r.appendChild(m); return m; }
    function person(cid,dir,x,y){ return im("people/"+cid+"_"+dir+"_idle.svg", x, y, 18, 24); }
    place2(im, person); r.appendChild(el("div","tone"));
    wrap.appendChild(r); wrap.appendChild(el("div","cap", title)); host.appendChild(wrap);
  }
  var IT = ${JSON.stringify(ITEMS_BY_NAME)};
  room("店里（前台 + 货 + 店员）", 340, 190, function(im, person){
    im("items/station_counter.svg", 244, 40, IT["station_counter"][0], IT["station_counter"][1]);
    im("items/food_apple.svg", 30, 34, IT["food_apple"][0], IT["food_apple"][1]);
    im("items/food_pear.svg",  30, 68, IT["food_pear"][0], IT["food_pear"][1]);
    im("items/meal_simple.svg", 30, 102, IT["meal_simple"][0], IT["meal_simple"][1]);
    im("items/food_apple_empty.svg", 96, 34, IT["food_apple"][0], IT["food_apple"][1]);
    person("n_sun","down",226,118); person("n_wang","down",150,122);
  });
  room("加工厂（工位 + 机器 + 工人）", 340, 190, function(im, person){
    im("items/station_workbench.svg", 30, 40, IT["station_workbench"][0], IT["station_workbench"][1]);
    im("items/industry_machine.svg", 26, 90, IT["industry_machine"][0], IT["industry_machine"][1]);
    im("items/meal_simple_raw.svg", 110, 96, IT["meal_simple_raw"][0], IT["meal_simple_raw"][1]);
    person("n_zhou","down",130,130); person("n_li","side",200,134);
  });
  room("家里（床 + 马桶）", 340, 190, function(im, person){
    im("items/bed_basic.svg", 40, 34, IT["bed_basic"][0], IT["bed_basic"][1]);
    im("items/toilet_basic.svg", 250, 30, IT["toilet_basic"][0], IT["toilet_basic"][1]);
    person("me","up",160,100); person("n_zhang","side",190,104);
  });
}

/* 时间色调（参数，不是贴图 —— 见 manifest.atmosphere） */
function tones(){
  var list = ${JSON.stringify(AT.time || [])};
  var host = document.getElementById("tones");
  function apply(i){
    var tn = list[i];
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
  list.forEach(function(tn, i){
    var b = el("button","", tn.label);
    b.onclick = function(){
      host.querySelectorAll("button").forEach(function(x){ x.classList.remove("on"); });
      b.classList.add("on"); apply(i);
    };
    host.appendChild(b);
    if (tn.name === "day"){ b.classList.add("on"); apply(i); }
  });
}

scenes(); tones(); renderAll();
document.getElementById("stat").textContent =
  M.assets.length + " 个资产 · 网格 " + M.grid + "px · 2× 绘制";
document.querySelectorAll("[data-z]").forEach(function(b){
  b.onclick = function(){
    Z = parseFloat(b.dataset.z);
    document.querySelectorAll("[data-z]").forEach(function(x){ x.classList.remove("on"); });
    b.classList.add("on");
    document.querySelectorAll(".cell img").forEach(function(img){
      var W=parseFloat(img.dataset.w), H=parseFloat(img.dataset.h), k=parseFloat(img.dataset.k);
      if(!W) return;
      img.style.width=(W*Z*k)+"px"; img.style.height=(H*Z*k)+"px";
      var bx=img.parentNode;
      bx.style.width=(W*Z*k)+"px"; bx.style.height=(H*Z*k)+"px";
    });
  };
});
document.getElementById("bGrid").onclick = function(){
  this.classList.toggle("on"); document.body.classList.toggle("grid"); };
document.getElementById("bLb").onclick = function(){
  var on = this.classList.toggle("on");
  document.querySelectorAll(".cell .lb,.cell .dim").forEach(function(e){
    e.style.display = on?"":"none"; });
};
`;

const HTML = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>美术资产 · 分类预览</title><style>${CSS}</style></head><body>
<header>
 <b>美术资产 · 分类预览</b><span id="stat" style="color:#7a7264;font-size:12px"></span>
 <span style="flex:1"></span>
 缩放 <button data-z="0.5">0.5×</button><button data-z="1" class="on">1×</button>
      <button data-z="2">2×</button><button data-z="3">3×</button>
 <button id="bGrid">格子</button><button id="bLb" class="on">标签</button>
 <span style="width:1px;height:16px;background:#ded7c8"></span>
 <span style="color:#7a7264;font-size:12px">时间</span><span id="tones" style="display:flex;gap:4px"></span>
</header>

<div class="hint" style="padding-top:10px">
 按 <b>docs/asset-list.md</b> 的九大类组织。每节右上角是数量，<b>虚线框是「还缺什么」</b> ——
 所以这张表同时是缺口报告。</div>

<h2>A 组合场景 <span class="hint">· 资产放在一起才知道搭不搭（不算资产类别，只是验收用）</span></h2>
<div class="scenes">
  <div><div class="scene" id="scene"></div><div class="hint">地图一角（含招牌与雨棚）</div></div>
</div>
<div class="scenes" id="scenes2"></div>
<div class="hint">★ 物品必须和人摆在一起才看得出大小 —— 床边那个人是 18×24</div>

<div id="cats"></div>
<script>${SCRIPT}</script></body></html>`;

fs.writeFileSync(path.join(ROOT, "out/preview.html"), HTML, "utf8");
console.log(`分类预览 → art/out/preview.html （${(HTML.length / 1024).toFixed(0)} KB，双击就能开）`);
