/**
 * simulationStore —— 模拟时间与控制状态(UI 用); 不含世界真值。
 */
import { create } from 'zustand';
import type { Snapshot } from '../protocol/schemas';

export type ConnectionStatus = 'connecting' | 'open' | 'closed';

interface SimulationState {
  tick: number;
  day: number;
  clock: string;
  speed: string;
  running: boolean;
  tps: number;
  connectionStatus: ConnectionStatus;
  applySnapshot: (snap: Snapshot) => void;
  setConnection: (s: ConnectionStatus) => void;
}

export const useSimulationStore = create<SimulationState>()((set) => ({
  tick: 0,
  day: 1,
  clock: '00:00',
  speed: 'pause',
  running: false,
  tps: 0,
  connectionStatus: 'connecting',

  applySnapshot: (snap) => {
    set({
      tick: snap.tick,
      day: snap.day,
      clock: snap.clock,
      speed: snap.speed,
      running: snap.running,
      tps: snap.tps ?? 0,
    });
  },

  setConnection: (s) => set({ connectionStatus: s }),
}));
