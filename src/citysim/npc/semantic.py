"""semantic —— NPC 【说什么】(认知侧)。

一句话: **把真值攒成结构化事件。措辞不在这层。**

    semantic.py (这)      说【什么】: 谁 / 什么行为 / 什么强度 / 涉及谁 / 什么真值
    game/lines.py         说【成什么话】: 模板池 + 词表(游戏层资产)

这么切的两个理由:

1. **措辞是表现层的事。** 认知层不该有别字、语气、模板。而且措辞是唯一会被
   替换的东西 —— 以后要接 LLM(设计决定 D3「LLM 藏在接口后面」)、要换语言、
   要做 persona × mood, 换的全是 `lines.py`。

2. **`fact` 与 `slots` 必须分开。** 传闻抄的是 `fact`(真值), 而价格必须是
   数字 —— 设计决定 #18 要求"精度衰减按 remember 分桶, 只丢精度不造新信息"
   ("四块五"→"四块多")。价格一早在措辞里变成 `"8块"`, 衰减就只能改字符串
   了, 无法精算。

本模块在 npc 层: 只读纯数据, 不 import world。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from citysim.core.types import SemanticEvent

# act 集合与说话优先级
#
# 注: STATE 目前【没有构造器】(没有任何地方造 STATE 事件, 也没人渲染它)。
# 留着是因为 PRIORITY 的档位是"说到什么程度"的语义刻度, 将来加"我身体怎么样"
# 这类自言自语时直接用。别因为它是死的就删掉优先级入口。
ACTS: tuple[str, ...] = ("STATE", "INTENT", "SURPRISE", "DOUBT", "DENIED",
                         "REPORT", "SAY")
# SAY = 说者头顶那半句("跟林静说：简餐8块") —— 不含新信息, 不进说话队列,
#       也不进 PRIORITY; 它只是把"谁给谁说"画出来。
PRIORITY: Mapping[str, int] = {
    "DOUBT": 6,        # 信念被现实推翻 —— 永远最好看, 排最前
    "DENIED": 5,       # 我被拒绝了(没钱/没货/有人占着) —— **玩家最该看见的一刻**
    "SURPRISE": 4,     # 预期与观察有落差
    "INTENT": 3,       # 我打算干什么
    "STATE": 2,        # 我身体怎么样
    "REPORT": 1,       # 转述别人说的
}

_counter = {"n": 0}


def _next_seq() -> int:
    _counter["n"] += 1
    return _counter["n"]


def _event(seq: int, tick: int, speaker: str, act: str, topic: str,
           slots: Mapping[str, Any], *, source: str = "",
           fact: Mapping[str, Any] | None = None) -> SemanticEvent:
    """组装一条事件。**不做任何判断** —— 调用方给真值, 这里只装箱。"""
    return SemanticEvent(
        event_id=f"sem{seq}", tick=tick, speaker=speaker, act=act,
        topic=topic, slots=dict(slots), source=source, fact=dict(fact or {}))


# ---------------------------------------------------------------------------
# 选材: 从记忆里挑一件【值得转述】的事(= REPORT)
# ---------------------------------------------------------------------------
def pick_retellable(rows: Sequence[Mapping[str, Any]], *, home: str,
                    knows) -> Mapping[str, Any] | None:
    """挑一件值得转述的事 —— 转述的来源是**记忆**, 不是刚发生的事。

    为什么需要它: 语义事件(刚看到的意外)冒完泡就没了, 但**新闻要能带走** ——
    不然"在城里传开"就无从发生。

    值得说 = ① 不是我自己家里的东西(自家床/马桶不是新闻)
             ② 对方还不知道
    排序(确定): 有来源的(我听来的 = 新闻) > 在售的(别人能去买) > 信得过的 >
                 item_id
    """
    def rank(r: Mapping[str, Any]) -> tuple:
        has_src = 1 if str(r.get("source", "")) else 0
        for_sale = 1 if float(r.get("price", 0.0)) > 0 else 0
        return (-has_src, -for_sale, -float(r.get("believe", 0.0)),
                str(r.get("item_id", "")))
    best = None
    for r in sorted(rows, key=rank):
        iid = str(r.get("item_id", ""))
        if not iid or knows(iid):
            continue                      # 对方已经知道了 → 不说
        if home and str(r.get("located", "")) == home:
            continue                      # 我自己家里的东西不是新闻
        if not str(r.get("afford", "")):
            continue                      # 说不出它能干什么 → 没意义
        best = r
        break
    return best


# ---------------------------------------------------------------------------
# 事件构造(调用方给【真值】; 措辞槽给【词】—— 但绝不在这里拼句子)
# ---------------------------------------------------------------------------
def denied(tick: int, speaker: str, why: str, *,
           topic: str = "") -> SemanticEvent:
    """我被拒绝了: 没钱 / 没货 / 有人占着 / 白跑一趟。

    `why` 是**引擎给的原始原因**(可能带括号的长句), 不是给人看的措辞 ——
    缩短/润色是 lines.fail_word 的事。
    """
    return _event(_next_seq(), tick, speaker, "DENIED",
                  topic or "denied", {"why": why})


def intent(tick: int, speaker: str, afford: str, driver: str,
           topic: str = "") -> SemanticEvent:
    """我打算干什么。

    afford = 驱动这次行动的需求(hunger/energy/bladder) —— 词由 lines.GOAL_WORDS 给。
    driver = "now"(眼前缺) / "future"(囤货) —— **措辞必须跟真实驱动一致**:
             不饿却去补货时, 不许说"我有点饿"。
    """
    return _event(_next_seq(), tick, speaker, "INTENT",
                  topic or f"intent.{afford}",
                  {"afford": afford, "driver": driver})


def surprise(tick: int, speaker: str, item_id: str, item_name: str,
             was: Any, now: Any, *, fact: Mapping[str, Any] | None = None,
             topic: str = "") -> SemanticEvent:
    """现场与记忆不符。

    `was` / `now` 可以是**数字**(价格, 渲染时按钱说)或**词**("卖光了")。
    `fact` 是传播真值(item_id/price/stock/believe/…) —— 传闻抄它, 渲染不读它。
    """
    return _event(_next_seq(), tick, speaker, "SURPRISE",
                  topic or f"item.{item_id}",
                  {"item": item_name, "was": was, "now": now}, fact=fact)


def doubt(tick: int, speaker: str, item_id: str, item_name: str, who: str,
          was: Any, now: Any, *, fact: Mapping[str, Any] | None = None,
          source: str = "") -> SemanticEvent:
    """信念被现实推翻: 这条记忆本来是【别人说的】(source=who) —— 最值得说的事。"""
    return _event(_next_seq(), tick, speaker, "DOUBT", f"item.{item_id}",
                  {"item": item_name, "who": who, "was": was, "now": now},
                  source=source or who, fact=fact)


def report(tick: int, speaker: str, item_id: str, item_name: str,
           now: Any, who: str = "", *,
           fact: Mapping[str, Any] | None = None) -> SemanticEvent:
    """转述: 听者头上的那条"听说…"。

    `who` 同时进 slots: 模板里的 {who} 就一定能填上(不依赖调用方记得传
    speaker_name —— 以前漏传就会渲染出"跟我说苹果5块"这种没主语的话)。
    """
    return _event(_next_seq(), tick, speaker, "REPORT",
                  f"item.{item_id}",
                  {"item": item_name, "now": now, "who": who},
                  source=who, fact=fact)


def say(tick: int, speaker: str, to_name: str, item_id: str,
        item_name: str, now: Any, *,
        fact: Mapping[str, Any] | None = None) -> SemanticEvent:
    """说者头顶那半句("→ 林静：简餐8块")。

    它不是语义事件: 不含新信息, 也不该被别人转述 —— 只是把"谁给谁说的"
    在画面上连成一条桥。所以它不进 `_say_queue`, 直接进气泡。
    """
    return _event(_next_seq(), tick, speaker, "SAY", f"item.{item_id}",
                  {"to": to_name, "item": item_name, "now": now}, fact=fact)
