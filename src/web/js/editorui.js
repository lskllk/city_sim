/** editorui.js —— 编辑器的外壳：打开、顶栏、四个模式。 */
import { $, esc, app, store, toast, show, ensureAssets, BUILD } from "./core.js";
import { fetchManifest } from "./assets.js";
import { Editor } from "./editor.js";
import { openPeople, newNpc, closePeople, showPanel } from "./editornpc.js";
import { openBuilding, openCompany, closeBuilding, closeCompany } from "./editorbld.js";

export async function openEditor() {
  if (!app.editor) {
    const a = await ensureAssets();
    await a.preloadMap();
    const ui = {
      toast,
      setScene: (name, stats, saved) => {
        // 场景名不带 .json —— 尾缀不是给人看的
        $("eName").textContent = String(name || "").replace(/\.json$/i, "") || "—";
        $("eDirty").textContent = saved ? "" : " •";
      },
      // ★ 顶栏不塞统计（节点/路/房）也不塞撤销计数 —— 太多废话。
      //   保留成空函数，编辑器里那几处调用不用动。
      setStats: () => {},
      setDirty: (d) => { $("eDirty").textContent = d ? " •" : ""; },
      setUndo: () => {},
      // 没吸附就不显示（原来是 "—"，纯噪音）
      setCursor: () => { $("eSnapLabel").textContent = app.editor.snapText() || ""; },
      version: () => { $("eVer").textContent = BUILD; },
      openBuilding: (bid) => openBuilding(bid),   // 地图上点建筑 → 跳过来
      setTool: (t) => {
        for (const b of $("eTool").children) b.classList.toggle("on", b.dataset.tool === t);
        renderPalette();          // 调色盘那格的高亮跟着走
      },
    };
    app.editor = await new Editor($("ecanvas"), $("elabels"), a, ui).init();
    ui.version();
    await buildPalettes();
    ui.setTool("select");
    // 类别 tab
    for (const b of $("eTabs").children)
      b.onclick = () => {
        curCat = b.dataset.cat;
        for (const x of $("eTabs").children) x.classList.toggle("on", x === b);
        renderPalette();
      };
    // 吸附 / 栅格 复选框 + 栅格尺寸（整米）
    const wire = (id, fn) => {
      const lab = $(id), cb = lab.querySelector("input");
      cb.onchange = () => { lab.classList.toggle("on", cb.checked); fn(cb.checked); app.editor.redraw(); };
    };
    wire("eSnapNet", v => { app.editor.doc.netSnap = v; });
    wire("eSnapGrid", v => { app.editor.doc.gridSnap = v; });
    $("eGridSize").onchange = (e) => {
      app.editor.doc.gridM = Math.max(1, Math.round(+e.target.value || 1));
      e.target.value = app.editor.doc.gridM;
      app.editor.redraw();
    };
    app.editor.view.el.addEventListener("pointermove", (e) => {
      const r = app.editor.view.el.getBoundingClientRect();
      const [x, y] = app.editor.view.toWorld(e.clientX - r.left, e.clientY - r.top);
      // ★ 摆家具时显示【屋内坐标】：外面的世界坐标在这里没意义
      //   （而且会让人以为格子还是室外那套 —— 用户实测："
      //   十字坐标还是按照室外在动"）。
      const ed = app.editor, bid = ed?.placingIn?.();
      if (bid) {
        const r4 = ed._rect4(bid);
        const rx = (x - r4[0]), ry = (y - r4[1]);
        $("eXY").textContent = "屋内 " + rx.toFixed(1) + ", " + ry.toFixed(1) + " m";
      } else {
        $("eXY").textContent = `${Math.round(x)},${Math.round(y)}`;
      }
      $("eSnapLabel").textContent = app.editor.snapText() || "";
    });
  }
  show("editor");
  const name = await app.editor.openLatest();
  // ★ 打开时清过脏数据就说一声 —— 静默删除会让人以为东西自己丢了
  const pruned = app.editor.doc.prune();
  if (pruned.length) toast("清掉了脏数据：" + pruned.join("，"));
  else toast(`打开 ${name}（最近编辑的那张）`);
}

/** 三个类别的调色盘。切 tab 就换一屏，都平铺，不滚动。
 *
 *  每一格带一个 act：
 *    width  道路宽度（点一下改画笔，接着画）
 *    bld    建筑类型（切到「摆放」）
 *    prop   环境物件（切到「摆放」）
 *  ★ 车【不算场景资产】，两边都不给 —— 它是模拟里跑出来的，不是摆上去的。
 */
let PALETTE = { bld: [], road: [], env: [], area: [] };
let curCat = "bld";

const PROP_ZH = { tree_s: "小树", tree_m: "中树", tree_l: "大树",
                  bush_1: "灌木", bush_2: "矮丛", bench: "长椅", lamp: "路灯",
                  bin: "垃圾桶", flowerbed: "花坛" };

