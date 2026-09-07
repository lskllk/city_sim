/**
 * WorldView.tsx —— 世界画布 + HUD(时间倍率) + 悬浮对象说明。
 */
import { useEffect, useRef, useState } from 'react';
import { SimulationStage } from '../engine/pixi/SimulationStage';
import { cmd } from '../protocol/commands';
import { useSelectionStore } from '../state/selectionStore';
import { useWorldStore } from '../state/worldStore';
import { useSimulationStore } from '../state/simulationStore';

type Hover = { x: number; y: number; kind: 'npc' | 'entity' | 'location'; id: string } | null;

const TAG_ZH: Record<string, string> = {
  edible: '食物', sleepable: '床铺', toilet: '卫生间', drink: '饮水',
  entertain: '娱乐', consumable: '消耗品', fun: '娱乐', work: '工作台',
};

export function WorldView() {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<SimulationStage | null>(null);
  const [hover, setHover] = useState<Hover>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const stage = new SimulationStage(mount, {
      onPick: (k, id) => useSelectionStore.getState().select(k, id),
    });
    stageRef.current = stage;
    return () => {
      stage.destroy();
      stageRef.current = null;
    };
  }, []);

  const onMove = (ev: React.PointerEvent<HTMLDivElement>) => {
    const mount = mountRef.current;
    const stage = stageRef.current;
    if (!mount || !stage) return;
    const rect = mount.getBoundingClientRect();
    const hit = stage.hoverAt(ev.clientX - rect.left, ev.clientY - rect.top);
    setHover(hit ? { x: ev.clientX - rect.left, y: ev.clientY - rect.top, ...hit } : null);
  };

  return (
    <div className="world-view">
      <div className="world-canvas" ref={mountRef}
           onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      <div className="world-hud">
        <button className="ctl small" onClick={() => stageRef.current?.resetView()}>
          ⊞ Reset View
        </button>
        <SelectedLabel />
        <span className="hud-spacer" />
        <TimeRateControl />
      </div>
      {hover && <HoverTip hover={hover} />}
      <ConnBanner />
    </div>
  );
}

/** 时间倍率接口: 暂停 / 1x / 10x / 100x / 1000x(发后端 set_speed)。 */
function TimeRateControl() {
  const speed = useSimulationStore((s) => s.speed);
  const conn = useSimulationStore((s) => s.connectionStatus);
  const dis = conn !== 'open';
  const rates: Array<[string, string]> = [
    ['pause', '⏸'],
    ['1x', '1x'],
    ['10x', '10x'],
    ['100x', '100x'],
    ['1000x', '1000x'],
  ];
  return (
    <span className="rate-bar">
      {rates.map(([spd, label]) => (
        <button key={spd} className={`ctl small ${speed === spd ? 'active' : ''}`}
                disabled={dis}
                onClick={() => cmd('set_speed', { speed: spd })}>
          {label}
        </button>
      ))}
    </span>
  );
}

function SelectedLabel() {
  const kind = useSelectionStore((s) => s.kind);
  const npcId = useSelectionStore((s) => s.selectedNpcId);
  const locId = useSelectionStore((s) => s.selectedLocationId);
  const entId = useSelectionStore((s) => s.selectedEntityId);
  const name = useSelectedName(kind, npcId, locId, entId);
  return <span className="hud-npc">{name}</span>;
}

function useSelectedName(kind: string | null, npcId: string | null,
  locId: string | null, entId: string | null): string {
  const npc = useWorldStore((s) => (kind === 'npc' && npcId ? s.npcs[npcId] : undefined));
  const loc = useWorldStore((s) => (kind === 'location' && locId ? s.rooms[locId] : undefined));
  const ent = useWorldStore((s) => (kind === 'entity' && entId ? s.entities[entId] : undefined));
  if (npc) return `已选中：${npc.name}`;
  if (loc) return `已选中 地点：${loc.name || locId}`;
  if (ent) return `已选中 物品：${ent.name}`;
  return '点选 NPC / 地点 / 物品';
}

function HoverTip({ hover }: { hover: NonNullable<Hover> }) {
  const lines = useHoverLines(hover);
  if (!lines) return null;
  return (
    <div className="hover-tip" style={{ left: hover.x + 14, top: hover.y + 14 }}>
      {lines.map((l, i) => <div key={i} className={i === 0 ? 'tip-title' : ''}>{l}</div>)}
    </div>
  );
}

function useHoverLines(h: NonNullable<Hover>): string[] | null {
  const ws = useWorldStore.getState();
  const roomName = (id: string): string => ws.rooms[id]?.name ?? id;
  if (h.kind === 'entity') {
    const e = ws.entities[h.id];
    if (!e) return null;
    const tags = (e.tags ?? []).map((t) => TAG_ZH[t] ?? t).join('、') || '物品';
    const lines = [`${e.icon ?? ''} ${e.name}`];
    lines.push(tags);
    if (typeof e.stock === 'number' && e.stock >= 0) lines.push(`库存 ${e.stock}`);
    if (e.claimed_by) lines.push(`使用中`);
    return lines;
  }
  if (h.kind === 'npc') {
    const n = ws.npcs[h.id];
    if (!n) return null;
    return [`${n.name}`, `地点 ${roomName(n.loc)}`];
  }
  return [`${roomName(h.id)}`];
}

function ConnBanner() {
  const status = useSimulationStore((s) => s.connectionStatus);
  if (status === 'open') return null;
  const text = status === 'connecting'
    ? 'Simulation connecting…' : 'Simulation disconnected — 自动重连中';
  return <div className={`conn-banner ${status}`}>{text}</div>;
}
