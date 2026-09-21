// 人物设计器回归。
//
// ★ 为什么会专门写这一份：这类错【不报错、不白屏】，只是显示得不对 ——
//   最典型的是模板里 value=" 少了闭合引号，后面整段 HTML 被吞进属性值里，
//   人看到的是 `></div><div class=` 这种鬼东西，而控制台一片安静。
//   所以这里的核心断言是：**表单里每个字段的值 == 场景里那个人的值**。
//
// 用法：node tools/cdp.mjs "<url>#editor" 8 --eval-file tools/regress_people.mjs
(async () => {
  const e = window.citysim.editor, el = e.view.el, R = el.getBoundingClientRect();
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const $ = (id) => document.getElementById(id);
  const S = (x, y) => { const p = e.view.screenOf(x, y);
    return { clientX: R.left + p[0], clientY: R.top + p[1] }; };
  const mk = (t, p) => new PointerEvent(t, { bubbles: true, cancelable: true,
    pointerId: 401, isPrimary: true, clientX: p.clientX, clientY: p.clientY,
    button: 0, buttons: t === "pointerup" ? 0 : 1 });
  const log = [], ok = (n, c, d) => log.push(`${c ? "✓" : "✗"} ${n}${d ? "  " + d : ""}`);

  // 真场景不许被这一份测试改动
  const sceneReal = async () =>
    JSON.stringify(await (await fetch("/api/scene?name=scene.json", { cache: "no-store" })).json());
  const REAL_BEFORE = await sceneReal();

  try {
    $("eModes").querySelector('[data-mode="people"]').click();
    await wait(1600);

    // ① 布局：左右固定宽度，中间留给地图；面板在地图名牌之上
    const box = (s) => { const n = document.querySelector(s); const r = n.getBoundingClientRect();
      return { l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width),
               h: Math.round(r.height) }; };
    const L = box(".plist"), F = box(".pform");
    ok("左右固定宽度，中间留给地图", L.w === 214 && F.w === 296 && F.l - L.r > 300,
       `左 ${L.w} · 右 ${F.w} · 中间 ${F.l - L.r}`);
    const mid = document.querySelector(".pform").getBoundingClientRect();
    const top = document.elementFromPoint(mid.left + mid.width / 2, mid.top + 60);
    const onTop = !!(top && $("pForm").contains(top));
    ok("编辑栏在第一图层（没被地图名牌盖住）", onTop,
       `最上层是 ${top ? (top.id || top.className || top.tagName) : "?"} · 面板 z=${getComputedStyle(document.querySelector(".pform")).zIndex}`);

    // ② 名单：头像 + 姓名，固定高度可滚
    const items = [...$("pList").children];
    ok("名单 = 头像 + 姓名（固定高度可滚）",
       items.length >= 1 && items.every((b) => b.querySelector("img"))
       && getComputedStyle($("pList")).overflowY === "auto",
       `${items.length} 条 · 高 ${Math.round($("pList").getBoundingClientRect().height)}`);
    const face = items[0].querySelector("img").getAttribute("src");
    ok("头像能取到（不是 404）", (await fetch(face)).ok, face);

    // ③ ★ 核心：表单里每个字段 == 场景里那个人的值
    items[0].click();
    await wait(350);
    const who = e.doc.npcs[0];
    const got = { name: $("pName").value, birthday: $("pBirth").value,
                  gender: $("pGender").value, money: $("pMoney").value,
                  role: $("pRole").value };
    const same = got.name === (who.name || "") && got.birthday === (who.birthday || "")
      && got.gender === who.gender && got.money === String(who.money ?? 100)
      && got.role === (who.role || "");
    ok("表单字段 == 场景里的值（防「属性值被 HTML 吞掉」）", same,
       JSON.stringify(got));

    // ④ 锁定：编辑时姓名/生日/性别不可改
    ok("编辑时 姓名/生日/性别 锁定",
       $("pName").disabled && $("pBirth").disabled && $("pGender").disabled);

    // ⑤ 头像：默认只显示当前 + 编辑按钮；弹框里只有图
    ok("头像默认只显示当前 + 编辑按钮",
       !!$("pFaceNow") && !!$("pFaceEdit") && $("pFacePop").classList.contains("hide"));
    $("pFaceEdit").click();
    await wait(200);
    const pop = $("pFacePop");
    ok("头像弹框：8 张图、不带名字",
       !pop.classList.contains("hide") && pop.querySelectorAll("img").length === 8
       && pop.innerText.trim() === "", `${pop.querySelectorAll("img").length} 张`);
    pop.children[2].click();
    await wait(250);
    ok("选头像生效", $("pFaceNow").getAttribute("src").includes(pop.children[2].dataset.look),
       $("pFaceNow").getAttribute("src").split("/").pop());

    // ⑥ 住所：地图点选；住满了拒绝
    const homes = Object.keys(e.doc.buildings).filter((b) => e.doc.isHome(b));
    const cap = e.doc.homeCapacity(homes[0]);
    e.doc.npcs.forEach((n, i) => { n.home = i < cap ? homes[0] : homes[1]; });
    items[0].click();
    await wait(300);
    const mover = e.doc.npcs.find((n) => n.home === homes[1]);
    const mi = e.doc.npcs.indexOf(mover);
    $("pList").children[mi].click();
    await wait(300);
    const c0 = e.doc.buildings[homes[0]].center;
    e.view.centerOn(c0[0], c0[1], 2.2);
    await wait(150);
    const dst = S(c0[0], c0[1]);
    $("pPickHome").click();
    await wait(200);
    el.dispatchEvent(mk("pointerdown", dst));
    el.dispatchEvent(mk("pointerup", dst));
    await wait(250);
    ok("住满了 → 拒绝搬入", mover.home !== homes[0],
       `${e.doc.nameOf(homes[0])} ${e.doc.residents(homes[0])}/${cap} · 仍住 ${e.doc.nameOf(mover.home)}`);

    // ⑦ 一键随机 + 存进场景
    $("pAdd").click();
    await wait(300);
    ok("新增 → 空白表单、姓名可填", !$("pName").disabled && $("pName").value === "");
    $("pSave").click();
    await wait(200);
    const n0 = e.doc.npcs.length;
    ok("不填姓名不许存", e.doc.npcs.length === n0);
    $("pRandom").click();
    await wait(300);
    ok("一键随机：姓名 + 生日 + 特性",
       /^[\u4e00-\u9fa5]{2,5}$/.test($("pName").value)
       && /^\d{4}-\d{2}-\d{2}$/.test($("pBirth").value)
       && [...$("pTraits").children].filter((b) => b.classList.contains("on")).length === 2,
       `${$("pName").value} · ${$("pBirth").value} · 特性 ${[...$("pTraits").children].filter((b) => b.classList.contains("on")).length} 个`);
    $("pSave").click();
    await wait(400);
    ok("存进场景", e.doc.npcs.length === n0 + 1, `${n0} → ${e.doc.npcs.length}`);
  } catch (err) {
    log.push("✗ 抛错  " + String((err && err.stack) || err).slice(0, 300));
  }

  log.push(...await checkHover([...$("pList").children]));

  const after = await sceneReal();
  ok("真场景 scene.json 一个字节都没变", after === REAL_BEFORE);
  return { log };
})()

/* ── 悬浮高亮（人物 → 他的住处）───────────────────────────────────────
   ★ 这条是用户点出来的：名单里划过一个名字，地图上要亮起对应的楼。
     没有它的话，名字对得上、但地图上看不到是哪一栋。 */
async function checkHover(npcList) {
  const log = [];
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const e = window.citysim.editor, D = e.doc;
  let idx = 0;
  for (let i = 0; i < D.npcs.length; i++) if (D.npcs[i].home) { idx = i; break; }
  npcList[idx].dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
  await wait(300);
  const on = e.hoverLoc === D.npcs[idx].home && e.overlay2.children.length >= 1
    && !!e.view._paper?.get("hover:loc");
  log.push((on ? "✓" : "✗") + " 人物悬浮 → 地图高亮他的住处  "
    + D.npcs[idx].name + " 住「" + D.nameOf(D.npcs[idx].home) + "」"
    + " · 高亮层 " + e.overlay2.children.length);
  npcList[idx].dispatchEvent(new MouseEvent("mouseleave", { bubbles: true }));
  await wait(250);
  const off = e.hoverLoc === "" && !e.view._paper?.get("hover:loc");
  log.push((off ? "✓" : "✗") + " 移开就撤掉");
  return log;
}
