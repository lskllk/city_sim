"""lines —— NPC 的话【怎么讲】(措辞层)。**游戏层的资产。**

    npc/semantic.py   说【什么】: 结构化事件 + 真值      ← 内核
    game/lines.py     说【成什么话】: 模板池 + 词表        ← 这里, 游戏层

**内核一句话都不会说。** 它只产结构化事件; 怎么把事件译成中文是一个可以
整个换掉的游戏资产 —— 换语言、换语气、接 LLM、换成美术手写文案, 动的都是
这个文件。内核不该有自己的文风。

怎么接上去: `build_snapshot(..., render_line=fn)` 注入一个 `fn(event) -> str`。
不注入 → 快照里的气泡只带结构化事件, 谁拿到谁自己渲染(前端/GDScript 都行)。

做法是最小集: 手写组合式模板池(**句子 = opener + core + tail**), 选哪一段由
speaker/act/topic/天 确定性地派生 —— 不掷骰子, 也不会每次都一样。

两条硬规矩:

  · **随机只允许发生在这一步。** 谁 / 什么行为 / 什么强度全是真值, 一个都不许编。
    这里用的是 crc32(不用内置 hash(), 每进程随机化) —— 措辞不该吃掉模拟的随机性,
    否则回放会飘。

  · **槽位里的 {xxx} 只能填【真值里有的东西】。** 缺槽就留空
    (塌了就少说几个字, 不能说错)。
"""
from __future__ import annotations

import zlib
from typing import Any, Mapping, Sequence

from citysim import api

# ---------------------------------------------------------------------------
# 词表: 真值 → 人话。渲染时才用, 传播时用不到。
# ---------------------------------------------------------------------------
def money_word(v: float) -> str:
    """价格 → 人话("5块" / "4.5块" / "免费")。只吃真值, 不做判断。"""
    v = float(v)
    if v <= 0.0:
        return "免费"
    return ("%d块" % int(round(v))) if abs(v - round(v)) < 1e-6 else ("%g块" % v)


def price_word(v: Any) -> str:
    """价格 → 人话; 不标价(<=0)时说"有货"而不是"免费"。

    和 money_word 分开是因为语义不同: 店里标 0 元是"有货但不卖钱"(非卖品/
    赠送), 而报告一件东西时 <=0 只是"没说价"。
    """
    if not isinstance(v, (int, float)):
        return str(v or "有货")
    return money_word(v) if float(v) > 0 else "有货"


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


NEED_WORDS: Mapping[str, str] = {
    "hunger": "饿", "energy": "困", "bladder": "憋",
}

GOAL_WORDS: Mapping[str, tuple[str, str, str]] = {
    # signal -> (去干什么, 眼前缺的理由, 未来缺(囤货)的理由)
    # ★ 措辞必须跟【真实驱动】一致: 不饿却去补货时, 不许说"我有点饿"。
    "hunger": ("找点吃的", "有点饿", "家里快没吃的了"),
    "energy": ("歇一会儿", "累了", "得补补觉"),
    "bladder": ("去趟厕所", "憋得慌", "该去一趟了"),
}


# ---------------------------------------------------------------------------
# 组合式模板池: 句子 = opener + core + tail
#   · 只写片段, 组合数是乘积(3~4 × 2~3 × 2~3 ≈ 12~30 种说法/act)
#   · core 里的 {xxx} 只能填【槽位里已有的真值】—— 渲染时不许新增实体
#   · 槽位里的词本身是中文(由 _words 从真值翻好), 保证不出现 "听说apple"
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
        # ★ 开场必须带【说话人名字】—— "谁给谁说的"是玩家最需要的一眼信息
        "opener": ("听{who}说", "{who}说", "{who}跟我说"),
        "core": ("{item}{now}", "{item}现在{now}"),
        "tail": ("", "。", "，不知道真的假的"),
    },
}


def _pick(speaker: str, act: str, topic: str, salt: int) -> float:
    """[0,1) 的确定性"随机"值: 同一个人说同一件事, 选中的片段是固定的。

    不用内置 hash()(每进程随机化), 也不用 rng —— 措辞不该吃掉模拟的随机性。
    带上"第几天" → 同一件事隔天再说会换个说法。
    """
    key = "%s|%s|%s|%d" % (speaker, act, topic, salt)
    return (zlib.crc32(key.encode("utf-8")) % 10_000) / 10_000.0


