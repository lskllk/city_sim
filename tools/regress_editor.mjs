// 全量回归：编辑器 + 游戏的每一条约定
(async () => {
  const e = window.citysim.editor, el = e.view.el, R = el.getBoundingClientRect();
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const S = (wx, wy) => { const [x, y] = e.view.screenOf(wx, wy);
    return { clientX: R.left + x, clientY: R.top + y }; };
  const mk = (t, p, id = 21) => new PointerEvent(t, { bubbles: true, cancelable: true,
    pointerId: id, isPrimary: true, clientX: p.clientX, clientY: p.clientY, button: 0,
    buttons: t === "pointerup" ? 0 : 1 });
  async function drag(from, to, steps = 6) {
    const a = S(...from), b = S(...to);
    el.dispatchEvent(mk("pointerdown", a));
    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      el.dispatchEvent(mk("pointermove", { clientX: a.clientX + (b.clientX - a.clientX) * t,
        clientY: a.clientY + (b.clientY - a.clientY) * t }));
      await wait(5);
    }
    el.dispatchEvent(mk("pointerup", b)); await wait(30);
  }
  async function click(at) {
    const p = S(...at);
    el.dispatchEvent(mk("pointerdown", p)); el.dispatchEvent(mk("pointerup", p)); await wait(30);
  }
  const st = () => ({ n: Object.keys(e.doc.nodes).length, ed: Object.keys(e.doc.edges).length,
                      b: Object.keys(e.doc.buildings).length });
  const log = []; const ok = (n, c, d) => log.push(`${c ? "✓" : "✗"} ${n}${d ? "  " + d : ""}`);
  const deg = id => Object.values(e.doc.edges).filter(x => x.a === id || x.b === id).length;

  const s0 = st();
  // 1 平移默认行为
  const c0 = [e.view.cam.x, e.view.cam.y];
  await drag([500, 560], [620, 560]);
  ok("拖空白 = 平移", Math.abs(e.view.cam.x - c0[0]) > 60, `cam.x ${c0[0].toFixed(0)}→${e.view.cam.x.toFixed(0)}`);
  e.view.cam.x = c0[0]; e.view.cam.y = c0[1]; e.view.apply();

  // 2 两点法
  e.setTool("road"); await drag([70, 60], [70, 200]);
  const s1 = st();
  ok("两点法画路（+2 节点 +1 边）", s1.n === s0.n + 2 && s1.ed === s0.ed + 1);

  // 3 未成路不留东西
  const s2 = st(); await drag([70, 120], [70, 120]); const s3 = st();
  ok("未成路不留孤儿节点", s3.n === s2.n && s3.ed === s2.ed);

  // 4 拆边
  e.setTool("road"); const a4 = st(); await drag([70, 140], [200, 140]); const b4 = st();
  ok("起点落在路中段 → 拆边（+2 节点 +2 边）",
     b4.n === a4.n + 2 && b4.ed === a4.ed + 2, `${a4.n}/${a4.ed}→${b4.n}/${b4.ed}`);

  // 5 拖节点带着路走
  e.setTool("select");
  const mid = Object.entries(e.doc.nodes).find(([id, n]) => !n.door_of && deg(id) >= 3);
  if (mid) {
    const before = JSON.stringify(e.doc.edges);
    await drag([...mid[1].xy], [mid[1].xy[0] + 16, mid[1].xy[1] + 8]);
    ok("拖节点，连着它的路跟着动", JSON.stringify(e.doc.edges) !== before, `${mid[0]} 度数 ${deg(mid[0])}`);
  } else ok("拖节点", false, "没有三岔节点");

  // 6 摆房 + 自动贴边
  e.setTool("build", "home_small");
  const s5 = st(); await click([120, 300]); const s6 = st();
  ok("摆房 +1", s6.b === s5.b + 1);
  const nb = Object.keys(e.doc.buildings).pop(), B = e.doc.buildings[nb];
  const rd = e.doc.nearestRoad(B.center);
  ok("落点自动贴到路边", Math.abs(rd.dist - (rd.width / 2 + 0.6)) < 0.35,
     `离中线 ${rd.dist.toFixed(2)} m（路宽 ${rd.width} → 期望 ${(rd.width / 2 + 0.6).toFixed(2)}）`);

  // 7 门即节点
  const door = e.doc.doorWorlds(B)[0].pos;
  const before7 = new Set(Object.keys(e.doc.nodes));
  e.setTool("road"); await drag([door[0], door[1] + 22], [door[0] + 1.2, door[1] + 0.8]);
  // 门要接进路网：要么认领了门上那颗既有节点，要么新画时生成一颗
  const dn = Object.keys(e.doc.nodes).find(n => e.doc.nodes[n].door_of === nb);
  const linked = dn ? Object.values(e.doc.edges)
    .some(ed => ed.a === dn || ed.b === dn) : false;
  ok("门接进路网（door_of + 有边连着）", !!dn && linked,
     dn ? `${dn} door_of=${e.doc.nodes[dn].door_of} 连边=${linked}` : "没有 door_of 节点");

  // 8 挪房子，门节点跟着走
  if (dn) {
    const p0 = [...e.doc.nodes[dn].xy];
    e.setTool("select"); await drag([...B.center], [B.center[0] + 12, B.center[1] + 5]);
    const moved = Math.hypot(e.doc.nodes[dn].xy[0] - p0[0], e.doc.nodes[dn].xy[1] - p0[1]);
    ok("挪房子，门节点跟着走", moved > 4, `${moved.toFixed(1)} m`);
  }

  // 9 删建筑
  e.setTool("erase"); const s7 = st(); await click([...e.doc.buildings[nb].center]); const s8 = st();
  ok("删除建筑 -1", s8.b === s7.b - 1);

  // 10 高亮
  e.setTool("road");
  el.dispatchEvent(mk("pointerdown", S(80, 340)));
  el.dispatchEvent(mk("pointermove", S(170, 340))); await wait(30);
  const hi = e.overlay2.children.length;
  el.dispatchEvent(mk("pointerup", S(170, 340))); await wait(30);
  ok("画路时有落点/捕获高亮", hi >= 2, `${hi} 个图形`);

  // 11 名牌跟着建筑（拖动过程中）
  e.setTool("select");
  const bid = "bld_004", bb = e.doc.buildings[bid], nm = e.doc.nameOf(bid);
  const plate = () => [...document.querySelectorAll("#elabels .plate")]
    .find(x => x.textContent === nm)?.style.transform;
  e.view.cam.k = 1.0; e.redraw();
  const t0 = plate();
  const pa = S(...bb.center), pb = S(bb.center[0] + 18, bb.center[1] + 6);
  el.dispatchEvent(mk("pointerdown", pa));
  for (let i = 1; i <= 5; i++) {
    el.dispatchEvent(mk("pointermove", { clientX: pa.clientX + (pb.clientX - pa.clientX) * i / 5,
      clientY: pa.clientY + (pb.clientY - pa.clientY) * i / 5 })); await wait(6);
  }
  const t1 = plate();
  el.dispatchEvent(mk("pointerup", pb)); await wait(30);
  ok("拖房子时名牌跟着走", t0 !== t1, t0 === t1 ? "没动 ✗" : "");

  // 12 保存
  await e.save();
  ok("保存成功（dirty 清零）", e.doc.dirty === false);

  return { log, 最终: st() };
})()