async function buildPalettes() {
  const cat = await (await fetch("/api/catalog", { cache: "no-store" })).json();
  const m = await fetchManifest();
  const prop = (a) => ({ act: "prop", key: a.name,
                         label: PROP_ZH[a.name] || a.name, sub: `${a.w}×${a.h}`,
                         hint: `props/${a.name}.svg` });
  // 车不进调色盘：车是模拟里跑的，不是摆上去的场景资产
  const props = m.assets.filter(a => a.sub === "props" && !/^car_/.test(a.name));

  PALETTE.bld = cat.buildings.map(b => ({
    act: "bld", key: b.type, label: b.name, sub: b.kind,
    hint: `${b.type} · 容量 ${b.capacity} · 默认 ${b.size[0].toFixed(1)}×${b.size[1].toFixed(1)} m`,
  }));
  PALETTE.road = [3, 4, 6, 8].map(w => ({
    act: "width", key: String(w), label: `${w} 米`,
    sub: w <= 3 ? "小巷" : w <= 4 ? "标准" : w <= 6 ? "大路" : "主干道",
    hint: "画路用的宽度；改完接着画",
  }));
  PALETTE.env = props.map(prop);
  // 地面区域：玩法后面再说，先把这几个用途预留出来
  PALETTE.area = [
    { act: "area", key: "farm", label: "农田", sub: "借 dirt",
      hint: "点节点围出闭合多边形；点回第一个节点闭合" },
    { act: "area", key: "concrete", label: "水泥地", sub: "借 plaza",
      hint: "同上" },
    { act: "area", key: "tile", label: "地砖", sub: "借 plaza",
      hint: "同上" },
  ];
  renderPalette();
}

function renderPalette() {
  const host = $("ePalette");
  host.innerHTML = "";

  for (const it of (PALETTE[curCat] || [])) {
    const b = document.createElement("button");
    b.dataset.key = it.key;
    b.title = it.hint || "";
    b.innerHTML = `${it.label}<span class="k">${it.sub || ""}</span>`;
    const on = (it.act === "bld" && app.editor.buildType === it.key)
            || (it.act === "width" && String(app.editor.roadWidth) === it.key)
            || (it.act === "prop" && app.editor.propName === it.key)
            || (it.act === "area" && app.editor.areaKind === it.key && app.editor.tool === "area");
    if (on) b.classList.add("on");
    b.onclick = () => {
      // 点调色盘 = 进那个状态。再点一次同一格 = 退回「选择」。
      const same = (it.act === "bld" && app.editor.buildType === it.key)
                || (it.act === "prop" && app.editor.propName === it.key)
                || (it.act === "area" && app.editor.areaKind === it.key && app.editor.tool === "area")
                || (it.act === "width" && String(app.editor.roadWidth) === it.key && app.editor.tool === "road");
      if (same) { app.editor.buildType = ""; app.editor.propName = ""; app.editor.setTool("select"); }
      else if (it.act === "bld") { app.editor.propName = ""; app.editor.buildType = it.key; app.editor.setTool("place", it.key); }
      else if (it.act === "prop") { app.editor.buildType = ""; app.editor.propName = it.key; app.editor.setTool("place"); }
      else if (it.act === "area") { app.editor.areaKind = it.key; app.editor.setTool("area"); }
      else { app.editor.roadWidth = +it.key; app.editor.setTool("road"); }
      renderPalette();
    };
    host.appendChild(b);
  }
}

// 模式切换
for (const b of $("eModes").children)
  b.onclick = () => {
    const m = b.dataset.mode;
    if (m === "people") openPeople();
    else if (m === "building") openBuilding();
    else if (m === "company") openCompany();
    else { showPanel(""); app.editor.view.el.style.cursor = "crosshair"; app.editor.hoverLoc = ""; }
  };
$("pAdd").onclick = newNpc;

$("eMenu").onclick = () => show("menu");
$("eSave").onclick = () => app.editor?.save();
$("eSaveAs").onclick = () => {
  const name = prompt("另存为（写到 config/scenes/）：", app.editor?.name || "scene.json");
  if (name) app.editor.save(name.trim().replace(/[^\w.-]/g, "") || "scene.json");
};
// ★ 不传第二个参数！传 app.editor.buildType 的话：setTool("select") 先清空，
//   紧接着 `if (buildType)` 又把它塞回来 —— 点「选择」调色盘不取消高亮。
for (const b of $("eTool").children)
  b.onclick = () => app.editor.setTool(b.dataset.tool);

window.addEventListener("keydown", (e) => {
  const inEditor = !$("editor").classList.contains("hide");
  if (e.key === "Escape") {
    // Esc = 同一个 cancelGesture（和右键一样），不只是清选中
    if (inEditor) app.editor.deselect(); else clearSel();
  }
  if (e.key === "f" && app.world) app.world.view.fill();
  if (e.ctrlKey && e.key === "s" && inEditor) { e.preventDefault(); app.editor.save(); }
  if ((e.key === "Delete" || e.key === "Backspace") && inEditor) {
    if (app.editor.deleteSelected()) e.preventDefault();
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && inEditor) {
    e.preventDefault(); app.editor.undo();
  }
  if (inEditor) {
    const map = { "1": "select", "2": "erase" };
    if (map[e.key]) app.editor.setTool(map[e.key], app.editor.buildType);
  }
});
