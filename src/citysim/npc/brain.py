"""brain —— decide() 纯函数 + utility。

定位: 由 Percept + signals 决定下一个 Intent(做什么)。纯函数: 不得修改任何
入参、不得访问全局状态。utility 打分迁移自旧 person/brain/indicator.py。
"""
from __future__ import annotations

import math

from typing import Mapping

from citysim.core.config import SimConfig
from citysim.core.types import (
    Buy,
    DecisionTrace,
    Idle,
    Intent,
    Interact,
    MoveTo,
    Percept,
)
from citysim.npc.memory import MemBase, MemItem


def perceive_into(mem: MemBase, percept: Percept, tick: int) -> None:
    """感知 → 记忆(写入): 把当前可见实体 upsert 进记忆库。非纯函数。

    同地 re-obs: 现场为准, 整行覆盖(located/owner/claimed/afford/price/…)并刷新
    believe/remember/last_seen。只 upsert 可见实体, 不做证伪删行(由上层策略定)。

    现场看到的 → source=""(亲眼) 且 believe=1.0: 不管之前听谁说过, 亲眼所见最硬。
    """
    for v in percept.visible:
        # TODO: affordances 多键 dict → 决定单值 or dict(MemItem.afford 现单值)
        afford, value = (next(iter(v.affordances.items()), ("", 0.0)))
        # owner 直接存世界真值 id(person_id/company_id/""=无主)：判定"自己的"靠
        # decide 的 self_id 比对, 不再用 "me" 哨兵。claimed 语义待对齐。
        claimed = not v.claimable
        row = mem.get(v.entity_id)
        if row is None:
            mem.set(MemItem(
                item_id=v.entity_id, located=v.location_id,
                owner=v.owner, claimed=claimed, afford=afford, value=float(value),
                item_type=v.item_type, tags=tuple(sorted(v.tags)), source="",
                price=v.price, stock=int(v.stock),
                shelf_life_ticks=int(v.shelf_life_ticks),
                expires_tick=int(v.expires_tick),
                believe=1.0, remember=1.0, last_seen=tick))
        else:
            mem.update(
                v.entity_id, located=v.location_id, owner=v.owner,
                claimed=claimed, afford=afford or row.afford,
                value=float(value) if value else row.value,
                item_type=v.item_type, tags=tuple(sorted(v.tags)), source="",
                price=v.price, stock=int(v.stock),
                shelf_life_ticks=int(v.shelf_life_ticks),
                expires_tick=int(v.expires_tick),
                believe=1.0, remember=1.0, last_seen=tick)


FORGET_DEFAULT = 0.1  # remember 低于此 → 遗忘删除(默认阈值)

# 默认的位移成本(无路网/无成本矩阵时的降级): 固定 tick。
DEFAULT_TRAVEL_TICKS = 30
MAX_BUY_QTY = 30      # 单次购买上限(只是防手滑; 真正的量由目标存量决定)


def forget(mem: MemBase, now_tick: int, half_life_ticks: int,
           forget_threshold: float = FORGET_DEFAULT) -> int:
    """遗忘策略: 按 last_seen 把 remember 半衰衰减, 低于阈值删行。

    返回值 = 本次被遗忘删除的 item 数。何时调用/半衰/阈值由上层定(如每游戏日)。
    """
    gone = 0
    for r in mem.items():
        dt = max(0, now_tick - r.last_seen)
        if dt <= 0:
            continue
        rem = r.remember * (0.5 ** (dt / max(1, half_life_ticks)))
        if rem < forget_threshold:
            mem.delete(r.item_id)
            gone += 1
        else:
            mem.update(r.item_id, remember=rem)
    return gone


