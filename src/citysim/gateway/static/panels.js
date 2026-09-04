/* panels.js —— 右侧检查器(状态/为什么/知识/事件) + 底部事件流。 */
const Panels = (() => {
  let currentNpc = null, currentTab = "status", detail = null;

  const sigColor = (v) => v > 0.6 ? "good" : v > 0.3 ? "mid" : "bad";

  function sigBar(name, v) {
    const pct = Math.round(Math.max(0, Math.min(1, v)) * 100);
    return `<div class="sig"><span>${name}</span>
      <div class="bar"><div class="fill ${sigColor(v)}" style="width:${pct}%"></div></div>
      <span style="text-align:right">${pct}%</span></div>`;
  }

  function tabStatus(d) {
    let h = `<h3>${d.name} (${d.id}) · ${d.loc}</h3>`;
    h += `<div>活动: <b>${d.activity || "idle"}</b></div>`;
    if (d.intent) h += `<div>意图: ${d.intent.kind} → ${d.intent.target || "—"}</div>
       <div style="color:#9aa">${d.intent.reason || ""}</div>`;
    h += `<h3>信号</h3>` + Object.entries(d.signals).map(([k, v]) => sigBar(k, v)).join("");
    h += `<h3>KB</h3><div class="row"><span>overlay ${(d.kb_counts||{}).overlay}</span>
         <span>tomb ${(d.kb_counts||{}).tombstones}</span>
         <span>原型 ${(d.kb_counts||{}).archetype}</span></div>`;
    return h;
  }

  function factLine(f, kb) {
    const c = { INJECTED: "#9aa", OBSERVED: "#6fdc8c", TOLD: "#7ab3ff", INFERRED: "#e6a94a" }[f.source_kind] || "#888";
    let src = `[${f.source_kind} @t${f.tick}]`;
    const refs = (f.source_ref || []);
    if (refs.length) src += ` 来源: ${refs.map(r => r.startsWith("f:") ? `<span class='kbtn' title='追溯根 ${r}'>← fact ${r}</span>` : `<b>${r} 告知</b>`).join(" ")}`;
    return `<div class="fact" style="border-left-color:${c}">
      <b>${f.subject}</b> ${f.relation} <b>${f.obj}</b> c=${f.confidence}
      <div class="src">${src}</div></div>`;
  }

  function tabWhy(d) {
    const it = d.intent;
    if (!it) return `<p>（尚未决策）</p>`;
    let h = `<div>意图: <b>${it.kind}</b> → ${it.target || "—"}</div>
             <div style="color:#9aa">${it.reason || ""}</div>`;
    if (it.ranked && it.ranked.length) {
      h += `<h3>候选打分</h3>` + it.ranked.map(r =>
        `<div class="row rank"><span style="width:110px">${r.id}</span>
         <div class="sig" style="flex:1"><div class="bar"><div class="fill mid" style="width:${Math.min(100, r.score * 200)}%"></div></div></div>
         <span>${r.score.toFixed(3)}</span></div>`).join("");
    }
    if (it.plan && it.plan.length) h += `<h3>计划</h3><div>${it.plan.join(" → ")}</div>`;
    h += `<h3>依据事实</h3>`;
    if (it.used_facts && it.used_facts.length) {
      h += it.used_facts.map(f => factLine(f)).join("");
    } else {
      h += `<p style="color:#9aa">本次决策未使用知识（视野内直接可见）</p>`;
    }
    return h;
  }

  function tabKb(d) {
    const div = document.createElement("div");
    div.innerHTML = "";
    kbGraph(div, d.kb, d.kb_counts || null, null);
    return div.innerHTML;
  }

  function tabEvents(d) {
    if (!d.events || !d.events.length) return `<p>（暂无事件）</p>`;
    return d.events.map(ev => eventLine(ev)).join("");
  }

  function eventLine(ev) {
    const t = ev.tick;
    const p = ev.payload || {};
    if (ev.kind === "told")
      return `<li class="told">[t${t}] ${ev.subject} 告知 ${p.audience}：${p.subject} ${p.relation} ${p.obj} (${p.conf})</li>`;
    if (ev.kind === "intent_failed")
      return `<li class="intent_failed">[t${t}] ${ev.subject} 失败: ${p.why || ev.target}</li>`;
    if (ev.kind === "interaction_done")
      return `<li class="interaction_done">[t${t}] ${ev.subject} 完成 ${p.entity || ev.target}</li>`;
    if (ev.kind === "decision")
      return `<li class="decision">[t${t}] ${ev.subject} → ${ev.intent} ${ev.target || ""} ${ev.plan ? "(" + ev.plan + ")" : ""}</li>`;
    return `<li>[t${t}] ${ev.subject} ${ev.kind}</li>`;
  }

  function render() {
    const panel = document.getElementById("panel");
    if (!detail) { panel.innerHTML = "<p style='color:#9aa'>点一个小人查看</p>"; return; }
    const tab = currentTab;
    panel.innerHTML = tab === "status" ? tabStatus(detail)
      : tab === "why" ? tabWhy(detail)
      : tab === "kb" ? tabKb(detail)
      : tabEvents(detail);
    // kb tab 需要真实 DOM 挂 SVG/表
    if (tab === "kb") {
      panel.innerHTML = "";
      kbGraph(panel, detail.kb, detail.kb_counts || null);
    }
  }

  function askDetail() {
    if (!currentNpc) return;
    App.query({ what: "npc_detail", npc_id: currentNpc }, (reply) => {
      if (reply && reply.ok) { detail = reply.data; document.getElementById("inspTitle").textContent =
        `${reply.data.name} (${reply.data.id})`; render(); }
    });
  }

  function select(npcId) {
    currentNpc = npcId; detail = null; askDetail();
  }

  return {
    setTab(t) { currentTab = t; render(); },
    select,
    refresh: askDetail,
    eventLine,
  };
})();

// 页签绑定
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    document.querySelectorAll("#tabs button").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    Panels.setTab(b.dataset.tab);
  });
});
