/**
 * App.tsx —— 布局 + WS 生命周期。消息按 kind 分发到 store(事件独立流)。
 */
import { useEffect } from 'react';
import { connect } from '../protocol/websocket';
import { setSender } from '../protocol/commands';
import type { AnyMessage, EventData, HelloMessage, Snapshot } from '../protocol/schemas';
import { applySnapshot } from '../simulation/snapshot';
import { useWorldStore } from '../state/worldStore';
import { useSimulationStore } from '../state/simulationStore';
import { useEventLogStore } from '../state/eventLogStore';
import { WorldView } from '../views/WorldView';
import { Inspector } from '../ui/Inspector/Inspector';

export function App() {
  useEffect(() => {
    const client = connect({
      onStatus: (s) => useSimulationStore.getState().setConnection(s),
      onMessage: (msg: AnyMessage) => dispatch(msg),
    });
    setSender((obj) => { client.send(obj); });
    return () => {
      setSender(null);
      client.close();
    };
  }, []);

  return (
    <div className="app observer">
      <WorldView />
      <Inspector />
    </div>
  );
}

function dispatch(msg: AnyMessage): void {
  try {
    const kind = msg?.kind;
    const payload = msg?.payload as unknown;
    if (kind === 'hello') {
      const h = payload as HelloMessage;
      if (!h || typeof h !== 'object') return;
      useWorldStore.getState().clearWorld();
      useEventLogStore.getState().clearLog();
      useWorldStore.getState().initHello(h);
    } else if (kind === 'snapshot') {
      const snap = payload as Snapshot;
      if (snap && typeof snap.tick === 'number') applySnapshot(snap);
      else console.error('[app] snapshot payload invalid; ignored');
    } else if (kind === 'event') {
      const ev = payload as EventData;
      if (ev && typeof ev === 'object') useEventLogStore.getState().appendEvent(ev);
    } else if (kind === 'reply' || kind === 'pong') {
      // MVP 不主动 query; 应答可忽略
    } else {
      console.warn('[app] unknown message kind:', kind);
    }
  } catch (err) {
    console.error('[app] dispatch error', err);
  }
}
