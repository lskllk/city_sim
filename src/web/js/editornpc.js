/** editornpc.js —— 编辑器 · 人物设计。 */
import { $, esc, app, store, toast, show } from "./core.js";
import { SIGNAL_ZH } from "./zh.js";

//  ★ 人物数据本来就在场景里（scene.npcs），所以它是【场景编辑器的一个模式】，
//    不是另开一个地方。保存场景 = 保存这份名单。
//    右边编辑栏里所有「可选项」都来自 /api/npc-parts（内核侧的配置 + 美术），
//    前端不硬编码任何一份 —— 改 config/ 或 art/ 这里就跟着变。
let PARTS = null;            // /api/npc-parts
let npcSel = "";             // 选中的人 id
let draft = null;            // 正在编辑的草稿（没保存前不动场景）

export async function openPeople() {
  if (!PARTS) {
    PARTS = await (await fetch("/api/npc-parts", { cache: "no-store" })).json();
    // ★ 在这里就把「有哪些长相」记下来。
    //   原来是 renderNpcForm() 里才赋值，而 renderPeople() 是【先建列表、后调表单】——
    //   建列表时 PARTS_LOOK 还是空的，于是每个人的头像都回退成默认那个（踩过）。
    PARTS_LOOK = new Set((PARTS.looks || []).map((l) => l.id));
  }
  showPanel("people");
  app.editor.view.el.style.cursor = "default";
  npcSel = ""; draft = null;
  renderPeople();
}

/** 只留一个面板。
 *  ★ 以前每个 open* 各写一遍"我开、别人关"，结果漏了公司那个 ——
 *    在地图上点建筑会跳到建筑模式，但公司面板还挂在那儿。 */
export function showPanel(which) {
  for (const [k, el] of Object.entries(
    { people: $("ePeople"), building: $("eBld"), company: $("eComp") }))
    el.classList.toggle("hide", k !== which);
  $("eplace").classList.toggle("hide", !!which);   // 什么都不开 → 地图模式的摆放栏
  for (const b of $("eModes").children)
    b.classList.toggle("on", b.dataset.mode === (which || "map"));
  $("popVeil")?.remove();
  for (const id of ["cBldPop", "bItemPop", "thingPop"]) $(id).classList.add("hide");
}

export function closePeople() {
  showPanel("");
  app.editor.hoverLoc = "";
  app.editor.view.el.style.cursor = "crosshair";
}

function renderPeople() {
  const list = app.editor.doc.npcs;
  $("pCount").textContent = list.length + " 人";
  const host = $("pList");
  host.innerHTML = "";
  if (!list.length) host.innerHTML = '<div class="none">还没有人</div>';
  for (const n of list) {
    const b = document.createElement("button");
    const face = PARTS_LOOK.has(n.look) ? n.look : "me";
    b.innerHTML = '<img src="/art/portraits/' + face + '.svg">'
      + '<span class="nm">' + esc(n.name || "(无名)") + "</span>"
      + '<span class="tag2">' + (n.gender === "female" ? "女" : "男") + "</span>";
    if (n.id === npcSel) b.classList.add("on");
    b.onclick = () => { npcSel = n.id; draft = null; renderPeople(); };
    // ★ 悬浮 → 在地图上高亮他的住处
    b.onmouseenter = () => { app.editor.hoverLoc = n.home || ""; app.editor.redraw(); };
    b.onmouseleave = () => { app.editor.hoverLoc = ""; app.editor.redraw(); };
    host.appendChild(b);
  }
  renderNpcForm();
}

let PARTS_LOOK = new Set();

export function newNpc() {
  npcSel = "";
  draft = { name: "", gender: "female", birthday: "", home: "", role: "",
            money: 100, personality: {}, traits: {}, look: "me" };
  renderPeople();
}

