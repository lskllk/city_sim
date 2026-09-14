"""semantic —— NPC 说什么(语义层 M-S1)。

铁律(docs/20260913/semantic_event.md §1):
  1. **随机只在措辞层。** 谁 / 知道什么 / 什么行为 / 什么强度 —— 全部为真、确定。
  2. **准确性靠约束, 不靠更聪明的模型。** 槽位只允许真值, 渲染时不许新增实体。
  3. **语义系统 = 知识系统的可视化 + 传播载体。** 说出的话就是一条带来源的 Fact。
  4. **知识边界优先于表达力。** 只能说它【知道】的事。

M-S1 只做最小集:
  · act: STATE / INTENT / SURPRISE / DOUBT (+ REPORT, 传播时的转述)
  · 手写【组合式模板池】(句子 = opener + core + tail), 每个 act 十几种说法;
    选哪一段是【确定性的】(由 speaker/act/topic/天 派生) —— 不掷骰子也能不重复。
  · **不接 LLM**, 不带语域(persona × mood)。

本模块在 npc 层: 只读纯数据, 不 import world。
"""
from __future__ import annotations

import zlib
from typing import Any, Mapping, Sequence

from citysim.core.types import SemanticEvent

# act 集合与说话优先级(docs/20260913/semantic_event.md §8)
ACTS: tuple[str, ...] = ("STATE", "INTENT", "SURPRISE", "DOUBT", "DENIED",
                         "REPORT")
PRIORITY: Mapping[str, int] = {
    "DOUBT": 6,        # 信念被现实推翻 —— 永远最好看, 排最前
    "DENIED": 5,       # 我被拒绝了(没钱/没货/有人占着) —— **玩家最该看见的一刻**
    "SURPRISE": 4,     # 预期与观察有落差
    "INTENT": 3,       # 我打算干什么
    "STATE": 2,        # 我身体怎么样
    "REPORT": 1,       # 转述别人说的
}

# ---------------------------------------------------------------------------
# 组合式模板池: 句子 = opener + core + tail
#   · 只写片段, 组合数是乘积(3~4 × 2~3 × 2~3 ≈ 12~30 种说法/act)
#   · core 里的 {xxx} 只能填【槽位里已有的真值】—— 渲染时不许新增实体
#   · 槽位里的词本身是中文(调用方给), 保证不出现 "听说apple"
# ---------------------------------------------------------------------------
_SALT = {"opener": 1, "core": 2, "tail": 3}

_POOLS: Mapping[str, Mapping[str, Sequence[str]]] = {
    "STATE": {
        "opener": ("唉，", "", "嗯……", "哎"),
        "core": ("肚子有点空了", "有点{need}了", "{need}上来了"),
        "tail": ("", "。", "……"),
    },
    "INTENT": {
        "opener": ("", "走了，", "我先", "走一步看一步，"),
        "core": ("{why}，去{goal}", "去{goal}", "打算{goal}"),
        "tail": ("", "。", "。", "。"),
    },
    "SURPRISE": {
        "opener": ("咦？", "诶？", "", "奇怪，"),
        "core": ("{item}怎么{now}了", "{item}是{now}", "{item}现在{now}"),
        "tail": ("", "？", "？我记得是{was}啊", "……跟我记得的不一样"),
    },
    "DOUBT": {
        "opener": ("", "诶——", "这不对啊，", "嗯？"),
        "core": ("{item}不是说好{was}吗", "{who}说{item}{was}的呀",
                 "{item}怎么成了{now}"),
        "tail": ("", "？", "，{who}是不是记错了？", "……", ""),
    },
    "DENIED": {
        "opener": ("哎，", "算了，", "", "啧，"),
        "core": ("{why}", "{why}啊", "白跑一趟——{why}"),
        "tail": ("", "。", "……"),
    },
    "REPORT": {
        "opener": ("听说", "听{who}说", "他们说"),
        "core": ("{item}{now}", "{item}现在{now}"),
        "tail": ("", "。", "，不知道真的假的"),
    },
}


def _pick(speaker: str, act: str, topic: str, salt: int) -> float:
    """[0,1) 的确定性“随机”值: 同一个人说同一件事, 选中的片段是固定的。

    不用内置 hash()(每进程随机化), 也不用 rng —— 措辞不该吃掉模拟的随机性。
    带上“第几天” → 同一件事隔天再说会换个说法。
    """
    key = "%s|%s|%s|%d" % (speaker, act, topic, salt)
    return (zlib.crc32(key.encode("utf-8")) % 10_000) / 10_000.0


def render(ev: SemanticEvent, *, speaker_name: str = "") -> str:
    """把语义事件渲染成一句人话(确定、可回放)。

    speaker_name 只在 REPORT 里用于“听{who}说” —— 必须是真名(来自 slots/调用方),
    不许在渲染时引入新的实体。
    """
    spec = _POOLS.get(ev.act)
    if spec is None:
        return ""
    day = ev.tick // 1440
    topic = f"{ev.topic}|{day}"

    def seg(name: str) -> str:
        pool = spec[name]
        idx = int(_pick(ev.speaker, ev.act, topic, _SALT[name]) * len(pool))
        text = pool[min(idx, len(pool) - 1)]
        return _fill(text, ev.slots, speaker_name)
    return (seg("opener") + seg("core") + seg("tail")).strip()


