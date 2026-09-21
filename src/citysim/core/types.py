"""数据契约层 —— NPC 与世界的全部通信数据结构(全部 frozen + slots)。

世界给 NPC 看: Percept / EntityView
NPC 想干什么: Intent
世界对 NPC 说什么: Notify(发生了什么) / Command(照这个做)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

@dataclass(frozen=True, slots=True)
class EntityView:
    """NPC 视野里的一个可交互实体(世界侧不可变快照)。"""
    entity_id: str
    name: str
    tags: frozenset[str]                  # {"edible","sleepable","toilet",...}
    affordances: Mapping[str, float]      # 完成后信号效果 {"hunger": +0.4}
    duration_ticks: int
    stock: int = -1                       # 存量(-1=无限); 囤货要靠它算“家里还剩几个”
    shelf_life_ticks: int = 0             # 保质期(0=不坏) —— 目标存量由它推导
    expires_tick: int = 0                 # 到点变质(0=不过期)
    location_id: str = ""
    price: float = 0.0                    # 价格(0=免费)
    owner: str = ""                       # 归属(""=无主/商店) —— 已把所在地主人折进来
    household: bool = False               # ★ 定死: 这件东西放在某住所(kind=home),
                                          #   而我是该住所的授权人(owner/open_to/公共)
                                          #   → 自家财产, 免费使用, 不看 price
    free_use: bool = False                # ★ 定死三条规则的综合结论: 我能【免费直接
                                          #   用】它(住所授权 / 公共无主 / 本公司店员)。
                                          #   False + price>0 → 才要买(Buy)。
    item_type: str = ""                   # 物品类型 id(去重/合并用)


@dataclass(frozen=True, slots=True)
class Percept:
    tick: int
    hour_f: float
    location_id: str
    visible: tuple[EntityView, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    ranked: tuple[tuple[str, float], ...] = ()   # (entity_id, utility分) 降序
    reason: str = ""
    features: Mapping[str, float] = field(default_factory=dict)
    # 结构化 trace: 相关信号及其缺口(need = 1-signal, 降序)
    relevant_signals: tuple[tuple[str, float], ...] = ()


# --- 意图(多态): 每种意图自持字段, 取代单一 kind+target_id ---
@dataclass(frozen=True, slots=True)
class Idle:
    trace: DecisionTrace = field(default_factory=DecisionTrace)


@dataclass(frozen=True, slots=True)
class MoveTo:
    dest: str
    trace: DecisionTrace = field(default_factory=DecisionTrace)


@dataclass(frozen=True, slots=True)
class Interact:
    target_id: str
    trace: DecisionTrace = field(default_factory=DecisionTrace)


@dataclass(frozen=True, slots=True)
class Buy:
    item_id: str
    qty: int = 1
    trace: DecisionTrace = field(default_factory=DecisionTrace)


@dataclass(frozen=True, slots=True)
class Wander:
    """闲逛: 去 dest 待一段【观察窗口】(默认 60t), 靠"看见新东西"补 fun。

    它是 committed goal(期间不重算, 只有 PLAN 能抢), 所以不是"可被任何需求打断"。
    窗口状态(roam_until/roam_gain)挂在目标上, 见 person/goal.py 的 _advance。
    """
    dest: str
    trace: DecisionTrace = field(default_factory=DecisionTrace)


Intent = Idle | MoveTo | Interact | Buy | Wander


# ---------------------------------------------------------------------------
# world → npc 的【通知】(单向广播)
# ---------------------------------------------------------------------------
# 和 Intent 正好相反: Intent 是 NPC 说给世界听; Notify 是世界说给 NPC 听。
#
# ★ 为什么要有它: 以前 world 直接调二十几个 setter 改 NPC 身上的东西(身体/
#   钱/工作/记忆/头顶的字), 没有一个统一的【门】—— 看不清“世界到底能改他什么”。
#   现在世界只有两个口:
#     notify(ev)  世界只说【发生了什么】, NPC 自己决定怎么改自己;
#     assign(cmd) 老板/作者下的【指令】(雇佣/排班/计划…), 显式可审计。
#   所以这层不叫“事件”而叫“通知”: 它不携带“你该变成什么样”。
@dataclass(frozen=True, slots=True)
class InteractionDone:
    """一次交互自然完成(NPC 已经在 _intake 里消化完了)。

    `stock`: 那件东西用完之后还剩多少(world 才知道)。**必须带回** ——
    因为观察是有条件的, 记忆不再每 tick 刷新, "吃一个少一个"只能靠
    交互结果自己写(否则记忆会一直以为还有很多)。-1 = 不知道。
    """
    entity_id: str
    tick: int = 0
    stock: int = -1


@dataclass(frozen=True, slots=True)
class InteractionFailed:
    """一次请求被否决/被打断 —— 只报【原因 + 时刻】, 证伪/冷却归 NPC 自己写。"""
    target_id: str
    why: str = ""
    tick: int = 0
    retry_ticks: int | None = None


@dataclass(frozen=True, slots=True)
class ItemGone:
    """某件东西没了(吃光/过期销毁): 该不该忘、忘多深, NPC 自己决定。"""
    entity_id: str


@dataclass(frozen=True, slots=True)
class WagePaid:
    """发工资(钱是进这个人的)。"""
    amount: float


@dataclass(frozen=True, slots=True)
class Bought:
    """买到了: 货已送到家(或手里)。

    成交是【异步】的(排队 → 世界那边才扣钱发货), 而且送货细节(落到哪个容器、
    能补什么、剩多少、保质期)比一个 InteractionDone 富得多。这些必须回到 NPC
    手里 —— 它靠它们写“家里多了什么”的记忆, 下次决策才能算出“家里还剩几个”
    (= 囤货模型)。以前这是【唯一】从信箱递过来的东西。
    """
    item_id: str
    container: str = ""                   # 落到哪个容器实体(空 = 没落地)
    home: str = ""
    stock: int = 0
    afford: str = ""                      # 能补哪个信号
    value: float = 0.0
    item_type: str = ""
    tags: tuple[str, ...] = ()
    shelf_life_ticks: int = 0
    expires_tick: int = 0
    tick: int = 0


Notify = InteractionDone | InteractionFailed | ItemGone | WagePaid | Bought


# --- 上面的人（老板/作者/计划器）下的【指令】(不是“发生了什么”，是“照这个做”）---
# 和 notify 的分工:
#   notify  世界说“发生了什么”         → NPC 自己决定怎么改自己;
#   assign  上面的人说“你以后照这个做”   → NPC 照做(雇佣/排班/时薪/角色/日计划)。
# 这两条是 world 能碰 NPC 的【全部】入口。
@dataclass(frozen=True, slots=True)
class Work:
    """工作绑定(雇佣 / 改岗): 公司 + 店 + 工位 + 班次 + 时薪(+角色)。"""
    company_id: str
    shop_id: str = ""
    station_id: str = ""
    open_minute: int = 0
    close_minute: int = 1440
    wage_per_hour: float = 0.0
    role: str = "worker"                 # "" = 不动现有角色


@dataclass(frozen=True, slots=True)
class Unwork:
    """撤掉工作绑定(撤岗/辞退): 清掉 _work，保留人。"""


@dataclass(frozen=True, slots=True)
class Shift:
    """改【本人班次】(不影响公司营业时间)。open 0..1439, close 1..1440。"""
    open_minute: int
    close_minute: int


@dataclass(frozen=True, slots=True)
class Wage:
    """改【本人时薪】(逐人; 公司的 payroll 由 world 侧同步改)。"""
    wage_per_hour: float


@dataclass(frozen=True, slots=True)
class Role:
    """给/改角色。"""
    role: str


@dataclass(frozen=True, slots=True)
class Plan:
    """灌入当天日程表(LLM/作者产物)，覆盖旧计划。"""
    entries: Sequence[Any] = ()


Command = Work | Unwork | Shift | Wage | Role | Plan


# ---------------------------------------------------------------------------
# 语义层契约
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SemanticEvent:
    """NPC 要把内部状态说成的一句话(结构化, 还没措辞)。

    铁律: 这里全是【真值】。谁说的 / 什么行为 / 什么强度 / 涉及谁 —— 一个都不许编。
    随机只发生在【渲染措辞】那一步(见 game/lines.render)。

    两个 dict 分得很清, 不要混:
      · slots —— 【措辞槽】: 已经变成词的片段(item/was/now/why/goal/who)。
                  只给渲染器看, 传播时不带走。
      · fact  —— 【传播真值】: item_id/price/stock/believe/tags/… 渲染不读。
                  传闻抄的是它(见 world/run/gossip), 所以价格必须是【数字】
                   —— 一旦早在 slots 里变成 "8块", 精度衰减就只能改字符串了。
    """
    event_id: str                     # sem<N>
    tick: int
    speaker: str                      # npc_id
    act: str                          # STATE/INTENT/SURPRISE/DOUBT/REPORT
    topic: str                        # 冷却 / 去重键 ^[a-z][a-z0-9_.]*$
    slots: Mapping[str, Any] = field(default_factory=dict)   # 措辞槽(词)
    source: str = ""                  # "" = 自身; 否则 fact_id / 来源 npc_id
    fact: Mapping[str, Any] = field(default_factory=dict)    # 传播真值(数字/码)


@dataclass(frozen=True, slots=True)
class Decision:
    """Person 的一次决策(供 engine 仲裁): intent + 来源。

    source 区分来源:
      "need"   → 需求(utility)驱动; 只在空闲时产生
      "plan"   → 计划/上班; 唯一能中止当前交互的来源
      "idle"   → 无事可做
    """
    intent: Intent
    source: str = "idle"          # "need" | "plan" | "idle"


def intent_kind(intent: Intent) -> str:
    """意图 → 旧式 kind 字符串(日志/快照/前端兼容)。"""
    if isinstance(intent, Idle):
        return "idle"
    if isinstance(intent, MoveTo):
        return "move_to"
    if isinstance(intent, Interact):
        return "interact"
    if isinstance(intent, Buy):
        return "buy"
    if isinstance(intent, Wander):
        return "wander"
    raise TypeError(f"unknown intent {intent!r}")


def intent_target(intent: Intent) -> str | None:
    """意图 → 目标 id(旧式 target_id; idle 为 None)。"""
    if isinstance(intent, MoveTo):
        return intent.dest
    if isinstance(intent, Interact):
        return intent.target_id
    if isinstance(intent, Buy):
        return intent.item_id
    if isinstance(intent, Wander):
        return intent.dest
    return None
