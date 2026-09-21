// 建筑编辑回归。
//
// 和人物那份一个路子：左边名单、右边详情，**没有"新增"**——房子是在地图上摆的。
// 核心断言还是那两条：
//   ① 表单里每个字段的值 == 场景里那栋楼的值（防「属性值被 HTML 吞掉」那类错）
//   ② 真场景一个字节都不许变
//
// 用法：node tools/cdp.mjs "<url>#editor" 8 --eval-file tools/regress_building.mjs
(async () => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const $ = (id) => document.getElementById(id);
  const e = window.citysim.editor, D = e.doc;
  const log = [], ok = (n, c, d) => log.push(`${c ? "✓" : "✗"} ${n}${d ? "  " + d : ""}`);
  const sceneReal = async () =>
    JSON.stringify(await (await fetch("/api/scene?name=scene.json", { cache: "no-store" })).json());
  const REAL_BEFORE = await sceneReal();

  try {
    $("eModes").querySelector('[data-mode="building"]').click();
    await wait(1800);

    // ① 名单：每栋一个（没有"新增"）
    const items = [...$("bList").children];
    const n = Object.keys(D.buildings).length;
    ok("建筑名单齐全", items.length === n && n > 0, `${n} 栋`);
    ok("没有「新增」（房子只能在地图上摆）", !$("bAdd") && !$("bNew"));

    // ② ★ 表单字段 == 场景里的值
    items[0].click();
    await wait(350);
    const bid = Object.keys(D.buildings)
      .sort((a, b) => D.nameOf(a).localeCompare(D.nameOf(b), "zh"))[0];
    const b = D.buildings[bid], loc = D.meta.locations?.[bid] || {};
    const same = $("bType").value === b.type
      && $("bName").value === (loc.name || D.nameOf(bid))
      && $("bPub").checked === (loc.public === true)
      && $("bForm").innerText.includes(b.size[0].toFixed(1));
    ok("表单字段 == 场景里的值", same,
       `类型=${$("bType").value} 名字=${$("bName").value} 公开=${$("bPub").checked}`);

    // ③ 「里面的东西」
    const inside = (D.meta.entities || []).filter((x) => x.at === bid);
    const rows = $("bForm").querySelectorAll(".things .th").length;
    ok("里面的东西列出来了", rows === Math.max(inside.length, 0) || inside.length === 0,
       `${rows} 行（场景里 ${inside.length} 件）`);
    ok("物品下拉是内核的全表", $("bNewItem").options.length >= 19,
       `${$("bNewItem").options.length} 种`);

    // ④ 改存量 / 售价 → 写回场景
    const withStock = inside.findIndex((x) => x.stock != null);
    if (withStock >= 0) {
      const inp = $("bForm").querySelector('[data-stock="' + withStock + '"]');
      const old = D.meta.entities[D.meta.entities.indexOf(inside[withStock])].stock;
      inp.value = String(old + 7);
      inp.dispatchEvent(new Event("change", { bubbles: true }));
      await wait(200);
      const now = D.meta.entities[D.meta.entities.indexOf(inside[withStock])].stock;
      ok("改存量写回场景", now === old + 7, `${old} → ${now}`);
    } else {
      ok("改存量写回场景", true, "（这栋没有带存量的货，跳过）");
    }

    // ⑤ 放一件 / 拿走一件
    const before = (D.meta.entities || []).filter((x) => x.at === bid).length;
    $("bAddItem").click();
    await wait(300);
    const after = (D.meta.entities || []).filter((x) => x.at === bid).length;
    ok("能往里放一件", after === before + 1, `${before} → ${after}`);
    const delBtn = $("bForm").querySelector("[data-del]");
    if (delBtn) {
      delBtn.click();
      await wait(300);
      const back = (D.meta.entities || []).filter((x) => x.at === bid).length;
      ok("能拿走一件", back === after - 1, `${after} → ${back}`);
    }

    // ⑥ 悬浮 → 高亮整栋 + 亮名字
    items[1].dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
    await wait(300);
    const hl = e.hoverLoc && e.overlay2.children.length >= 1
      && !!e.view._paper?.get("hover:loc");
    ok("悬浮 → 地图高亮整栋 + 亮出名字", !!hl,
       `${D.nameOf(e.hoverLoc)} · 高亮层 ${e.overlay2.children.length}`
       + ` · 牌子「${e.view._paper?.get("hover:loc")?.textContent}」`);
    items[1].dispatchEvent(new MouseEvent("mouseleave", { bubbles: true }));
    await wait(250);
    ok("移开就撤掉", e.hoverLoc === "" && !e.view._paper?.get("hover:loc"));
  } catch (err) {
    log.push("✗ 抛错  " + String((err && err.stack) || err).slice(0, 300));
  }

  ok("真场景 scene.json 一个字节都没变", (await sceneReal()) === REAL_BEFORE);
  return { log };
})()
