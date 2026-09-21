// 驱动：两点法 / 不留孤儿 / 拆边 / 拖节点 / 吸附 / 高亮
(async () => {
  const e = window.citysim.editor, el = e.view.el, R = el.getBoundingClientRect();
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  const S = (wx, wy) => { const [x, y] = e.view.screenOf(wx, wy); return { clientX: R.left + x, clientY: R.top + y }; };
  const mk = (t, p, id = 7) => new PointerEvent(t, { bubbles: true, cancelable: true,
    pointerId: id, isPrimary: true, clientX: p.clientX, clientY: p.clientY, button: 0,
    buttons: t === "pointerup" ? 0 : 1 });
  async function gesture(from, to, steps = 6, release = true) {
    const a = S(...from), b = S(...to);
    el.dispatchEvent(mk("pointerdown", a));
    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      el.dispatchEvent(mk("pointermove", { clientX: a.clientX + (b.clientX - a.clientX) * t,
        clientY: a.clientY + (b.clientY - a.clientY) * t }));
      await wait(5);
    }
    if (release) el.dispatchEvent(mk("pointerup", b));
    await wait(30);
  }
  const snapStats = () => ({ n: Object.keys(e.doc.nodes).length,
                             ed: Object.keys(e.doc.edges).length,
                             b: Object.keys(e.doc.buildings).length });
  const log = []; const step = (n, ok, d) => log.push(`${ok ? "✓" : "✗"} ${n}${d ? "  " + d : ""}`);

  const s0 = snapStats();

  // ① 两点法：从空白画一条
  e.setTool("road");
  await gesture([70, 60], [70, 190]);
  const s1 = snapStats();
  step("两点法画一条路（+2 节点 +1 边）",
       s1.n === s0.n + 2 && s1.ed === s0.ed + 1, `${s0.n}/${s0.ed} → ${s1.n}/${s1.ed}`);

  // ② 没画成 → 一个节点都不许留下（起点终点同一处）
  const s2 = snapStats();
  await gesture([70, 100], [70, 100]);
  const s3 = snapStats();
  step("未成路不留孤儿节点", s3.n === s2.n && s3.ed === s2.ed,
       `${s2.n}/${s2.ed} → ${s3.n}/${s3.ed}`);

  // ③ 起点落在【既有路的中段】→ 拆成三条路四个节点
  e.setTool("road");
  const before = snapStats();
  await gesture([70, 125], [190, 125]);        // 起点在刚画那条路的中段
  const after = snapStats();
  const n0 = before.n, n1 = after.n, e0 = before.ed, e1 = after.ed;
  step("起点落在路中段 → 拆边：+2 节点 +2 边（原路一分为二 + 新路两端各一个节点）",
       n1 === n0 + 2 && e1 === e0 + 2, `节点 ${n0}→${n1} · 边 ${e0}→${e1}`);

  // ④ 拖节点：连着它的路要跟着动
  e.setTool("select");
  const degree = (id) => Object.values(e.doc.edges)
    .filter(ed => ed.a === id || ed.b === id).length;
  const mid = Object.entries(e.doc.nodes)
    .find(([id, nn]) => !nn.door_of && degree(id) >= 3);
  if (mid) {
    const [nid] = mid;
    const before2 = JSON.stringify(e.doc.edges);
    await gesture([...e.doc.nodes[nid].xy], [e.doc.nodes[nid].xy[0] + 18, e.doc.nodes[nid].xy[1] + 8]);
    step("拖节点，连着它的路跟着动", JSON.stringify(e.doc.edges) !== before2,
         `${nid} 连着 ${Object.values(e.doc.edges).filter(ed => ed.a === nid || ed.b === nid).length} 条路`);
  } else { step("拖节点", false, "找不到三岔节点"); }

  // ⑤ 吸附：落点应该吸到路中线上，而不是鼠标原处
  e.setTool("road");
  const p0 = [70, 300];
  const near = [70.9, 299.4];
  const s = e.doc.snap(near, "");
  step("吸附生效（点飘开也能吸到网格/路上）",
       s.kind !== "free" || Math.abs(s.point[0] % 4) < 0.01 || Math.abs(s.point[1] % 4) < 0.01,
       `kind=${s.kind} point=(${s.point[0]}, ${s.point[1]})`);

  // ⑥ 关掉网络吸附 → 只剩栅格
  e.doc.netSnap = false;
  const s2b = e.doc.snap([70.9, 299.4], "");
  step("关掉网络吸附后只剩栅格", s2b.kind === "free" && s2b.point[0] % 4 === 0,
       `kind=${s2b.kind} point=(${s2b.point[0]}, ${s2b.point[1]})`);
  e.doc.netSnap = true;

  // ⑦ 栅格：整图视角下 4m 只有 7px → 不该画（就是用户说的"不知道干嘛的虚线"）
  e.doc.gridSnap = false; e.redraw();
  const h0 = e.handles.children.length;
  e.doc.gridSnap = true; e.redraw();
  const hLow = e.handles.children.length;
  step("整图视角不画栅格（太密 = 噪声）", hLow === h0, `手柄层 ${h0} → ${hLow} @k=${e.view.cam.k.toFixed(3)}`);
  const k0 = e.view.cam.k;
  e.view.cam.k = 1.0; e.redraw();
  const hHi = e.handles.children.length;
  step("放大后才画栅格", hHi === hLow + 1, `手柄层 ${hLow} → ${hHi} @k=1.0`);
  e.view.cam.k = k0; e.redraw();

  // ⑧ 画路时的高亮：橡皮筋 + 吸附环 + 目标路段
  el.dispatchEvent(mk("pointerdown", S(70, 320)));
  el.dispatchEvent(mk("pointermove", S(160, 320)));
  await wait(30);
  const hi = e.overlay2.children.length;
  step("画路时有高亮（吸附环 / 橡皮筋 / 目标段）", hi >= 2, `高亮层 ${hi} 个图形`);
  el.dispatchEvent(mk("pointerup", S(160, 320)));
  await wait(30);

  return { log, 最终: snapStats(), 起点统计: s0 };
})()
