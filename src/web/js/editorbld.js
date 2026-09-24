/** editorbld.js —— 编辑器 · 建筑 + 公司。 */
import { $, esc, app, store, toast, show } from "./core.js";
import { SIGNAL_ZH } from "./zh.js";
import { showPanel } from "./editornpc.js";

//  ★ 建筑【没有"新增"】—— 房子是在地图上摆的（画路 → 摆房），这里只编辑。
//    右边能改的是"这栋楼是什么、归谁、里面摆了什么"。
let BPARTS = null;          // /api/building-parts
let bldSel = "";            // 选中的建筑 id

export async function openBuilding(pick) {
  if (!BPARTS) BPARTS = await (await fetch("/api/building-parts", { cache: "no-store" })).json();
  showPanel("building");
  app.editor.hoverLoc = "";
  // 换一栋楼就退出摆放模式 —— 否则会拿着上一栋的坐标拖新楼的家具
  if (app.editor.placing && pick && pick !== bldSel) {
    app.editor.placing = false;
    app.editor.redraw();
  }
  bldSel = pick || "";
  renderBuildings();
}

/** 编辑器进出摆放模式时，让建筑面板跟着切。
 *
 *  ★ 为什么要有这个：屋里那行「屋内栅格」是【只在摆放时显示】的，
 *    它由 renderBldForm 渲染。而双击楼进摆放是地图上的动作 ——
 *    编辑器不知道有面板这回事，面板也不知道摆放状态变了，
 *    于是：双击进去看不到栅格调节，一直等到某次保存重画面板才冒出来
 *    （用户："双击后 无栅格调节 保存后栅格调节跳出"）。
 *   加一个 hook：编辑器负责说"我进/出摆放了"，面板负责跟着重画。
 *
 *  ★ 不能直接调 openBuilding —— 它有一条"换楼就退出摆放"的规则，
 *    而这里恰恰是"正在摆放时又双击了另一栋楼"，会被它踢出去。
 */
export function syncPlacing(bid) {
  if (bid) { bldSel = bid; showPanel("building"); }
  renderBldForm();
}

export function closeBuilding() {
  showPanel("");
  app.editor.hoverLoc = "";
  app.editor.placing = false;      // 离开建筑模式就别停在"拖家具"状态里
  app.editor.redraw();
}

//  公司本来就在场景里（scene.companies），编辑器不是新建一批，而是管这批。
//  ★ 两条规则：
//    1. 能分配给公司的建筑，由【建筑类型】定死（KIND_BY_BUILDING）——
//       店铺只能零售、工厂只能制造，不是手选。别的楼（住宅/广场/市场…）开不了公司。
//    2. 公司占用的建筑，里面所有物品都归公司 —— 分配时一并把 owner 搬过去。
let compSel = "";

export async function openCompany() {
  if (!BPARTS) BPARTS = await (await fetch("/api/building-parts", { cache: "no-store" })).json();
  showPanel("company");
  app.editor.hoverLoc = "";
  compSel = "";
  $("cAdd").onclick = openNewCompany;
  renderCompanies();
}

export function closeCompany() {
  showPanel("");
  app.editor.hoverLoc = "";
}

const COMP_KIND_ZH = { retail: "零售", manufacture: "制造" };

/** 这栋楼现在归谁（没主 = 空字符串）。 */
function ownerOf(bid) {
  const c = (app.editor.doc.meta.companies || [])
    .find((x) => (x.shops || []).includes(bid));
  return c ? c.id : "";
}

/** 这种建筑能开什么公司（空 = 开不了）。
 *  ★ 必须查 BPARTS（/api/building-parts）—— D.types 来自 /api/catalog，
 *    那里没有 company_kind，拿 D.types 查会全都不匹配、一个候选都出不来。 */
function compKindOfType(ty) {
  const t = (BPARTS?.types || []).find((x) => x.type === ty);
  return t ? (t.company_kind || "") : "";
}

