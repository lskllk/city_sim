/**
 * snapshot.ts —— WS snapshot → stores。不做 simulation。
 */
import type { Snapshot } from '../protocol/schemas';
import { useWorldStore } from '../state/worldStore';
import { useSimulationStore } from '../state/simulationStore';

export function applySnapshot(snap: Snapshot): void {
  if (!snap || typeof snap.tick !== 'number') {
    console.error('[snapshot] missing required field tick; ignored');
    return;
  }
  // 只读写当前类型已知字段; snapshot 缺 optional field 不崩溃
  useWorldStore.getState().applySnapshot(snap);
  useSimulationStore.getState().applySnapshot(snap);
}
