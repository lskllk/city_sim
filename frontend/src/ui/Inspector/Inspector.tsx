/**
 * Inspector.tsx —— 最小 Observer Inspector(单一实体检查器)。
 * 四区: Status / Decision / Cognitive Memory / Event Log。
 * 只读展示选中实体的已有数据; 不控制 simulation。
 */
import type { ReactNode } from 'react';
import { useWorldStore } from '../../state/worldStore';
import { useSelectionStore } from '../../state/selectionStore';
import type { KbEdge, NPCSnapshot } from '../../protocol/schemas';

const SIG_ZH: Record<string, string> = {
  energy: '精力', hunger: '饥饿', thirst: '口渴', bladder: '如厕',
  fun: '娱乐', hp: '生命',
};
const EVENT_ZH: Record<string, string> = {
  decision: '决策', perceived: '感知', learned: '学习', told: '传闻',
  bought: '购买', interaction_done: '完成', intent_failed: '失败',
  npc_died: '死亡', stock_changed: '补货',
};

export function Inspector() {
  const kind = useSelectionStore((s) => s.kind);
  const npcId = useSelectionStore((s) => s.selectedNpcId);
  const locId = useSelectionStore((s) => s.selectedLocationId);
  const entId = useSelectionStore((s) => s.selectedEntityId);
  const ws = useWorldStore();

  if (!kind || kind === null) {
    return <aside className="inspector"><div className="insp-empty">
      城市观察窗<br /><span>点选 NPC / 物件 / 建筑查看</span></div></aside>;
  }
  if (kind === 'npc' && npcId) {
    const n = ws.npcs[npcId];
    if (n) return <NpcInspector npc={n} />;
  }
  if (kind === 'entity' && entId) {
    const e = ws.entities[entId];
    if (e) return <EntityInspector id={entId} />;
  }
  if (kind === 'location' && locId) {
    return <LocationInspector id={locId} />;
  }
  return <aside className="inspector"><div className="insp-empty">未找到</div></aside>;
}