function renderCompanies() {
  const list = app.editor.doc.meta.companies || [];
  $("cCount").textContent = list.length + " 家";
  const host = $("cList");
  host.innerHTML = "";
  if (!list.length) host.innerHTML = '<div class="none">还没有公司</div>';
  for (const c of list) {
    const el = document.createElement("button");
    el.innerHTML = '<span class="nm">' + esc(c.name || c.id) + "</span>"
      + '<span class="tag2">' + esc(COMP_KIND_ZH[c.kind] || c.kind || "") + "</span>"
      + '<span class="tag2">' + (c.shops || []).length + " 栋</span>";
    if (c.id === compSel) el.classList.add("on");
    el.onclick = () => { compSel = c.id; renderCompanies(); };
    // 悬浮 → 地图上高亮它占的建筑（一栋一栋亮）
    el.onmouseenter = () => { app.editor.hoverLoc = (c.shops || [])[0] || ""; app.editor.redraw(); };
    el.onmouseleave = () => { app.editor.hoverLoc = ""; app.editor.redraw(); };
    host.appendChild(el);
  }
  renderCompForm();
}

function renderCompForm() {
  const host = $("cForm");
  const D = app.editor.doc;
  const c = (D.meta.companies || []).find((x) => x.id === compSel);
  if (!c) {
    host.innerHTML = '<div class="none2" style="text-align:center;padding:60px 0">'
      + "点左边选一家公司，或者点「+ 新增」</div>";
    return;
  }
  // ★ 公司占【一栋】，不是一堆。没有"空公司"这个状态 ——
  //   想腾出来只有两条路：搬走（东西跟着走）、注销（东西全删）。
  const here = (c.shops || [])[0] || "";
  const owns = here
    ? '<div class="owns"><span class="nm5">' + esc(D.nameOf(here) || here) + "</span>"
      + '<span class="n2">' + D.at(here).length + " 件</span></div>"
    : '<div class="none2">没有建筑（虚空公司，保存时会被删）</div>';

  // 制造公司必须说清楚产出什么（内核 register 时会拦），所以这个能改。
  // ★ 只列 material 类的货 —— 工厂产的是原料，不是床。
  //   （当前值即使不在表里也留着，否则一保存就把已有的产出洗掉）
  const mats = (BPARTS?.items || []).filter((it) => (it.tags || []).includes("material"));
  const curProd = c.produces_item;
  const prodSel = c.kind === "manufacture"
    ? '<div class="row"><label>产出</label><select id="cProd">'
      + '<option value="">（没定）</option>'
      + mats.map((it) => '<option value="' + esc(it.type) + '"'
          + (curProd === it.type ? " selected" : "") + ">" + esc(it.name) + "</option>").join("")
      + (curProd && !mats.some((it) => it.type === curProd)
          ? '<option value="' + esc(curProd) + '" selected>' + esc(curProd) + "</option>" : "")
      + "</select></div>" : "";

  host.innerHTML =
    "<h2>" + esc(c.name || c.id) + "</h2>"
    + '<div class="row"><label>名字</label><input id="cName" type="text" value="'
    + esc(c.name || "") + '"></div>'
    + '<div class="row"><label>类型</label><span class="hn">'
    + esc(COMP_KIND_ZH[c.kind] || c.kind || "—") + "（" + esc(c.kind || "") + "）"
    + '<span class="lock">　由楼定</span></span></div>'
    + '<div class="row"><label>现金</label><input id="cCash" type="number" step="1" value="'
    + (c.cash ?? 0) + '"></div>'
    + prodSel
    + '<div class="row"><label>营业</label><span class="hn">'
    + esc(String(c.open || "").slice(0, 5) || "—") + " – "
    + esc(String(c.close || "").slice(0, 5) || "—") + "</span></div>"
    + '<div class="row"><label>时薪</label><span class="hn">' + (c.wage_per_hour ?? 0) + " 元/时</span></div>"
    + '<div class="row"><label>员工</label><span class="hn">' + (c.staff || []).length + " 人</span></div>"

    + '<div class="sec">所在建筑</div>'
    + owns
    + '<div class="addrow"><button id="cMove">搬走…</button></div>'

    + '<div class="bar2"><button class="primary" id="cSave">保存</button>'
    + '<span class="sp"></span>'
    + '<button class="danger" id="cDel">注销公司</button></div>';

  const on = (id, fn) => { const e2 = $(id); if (e2) e2.onclick = fn; };

  on("cMove", () => openMove(c));
  on("cDel", () => delCompany(c));
  on("cSave", async () => {
    const nm = $("cName").value.trim();
    if (!nm) return toast("公司名不能空");
    if ($("cProd") && !$("cProd").value)
      return toast("制造公司要说清楚产出什么");
    app.editor.pushUndo();
    c.name = nm;
    c.cash = Number($("cCash").value) || 0;
    if ($("cProd")) c.produces_item = $("cProd").value;
    app.editor.doc._changed();   // ★ 走 _changed()（见上）
    renderCompanies();
    await app.editor.save();
    toast("已保存到 " + (app.editor.name || "场景"));
  });
}

