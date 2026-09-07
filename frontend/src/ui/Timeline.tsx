/**
 * Timeline.tsx —— 第一版只做当前 tick/clock + play/pause/step/speed。无 seek。
 */
import { cmd } from '../protocol/commands';
import { useSimulationStore } from '../state/simulationStore';

export function Timeline() {
  const tick = useSimulationStore((s) => s.tick);
  const day = useSimulationStore((s) => s.day);
  const clock = useSimulationStore((s) => s.clock);
  const speed = useSimulationStore((s) => s.speed);
  const running = useSimulationStore((s) => s.running);
  const conn = useSimulationStore((s) => s.connectionStatus);
  const disabled = conn !== 'open';

  const fmtTick = (t: number): string =>
    `D${Math.floor(t / 1440) + 1} ${String(Math.floor((t % 1440) / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;

  return (
    <div className="timeline">
      <span className="tl-clock mono">{clock}</span>
      <span className="tl-sub mono">Day {day}</span>
      <span className="tl-sub mono">tick {tick}</span>
      <span className="tl-sub mono dim">{fmtTick(tick)}</span>
      <span className="tb-sep" />
      <button className="ctl" disabled={disabled || running}
              onClick={() => cmd('set_speed', { speed: '1x' })}>▶</button>
      <button className="ctl" disabled={disabled || speed === 'pause'}
              onClick={() => cmd('set_speed', { speed: 'pause' })}>⏸</button>
      <button className="ctl" disabled={disabled}
              onClick={() => cmd('step', { ticks: 1 })}>Step +1</button>
      {['1x', '10x', '100x'].map((spd) => (
        <button key={spd} className={`ctl ${speed === spd ? 'active' : ''}`}
                disabled={disabled}
                onClick={() => cmd('set_speed', { speed: spd })}>{spd}</button>
      ))}
    </div>
  );
}
