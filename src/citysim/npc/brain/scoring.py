"""npc/brain/scoring —— 打分: 效用 ÷ 成本。

效用 = 需求缺口 × 价值 × 人格 × 信念; 成本 = 价格 + 走一趟的代价。
★ 走一趟按【净价值】摊到每份货上(见 _net_value)—— 不摊的话,
  "去远处囤货"会被按一份的价钱罚掉整趟路费。
"""
from __future__ import annotations

from typing import Mapping
from citysim.core.config import SimConfig

from citysim.npc.brain.candidates import _self_use

DEFAULT_TRAVEL_TICKS = 30


def _score_candidates(cands, personality: Mapping[str, float],
                      location_id: str, cfg: SimConfig,
                      travel_ticks: Mapping[str, int] | None = None,
                      money: float = float("inf"),
                      self_id: str = "",
                      hour_f: float = 0.0,
                      favor: Mapping[str, float] | None = None,
                      home: str = "",
                      workplace: str = "",
                      leave_cost: float = 0.0):
    """[阶段2+3] 评分 + 排序。

        eff = (need^power × 净收益 × personality × believe) / (1 + λ × cost)
        净收益 = value − (路上掉掉的量 × 走路放大系数) ÷ 买几份   ← 任何信号通用
        cost   = price×qty + price×(1 −believe)      (纯钱 + 不确定性)

     为什么路费要"÷ 买几份": 跑一趟只买 1 个, 那这趟的消耗全压在这一个上(近的好);
     一趟囤 16 份, 这点消耗摊到 16 份上就不算什么了 → 远的店也值得去 ✓
     (用户定的口径: 买一个近点好, 买得多路费不该成为劣势)
     believe 项: “听说便宜”不如“亲眼看到便宜”可靠(κ = 1)。
     """
    needs: dict[str, float] = {}
    scored = []
    for row, sig, need, want, driver in cands:
        needs[sig] = need
        # 每种需求可以有自己的幂次(精力要钝: 不太困就别去躺)
        power = cfg.power_by_signal.get(sig, cfg.utility_power)
        if driver == "explore":
            # ★ "去我记得能解它的地方看看" —— 地点行没有价值/价格, 不走常规公式。
            #   给个小而定、随缺口线性长起来的分: 够过阈值(不然等于没去),
            #   又不会盖过任何真候选(有真候选时根本不会生这条)。
            scored.append((row.item_id, sig, cfg.explore_score * need,
                           row.located, row, 1, driver))
            continue
        # 走这一趟要多少 tick
        ticks = 0
        if row.located and location_id and row.located != location_id:
            ticks = DEFAULT_TRAVEL_TICKS
            if travel_ticks:
                ticks = int(travel_ticks.get(
                    _travel_key(location_id, row.located),
                    DEFAULT_TRAVEL_TICKS))
        # 买几份 / 买得起吗 —— 要按【打算买几件】算, 不是按单价!
        # (旧版只看单价: 钱只够 1 件、却按缺口要买 4 件 → 白跑一趟再失败)
        qty = max(1, int(want))
        # 免费自用的不当商品算钱(口径与候选/分流同一个 _self_use)。
        for_sale = row.price > 0 and not _self_use(row, self_id, home, workplace)
        if for_sale:
            affordable = int(float(money) // float(row.price))
            if affordable < 1:
                continue                 # 一件都买不起 → 别白跑
            qty = min(qty, affordable)   # 钱够几件就买几件
        # ★ 净收益: 路上需求在掉 → 补回来的没 value 那么多;
        #   而且是"这一趟"的消耗 → 按份数摊平(买得多, 路费就不是劣势)
        # ★ 食物按【真实缺口】封顶: 补不了那么多就不算那么多(补 20 也不虚高)。
        #   只对 driver="now"(need==1−signal, 同一根轴); future(囤货)的 need
        #   是“目标存量缺口”, 不是同一轴, 不能夹。
        val = float(row.value)
        if driver == "now":
            val = min(val, need)
        net = _net_value(cfg, sig, val, ticks,
                         float(personality.get(sig, 1.0)), hour_f, qty=qty)
        # ★ 对【这家店】的好感度(0..2, 中性 1.0): 声誉是店的, 不是商品的。
        #   掉到 0 → 这条直接不成立(再便宜也不去); 高于 1 则是加分项。
        fav = float((favor or {}).get(str(row.located), cfg.favor_neutral))
        if fav <= 0.0:
            continue
        base = (need ** power) * net \
            * float(personality.get(sig, 1.0)) * row.believe * fav
        # —— 成本 ——
        # 只有【真在卖】才把价放进成本。免费自用(住所/公共/本公司店员)不看 price
        # ——否则凭听说(believe<1)得来的家用物品会被“不确定折扣”莫名扣分。
        cost = 0.0
        if for_sale:
            cost = float(row.price) * qty
            cost += float(row.price) * (1.0 - row.believe)   # 不确定的便宜要打折
        # ★ 上班离岗代价(旷工扣日薪): 在班 + 人在工位 + 目的地不是工位。
        #   手边的公司货(row.located == workplace)不计。
        if (leave_cost > 0.0 and workplace and location_id == workplace
                and row.located and row.located != workplace):
            cost += leave_cost
        eff = base / (1.0 + cfg.cost_lambda * cost)
        scored.append((row.item_id, sig, eff, row.located, row, qty, driver))
    scored.sort(key=lambda x: (-x[2], x[0]))
    ranked = tuple((s[0], round(s[2], 4)) for s in scored)
    relevant = tuple(sorted(needs.items(), key=lambda kv: (-kv[1], kv[0])))
    return scored, ranked, relevant


def _net_value(cfg: SimConfig, sig: str, value: float, ticks: int,
               sig_mul: float, hour_f: float, qty: int = 1) -> float:
    """净收益 = 这件东西给的价值 − 【这一趟】路上掉掉的量，再按买几份摊平。

    用户提的例子: 在家吃梨立刻补 0.30; 出门买苹果 value 0.35,
    但走 23 tick 路上饿掉一部分 → 真正到手没那么多。
    **长途更明显** —— 这就是"更近的店"该有的优势, 而且不需要另设"走路要多少钱"
    (那种估算既重复又不准)。同一个式子对 hunger / energy / bladder 都成立。

    ÷ qty 的含义(用户定的口径):
      · 只买 1 个 → 这趟的消耗全压在这一个上 → **近的店更好** ✓
      · 一趟囤 16 份 → 这点消耗摊到 16 份上 → **远的店也不再是劣势** ✓
      · 不摊的话, "远店囤货"会被按"一份"罚整趟(实测 13.4%), 而钱那边
        却按 16 份收 —— 两边口径不一致。
    """
    if ticks <= 0:
        return max(0.0, float(value))
    k = float(getattr(cfg, "travel_penalty", 1.0))
    loss = drain_per_tick(cfg, sig, hour_f, sig_mul, busy=True) * ticks * k
    return max(0.0, float(value) - loss / max(1, int(qty)))


def drain_per_tick(cfg: SimConfig, sig: str, hour_f: float,
                   sig_mul: float = 1.0, busy: bool = False) -> float:
    """这个需求【每 tick】掉多少(0..1)。**任何信号通用, 且和 heartbeat 同源**。

    这就是"出门是有代价的"的物理表达: 走 N tick 的路上需求本身在下降,
    所以那件东西真正补回来的只有 `value − drain × ticks`。

    ★ 它【不是一个可调参数】—— 它就是用 [metabolism] 那张表算出来的、
      身体每 tick 真的掉多少(见 Person.heartbeat):
        hunger/bladder  基准速率 × 个人系数
        energy          再 × 昼夜曲线(夜里掉得快) × 赶路 1.8 倍(busy)
      参考就是"时间 × 速率 = 真掉了多少": hunger -1/720/tick → 走 30 tick(半小时)
      就是 4.2%; energy 白天 30 tick ≈ 1.0%, 21:00 之后 ≈ 9.4%。
      想让它更"怕走路", 该调的是物理量(busy_energy_mul), 不是这里的系数。
    """
    rate = -min(0.0, float(cfg.metabolism.get(sig, 0.0)))
    if rate <= 0.0:
        return 0.0
    if sig == "energy":
        rate *= float(cfg.rhythm_at(hour_f))      # 注意: 单位是【小时 0..24】
        if busy:
            rate *= float(cfg.busy_energy_mul)    # 赶路 = 在做事(与 heartbeat 一致)
    return rate * float(sig_mul)


def _travel_key(a: str, b: str) -> str:
    return "%s|%s" % (a, b) if a <= b else "%s|%s" % (b, a)