/** ★ 新增公司 = 内核那套：先挑一栋【能开公司且没主】的楼，类型由楼定死。
 *  公司 id 也按内核的规矩来：org_<楼id>（场景里现有那几家就是这个形状）。 */
function openNewCompany() {
  const D = app.editor.doc;
  const ok = Object.keys(D.buildings)
    .filter((bid) => compKindOfType(D.buildings[bid].type) && !ownerOf(bid))
    .sort((a, b) => D.nameOf(a).localeCompare(D.nameOf(b), "zh"));

  const pop = $("cBldPop");
  pop.dataset.role = "new";
  pop.innerHTML = ok.length
    ? ok.map((bid) => {
        const t = D.types[D.buildings[bid].type] || {};
        const k2 = compKindOfType(D.buildings[bid].type);
        return '<button data-new="' + esc(bid) + '">'
          + '<span class="nm4">' + esc(D.nameOf(bid) || bid) + "</span>"
          + '<span class="n5">' + esc(COMP_KIND_ZH[k2] || k2) + "（"
          + esc(t.name || t.type || "") + "）</span></button>";
      }).join("")
    : '<div class="none2" style="grid-column:1/-1;text-align:center;padding:18px 0">'
      + "没有空着、又能开公司的楼<br><span style=\"font-size:11px\">"
      + "先去地图上摆一栋店铺或加工厂</span></div>";
  pop.classList.remove("hide");
  let veil = $("popVeil");
  if (!veil) { veil = document.createElement("div"); veil.id = "popVeil";
               document.body.appendChild(veil); }
  const close = () => { pop.classList.add("hide"); pop.dataset.role = ""; veil.remove(); };
  veil.onclick = close;
  for (const b of pop.querySelectorAll("[data-new]"))
    b.onclick = () => { close(); newCompanyOn(b.dataset.new); };
}

async function newCompanyOn(bid) {
  const D = app.editor.doc;
  const kind = compKindOfType(D.buildings[bid].type);
  let cid = "org_" + bid;
  let n = 2;
  while ((D.meta.companies || []).some((c) => c.id === cid)) cid = "org_" + bid + "_" + n++;
  app.editor.pushUndo();
  const c = {
    id: cid, name: D.nameOf(bid) + "公司", kind,
    shops: [bid], cash: 1000, open: "08:00", close: "19:00",
    wage_per_hour: 3, hiring_slots: 0, staff: [],
    // 制造公司必须指定产出（内核会拦），先给个占位让它合法
    produces_item: kind === "manufacture"
      ? ((BPARTS?.items || []).find((x) => (x.tags || []).includes("material"))?.type || "") : "",
  };
  (D.meta.companies ||= []).push(c);
  let moved = 0;
  for (const e2 of D.meta.entities || [])
    if (e2.at === bid) { e2.owner = cid; moved++; }
  D._changed();   // ★ 走 _changed()：set dirty + 通知监听器（监听里整屏重画）
  compSel = cid;
  renderCompanies();
  await app.editor.save();
  toast("开了家公司：" + c.name + "（连同楼里的 " + moved + " 件）");
  if (kind === "manufacture" && !c.produces_item)
    toast("制造公司还得选一下产出什么");
}

/** 注销公司：楼腾出来（里面的东西不再归它），公司本身从场景里拿掉。 */
/** ★ 注销 = 楼里的东西【全删】。
 *  编辑器模式，没有回收折现那回事 —— 别把两个模型混在一起。 */
async function delCompany(c) {
  const D = app.editor.doc;
  const here = (c.shops || [])[0] || "";
  const n = D.at(here).length;
  if (!confirm("注销「" + (c.name || c.id) + "」？\n"
      + (here ? (D.nameOf(here) || here) + " 里的 " + n + " 件东西会一起删掉。\n" : "")
      + "（编辑器里没有折现回收）")) return;
  app.editor.pushUndo();
  const arr = D.meta.entities || [];
  D.meta.entities = here ? arr.filter((e2) => e2.at !== here) : arr;
  const cs = D.meta.companies || [];
  const k = cs.indexOf(c);
  if (k >= 0) cs.splice(k, 1);
  D._changed();   // ★ 走 _changed()：set dirty + 通知监听器（监听里整屏重画）
  compSel = "";
  D.prune();
  renderCompanies();
  await app.editor.save();
  toast("注销了 " + (c.name || c.id) + (n ? "（连里面的 " + n + " 件）" : ""));
}