def decide(
    signals: Mapping[str, float],
    personality: Mapping[str, float],
    mem: MemBase,
    location_id: str,             # 自身状态: 我在哪(决策不看环境 percept)
    cfg: SimConfig,
    now_tick: int,                # 当前 tick(过滤失败冷却 cool_until)
    self_id: str = "",            # 自身身份 id(判定"自己的"用品)
    travel_ticks: Mapping[str, int] | None = None,   # "a|b" -> tick(可选)
    money: float = float("inf"),  # 买不起的就不作为候选(否则反复失败刷屏)
    home: str = "",               # 住址(囤货要看“我家还剩几个”)
) -> Intent:
    """决策主算法。纯函数。铁律:

      决策只读【记忆 mem + 自身状态 signals/personality/location】,
      绝不看环境/现场(percept/world)。现场真值只在感知写入(observe)与执行失败
      反证时进入记忆; decide 自己永远不查现场。

    流程: 候选收集(无门槛) → 评分(需求 ÷ 成本) → 排序 → 选优分流。

    注: 这里**不再有 fallback_need / REFLEX_SIGNALS 筛选层** —— 记忆里的行
    全部参与打分, 唯一的阀值在得分上(cfg.utility_threshold)。
    """
    intent, _eff = decide_scored(signals, personality, mem, location_id, cfg,
                                 now_tick, self_id, travel_ticks, money, home)
    return intent


def decide_scored(
    signals: Mapping[str, float],
    personality: Mapping[str, float],
    mem: MemBase,
    location_id: str,
    cfg: SimConfig,
    now_tick: int,
    self_id: str = "",
    travel_ticks: Mapping[str, int] | None = None,
    money: float = float("inf"),
    home: str = "",
) -> tuple[Intent, float]:
    """同 decide, 但多返回【得分】。

    得分是“这件事现在值多少分”。用来回答“值不值得打断我正在做的事”:
    每 tick 重算一次, 只有新事的分明显高于当前事(迟滞)才换 —— 否则会在两个
    差不多好的目标之间反复横跳。
    """
    cands = _gather_candidates(
        mem, signals, now_tick, home=home, cfg=cfg,
        future_weight=cfg.stock_future_weight,
        thrift=float(personality.get("thrift", 1.0)))
    scored, ranked, relevant = _score_candidates(
        cands, personality, location_id, cfg, travel_ticks, money, self_id,
        hour_f=(now_tick % max(1, cfg.ticks_per_day)) / 60.0)
    return _choose(scored, ranked, relevant, cfg, self_id, location_id, home)


def _home_stock(mem: MemBase, home: str) -> dict[str, float]:
    """我家里每种“能提供什么”还剩几个(按 afford 汇总 stock)。

    只看 located == home 的行 —— 店里的货不算“我家的存货”。
    """
    out: dict[str, float] = {}
    if not home:
        return out
    for row in mem.items():
        if row.located != home or not row.afford:
            continue
        out[row.afford] = out.get(row.afford, 0.0) + max(0.0, float(row.stock))
    return out


def _stock_target(cfg: SimConfig, sig: str, value: float,
                  shelf_life: int, thrift: float) -> float:
    """我该囤多少【份】(不是 0..1, 就是份数)。

        每天消耗份数 = (-metabolism[sig] × ticks_per_day) / value
        目标 = 每天消耗份数 × 保质期天数 × stock_fill × thrift

    —— “在它坏掉之前我吃得完多少”。短保的东西自然囤得少。
    不会坏的东西(无保质期)按 stock_default_days 算。
    """
    if value <= 0.0:
        return 0.0
    daily_drain = -min(0.0, float(cfg.metabolism.get(sig, 0.0)))         * float(cfg.ticks_per_day)
    if daily_drain <= 0.0:
        return 0.0
    per_day = daily_drain / value                     # 每天吃几份
    days = (float(shelf_life) / float(cfg.ticks_per_day)
            if shelf_life > 0 else cfg.stock_default_days)
    return per_day * days * cfg.stock_fill * max(0.0, float(thrift))


def _future_need(cfg: SimConfig, have: float, sig: str, value: float,
                 shelf_life: int, thrift: float) -> float:
    """【预期需求】= 家里缺口 / 目标存量(0..1)。

    这就是“囤货”: 不是“饿了才去买”, 而是“家里快没存货了 → 提前补”。

    目标存量【不是魔法数字】, 而是从保质期推导出来的:
        每天消耗份数 = (-metabolism[sig] × ticks_per_day) / value
        目标 = 每天消耗份数 × 保质期天数 × stock_fill × thrift
    —— 即“在它坏掉之前我吃得完多少”。所以**短保的东西自然囤得少**。
    不会坏的东西(无保质期)按 stock_default_days 算。
    """
    target = _stock_target(cfg, sig, value, shelf_life, thrift)
    if target <= 0.0:
        return 0.0
    return min(1.0, max(0.0, (target - have) / target))


