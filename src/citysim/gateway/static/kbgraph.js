/* kbgraph.js —— SVG 二分图: subject(左列)/obj(右列), 边色=来源, 边宽=confidence。 */
function kbGraph(container, kb, counts, onClickFact) {
  container.innerHTML = "";
  if (!kb || !kb.edges || kb.edges.length === 0) {
    container.innerHTML = "<p style='color:#9aa'>（无知识事实）</p>";
    return;
  }
  if (counts) {
    const h = document.createElement("div");
    h.className = "row";
    h.innerHTML = `<span>overlay <b>${counts.overlay}</b></span>
      <span>tombstones <b>${counts.tombstones}</b></span>
      <span>archetype <b>${counts.archetype}</b></span>`;
    container.appendChild(h);
  }
  const color = { INJECTED: "#9aa", OBSERVED: "#6fdc8c", TOLD: "#7ab3ff", INFERRED: "#e6a94a" };
  // 去重节点集合
  const subs = [], objs = [], seenS = new Set(), seenO = new Set();
  const table = document.createElement("table");
  table.className = "kbt";
  const thead = "<tr><th>subject</th><th>关系</th><th>obj</th><th>conf</th><th>来源</th><th>tick</th></tr>";
  let body = thead;
  for (const e of kb.edges) {
    const c = color[e.source_kind] || "#888";
    const conf = Number(e.confidence || 0).toFixed(2);
    body += `<tr data-s="${e.src}" data-r="${e.relation}" data-o="${e.dst}">
      <td>${e.src}</td><td>${e.relation}</td><td>${e.dst}</td>
      <td style="width:70px"><div class="sig"><div class="bar"><div class="fill mid" style="width:${conf * 100}%"></div></div></div></td>
      <td><span class="dot" style="background:${c}"></span> ${e.source_kind}</td>
      <td>${e.tick ?? ""}</td></tr>`;
    if (!seenS.has(String(e.src))) { seenS.add(String(e.src)); subs.push(String(e.src)); }
    if (!seenO.has(String(e.dst))) { seenO.add(String(e.dst)); objs.push(String(e.dst)); }
  }
  table.innerHTML = body;
  container.appendChild(table);
  // SVG 二分图
  const W = 300, H = 240;
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.classList.add("kb");
  const left = 70, right = W - 70;
  const sy = (i, n) => (n === 1 ? H / 2 : 24 + (i * (H - 48)) / (n - 1));
  for (const e of kb.edges) {
    const xi = subs.indexOf(String(e.src)), xo = objs.indexOf(String(e.dst));
    const y1 = sy(xi, subs.length), y2 = sy(xo, objs.length);
    const line = document.createElementNS(svgNS, "line");
    line.setAttribute("x1", left); line.setAttribute("y1", y1);
    line.setAttribute("x2", right); line.setAttribute("y2", y2);
    line.setAttribute("stroke", color[e.source_kind] || "#888");
    line.setAttribute("stroke-width", 1 + 3 * (e.confidence || 0));
    svg.appendChild(line);
  }
  const node = (x, y, label) => {
    const g = document.createElementNS(svgNS, "g");
    g.setAttribute("class", "knode");
    const r = document.createElementNS(svgNS, "rect");
    r.setAttribute("x", x - 60); r.setAttribute("y", y - 9);
    r.setAttribute("width", 120); r.setAttribute("height", 18);
    r.setAttribute("rx", 4); r.setAttribute("fill", "#1e222b"); r.setAttribute("stroke", "#555");
    const t = document.createElementNS(svgNS, "text");
    t.setAttribute("x", x); t.setAttribute("y", y + 4);
    t.setAttribute("text-anchor", "middle"); t.setAttribute("fill", "#dfe3ea");
    t.setAttribute("font-size", "11");
    t.textContent = String(label);
    g.appendChild(r); g.appendChild(t);
    return g;
  };
  subs.forEach((s, i) => svg.appendChild(node(left, sy(i, subs.length), s)));
  objs.forEach((o, i) => svg.appendChild(node(right, sy(i, objs.length), o)));
  container.appendChild(svg);
  if (onClickFact) {                       // g5-life 07: who_knows 高亮入口
    table.style.cursor = "pointer";
    table.addEventListener("click", (ev) => {
      const tr = ev.target.closest("tr");
      if (tr && tr.dataset.s !== undefined)
        onClickFact(tr.dataset.s, tr.dataset.r, tr.dataset.o);
    });
  }
}
