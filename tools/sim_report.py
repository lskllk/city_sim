"""sim_report —— 把【任意场景】无头跑 N 天, 出一份"这城市能不能活"的报告。

用法:
    python tools/sim_report.py                          # config/scenes/scene.json, 30 天
    python tools/sim_report.py config/scenes/x.json 60  # 指定场景/天数

看四件事:
  1 生死   谁死了、死在第几天、死前 hunger/钱/在哪
  2 钱往哪走 公司: 收入(零售) / 支出(工资+进货) / 期末现金; 居民: 期初→期末
  3 货往哪走 每个实体的库存 期初→期末(有没有"死库存吃完就没了")
  4 行为   活动次数直方图 + 每人 hunger==0 的最长连续时长(隐性饿肚子)

退出码: 有人死 / 有公司破产 → 1 (可直接当 CI 门禁)。
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from citysim.core.config import load_config                      # noqa: E402
from citysim.gateway.scenarios import load_scene                  # noqa: E402
from citysim.sim.loop import run_tick                             # noqa: E402
from citysim.world.engine import act_class_of                     # noqa: E402


def main(scene: str = "config/scenes/scene.json", days: int = 30) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cfg = load_config("config/sim.toml")
    world, systems, rng = load_scene(scene)
    ticks = days * 1440

    # --- 期初快照 ---------------------------------------------------------
    cash0 = {cid: c.cash for cid, c in world.companies.items()}
    money0 = {pid: p.money for pid, p in world.npcs.items()}
    stock0 = {e.entity_id: e.stock for e in world.entities.values()}
    alive = set(world.npcs)
    last: dict[str, dict] = {pid: {} for pid in world.npcs}
    deaths: list[tuple[int, str, dict]] = []

    flow = collections.Counter()          # 全城现金流(按公司无关, 先记总量)
    by_kind = collections.Counter()
    span = collections.Counter()          # 活动: 人·tick
    zero_run = {pid: [0, 0] for pid in world.npcs}   # [当前连续, 最长连续] hunger==0
    money_min = dict(money0)

    orig_publish = world.bus.publish

    def hook(ev) -> None:                 # 只读监听, 不改世界
        by_kind[ev.kind] += 1
        p = ev.payload
        if ev.kind == "wage_paid":
            flow["wage_out"] += float(p.get("wage", 0) or 0)
        elif ev.kind == "wage_failed":
            flow["wage_FAILED"] += float(p.get("wage", 0) or 0)
        elif ev.kind == "bought":
            flow["retail_in"] += float(p.get("price", 0) or 0)
        elif ev.kind == "restocked" and p.get("cost"):
            flow["wholesale_out"] += float(p.get("cost", 0) or 0)
        orig_publish(ev)

    world.bus.publish = hook

    for t in range(1, ticks + 1):
        run_tick(world, systems, cfg, rng)
        for pid in sorted(world.npcs):
            span[act_class_of(world, systems, pid)] += 1
        for pid in list(alive):
            if pid in world.npcs:
                p = world.npcs[pid]
                last[pid] = {"hun": p.signals.get("hunger"), "hp": p.signals.get("hp"),
                             "money": p.money, "loc": world.loc_of(pid)}
                money_min[pid] = min(money_min.get(pid, p.money), p.money)
                run = zero_run[pid]
                run[0] = run[0] + 1 if (p.signals.get("hunger") or 0) <= 0.0 else 0
                run[1] = max(run[1], run[0])
            else:
                deaths.append((t, pid, dict(last[pid])))
                alive.discard(pid)

    # --- 报告 -------------------------------------------------------------
    print("=" * 78)
    print("场景 %s | %d 天(%d tick) | 居民 %d" % (scene, days, ticks, len(money0)))
    print("=" * 78)

    print("\n【1 生死】")
    if not deaths:
        print("  无死亡 ✔")
    for t, pid, d in deaths:
        print("  ✘ D%d  %-16s 死前 hunger=%.2f hp=%.2f 钱=¥%.0f 位置=%s"
              % (t // 1440, pid, d.get("hun", -1), d.get("hp", -1),
                 d.get("money", -1), d.get("loc", "")))
    print("  存活 %d/%d" % (len(alive), len(money0)))

    print("\n【2 钱往哪走】")
    print("  全城流水: 零售收入 ¥%.0f | 工资发出 ¥%.0f | 进货支出 ¥%.0f | 工资发不出 ¥%.0f"
          % (flow["retail_in"], flow["wage_out"], flow["wholesale_out"],
             flow["wage_FAILED"]))
    for cid in sorted(world.companies):
        c = world.companies[cid]
        flag = "  ← 破产(发不出工资!)" if c.cash < 1 else ""
        print("  公司 %-14s ¥%8.0f → ¥%8.0f  (Δ%+.0f)%s"
              % (cid, cash0[cid], c.cash, c.cash - cash0[cid], flag))
    print("  居民:")
    for pid in sorted(money0):
        if pid not in world.npcs:
            print("    %-16s ¥%6.0f → 死了" % (pid, money0[pid]))
            continue
        p = world.npcs[pid]
        print("    %-16s ¥%6.0f → ¥%6.0f (最低¥%.0f)  饥饿0最长%.1f天"
              % (pid, money0[pid], p.money, money_min[pid],
                 zero_run[pid][1] / 1440.0))

    print("\n【3 货往哪走】(期初 → 期末)")
    for eid in sorted(stock0):
        if eid not in world.entities:
            print("    %-20s %5d → 没了" % (eid, stock0[eid]))
        else:
            e = world.entities[eid]
            if e.stock != stock0[eid]:
                print("    %-20s %5d → %5d  %s" % (eid, stock0[eid], e.stock,
                      "← 吃光了" if e.stock == 0 else ""))

    print("\n【4 行为】(时间花在哪: 人·天)")
    tot = sum(span.values()) or 1
    for cls, n in span.most_common(12):
        print("    %-10s %8.1f 人·天 (%.0f%%)" % (cls, n / 1440.0, 100.0 * n / tot))
    print("  事件:", by_kind.most_common(12))

    bad = bool(deaths) or any(c.cash < 1 for c in world.companies.values())
    print("\n" + ("✘ 不健康: " + ("有人死 " if deaths else "")
                  + "有公司破产" if bad else "✔ 健康: 无人死、无公司破产") + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(a[0] if a else "config/scenes/scene.json",
                          int(a[1]) if len(a) > 1 else 30))
