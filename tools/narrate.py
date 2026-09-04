"""narrate —— 把事件流翻译成人话(testm5 第五节, 供人工 review)。

用法: python tools/narrate.py --days 3 [--npc 王二]
输入: 一份回放日志(tools 场景 log=True 的 log_lines)
输出: 逐条可读叙事。每次 move_to 都应能用一句话解释(因为看见/听说 X)。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def _clock(tick: int) -> str:
    day = tick // 1440 + 1
    hh, mm = (tick % 1440) // 60, (tick % 1440) % 60
    return f"[d{day} {hh:02d}:{mm:02d}]"


def narrate(lines: list[str], npc_filter: str | None = None) -> list[str]:
    out = []
    for line in lines:
        parts = line.split("\t")
        kind = parts[0]
        if kind == "D":
            tick, pid, itype, target, plan = (int(parts[1]), parts[2],
                                              parts[3], parts[4], parts[5])
            name = pid
            if npc_filter and npc_filter not in pid and npc_filter not in name:
                continue
            if itype == "move_to":
                out.append(f"{_clock(tick)} {name} 前往 {target}")
            elif itype == "interact":
                where = f"使用 {target}"
                if plan:
                    where += f" (计划: {plan.replace(',', '→')})"
                out.append(f"{_clock(tick)} {name} {where}")
            elif itype == "idle":
                out.append(f"{_clock(tick)} {name} 闲着")
        elif kind == "E":
            tick = int(parts[1])
            ekind, subj, payload = parts[2], parts[3], parts[4]
            if ekind == "intent_failed":
                out.append(f"{_clock(tick)} {subj} 扑空/失败 {payload}")
            elif ekind == "interaction_done":
                ent = payload.split("entity=")[-1]
                out.append(f"{_clock(tick)} {subj} 完成 {ent}")
            elif ekind == "told":
                kv = dict(p.split("=", 1) for p in payload.split(";")
                          if "=" in p)
                recv = kv.get("audience", "?")
                out.append(
                    f"{_clock(tick)} {subj} 遇 {recv} → 告知 "
                    f"{kv.get('subject')} {kv.get('relation')} {kv.get('obj')}"
                    f" (信度 {kv.get('conf')})")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True, help="回放日志文件路径")
    ap.add_argument("--npc", default=None)
    ap.add_argument("--tail", type=int, default=200)
    a = ap.parse_args()
    lines = Path(a.log).read_text(encoding="utf-8").splitlines()
    for l in narrate(lines, a.npc)[-a.tail:]:
        print(l)