def _gather_candidates(mem: MemBase, signals: Mapping[str, float],
                       now_tick: int,  *, home: str = "",
                       cfg: SimConfig | None = None,
                       future_weight: float = 0.0, thrift: float = 1.0):
    """[阶段1] 候选收集 —— **不过滤**。

    只要能提供点什么(afford 非空 且 value>0)就是候选。
    “值不值得做”全部交给后面的得分与阀值; 这里只看两个硬事实:
      - afford/value 缺失 → 这条记忆没告诉我能得到什么;
      - stock == 0: 空的东西不值得跑一趟(-1 = 无限, 不算空);
      - cool_until: 刚失败过的别马上再试(防重试死循环)。

    need = max(眼前的缺口, w × 未来的缺口)
      · 眼前的缺口 = 1 − signal
      · 未来的缺口 = 囤货(家里存货相对目标还有多少缺口)
    返回 [(row, sig, need), ...]。
    """
    stock = (_home_stock(mem, home)
             if (cfg is not None and future_weight > 0.0) else {})
    out = []
    for row in mem.items():
        if row.cool_until and row.cool_until > now_tick:
            continue          # 失败冷却中(如厕所刚被占), 稍后再看
        sig = row.afford
        if not sig or row.value <= 0:
            continue
        if int(getattr(row, "stock", -1)) == 0:
            continue          # 空的(已消耗/已变质) —— 别去
        need = 1.0 - float(signals.get(sig, 1.0))
        # 缺口只驱动【补货】(出门/买), 不驱动“把家里最后一点吃掉”
        # —— 后者只会把存货变得更少。所以只在不位于本家时才加预期需求。
        # 该买几份: 补到目标存量为止(不再是“一次只买一个”)
        want = 1
        # driver: 这次行动到底是【眼前缺】还是【未来缺(囤货)】驱动的 ——
        # 措辞层必须知道这件事, 否则会说出“好饿, 去买点吃的”这种假话。
        driver = "now"
        # 只有【会消耗的东西】才谈得上囤货 —— 床/马桶的 stock 永远 1,
        # 对它做目标存量会推出“囤 2.5 张床”, 进而把床的分抬到压过吃饭。
        consumable = "consumable" in tuple(getattr(row, "tags", ()) or ())
        # ★ 注意不能写 `if stock` —— _home_stock 在"家里什么都没有"时返回 {}(假值),
        #   于是整个囤货分支被跳过 → 买什么都只买 1 份、也永远不"为了以后"出门。
        #   实测: 6 个 NPC 全都没有存货 → 囤货逻辑一次都没生效过。
        # 还需 home 非空: "囤货"的本义是【给家里补货】。无住所的人(编辑器里
        # 那些 home="")没有"家里的存货"这个概念, 硬算会得出"我什么都没有 →
        # 立刻去吃" → 家里剩一份饭、人不饿也会被吃掉(测试抓到的循环)。
        if cfg is not None and consumable and home and row.located != home:
            have = float(stock.get(sig, 0.0))
            target = _stock_target(cfg, sig, row.value,
                                   int(getattr(row, "shelf_life_ticks", 0)),
                                   thrift)
            fut = _future_need(cfg, have, sig, row.value,
                               int(getattr(row, "shelf_life_ticks", 0)),
                               thrift)
            if fut > 0.0 and future_weight * fut > need:
                need = future_weight * fut
                driver = "future"          # ← 未来缺口赢了: 不是“我饿了”
                # 【只有囤货才一次买多份】。眼前缺(=真的饿了)只买 1 份:
                # 否则"买 3 份的钱"会把救命那一下的得分压下去 →
                # 快饿死了却还在床上躺着(测试抓到的回归: 命比钱大)✗
                if target > 0.0:
                    want = max(1, int(math.ceil(target - have)))
        out.append((row, sig, need, want, driver))
    return out


