/**
 * eventLogStore —— 全局 Event Stream(仅 UI 的最近事件列表, 不参与 world truth)。
 */
import { create } from 'zustand';
import type { EventData } from '../protocol/schemas';

export interface EventRow {
  key: string;
  tick: number;
  type: string;
  source: string | null;
  target: string | null;
  raw: EventData;
}

const MAX_ROWS = 300;

interface EventLogState {
  rows: EventRow[];
  appendEvent: (ev: EventData) => void;
  clearLog: () => void;
}

function rowKey(ev: EventData, idx: number): string {
  if (ev.event_id) return ev.event_id;
  return `${ev.tick}:${idx}:${ev.source ?? ev.kind ?? '?'}`;
}

export const useEventLogStore = create<EventLogState>()((set) => ({
  rows: [],
  appendEvent: (ev) => {
    const type = ev.type ?? ev.kind ?? 'unknown';
    set((s) => {
      const row: EventRow = {
        key: rowKey(ev, s.rows.length),
        tick: ev.tick,
        type,
        source: ev.source ?? ev.subject ?? null,
        target: ev.target ?? null,
        raw: ev,
      };
      const rows = [...s.rows, row];
      if (rows.length > MAX_ROWS) rows.splice(0, rows.length - MAX_ROWS);
      return { rows };
    });
  },
  clearLog: () => set({ rows: [] }),
}));