def _words(ev: api.SemanticEvent) -> dict:
    """把事件的【真值】翻成【措辞槽】(词)。act 不同, 翻法不同。

    这是"事实 / 表达"两层之间唯一的翻译点 —— 价格在这儿才变成 "8块",
    需求码在这儿才变成 "饿", 引擎的失败原因在这儿才变短。
    """
    s: dict[str, Any] = dict(ev.slots)
    if ev.act == "INTENT":
        words = GOAL_WORDS.get(str(s.pop("afford", "")))
        if words is None:
            return {}
        future = str(s.pop("driver", "")) == "future"
        s["goal"] = words[0]
        s["why"] = words[2] if future else words[1]
    elif ev.act == "DENIED":
        s["why"] = fail_word(str(s.get("why", "")))
    elif ev.act == "REPORT":
        s["now"] = price_word(s.get("now"))
    elif ev.act == "STATE":
        if "need" in s:
            s["need"] = NEED_WORDS.get(str(s["need"]), s["need"])
    else:                                   # SURPRISE / DOUBT
        for k in ("was", "now"):
            if isinstance(s.get(k), (int, float)):
                s[k] = money_word(s[k])
    return s


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


def render(ev: api.SemanticEvent, *, speaker_name: str = "",
           ticks_per_day: int = 1440) -> str:
    """把语义事件渲染成一句人话(确定、可回放)。

    speaker_name 只在 {who} 没进槽位时兜底 —— 现在 REPORT/DOUBT 都把 who 放进
    槽位了, 所以基本用不上(留着是为了兼容老调用)。
    """
    if ev.act == "SAY":
        # 说者那半句有自己的池子和哈希键(与历史行为一致), 不走模板管
        s = ev.slots
        return say_line(str(s.get("to", "")), str(s.get("item", "")),
                        s.get("now"))
    spec = _POOLS.get(ev.act)
    if spec is None:
        return ""
    slots = _words(ev)
    if not slots:
        return ""                            # 翻不出词(如没有对应词表的需求)
    day = ev.tick // max(1, int(ticks_per_day))   # 措辞轮换的日界
    topic = f"{ev.topic}|{day}"

    def seg(name: str) -> str:
        pool = spec[name]
        idx = int(_pick(ev.speaker, ev.act, topic, _SALT[name]) * len(pool))
        text = pool[min(idx, len(pool) - 1)]
        return _fill(text, slots, speaker_name)
    return (seg("opener") + seg("core") + seg("tail")).strip()


# 说者那半句气泡: "→ 林静：简餐8块"。不是语义事件(不含新信息),
# 只是把"谁给谁说"画出来 —— 所以只做措辞, 不进 event 队列。
SAY_POOL: tuple[str, ...] = ("→ {to}：{item}{now}", "跟{to}说：{item}{now}",
                             "{to}，{item}{now}")


def say_line(to_name: str, item_name: str, now: Any) -> str:
    """说者头顶那半句。措辞确定(用话题哈希), 不掷骰子。"""
    word = price_word(now)
    slots = {"to": to_name, "item": item_name, "now": word}
    key = f"{to_name}|{item_name}|{word}"
    idx = int(_pick(key, "SAY", "out", 7) * len(SAY_POOL))
    return _fill(SAY_POOL[min(idx, len(SAY_POOL) - 1)], slots, "")


# ---------------------------------------------------------------------------
# 注入点: 把它交给内核的快照投影
# ---------------------------------------------------------------------------
def renderer_for(cfg):
    """做成内核要的形状 `fn(event) -> str`, 把 cfg 绑进去。

    内核只知道这个接口(gateway/snapshot.build_snapshot(render_line=...)),
    不知道背后是模板池、另一个语言、还是 LLM。
    """
    tpd = int(getattr(cfg, "ticks_per_day", 1440) or 1440)
    return lambda ev: render(ev, ticks_per_day=tpd)