function renderNpcForm() {
  const host = $("pForm");
  const cur = draft || (npcSel ? app.editor.doc.npcs.find((n) => n.id === npcSel) : null);
  if (!cur) {
    host.innerHTML = '<div class="none" style="color:var(--ink2);font-size:13px;'
      + 'padding:60px 0;text-align:center">点左边选一个人，或者点「+ 新增」</div>';
    return;
  }
  const isNew = !!draft;
  const tags = new Set(Array.isArray(cur.traits?.tags) ? cur.traits.tags : []);
  const per = cur.personality || {};
  const looks = PARTS?.looks || [];
  PARTS_LOOK = new Set(looks.map((l) => l.id));

  const curLook = (cur.look || "me");
  // ★ 只要图，不要名字 —— 头像就是头像
  const faceRow = looks.map((l) =>
    '<button data-look="' + l.id + '" title="' + esc(l.name) + '" class="'
    + (curLook === l.id ? "on" : "") + '">'
    + '<img src="/art/portraits/' + l.id + '.svg"></button>').join("");

  // 住所：只显示"现在住哪"，改地址靠【在地图上点】
  const homeNow = cur.home
    ? esc(app.editor.doc.nameOf(cur.home) || cur.home)
      + "　" + (app.editor.doc.residents(cur.home) - 1) + "/" + app.editor.doc.homeCapacity(cur.home)
    : "（没有住处）";

  const perRow = (PARTS?.signals || []).map((s) =>
    '<div class="row"><label>' + (SIGNAL_ZH[s] || s) + '</label>'
    + '<input type="number" step="0.1" min="0" data-per="' + s + '" value="'
    + (per[s] ?? 1) + '"></div>').join("");

  const traitRow = (PARTS?.traits || []).map((x) =>
    '<button data-trait="' + x + '" class="' + (tags.has(x) ? "on" : "") + '">' + x + "</button>").join("");

  host.innerHTML =
    "<h2>" + (isNew ? "新增" : esc(cur.name || "(无名)")) + "</h2>"

    + '<div class="row"><label>头像</label><div class="inline">'
    + '<img class="faceNow" id="pFaceNow" src="/art/portraits/' + curLook + '.svg">'
    + '<button class="ghost" id="pFaceEdit">编辑头像</button></div></div>'
    + (faceRow ? '<div class="row"><label></label>'
        + '<div class="facepop hide" id="pFacePop">' + faceRow + "</div></div>" : "")

    + '<div class="row"><label>姓名</label><div class="inline">'
    + '<input id="pName" type="text" value="' + esc(cur.name || "") + '"'
    + (isNew ? "" : " disabled") + ">"
    + (isNew ? '<button class="ghost" id="pRollName">骰</button>' : "")
    + "</div></div>"

    + '<div class="row"><label>生日</label><div class="inline">'
    + '<input id="pBirth" type="date" value="' + esc(cur.birthday || "") + '"'
    + (isNew ? "" : " disabled") + ">"
    + (isNew ? '<button class="ghost" id="pRollBirth">骰</button>' : "")
    + "</div></div>"

    + '<div class="row"><label>性别</label><div class="inline">'
    + '<select id="pGender"' + (isNew ? "" : " disabled") + ">"
    + (PARTS?.genders || []).map((g) => '<option value="' + g + '"'
        + (cur.gender === g ? " app.selected" : "") + ">"
        + (g === "female" ? "女" : "男") + "</option>").join("")
    + "</select></div></div>"

    + '<div class="row"><label>住所</label><div class="inline">'
    + '<span id="pHomeNow" class="hn">' + homeNow + "</span>"
    + '<button class="ghost" id="pPickHome">地图点选</button>'
    + (cur.home ? '<button class="ghost" id="pClearHome">×</button>' : "")
    + "</div></div>"

    + '<div class="row"><label>角色</label><input id="pRole" type="text" value="'
    + esc(cur.role || "") + '"></div>'
    + '<div class="row"><label>初始钱</label><input id="pMoney" type="number" step="1" value="'
    + (cur.money ?? 100) + '"></div>'

    + '<div class="sec">性格</div>' + perRow
    + '<div class="sec">特性</div><div class="chips" id="pTraits">' + traitRow + "</div>"

    + '<div class="bar2"><button class="primary" id="pSave">'
    + (isNew ? "存进场景" : "保存修改") + "</button>"
    + '<button class="ghost" id="pRandom">随机</button><span class="sp"></span>'
    + (isNew ? "" : '<button class="danger" id="pDel">删掉</button>') + "</div>";

  const pop = $("pFacePop");
  const fe = $("pFaceEdit");
  if (fe) fe.onclick = (e) => {
    e.stopPropagation();
    pop?.classList.toggle("hide");
  };
  for (const b of host.querySelectorAll("#pFacePop button"))
    b.onclick = () => { cur.look = b.dataset.look; renderNpcForm(); };
  for (const b of host.querySelectorAll("#pTraits button"))
    b.onclick = () => {
      const s = new Set(Array.isArray(cur.traits?.tags) ? cur.traits.tags : []);
      if (s.has(b.dataset.trait)) s.delete(b.dataset.trait); else s.add(b.dataset.trait);
      cur.traits = { ...(cur.traits || {}), tags: [...s] };
      renderNpcForm();
    };
  const on = (id, fn) => { const e = $(id); if (e) e.onclick = fn; };
  on("pRollName", () => { cur.name = randName($("pGender").value); renderNpcForm(); });
  on("pRollBirth", () => { cur.birthday = randBirthday(); renderNpcForm(); });
  on("pRandom", () => {
    cur.name = randName($("pGender").value);
    cur.birthday = randBirthday();
    cur.traits = { ...(cur.traits || {}), tags: randTraits() };
    renderNpcForm();
  });
  on("pSave", async () => {
    const spec = {
      name: ($("pName")?.value || cur.name || "").trim(),
      gender: $("pGender").value,
      birthday: ($("pBirth")?.value || cur.birthday || "").trim(),
      home: cur.home || "",
      role: $("pRole").value.trim(),
      money: Number($("pMoney").value) || 0,
      personality: Object.fromEntries([...host.querySelectorAll("[data-per]")]
        .map((e) => [e.dataset.per, Number(e.value) || 1]).filter(([, v]) => v !== 1)),
      traits: cur.traits || {},
      look: cur.look || "me",
      tell_bias: cur.tell_bias ?? 1,
      init: cur.init || {},
    };
    if (isNew && !spec.name) return toast("先填个姓名");
    if (!spec.birthday) spec.birthday = randBirthday();
    app.editor.pushUndo();
    npcSel = app.editor.doc.upsertNpc(spec, isNew ? "" : npcSel);
    draft = null;
    app.editor.doc.dirty = true;
    app.editor.ui.setDirty?.(true);
    renderPeople();
    await app.editor.save();          // ★ 写盘，不然刷新就没了（同建筑面板）
    toast(isNew ? "加上了 " + spec.name : "已保存到 " + (app.editor.name || "场景"));
  });
  on("pPickHome", () => {
    // ★ 在地图上点一个住宅。满了就当场拒绝。
    toast("在地图上点一栋住宅");
    app.editor.pickBuilding((bid) => {
      if (!bid) return toast("那儿没有建筑");
      const r = app.editor.doc.canMoveIn(bid, npcSel || "");
      if (!r.ok) return toast(r.why);
      cur.home = bid;
      renderNpcForm();
      toast("住址 → " + (app.editor.doc.nameOf(bid) || bid) + "（" + (r.used + 1) + "/" + r.cap + "）");
    });
  });
  on("pClearHome", () => { cur.home = ""; renderNpcForm(); });
  on("pDel", () => {
    if (!confirm("真的删掉 " + cur.name + "？")) return;
    app.editor.pushUndo();
    app.editor.doc.removeNpc(npcSel);
    npcSel = ""; draft = null;
    app.editor.ui.setDirty?.(true);
    renderPeople();
  });
}

const randPick = (a) => a[Math.floor(Math.random() * a.length)];
function randName(g) {
  const pool = (PARTS?.given || {})[g === "male" ? "male" : "female"] || [];
  return randPick(PARTS?.surnames?.length ? PARTS.surnames : ["王"])
       + randPick(pool.length ? pool : ["明"]);
}
function randBirthday() {
  const y = 1955 + Math.floor(Math.random() * 45);
  const m = 1 + Math.floor(Math.random() * 12);
  const d = 1 + Math.floor(Math.random() * 28);
  return y + "-" + String(m).padStart(2, "0") + "-" + String(d).padStart(2, "0");
}
function randTraits() {
  const pool = [...(PARTS?.traits || [])];
  const out = [];
  for (let i = 0; i < 2 && pool.length; i++)
    out.push(...pool.splice(Math.floor(Math.random() * pool.length), 1));
  return out;
}