/** 能分给这家公司的楼：① 建筑类型支持这种公司 ② 还没被别人占。 */
/** 能搬去哪儿：① 建筑类型能开这种公司 ② 还没被别人占。
 *  ★ 没有“分配”——公司不是分来的，是【注册时挑楼】定的。
 *    搬走是换一栋楼，东西（家具和货）全跟着走。 */
function moveTargets(c) {
  const D = app.editor.doc;
  const cur = (c.shops || [])[0] || "";
  return Object.keys(D.buildings).filter((bid) => {
    if (bid === cur) return false;
    if (compKindOfType(D.buildings[bid].type) !== c.kind) return false;
    return !ownerOf(bid);
  }).sort((a, b) => D.nameOf(a).localeCompare(D.nameOf(b), "zh"));
}

function openMove(c) {
  const D = app.editor.doc;
  const ok = moveTargets(c);
  const canKind = Object.entries(BPARTS?.kind_by_building || {})
    .filter(([, v]) => v === c.kind)
    .map(([k]) => (D.types ? Object.values(D.types).find((t) => t.kind === k)?.name || k : k))
    .join(" / ");
  const pop = $("cBldPop");
  pop.dataset.role = "move";
  pop.innerHTML = ok.length
    ? ok.map((bid) => {
        const t = D.types[D.buildings[bid].type] || {};
        return '<button data-move="' + esc(bid) + '">'
          + '<span class="nm4">' + esc(D.nameOf(bid) || bid) + "</span>"
          + '<span class="n5">' + esc(t.name || t.type || "") + " · "
          + D.at(bid).length + " 件</span></button>";
      }).join("")
    : '<div class="none2" style="grid-column:1/-1;text-align:center;padding:18px 0">'
      + "没有别的地方可搬<br><span style=\"font-size:11px\">"
      + "要有一栋空着的「" + esc(canKind) + "」</span></div>";
  pop.classList.remove("hide");
  let veil = $("popVeil");
  if (!veil) { veil = document.createElement("div"); veil.id = "popVeil";
               document.body.appendChild(veil); }
  const close = () => { pop.classList.add("hide"); pop.dataset.role = ""; veil.remove(); };
  veil.onclick = close;
  for (const b of pop.querySelectorAll("[data-move]"))
    b.onclick = () => { close(); moveCompany(c, b.dataset.move); };
  if (!ok.length) toast("没地方可搬 —— 先在地图上摆一栋空的同类建筑");
}

/** ★ 搬走：里面所有东西（家具 + 货）全搬到目的。搬不过去就是搬走失败。 */
async function moveCompany(c, dest) {
  const D = app.editor.doc;
  const from = (c.shops || [])[0] || "";
  if (from === dest) return;
  if (ownerOf(dest)) return toast("那儿已经有公司了");
  if (compKindOfType(D.buildings[dest].type) !== c.kind)
    return toast("那栋楼开不了这种公司");
  const moved = D.at(from);
  // 目的地本来就有东西 → 一起归这家公司（公司占的建筑，里面的东西就是它的）
  for (const e of moved) { e.at = dest; e.owner = c.id; }
  for (const e of D.at(dest)) e.owner = c.id;
  c.shops = [dest];
  D._changed();   // ★ 走 _changed()：set dirty + 通知监听器（监听里整屏重画）
  D.prune();
  renderCompanies();
  await app.editor.save();
  toast((c.name || c.id) + " 从 " + (D.nameOf(from) || from) + " 搬到 "
    + (D.nameOf(dest) || dest) + "（" + moved.length + " 件一起）");
}


function renderBuildings() {
  const D = app.editor.doc;
  const ids = Object.keys(D.buildings).sort((a, b) => D.nameOf(a).localeCompare(D.nameOf(b), "zh"));
  $("bCount").textContent = ids.length + " 栋";
  const host = $("bList");
  host.innerHTML = "";
  for (const bid of ids) {
    const b = D.buildings[bid];
    const t2 = D.types[b.type] || {};
    const el = document.createElement("button");
    el.innerHTML = '<span class="nm">' + esc(D.nameOf(bid) || bid) + "</span>"
      + '<span class="tag2">' + esc(t2.kind || "") + "</span>";
    if (bid === bldSel) el.classList.add("on");
    el.onclick = () => { bldSel = bid; renderBuildings(); };
    // ★ 悬浮 → 在地图上高亮整栋楼
    // ★ 改完 hoverLoc 要重绘 —— 不然地图上什么都不亮（踩过）
    el.onmouseenter = () => { app.editor.hoverLoc = bid; app.editor.redraw(); };
    el.onmouseleave = () => { app.editor.hoverLoc = ""; app.editor.redraw(); };
    host.appendChild(el);
  }
  renderBldForm();
}

