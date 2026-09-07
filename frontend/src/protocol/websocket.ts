/**
 * websocket.ts —— 只管通信: connect / disconnect / reconnect(backoff) / send / parse。
 * 不修改任何 store; 消息交给 onMessage(kind/payload)。
 */
import type { AnyMessage, Envelope } from './schemas';

export type WsStatus = 'connecting' | 'open' | 'closed';

export interface WsHandlers {
  onMessage: (msg: AnyMessage) => void;
  onStatus?: (status: WsStatus) => void;
}

export interface WsClient {
  send: (obj: unknown) => boolean;
  close: () => void;
}

const BASE_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 8000;

/** 默认连接 backend(dev 经 vite 代理 /ws; 可被 VITE_WS_URL 覆盖)。 */
export function defaultWsUrl(): string {
  const override = (import.meta.env.VITE_WS_URL as string | undefined)?.trim();
  if (override) return override;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws`;
}

export function parseMessage(raw: string): AnyMessage | null {
  let obj: unknown;
  try {
    obj = JSON.parse(raw);
  } catch {
    console.error('[ws] malformed JSON message ignored');
    return null;
  }
  if (!obj || typeof obj !== 'object') {
    console.error('[ws] non-object message ignored');
    return null;
  }
  const m = obj as Record<string, unknown>;
  if (typeof m.kind !== 'string') {
    // 兼容极老格式: 按 payload 内含 type 推导 kind
    const legacyType = typeof m.type === 'string' ? (m.type as string) : null;
    if (!legacyType) return null;
    return { kind: legacyType, protocol_version: PROTOCOL_V_ANY, payload: m };
  }
  return {
    kind: m.kind,
    protocol_version: typeof m.protocol_version === 'number'
      ? m.protocol_version : PROTOCOL_V_ANY,
    payload: (m.payload !== undefined ? m.payload : m) as Envelope['payload'],
  } as AnyMessage;
}

const PROTOCOL_V_ANY = -1;

export function connect(opts: {
  url?: string;
  onMessage: (msg: AnyMessage) => void;
  onStatus?: (status: WsStatus) => void;
}): WsClient {
  const url = opts.url ?? defaultWsUrl();
  let ws: WebSocket | null = null;
  let closed = false;
  let timer: number | null = null;

  const emit = (s: WsStatus) => opts.onStatus?.(s);

  function open(): void {
    if (closed) return;
    emit('connecting');
    let sock: WebSocket;
    try {
      sock = new WebSocket(url);
    } catch (err) {
      console.error('[ws] failed to create socket', err);
      scheduleReconnect();
      return;
    }
    ws = sock;

    sock.onopen = () => {
      if (ws !== sock) return; // 已被新连接替换
      emit('open');
    };
    sock.onmessage = (e: MessageEvent) => {
      const msg = parseMessage(String(e.data));
      if (msg) opts.onMessage(msg);
    };
    sock.onerror = () => {
      console.error('[ws] connection error');
    };
    sock.onclose = () => {
      if (ws !== sock) return;
      emit('closed');
      scheduleReconnect();
    };
  }

  let attempt = 0;
  function scheduleReconnect(): void {
    if (closed || timer !== null) return;
    const delay = Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
    attempt += 1;
    timer = window.setTimeout(() => {
      timer = null;
      open();
    }, delay);
  }

  open();

  return {
    send(obj: unknown): boolean {
      if (ws && ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify(obj));
          return true;
        } catch (err) {
          console.error('[ws] send failed', err);
          return false;
        }
      }
      return false;
    },
    close(): void {
      closed = true;
      if (timer !== null) window.clearTimeout(timer);
      if (ws) {
        const s = ws;
        ws = null;
        s.onclose = null;
        try {
          s.close();
        } catch {
          /* ignore */
        }
      }
      emit('closed');
    },
  };
}