function NpcInspector({ npc }: { npc: NPCSnapshot }) {
  const room = useWorldStore((s) => s.rooms[npc.loc]);
  const signals = npc.signals ?? {};
  const order = ['energy', 'hunger', 'thirst', 'bladder', 'fun', 'hp'];
  const keys = order.filter((k) => k in signals)
    .concat(Object.keys(signals).filter((k) => !order.includes(k)));
  const ranked = uniqueByMax(npc.intent?.ranked ?? []);
  const kb: KbEdge[] = npc.kb?.edges ?? [];
  const events = [...(npc.events ?? [])].reverse().slice(0, 15);

  return (
    <aside className="inspector">
      <header className="insp-head">{npc.name}
        <span className="muted">{room?.name ?? npc.loc} · {npc.act_class || npc.activity}</span>
      </header>

      <InspSection title="Status">
        {keys.map((k) => {
          const v = Math.max(0, Math.min(1, Number(signals[k] ?? 0)));
          return (
            <div className="sig-row" key={k}>
              <span className="sig-name">{SIG_ZH[k] ?? k}</span>
              <div className="sig-bar"><div className="sig-fill"
                style={{ width: `${v * 100}%`, background: barColor(v) }} /></div>
              <span className="sig-val mono">{Math.round(v * 100)}%</span>
            </div>
          );
        })}
        {keys.length === 0 && <div className="muted">—</div>}
      </InspSection>

      <InspSection title="候选排名 · 实时">
        {ranked.length === 0 ? <div className="muted">暂无候选(该 NPC 还没决策)</div> : (
          <ol className="cand-list">
            {ranked.slice(0, 8).map((r, idx) => {
              const top = ranked[0].score || 1;
              const pct = Math.max(0, Math.min(100, Math.round((r.score / top) * 100)));
              const chosen = idx === 0 && npc.intent?.target === r.id;
              return (
                <li key={r.id} className={`cand-row ${idx === 0 ? 'top' : ''} ${chosen ? 'chosen' : ''}`}>
                  <span className="cand-rank mono">{idx + 1}</span>
                  <span className="cand-name">{resolveName(r.id)}</span>
                  <span className="cand-bar"><span className="cand-fill"
                    style={{ width: `${pct}%`, background: idx === 0 ? '#5bb0ff' : '#2c3c52' }} /></span>
                  <span className="cand-score mono">{r.score.toFixed(3)}</span>
                </li>
              );
            })}
          </ol>
        )}
      </InspSection>

      <InspSection title="Cognitive Memory">
        {kb.length === 0 ? <div className="muted">空</div> : (
          <ul className="kb-list">
            {kb.slice(0, 40).map((e, i) => (
              <li key={`${e.src}${e.relation}${e.dst}${i}`} className="mem-row">
                <span className={`src-chip k-${e.source_kind}`}>{e.source_kind}</span>
                <span className="mono">{resolveName(e.src)} {e.relation} {String(e.dst)}</span>
                <span className="mono dim">c={e.confidence.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        )}
      </InspSection>

      <InspSection title="Event Log">
        {events.length === 0 ? <div className="muted">暂无</div> : (
          <ul className="ev-list mini">
            {events.map((ev) => (
              <li key={String(ev.event_id ?? ev.tick)} className="ev-row">
                <span className="ev-tick mono">#{ev.tick}</span>
                <span className="ev-type">{EVENT_ZH[ev.kind ?? ev.type ?? ''] ?? ev.kind ?? ev.type}</span>
                <span className="ev-text">{oneLine(ev)}</span>
              </li>
            ))}
          </ul>
        )}
      </InspSection>
    </aside>
  );
}

function EntityInspector({ id }: { id: string }) {
  const e = useWorldStore((s) => s.entities[id]);
  const loc = useWorldStore((s) => (e ? s.rooms[e.loc] : undefined));
  const user = useWorldStore((s) => (e?.claimed_by ? s.npcs[e.claimed_by] : undefined));
  if (!e) return <aside className="inspector"><div className="muted">物件不存在</div></aside>;
  return (
    <aside className="inspector">
      <header className="insp-head">{e.name}
        <span className="muted">物件 · {loc?.name ?? e.loc}</span></header>
      <InspSection title="Status">
        <Kv k="类型" v={e.tags?.join(' / ') || '—'} />
        <Kv k="库存" v={String(e.stock ?? '—')} />
        <Kv k="使用中" v={user ? `${user.name}` : (e.claimed_by ? e.claimed_by : '否')} />
      </InspSection>
      <InspSection title="Decision"><div className="muted">物件无决策</div></InspSection>
      <InspSection title="Cognitive Memory"><div className="muted">无</div></InspSection>
      <InspSection title="Event Log"><div className="muted">暂无</div></InspSection>
    </aside>
  );
}

function LocationInspector({ id }: { id: string }) {
  const room = useWorldStore((s) => s.rooms[id]);
  const nNpc = useWorldStore((s) => Object.values(s.npcs).filter((n) => n.loc === id).length);
  const nEnt = useWorldStore((s) => Object.values(s.entities).filter((x) => x.loc === id).length);
  if (!room) return <aside className="inspector"><div className="muted">建筑不存在</div></aside>;
  return (
    <aside className="inspector">
      <header className="insp-head">{room.name || id}
        <span className="muted">建筑</span></header>
      <InspSection title="Status">
        <Kv k="NPC" v={String(nNpc)} />
        <Kv k="物件" v={String(nEnt)} />
      </InspSection>
      <InspSection title="Decision"><div className="muted">建筑无决策</div></InspSection>
      <InspSection title="Cognitive Memory"><div className="muted">无</div></InspSection>
      <InspSection title="Event Log"><div className="muted">暂无</div></InspSection>
    </aside>
  );
}

function InspSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="insp-sec">
      <div className="insp-sec-head">{title}</div>
      {children}
    </section>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return <div className="kv"><span>{k}</span><span className="mono">{v}</span></div>;
}

function oneLine(ev: { kind?: string; type?: string; intent?: string; target?: string | null;
  payload?: Record<string, unknown> }): string {
  const p = ev.payload ?? {};
  switch (ev.kind ?? ev.type) {
    case 'decision': return `决定 ${String(ev.intent ?? '')}${ev.target ? ` → ${ev.target}` : ''}`;
    case 'perceived': {
      const n = Array.isArray(p.observed_entity_ids) ? (p.observed_entity_ids as unknown[]).length : 0;
      return `感知 ${n} 物件`;
    }
    case 'learned': return `学到 ${String(p.subject ?? '')} ${String(p.relation ?? '')} ${String(p.obj ?? '')}`;
    case 'interaction_done': return `完成 ${String(p.entity ?? '')}`;
    case 'intent_failed': return `未遂：${String(p.why ?? '')}`;
    case 'bought': return `购买 ${String(p.item ?? '')}`;
    case 'told': return `传闻：${typeof p.short === 'string' ? p.short : ''}`;
    default: return '';
  }
}

function resolveName(id: string): string {
  const ws = useWorldStore.getState();
  return ws.entities[id]?.name ?? ws.npcs[id]?.name ?? ws.rooms[id]?.name ?? id;
}

function barColor(v: number): string {
  if (v < 0.25) return '#e05252';
  if (v < 0.5) return '#e8a34d';
  return '#3ddc84';
}

/** 候选去重: 同 id 保留最高分(ranked 按 affords 事实逐条生成会重复)。 */
function uniqueByMax(rows: Array<{ id: string; score: number }>):
Array<{ id: string; score: number }> {
  const best = new Map<string, number>();
  for (const r of rows) {
    const prev = best.get(r.id);
    if (prev === undefined || r.score > prev) best.set(r.id, r.score);
  }
  return [...best.entries()]
    .map(([id, score]) => ({ id, score }))
    .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
}