def _fill(template: str, slots: Mapping[str, Any], speaker_name: str) -> str:
    """填槽。缺失的槽位留空(不报错) —— 塌了就少说几个字, 不能说错。"""
    if "{" not in template:
        return template
    out = template
    for key, value in sorted(slots.items()):
        out = out.replace("{%s}" % key, str(value))
    out = out.replace("{who}", speaker_name)
    # 没填上的槽位整个去掉(不留下 "{item}" 这种东西)
    while "{" in out and "}" in out:
        a = out.index("{")
        b = out.find("}", a)
        if b < 0:
            break
        out = out[:a] + out[b + 1:]
    return out


def pick_retellable(rows: Sequence[Mapping[str, Any]], *, home: str,
                    knows) -> Mapping[str, Any] | None:
    """从记忆里挑一件【值得转述】的事(= REPORT)。

    为什么需要它: 语义事件(刚看到的意外)冒完泡就没了, 但**新闻要能带走** ——
    不然“在城里传开”就无从发生。所以转述的来源是**记忆**, 不是刚发生的事。

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
# 事件构造(调用方给【真值】; 这里只负责组装, 不做任何判断)
# ---------------------------------------------------------------------------
def _event(seq: int, tick: int, speaker: str, act: str, topic: str,
           slots: Mapping[str, Any], *, source: str = "",
           intensity: float = 0.0) -> SemanticEvent:
    return SemanticEvent(
        event_id=f"sem{seq}", tick=tick, speaker=speaker, act=act,
        topic=topic, slots=dict(slots), source=source,
        intensity=round(float(intensity), 3))


_counter = {"n": 0}


def _next_seq() -> int:
    _counter["n"] += 1
    return _counter["n"]


def money_word(v: float) -> str:
    """价格 → 人话("5块" / "免费")。只吃真值, 不做判断。"""
    v = float(v)
    if v <= 0.0:
        return "免费"
    return ("%d块" % int(round(v))) if abs(v - round(v)) < 1e-6 else ("%g块" % v)


## 失败原因 → 人话(引擎给的 reason 直接可用, 这里只统一措辞)
FAIL_WORDS: Mapping[str, str] = {
    "钱不够": "钱不够", "库存不足": "没货了", "非卖品": "人家不卖",
    "在售商品·需购买": "得先付钱", "已空(stock=0)": "卖光了",
    "已被他人占用": "有人占着", "目标不存在": "找不到了",
    "目标不在此地": "跑错地方了", "目标已达上限": "排不进去",
}


def fail_word(why: str) -> str:
    """把引擎的失败原因说成人话(带括号的去掉括号部分)。"""
    why = str(why or "").strip()
    if why in FAIL_WORDS:
        return FAIL_WORDS[why]
    head = why.split("(")[0].strip()
    return FAIL_WORDS.get(head, head or "没办成")


def denied(tick: int, speaker: str, why: str, *, topic: str = "",
           intensity: float = 0.4) -> SemanticEvent:
    """我被拒绝了: 没钱 / 没货 / 有人占着 / 白跑一趟。"""
    return _event(_next_seq(), tick, speaker, "DENIED",
                  topic or "denied", {"why": why}, intensity=intensity)


def state(tick: int, speaker: str, signal: str, need_word: str,
          intensity: float = 0.0) -> SemanticEvent:
    return _event(_next_seq(), tick, speaker, "STATE",
                  f"state.{signal}", {"need": need_word},
                  intensity=intensity)


def intent(tick: int, speaker: str, goal: str, why: str,
           topic: str = "", intensity: float = 0.0) -> SemanticEvent:
    return _event(_next_seq(), tick, speaker, "INTENT",
                  topic or "intent", {"goal": goal, "why": why},
                  intensity=intensity)


def surprise(tick: int, speaker: str, item_id: str, item_name: str,
             was: str, now: str, *, fact: Mapping[str, Any] | None = None,
             topic: str = "", intensity: float = 0.0) -> SemanticEvent:
    """fact 是【真值】(item_id/located/price/afford/…) —— 传播时听者抄它,
    措辞时不参与(只填模板里出现过的槽)。"""
    slots = {"item": item_name, "was": was, "now": now}
    slots.update(fact or {})
    return _event(_next_seq(), tick, speaker, "SURPRISE",
                  topic or f"item.{item_id}", slots, intensity=intensity)


def doubt(tick: int, speaker: str, item_id: str, item_name: str, who: str,
          was: str, now: str, *, fact: Mapping[str, Any] | None = None,
          source: str = "", intensity: float = 0.0) -> SemanticEvent:
    """信念被现实推翻: 这条记忆本来是【别人说的】(source=who) —— 最值得说的事。"""
    slots = {"item": item_name, "who": who, "was": was, "now": now}
    slots.update(fact or {})
    return _event(_next_seq(), tick, speaker, "DOUBT", f"item.{item_id}", slots,
                  source=source or who, intensity=intensity)


def report(tick: int, speaker: str, item_id: str, item_name: str,
           now: str, who: str = "", *,
           fact: Mapping[str, Any] | None = None) -> SemanticEvent:
    """转述: 听者头上的那条“听说…”。"""
    slots = {"item": item_name, "now": now}
    slots.update(fact or {})
    return _event(_next_seq(), tick, speaker, "REPORT",
                  f"item.{item_id}", slots, source=who)


## 需求信号 → 人话(渲染用; 只映射, 不判断)
NEED_WORDS: Mapping[str, str] = {
    "hunger": "饿", "energy": "困", "bladder": "憋",
}
GOAL_WORDS: Mapping[str, tuple[str, str]] = {
    # signal -> (去干什么, 为什么)
    "hunger": ("找点吃的", "有点饿"),
    "energy": ("歇一会儿", "累了"),
    "bladder": ("去趟厕所", "憋得慌"),
}
