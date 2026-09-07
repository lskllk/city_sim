/**
 * worldStore —— world mirror(只存 backend snapshot 提供的世界真值)。
 * snapshot 是 authoritative; 本 store 只是镜像, 不含任何 simulation 逻辑。
 */
import { create } from 'zustand';
import type { CanvasInfo, EntitySnapshot, HelloMessage,
  LocationInfo, NPCSnapshot, Snapshot } from '../protocol/schemas';

interface WorldState {
  entities: Record<string, EntitySnapshot>;
  npcs: Record<string, NPCSnapshot>;
  rooms: Record<string, LocationInfo>;
  canvas: CanvasInfo;
  scenario: string;
  seed: number;
  n_npc: number;
  kb_mode: string;
  signals: string[];
  applySnapshot: (snap: Snapshot) => void;
  initHello: (hello: HelloMessage) => void;
  clearWorld: () => void;
}

function toMap<T extends { id: string }>(arr: T[]): Record<string, T> {
  const out: Record<string, T> = {};
  for (const item of arr) out[item.id] = item;
  return out;
}

export const useWorldStore = create<WorldState>()((set) => ({
  entities: {},
  npcs: {},
  rooms: {},
  canvas: { w: 1280, h: 800 },
  scenario: '',
  seed: 0,
  n_npc: 0,
  kb_mode: '',
  signals: [],

  initHello: (hello) => {
    const locs = hello.locations?.locations ?? {};
    set({
      scenario: hello.scenario,
      seed: hello.seed,
      n_npc: hello.n_npc,
      kb_mode: hello.kb_mode,
      signals: Array.isArray(hello.signals) ? hello.signals : [],
      rooms: locs,
      canvas: hello.locations?.canvas ?? { w: 1280, h: 800 },
    });
  },

  applySnapshot: (snap) => {
    set({
      npcs: toMap(snap.npcs ?? []),
      entities: toMap(snap.entities ?? []),
    });
  },

  clearWorld: () => set({
    entities: {},
    npcs: {},
    rooms: {},
    scenario: '',
    seed: 0,
    n_npc: 0,
    kb_mode: '',
    signals: [],
  }),
}));
