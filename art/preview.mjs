#!/usr/bin/env node
/* ============================================================================
   art/preview.mjs —— 生成联络表 out/preview.html
   ----------------------------------------------------------------------------
   清单内联进 HTML，所以【双击就能开】，不需要起服务器。
   联络表能把资产放在一起看（有一块组合场景），也能单看每个资产。

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
const charIds = C.characters.map(c => c.id);
const charName = Object.fromEntries(C.characters.map(c => [c.id, c.name]));
const area = Math.round(M.assets.reduce((n, a) => n + a.w * a.h, 0) / 1000);

const CSS = `
body{margin:0;background:#efece4;color:#26221c;
  font:13px/1.5 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:9;background:#f7f4ee;border-bottom:1px solid #ded7c8;
  padding:9px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
h2{margin:26px 0 4px;font-size:14px;padding:0 16px}
h2 span{color:#7a7264;font-weight:400;font-size:12px}
.hint{padding:2px 16px 8px;color:#7a7264;font-size:12px}
button{font:inherit;padding:3px 10px;border:1px solid #ded7c8;border-radius:999px;
  background:#fff;cursor:pointer}
button.on{background:#26221c;color:#f7f4ee;border-color:#26221c}
.row{display:flex;flex-wrap:wrap;gap:10px;padding:0 16px}
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
.scene{position:relative;width:640px;height:352px;margin:0 16px;border:1px solid #ded7c8;
  border-radius:8px;overflow:hidden;background-color:#6d8a52;
  background-image:url(ground/grass.svg);background-size:${G}px ${G}px}
.scene .g{position:absolute;background-image:url(ground/asphalt.svg);
  background-size:${G}px ${G}px}
.scene .sw{position:absolute;background-image:url(ground/sidewalk.svg);
  background-size:${G}px 6px}
.scene img{position:absolute}
.scene .lit{visibility:hidden}
body.night .scene .lit{visibility:visible}
body.grid .box,body.grid .scene{background-image:
  linear-gradient(#00000012 1px,transparent 1px),
  linear-gradient(90deg,#00000012 1px,transparent 1px);background-size:${G}px ${G}px}
body.grid .scene{background-image:
  linear-gradient(#00000026 1px,transparent 1px),
  linear-gradient(90deg,#00000026 1px,transparent 1px),url(ground/grass.svg);
  background-size:${G}px ${G}px,${G}px ${G}px,${G}px ${G}px}
`;

const SCRIPT = `
var M = ${JSON.stringify({ assets: M.assets, grid: G })};
var Z = 1, SHOW_LB = true;
function el(t,c,h){ var e=document.createElement(t); if(c)e.className=c; if(h)e.innerHTML=h; return e; }
function cell(a){
  var c = el("div","cell");
  var b = el("div","box");
  b.style.width = Math.round(a.w*Z*1.6)+"px"; b.style.height = Math.round(a.h*Z*1.6)+"px";
  var img = el("img"); img.src = a.file;
  img.style.width = (a.w*Z*1.6)+"px"; img.style.height = (a.h*Z*1.6)+"px";
  b.appendChild(img); c.appendChild(b);
  c.appendChild(el("div","lb", a.name));
  var extra = a.tags.indexOf("oversize")>=0 ? " ⚠画布比建筑大" : "";
  c.appendChild(el("div","dim", a.w+"×"+a.h+" "+a.anchor+extra));
  return c;
}
function section(id, pred){
  var host = document.getElementById(id); if(!host) return;
  M.assets.filter(pred).forEach(function(a){ host.appendChild(cell(a)); });
}
section("s_ground", function(a){ return a.layer==="L0"; });
section("s_road",   function(a){ return a.layer==="L1"; });
section("s_props",  function(a){ return a.layer==="L2"; });
section("s_fx",     function(a){ return a.layer==="L6"; });
section("s_bld",    function(a){ return a.layer==="L3" && a.tags.indexOf("shadow")<0; });

(function(){
  var host = document.getElementById("s_ppl");
  ${JSON.stringify(charIds)}.forEach(function(cid){
    var wrap = el("div","ch");
    wrap.appendChild(el("div","", "<b>"+${JSON.stringify(charName)}[cid]+"</b>"));
    wrap.appendChild(el("div","meta", cid));
    var cells = el("div","cells");
    ${JSON.stringify(S.person.directions)}.forEach(function(dir){
      var b = el("div","box");
      b.style.cssText = "display:flex;align-items:center;justify-content:center;"
        +"background:#e9e6da;border-radius:5px;width:"+(18*Z*1.6)+"px;height:"+(24*Z*1.6)+"px";
      var img = el("img"); img.style.width=(18*Z*1.6)+"px"; img.style.height=(24*Z*1.6)+"px";
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
})();

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
  }
  bld("shop_a", 40, 30, 256, 160);
  bld("home_b", 330, 40, 192, 128);
  [[150,118,27],[470,108,20],[556,238,34],[92,248,20],[300,258,27]].forEach(function(t){
    im("props/tree_"+(t[2]>=30?"l":t[2]>=24?"m":"s")+".svg", t[0], t[1], t[2], t[2]+2);
  });
  im("props/car_1.svg", 250, 152, 18, 32);
  im("props/car_3.svg", 420, 168, 18, 32);
  im("props/lamp.svg", 500, 118, 10, 30);
  im("props/bench.svg", 200, 226, 26, 12);
  im("people/n_wang_down_idle.svg", 140, 232, 18, 24);
  im("people/n_li_down_idle.svg",   228, 236, 18, 24);
  im("people/n_sun_side_idle.svg",  180, 228, 18, 24);
  im("people/me_down_idle.svg",     330, 258, 18, 24);
})();

document.getElementById("stat").textContent =
  M.assets.length+" 个资产 · 网格 "+M.grid+"px · 2× 绘制 · ${area}k px²";
document.querySelectorAll("[data-z]").forEach(function(b){
  b.onclick = function(){
    Z = parseFloat(b.dataset.z);
    document.querySelectorAll("[data-z]").forEach(function(x){ x.classList.remove("on"); });
    b.classList.add("on");
    var i = 0;
    M.assets.forEach(function(a){
      // 跳过人物块（它们用固定尺寸的动画格）
      if (a.layer==="L4") return;
      var c = document.querySelectorAll(".cell")[i++]; if(!c) return;
      var img=c.querySelector("img"), bx=c.querySelector(".box");
      img.style.width=(a.w*Z*1.6)+"px"; img.style.height=(a.h*Z*1.6)+"px";
      bx.style.width=(a.w*Z*1.6)+"px"; bx.style.height=(a.h*Z*1.6)+"px";
    });
  };
});
document.getElementById("bGrid").onclick = function(){
  this.classList.toggle("on"); document.body.classList.toggle("grid");
};
document.getElementById("bNight").onclick = function(){
  this.classList.toggle("on"); document.body.classList.toggle("night");
};
document.getElementById("bLb").onclick = function(){
  SHOW_LB=!SHOW_LB; this.classList.toggle("on");
  document.querySelectorAll(".cell .lb,.cell .dim").forEach(function(e){
    e.style.display = SHOW_LB?"":"none"; });
};
`;

const HTML = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>美术资产 · 联络表</title><style>${CSS}</style></head><body>
<header>
 <b>美术资产 · 联络表</b><span id="stat" style="color:#7a7264;font-size:12px"></span>
 <span style="flex:1"></span>
 缩放 <button data-z="0.5">0.5×</button><button data-z="1" class="on">1×</button>
      <button data-z="2">2×</button><button data-z="3">3×</button>
 <button id="bGrid">格子</button><button id="bNight">夜色</button>
 <button id="bLb" class="on">标签</button>
</header>

<h2>地图一角 <span>· 资产放在一起才知道搭不搭</span></h2>
<div class="scene" id="scene"></div>
<div class="hint">「格子」对照 32px 网格 · 「夜色」看窗光</div>

<h2>地面 <span>· 可平铺</span></h2><div class="row" id="s_ground"></div>
<h2>道路 <span>· 路面是平涂，这里给的是纹理味</span></h2><div class="row" id="s_road"></div>
<h2>地块装饰 <span>· 锚点在底部中心，所以“立”在地上</span></h2><div class="row" id="s_props"></div>
<h2>建筑 <span>· 屋顶 + 立面揭示 + 门口 + 招牌位（留白，字由代码画）</span></h2>
<div class="hint">每栋三张：本体 / 落影 / 夜间窗光 —— 落影画布比建筑大一圈，那圈是偏移余量</div>
<div class="row" id="s_bld"></div>
<h2>人物 <span>· 走 4 帧 + 站 1 帧，循环播放 · 锚点在脚底</span></h2>
<div class="row" id="s_ppl"></div>
<h2>特效与标记</h2><div class="row" id="s_fx"></div>
<script>${SCRIPT}</script></body></html>`;

fs.writeFileSync(path.join(ROOT, "out/preview.html"), HTML, "utf8");
console.log(`联络表 → art/out/preview.html （${(HTML.length / 1024).toFixed(0)} KB，双击就能开）`);