def _travel_key(a: str, b: str) -> str:
    return "%s|%s" % (a, b) if a <= b else "%s|%s" % (b, a)


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


def _score_candidates(cands, personality: Mapping[str, float],
                      location_id: str, cfg: SimConfig,
                      travel_ticks: Mapping[str, int] | None = None,
                      money: float = float("inf"),
                      self_id: str = "",
                      hour_f: float = 0.0):
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
        for_sale = row.price > 0 and row.owner != self_id
        if for_sale:
            affordable = int(float(money) // float(row.price))
            if affordable < 1:
                continue                 # 一件都买不起 → 别白跑
            qty = min(qty, affordable)   # 钱够几件就买几件
        # ★ 净收益: 路上需求在掉 → 补回来的没 value 那么多;
        #   而且是"这一趟"的消耗 → 按份数摊平(买得多, 路费就不是劣势)
        net = _net_value(cfg, sig, row.value, ticks,
                         float(personality.get(sig, 1.0)), hour_f, qty=qty)
        base = (need ** power) * net \
            * float(personality.get(sig, 1.0)) * row.believe
        # —— 成本 ——
        cost = float(row.price) * qty if for_sale else 0.0
        cost += float(row.price) * (1.0 - row.believe)   # 不确定的便宜要打折
        eff = base / (1.0 + cfg.cost_lambda * cost)
        scored.append((row.item_id, sig, eff, row.located, row, qty, driver))
    scored.sort(key=lambda x: (-x[2], x[0]))
    ranked = tuple((s[0], round(s[2], 4)) for s in scored)
    relevant = tuple(sorted(needs.items(), key=lambda kv: (-kv[1], kv[0])))
    return scored, ranked, relevant


def _choose(scored, ranked, relevant, cfg: SimConfig, self_id: str,
            location_id: str, home: str = "") -> tuple[Intent, float]:
    """[阶段4] 选优分流 —— 只凭记忆行字段, 不看现场。全不够格则 Idle。

    返回 (intent, score): Idle 时 score = 0。
    不判断"是否本地": 异地成本已算进 cost(真实行走 tick)。
    自己的/免费公共 → Interact; **在售 → Buy**(要付钱)。
    """
    thresh = cfg.utility_threshold
    for item_id, sig, eff, loc, row, qty, driver in scored:
        if eff <= thresh:
            continue
        # 能不能用: 自己的 / 自己家里的(共享) / 无主免费公共; 【在售】→ 买
        # “自己家里的”很关键: 一张床只写在不同住户名下, 但同住的人都能用。
        mine = bool(self_id) and row.owner == self_id
        my_home = bool(home) and row.located == home
        free_public = row.owner == "" and row.price <= 0
        for_sale = row.price > 0 and row.owner != self_id
        if not (mine or my_home or free_public or for_sale):
            continue
        if not loc:                       # 无地点信息 → 不可达
            continue
        if loc != location_id:            # 异地 → 前往(到地方下一 tick 再动手)
            return MoveTo(
                dest=loc,
                trace=DecisionTrace(
                    ranked=ranked,
                    reason=f"记忆: {item_id} 能解 {sig} → 去 {loc}",
                    used_fact_ids=(), features={"driver": driver},
                    relevant_signals=relevant)), eff
        if for_sale:                      # 在店里 → 付钱买(不再白拿)
            n = max(1, min(int(qty), MAX_BUY_QTY))   # 一次补到目标存量(且钱够)
            return Buy(
                item_id=item_id, qty=n,
                trace=DecisionTrace(
                    ranked=ranked,
                    reason=f"买 {item_id} ×{qty} (¥{row.price:g}, score={eff:.3f})",
                    used_fact_ids=(), features={"driver": driver},
                    relevant_signals=relevant)), eff
        return Interact(
            target_id=item_id,
            trace=DecisionTrace(
                ranked=ranked,
                reason=f"目标 {item_id} (score={eff:.3f})",
                used_fact_ids=(), features={"driver": driver},
                relevant_signals=relevant)), eff
    return Idle(
        trace=DecisionTrace(
            ranked=ranked,
            reason="信号充足或没有值得做的目标",
            used_fact_ids=(),
            relevant_signals=relevant)), 0.0

