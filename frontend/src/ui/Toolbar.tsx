/**
 * Toolbar.tsx —— 连接/场景/种子/时间/速度控制。只发 backend 命令, 不碰 store 真值。
 */
import { cmd } from '../protocol/commands';
import { useSimulationStore } from '../state/simulationStore';
import { useWorldStore } from '../state/worldStore';

const SPEEDS: Array<[string, string]> = [
  ['1x', '1x'], ['10x', '10x'], ['100x', '100x'], ['1000x', '1000x'],
];

export function Toolbar() {
  const connectionStatus = useSimulationStore((s) => s.connectionStatus);
  const speed = useSimulationStore((s) => s.speed);
  const clock = useSimulationStore((s) => s.clock);
  const tick = useSimulationStore((s) => s.tick);
  const day = useSimulationStore((s) => s.day);
  const scenario = useWorldStore((s) => s.scenario);
  const seed = useWorldStore((s) => s.seed);

  const dotColor = connectionStatus === 'open' ? '#3ddc84'
    : connectionStatus === 'connecting' ? '#f0c35e' : '#e05252';

  const paused = speed === 'pause';

  return (
    <div className="toolbar">
      <span className="tb-conn" title={connectionStatus}>
        <span className="conn-dot" style={{ background: dotColor }} />
        {connectionStatus === 'open' ? '已连接' : connectionStatus === 'connecting' ? '连接中' : '已断开'}
      </span>
      <span className="tb-sep" />
      <span className="tb-label">场景</span>
      <span className="tb-value mono">{scenario || '—'}</span>
      <span className="tb-label">Seed</span>
      <span className="tb-value mono">{seed ?? '—'}</span>
      <span className="tb-label">Day</span>
      <span className="tb-value mono">{day}</span>
      <span className="tb-label">Clock</span>
      <span className="tb-value mono">{clock}</span>
      <span className="tb-label">Tick</span>
      <span className="tb-value mono">{tick}</span>
      <span className="tb-sep" />
      <button className="ctl" disabled={connectionStatus !== 'open' || paused}
              onClick={() => cmd('set_speed', { speed: '1x' })} title="播放(1x)">
        ▶ Play
      </button>
      <button className="ctl" disabled={connectionStatus !== 'open'}
              onClick={() => cmd('set_speed', { speed: 'pause' })} title="暂停">
        ⏸ Pause
      </button>
      <button className="ctl" disabled={connectionStatus !== 'open'}
              onClick={() => cmd('step', { ticks: 1 })} title="单步 1 tick">
        ⏭ Step
      </button>
      {SPEEDS.map(([spd, label]) => (
        <button key={spd}
                className={`ctl ${speed === spd ? 'active' : ''}`}
                disabled={connectionStatus !== 'open'}
                onClick={() => cmd('set_speed', { speed: spd })}>
          {label}
        </button>
      ))}
      <span className="tb-spacer" />
      <button className="ctl danger" disabled={connectionStatus !== 'open'}
              onClick={() => cmd('reset', {})} title="重置模拟(seed/scenario 由 backend 保持)">
        ⟳ Reset
      </button>
    </div>
  );
}
