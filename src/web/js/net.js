/** net.js —— WebSocket 客户端。
 *
 * 线上的形状是【信封】：`{kind, protocol_version, payload}` ——
 * 消息类型在 `kind`，数据在 `payload`。这里拆掉信封再交出去，
 * 让上层直接看见 `{type, ...}`（payload 内部自带 `type`，和 kind 同值）。
 *
 * 后端每帧推 snapshot，但**是增量的**：渲染状态没变的人不在帧里，
 * 消失的人放在 `gone` 里。所以这里不做"每帧替换"，只把消息交出去，
 * 由 store.js 负责合并 —— 合并规则是后端契约的一部分，不是前端自由发挥。
 */

export const PROTOCOL = 2;

export class Net {
  /** @param {(msg:object)=>void} onMsg */
  constructor(onMsg) {
    this.onMsg = onMsg;
    this.ws = null;
    this.ready = false;
    this._seq = 0;
    this._pending = new Map();      // req_id -> resolve
    this.lastError = "";
  }

  /** 连上并在拿到 hello 后 resolve。连不上会 reject（主菜单显示红字）。 */
  connect(url = `ws://${location.host}/ws`) {
    return new Promise((resolve, reject) => {
      let settled = false;
      try {
        this.ws = new WebSocket(url);
      } catch (e) {
        reject(new Error("WebSocket 建不起来：" + e.message));
        return;
      }
      const fail = (e) => {
        if (settled) return;
        settled = true;
        this.lastError = e.message || String(e);
        reject(new Error(this.lastError));
      };
      this.ws.onopen = () => { this.ready = true; };
      this.ws.onerror = () => fail(new Error("连不上 " + url + "（后端起了吗？）"));
      this.ws.onclose = (ev) => {
        this.ready = false;
        const why = ev.code === 1006 ? "连不上" : `关掉了（code ${ev.code}）`;
        if (!settled) fail(new Error(`${why}：${url}（后端起了吗？）`));
        else this.onMsg({ type: "__closed" });
      };
      this.ws.onmessage = (ev) => {
        let env;
        try { env = JSON.parse(ev.data); } catch { return; }
        // ★ 信封拆包：kind 是消息类型，payload 才是数据
        const msg = env && env.payload ? { type: env.kind, ...env.payload } : env;
        if (msg.type === "hello") {
          if (env.protocol_version !== PROTOCOL)
            console.warn(`协议版本不一致：后端 ${env.protocol_version} / 前端 ${PROTOCOL}`);
          if (!settled) { settled = true; resolve(msg); }
        }
        const p = this._pending.get(msg.req_id);
        if (p) { this._pending.delete(msg.req_id); p(msg); }
        this.onMsg(msg);
      };
    });
  }

  send(name, args = {}) {
    if (!this.ws || this.ws.readyState !== 1) return Promise.resolve(null);
    const req_id = "r" + (++this._seq);
    return new Promise((res) => {
      this._pending.set(req_id, res);
      // ★ 线上的指令形状是 {name, args, req_id} —— 不是 {type, ...args}
      //   （见 game/commands.py: handle_cmd 读的是 cmd["name"] / cmd["args"]）
      this.ws.send(JSON.stringify({ name, args, req_id }));
      // 后端回 reply；等不到就算了（别把 UI 卡住）
      setTimeout(() => { if (this._pending.delete(req_id)) res(null); }, 4000);
    });
  }

  close() { this.ws?.close(); }
}
