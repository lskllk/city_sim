/**
 * EventStream.tsx —— 全局事件流。点击: 选中事件; 若 source 是 NPC 则尝试定位。
 */
import { useEffect, useRef, useState } from 'react';
import type { EventRow } from '../state/eventLogStore';
import { useEventLogStore } from '../state/eventLogStore';
import { useWorldStore } from '../state/worldStore';
import { useSelectionStore } from '../state/selectionStore';

const TYPE_ZH: Record<string, string> = {
  decision: '决策', perceived: '感知', learned: '学习', told: '传闻',
  bought: '购买', interaction_done: '完成', intent_failed: '失败',
  stock_changed: '补货', npc_died: '死亡',
};

function nameOf(id: string | null | undefined): string {
  if (!id) return '—';
  const ws = useWorldStore.getState();
  return ws.npcs[id]?.name ?? ws.entities[id]?.name ?? ws.rooms[id]?.name ?? id;
}

function targetText(payload: Record<string, unknown>, target?: string | null): string {
  return nameOf(target ?? (typeof payload.target === 'string' ? payload.target : undefined));
}

function summarize(row: EventRow): string {
  const p = row.raw.payload ?? {};
  const who = nameOf(row.source);
  switch (row.type) {
    case 'decision': {
      const intent = String(row.raw.intent ?? row.raw.kind ?? 'idle');
      const t = row.target ? ` ${targetText(p, row.target)}` : '';
      return `${who} 决定 ${intent}${t}`;
    }
    case 'perceived': {
      const obs = Array.isArray(p.observed_entity_ids) ? (p.observed_entity_ids as unknown[]).length : 0;
      return `${who} 感知到 ${obs} 个实体`;
    }
    case 'learned': {
      const sub = nameOf(String(p.subject ?? ''));
      const rel = String(p.relation ?? '');
      const obj = String(p.obj ?? '');
      const kind = String(p.source_kind ?? '');
      return `${who} 学到 ${sub} ${rel} ${obj} [${kind}]`;
    }
    case 'told': {
      const aud = Array.isArray(p.audience)
        ? (p.audience as unknown[]).map((x) => nameOf(String(x))).join('、')
        : '';
      const short = typeof p.short === 'string' ? p.short : '';
      return `${who} 告诉 ${aud || '—'}：${short || `${String(p.subject ?? '')} ${String(p.relation ?? '')} ${String(p.obj ?? '')}`}`;
    }
    case 'bought':
      return `${who} 购买 ${nameOf(String(p.item ?? row.target ?? ''))} ¥${Number(p.price ?? 0).toFixed(1)}`;
    case 'interaction_done':
      return `${who} 完成 ${targetText(p, row.target ?? (typeof p.entity === 'string' ? p.entity : undefined))}`;
    case 'intent_failed':
      return `${who} 想${String(p.intent ?? row.raw.intent ?? '')}${targetText(p, row.target)}：${String(p.why ?? '未遂')}`;
    case 'stock_changed':
      return `${nameOf(row.source)} 库存 ${String(p.stock_before ?? '?')} → ${String(p.stock_after ?? '?')}`;
    case 'npc_died':
      return `${who} 死亡`;
    default:
      return `${who} ${row.type} ${JSON.stringify(p)}`;
  }
}

const FILTERS: Array<[string, string]> = [
  ['all', '全部'],
  ['decision', '决策'],
  ['perceived', '感知'],
  ['learned', '学习'],
  ['told', '传闻'],
  ['intent_failed', '失败'],
  ['bought', '购买'],
];

export function EventStream() {
  const rows = useEventLogStore((s) => s.rows);
  const [filter, setFilter] = useState('all');
  const selEvent = useSelectionStore((s) => s.selectedEventId);

  const shown = (filter === 'all' ? rows : rows.filter((r) => r.type === filter))
    .slice(-200);
  const listRef = useRef<HTMLUListElement | null>(null);

  useEffect(() => {
    // 定位到被选中事件(如 CurrentBehavior 的 View event)
    if (!selEvent) return;
    const el = listRef.current?.querySelector(`[data-key="${CSS.escape(selEvent)}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [selEvent]);

  const onRowClick = (row: EventRow) => {
    const sel = useSelectionStore.getState();
    sel.selectEvent(row.key);
    const ws = useWorldStore.getState();
    if (row.source && ws.npcs[row.source]) {
      sel.select('npc', row.source);
    }
    // source 不是 NPC: 不报错, 只选中事件
  };

  return (
    <div className="event-stream">
      <div className="panel-head">
        <span>Event Stream</span>
        <span className="filters">
          {FILTERS.map(([k, zh]) => (
            <button key={k} className={`chip ${filter === k ? 'active' : ''}`}
                    onClick={() => setFilter(k)}>{zh}</button>
          ))}
        </span>
      </div>
      <ul className="ev-list" ref={listRef}>
        {shown.length === 0 && <li className="ev-empty">暂无事件</li>}
        {shown.map((row) => (
          <li key={row.key} data-key={row.key}
              className={`ev-row t-${row.type} ${selEvent === row.key ? 'sel' : ''}`}
              onClick={() => onRowClick(row)}>
            <span className="ev-tick mono">#{row.tick}</span>
            <span className="ev-type">{TYPE_ZH[row.type] ?? row.type}</span>
            <span className="ev-text">{summarize(row)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