function renderBldForm() {
  const host = $("bForm");
  const D = app.editor.doc;
  if (!bldSel || !D.buildings[bldSel]) {
    host.innerHTML = '<div class="none2" style="text-align:center;padding:60px 0">'
      + "点左边选一栋楼</div>";
    return;
  }
  const bid = bldSel, b = D.buildings[bid], tp = D.types[b.type] || {};
  const inside = (D.meta.entities || []).filter((e) => e.at === bid);
  const mine = (D.meta.companies || []).find((c) => (c.shop_list || c.shops || []).includes(bid));
  const items = BPARTS?.items || [];
  const iconOf = (ty) => (items.find((x) => x.type === ty)?.icon)
    ? "/art/items/icon_" + ty + ".svg" : "";
  const isFix = (ty) => (items.find((x) => x.type === ty)?.tags || []).includes("fixture");

  const opt = (v, label, on) =>
    '<option value="' + v + '"' + (on ? " selected" : "") + ">" + label + "</option>";
  const typeOpts = (BPARTS?.types || []).map((x) =>
    opt(x.type, esc(x.name) + "（" + esc(x.kind) + " " + x.capacity + "）", b.type === x.type)).join("");
  // ★ 权限是【读出来】的，不是选出来的 —— 由建筑类型定，public 只是
  //   「谁都能进」这个更强的例外。
  //   以前靠一个 public 开关算：非住宅 + 没标公开 = 「仅内部人员」
  //   —— 于是店铺也被写成仅内部，显然不对。
  const dwellers = D.npcs.filter((n) => n.home === bid);
  const cap = tp.capacity || 0;
  const BY_KIND = {
    home: () => (dwellers.length
      ? "只住客能进 —— " + dwellers.map((n) => n.name).join("、")
        + "（" + dwellers.length + "/" + cap + "）"
      : "只住客能进 —— 还没人住（0/" + cap + "）"),
    shop: () => "顾客能进" + (mine && mine.open != null
      ? "（" + String(mine.open).slice(0, 5) + "–" + String(mine.close).slice(0, 5) + "）"
      : "（营业时）"),
    market: () => "谁都能进",
    public: () => "谁都能进",
    clinic: () => "病人能进",
    school: () => "学生和老师能进",
    work: () => "仅员工",
    factory: () => "仅员工",
  };
  const access = D.isPublic(bid) ? "谁都能进"
    : ((BY_KIND[tp.kind] || (() => "仅内部人员"))());
  const companyName = mine ? (mine.name || mine.id) : "无";

  // 一行一件，只有【图标 + 名字】+ 右边一个数量提示 —— 点它才弹详情。
  const things = inside.length ? inside.map((e, i) => {
    const it = items.find((x) => x.type === e.type) || {};
    const fix = isFix(e.type);
    const ic = iconOf(e.type);
    const qt = fix ? "" : "×" + (e.stock ?? it.stock ?? 0);
    // ★ 一行两个动作，用【两个地方】表达，不用单击/双击：
    //     整行 = 拿起来拖动（不在摆放模式就自动进 —— 这一行的意思永远一样）
    //     行尾 &#9998; = 改详情（存量/售价/删掉）
    //   为什么不用双击：双击必然先触发两次单击，要么给拿起加 220ms 延迟
    //   （每次拿起都卡一下），要么接受"弹框时手里还攥着东西"。两条都不干净。
    //   &#9998; 必须 stopPropagation —— 不然点它会冒泡到整行、顺手把家具拿起来。
    return '<button class="th" data-open="' + i + '" title="点一下拿起来摆；&#9998; 改详情">'
      + (ic ? '<img class="ic" src="' + ic + '">' : '<span class="ic"></span>')
      + '<span class="nm3">' + esc(it.name || e.type) + "</span>"
      + '<span class="qt">' + qt + "</span>"
      + '<span class="ed" data-edit="' + i + '" title="改详情">&#9998;</span></button>';
  }).join("") : '<div class="none2">空着</div>';

  // 候选（和头像那个一样：点「放一件」才弹）
  const cand = items.map((x) =>
    '<button data-put="' + x.type + '" title="' + esc(x.name) + '">'
    + (x.icon ? '<img src="/art/items/icon_' + x.type + '.svg">' : '<span class="ic"></span>')
    + '<span class="nm4">' + esc(x.name) + "</span></button>").join("");

  host.innerHTML =
    "<h2>" + esc(D.nameOf(bid) || bid) + "</h2>"
    + '<div class="row"><label>类型</label><select id="bType">' + typeOpts + "</select></div>"
    + '<div class="row"><label>名字</label><input id="bName" type="text" value="'
    + esc(D.nameOf(bid) || "") + '"></div>'
    + '<div class="row"><label>占地</label><span class="hn">'
    + b.size[0].toFixed(1) + " × " + b.size[1].toFixed(1) + " m</span></div>"
    + '<div class="row"><label>权限</label><span class="hn">' + esc(access) + "</span></div>"
    + '<div class="row"><label>公司</label><span class="hn">' + esc(companyName) + "</span></div>"

    // 屋内栅格：★ 和室外的 gridM 是两套参数。4 米的格子摆不了家具
    // （一件东西才 0.6 米宽），所以摆放时单独给一格。
    // 只在开着摆放模式时出现 —— 平时不占地方。
    + (app.editor.placing
        ? '<div class="snaprow" style="margin:10px 0 0"><span>屋内栅格</span>'
          + '<span class="sz"><input id="bGridIn" type="number" min="0.1" max="5" step="0.1" value="'
          + (D.gridInM || 0.5) + '">m</span></div>'
        : "")
    + '<div class="sec">里面的东西 <span class="dim">' + inside.length + " 件</span>"
    // ★ 没按钮了：进摆放 = 【双击地图上那栋楼】；出来 = Esc / 右键。
    //   这里只留一句提示 —— 不然没人知道怎么退出。
    + '<span class="dim hint">' + (app.editor.placing
        ? "拖家具摆位置 · Esc 退出" : "双击地图上的楼进摆放") + "</span></div>"
    + '<div class="things">' + things + "</div>"
    + '<div class="addrow"><button id="bAdd">+ 放一件</button></div>'

    + '<div class="bar2"><button class="primary" id="bSave">保存</button>'
    + '<span class="sp"></span>'
    + '<button class="danger" id="bDel">拆掉这栋楼</button></div>';

  const on = (id, fn) => { const e2 = $(id); if (e2) e2.onclick = fn; };
  // （「摆放家具」按钮已撤：改成【双击地图上的楼】直接进 —— 见 editor.js 的 _double）
  // ★ 位置是【前端的事】——后端只说"在哪个 region 里"。
  //   开了之后在地图上直接拖家具，松手就写进场景文件的 entities[].pos
  //   （相对楼内的 0~1 比值）。没摆过的会"从左到右码一排"，不是随机。
  //   必须 setTool("select") —— 拖拽只有在 select 下才接得住。
  // 屋内栅格：和室外的 gridM 是【两套】。4 米的格子摆不了家具（一件才 0.6 米）。
  const gin = $("bGridIn");
  if (gin) gin.onchange = () => {
    const v = Math.min(5, Math.max(0.1, +gin.value || 0.5));
    app.editor.doc.gridInM = v;
    gin.value = v;
    app.editor.redraw();
  };


  // 两个弹框住在 body 顶层（见 index.html 的注释），内容由这里填。
  $("bItemPop").innerHTML = cand;
  $("bItemPop").classList.add("hide");
  $("thingPop").classList.add("hide");
  for (const el2 of $("bItemPop").querySelectorAll("[data-put]"))
    el2.onclick = () => putItem(el2.dataset.put);

  // 「放一件」→ 弹出候选（和头像一样），点一个就放进去
  on("bAdd", () => {
    $("thingPop").classList.add("hide");          // 和"物品详情"互斥
    const pop = $("bItemPop");
    const open = pop.classList.contains("hide");
    pop.classList.toggle("hide", !open);
    let veil = $("popVeil");
    if (open) {
      if (!veil) { veil = document.createElement("div"); veil.id = "popVeil";
                   document.body.appendChild(veil); }
      veil.onclick = () => { pop.classList.add("hide"); veil.remove(); };
    } else veil?.remove();
  });
  function putItem(ty) {
    const it = items.find((x) => x.type === ty) || {};
    const fix = (it.tags || []).includes("fixture");
    app.editor.pushUndo();
    (D.meta.entities ||= []).push(fix
      ? { id: ty + "_" + String(Date.now()).slice(-5), at: bid, type: ty,
          owner: mine ? mine.id : undefined }
      : { id: ty + "_" + String(Date.now()).slice(-5), at: bid, type: ty,
          owner: mine ? mine.id : undefined, stock: it.stock ?? 1, price: it.price ?? 0 });
    D._changed();   // ★ 走 _changed()：set dirty + 通知监听器（监听里整屏重画）
    $("popVeil")?.remove();
    renderBldForm();
  }

  // ★ 整行单击 = 【拿起来拖动】。不分模式 —— 不在摆放模式就先进去，
  //   这样这一行的意思永远是同一个。（以前是"摆放时拿起、否则弹详情"，
  //   同一行点两下结果不同 —— 用户："这里的逻辑不对，有重复"。）
  //   叠在一起的东西在地图上点不中，所以列表必须能拿起 —— 这正是它的用处。
  for (const el2 of host.querySelectorAll("[data-open]")) {
    const ent = inside[+el2.dataset.open];
    el2.onclick = () => {
      const ed = app.editor;
      if (!ed.placing || ed.selected !== bid) ed.enterPlacing(bid);
      ed.takeItem(ent.id);
      renderBldForm();                 // 重画列表（反白）+ 地图
    };
  }
  // 行尾 ✎ = 改详情（存量 / 售价 / 删掉）。
  //   ★ stopPropagation 是必须的 —— 不然点它会冒泡到整行、顺手把家具拿起来。
  for (const el2 of host.querySelectorAll("[data-edit]"))
    el2.onclick = (e) => {
      e.stopPropagation();
      openThing(inside[+el2.dataset.edit]);
    };

  /** 把"手上拿着的那行"标出来，和地图上的高亮对上。 */
  function markRow(id) {
    for (const el3 of host.querySelectorAll("[data-open]"))
      el3.classList.toggle("pick",
        (inside[+el3.dataset.open] || {}).id === app.editor.pick);
  }
  if (app.editor.placing) markRow();

  /** 一件东西的详情框：字段 + 数据，尽量写全，但不写句子。
   *
   *  ★ 只用「标签 → 值」两栏，不写"家具 —— 不买卖、没有存量"这种话。
   *    读的人一眼扫完，不读句子；没值的行不出现（而不是写个"无"）。
   */
  function openThing(ent) {
    const it = items.find((x) => x.type === ent.type) || {};
    const fix = isFix(ent.type);
    const ic = iconOf(ent.type);
    const pop = $("thingPop");
    const rows = [];
    const put = (k, v, cls) => { if (v !== "" && v != null) rows.push(
      '<div class="row"><label>' + k + '</label><span class="hn ' + (cls || "") + '">'
      + v + "</span></div>"); };

    // ① 能改的放最上面（存量 / 售价）
    if (!fix) {
      rows.push('<div class="row"><label>存量</label><input id="tStock" type="number" value="'
        + (ent.stock ?? it.stock ?? 0) + '"></div>');
      rows.push('<div class="row"><label>售价</label><input id="tPrice" type="number" step="0.5" value="'
        + (ent.price ?? it.price ?? 0) + '"></div>');
    }

    // ② 所属 —— 规则：公司占的建筑，里面的东西就是它的。
    //    所以这是【读出来】的，不是选的（和建筑面板的「公司」同一个道理）。
    const co = (D.meta.companies || []).find((x) => (x.shops || []).includes(bid));
    put("所属", co ? esc(co.name || co.id) : '<span class="dim">无主</span>');

    // ③ 定义里的属性（没值的行不出现）
    put("类型", fix ? "家具" : "货");
    put("造价", it.build_cost ? it.build_cost : "");
    // duration_ticks 是【用这东西要花多久】（马桶 5 tick、前台 60 tick），不是耐久
    put("耗时", it.duration_ticks ? it.duration_ticks + " tick" : "");
    put("保质期", it.shelf_life_ticks
      ? (it.shelf_life_ticks / 1440).toFixed(it.shelf_life_ticks % 1440 ? 1 : 0) + " 天" : "");
    put("空态", it.persist_empty ? "保留" : "");
    const aff = Object.entries(it.affordances || {});
    put("效果", aff.length ? aff.map(([k, v]) =>
      esc(SIGNAL_ZH[k] || k) + " " + (v > 0 ? "+" : "") + v).join(" · ") : "");
    const at = Object.entries(it.attrs || {});
    put("附加", at.length ? at.map(([k, v]) => esc(k) + "=" + esc(v)).join(" · ") : "");

    pop.innerHTML =
      '<div class="th2">' + (ic ? '<img src="' + ic + '">' : "")
      + "<div><b>" + esc(it.name || ent.type) + "</b>"
      + '<div class="id">' + esc(ent.id || "") + "</div></div></div>"
      + rows.join("")
      + (it.tags?.length ? '<div class="tags2">' + it.tags.map((x) =>
          '<span>' + esc(x) + "</span>").join("") + "</div>" : "")
      + '<div class="bar3"><button class="primary" id="tSave">保存</button>'
      + '<span class="sp"></span><button class="danger" id="tDel">删掉</button></div>';
    pop.classList.remove("hide");
    let veil = $("popVeil");
    if (!veil) { veil = document.createElement("div"); veil.id = "popVeil";
                 document.body.appendChild(veil); }
    veil.onclick = () => { pop.classList.add("hide"); veil.remove(); };
    const close = () => { pop.classList.add("hide"); veil.remove(); };
    $("bItemPop").classList.add("hide");            // 和"放一件"的候选框互斥
    on("tSave", () => {
      app.editor.pushUndo();
      if (!fix) {
        ent.stock = Number($("tStock").value) || 0;
        ent.price = Number($("tPrice").value) || 0;
      }
      D._changed();   // ★ 走 _changed()：set dirty + 通知监听器（监听里整屏重画）
      close();
      renderBldForm();
    });
    on("tDel", () => {
      app.editor.pushUndo();
      const arr = D.meta.entities || [];
      const k = arr.indexOf(ent);
      if (k >= 0) arr.splice(k, 1);
      D._changed();   // ★ 走 _changed()：set dirty + 通知监听器（监听里整屏重画）
      close();
      renderBldForm();
    });
  }

  on("bSave", async () => {
    const name = $("bName").value.trim();
    const newType = $("bType").value;
    app.editor.pushUndo();
    if (name) D.names[bid] = name;
    if (D.meta.locations?.[bid]) D.meta.locations[bid].name = name || bid;
    if (newType !== b.type) {                      // 换类型：占地按新类型重算，中心不动
      const sz = D.sizeFor(newType);
      b.type = newType; b.size = sz;
      if (D.meta.locations?.[bid]) {
        D.meta.locations[bid].type = newType;
        D.meta.locations[bid].w = sz[0]; D.meta.locations[bid].h = sz[1];
        D.meta.locations[bid].x = +(b.center[0] - sz[0] / 2).toFixed(3);
        D.meta.locations[bid].y = +(b.center[1] - sz[1] / 2).toFixed(3);
      }
    }
    // ★ 权限 / 公司 不在这里写 —— 它们是读出来的（权限由类型 + public 决定，
    //   公司由 companies[].shops 决定）。以前这里会重写 public 和 shops，
    //   对着"只读"的值瞎改，反而把数据弄坏。
    D._changed();   // ★ 走 _changed()：set dirty + 通知监听器（监听里整屏重画）
    renderBuildings();
    // ★ 必须写盘。原来只改内存 —— 编辑完刷新一下改动全没了，
    //   看着就是"编辑失败"（顶栏那个「保存」才真写盘，两个按钮同名很容易混）。
    await app.editor.save();
    toast("已保存到 " + (app.editor.name || "场景"));
  });
  // ★ 拆楼 → 里面的东西一起删（施工队清场）。
  //   楼都没了，东西还挂在它身上就是【虚空物品】。
  //   顺带：这栋楼如果是某家公司的唯一住所，那家公司也没了（虚空公司）——
  //   两边都由 doc.prune() 兜底。
  on("bDel", async () => {
    const n = app.editor.doc.at(bid).length;
    if (!confirm("拆掉 " + (D.nameOf(bid) || bid) + "？"
        + (n ? "\n里面的 " + n + " 件东西也会一起删掉。" : ""))) return;
    app.editor.pushUndo();
    D.removeBuilding(bid);
    bldSel = "";
    D._changed();   // ★ 走 _changed()：set dirty + 通知监听器（监听里整屏重画）
    renderBuildings();
    await app.editor.save();
  });
}

// ── 真菜单：进来不自动开游戏，等玩家选 ──────────────────────────────
