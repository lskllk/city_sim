#!/usr/bin/env python3
"""tools/run.py —— 一键启动：起后端，等它真的起来了，再开浏览器。

为什么要在 Python 里做而不是写在 .cmd 里：
  · 要**等端口真的在监听**再开浏览器，不然浏览器先开、看到的是"无法访问"，
    用户以为是坏了。cmd 里轮询端口要写成一团乱麻，Python 里是三行。
  · 要判断"是不是已经在跑了" —— 再点一次不应该报错，应该直接开浏览器。
  · 要能读 .env 之类的端口覆盖（以后需要的话）。

用法:
    python tools/run.py                 # 起在 8765，自动开浏览器
    python tools/run.py --port 9000
    python tools/run.py --no-open       # 不开浏览器（跑 CI / 无界面时）
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.25)
        return s.connect_ex((host, port)) == 0


def wait_and_open(url: str, port: int, timeout: float = 20.0) -> None:
    """等端口真的在监听，再开浏览器。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_open(port):
            print(f"\n  ✓ 后端起来了 → {url}\n")
            try:
                webbrowser.open(url)
            except Exception:
                pass                      # 没浏览器就算了，URL 已经打出来了
            return
        time.sleep(0.2)
    print(f"\n  ⚠ 等了 {timeout:.0f} 秒还没起来 —— 看上面的报错。"
          f"手动开：{url}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="citysim 一键启动")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true", help="不自动开浏览器")
    args = ap.parse_args()
    url = f"http://{args.host}:{args.port}/game/"

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=== citysim ===")

    # 已经有人在跑了 → 直接开浏览器，别再起一个（会端口冲突报错，很劝退）
    if port_open(args.port, args.host):
        print(f"  后端已经在 {args.host}:{args.port} 上跑了 —— 直接开浏览器")
        if not args.no_open:
            webbrowser.open(url)
        print(f"  {url}")
        return 0

    # 依赖：没装就说清楚怎么装，别抛一堆 ImportError 让人猜
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as e:
        print(f"\n  ✗ 缺依赖：{e.name}")
        print('    装一下： python -m pip install -e ".[viz]"')
        return 1

    # 让源码目录可导入 —— 没 pip install -e 过也能跑（刚克隆下来就能双击）
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))

    if not args.no_open:
        threading.Thread(target=wait_and_open, args=(url, args.port), daemon=True).start()

    print(f"  起后端 {args.host}:{args.port} …（Ctrl+C 停）")
    print(f"  游戏   {url}")
    print(f"  编辑器 {url}#editor")
    print()
    import uvicorn
    from citysim.game.server import app
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
