/**
 * commands.ts —— 向 backend 发控制/查询命令的单例入口(App 启动时注入 sender)。
 */
type Sender = (obj: unknown) => void;
let sender: Sender | null = null;

export function setSender(fn: Sender | null): void {
  sender = fn;
}

export function send(obj: unknown): boolean {
  if (!sender) return false;
  sender(obj);
  return true;
}

export function cmd(name: string, args: Record<string, unknown> = {}): boolean {
  return send({ name, args, req_id: 0 });
}
