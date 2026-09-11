"""planner —— LLM 日计划生成器(接口骨架 + 规则模板降级)。

铁律(npc 层): 不 import world。世界状态由调用方以 PlannerInput(纯数据)注入。

设计:
- LLM 只\"生成计划\", 不执行; 输出经 schema + \"目标必须在记忆里\" 校验后才入库。
- 无 client / 抛错 / 非法输出 → 规则模板降级(保证不停摆)。
- 结果按输入指纹缓存 → 回放不重新调 API(确定性)。
- 计划条目 = (at_tick, 具体 Intent); target 只能取自该 NPC 记忆。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from citysim.core.types import Buy, Interact, MoveTo
from citysim.npc.schedule import PlanEntry


# ----------------------------------------------------------------------
# 输入快照(纯数据, 只含 NPC 已知/自身的东西)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class KnownItem:
    """NPC 记忆里的一行(计划只能引用这里的 item_id / located)。"""
    item_id: str
    located: str = ""
    afford: str = ""
    value: float = 0.0
    price: float = 0.0
    owner: str = ""
    stock: int = 0


@dataclass(frozen=True)
class PlannerInput:
    person_id: str
    home: str
    day_start_tick: int                        # 当天 0:00 的绝对 tick
    signals: Mapping[str, float] = field(default_factory=dict)
    money: float = 0.0
    known: tuple[KnownItem, ...] = ()
    failures: tuple[Mapping[str, Any], ...] = ()

    def known_ids(self) -> frozenset[str]:
        return frozenset(k.item_id for k in self.known)

    def known_locations(self) -> frozenset[str]:
        locs = {k.located for k in self.known if k.located}
        locs.add(self.home)
        return frozenset(locs)


@dataclass
class PlanResult:
    entries: list[PlanEntry]
    source: str = "template"                   # "llm" | "template"


class LLMClient(Protocol):
    """注入的 LLM 客户端: 给 prompt, 返回 JSON 文本(计划 spec)。"""
    def plan(self, prompt: str) -> str: ...


# ----------------------------------------------------------------------
# 时间: 支持标准时间 "HH:MM"(推荐) 或旧 at_minute(int, 0..1439)
# ----------------------------------------------------------------------
def parse_clock(s: str) -> int | None:
    """"HH:MM" → 当天分钟 0..1439; 非法返回 None。"""
    s = s.strip()
    hh, sep, mm = s.partition(":")
    if sep == "" or not (hh.isdigit() and mm.isdigit()):
        return None
    h, m = int(hh), int(mm)
    if 0 <= h < 24 and 0 <= m < 60:
        return h * 60 + m
    return None


def _at_minute(item: Mapping[str, Any]) -> int | None:
    """条目时间: 优先 'at'("HH:MM"), 兼容 'at_minute'(int, 0..1439)。"""
    if "at" in item:
        return parse_clock(str(item["at"]))
    v = item.get("at_minute")
    if isinstance(v, int) and 0 <= v < 1440:
        return v
    return None


# ----------------------------------------------------------------------
# 规则模板(降级路径)—— 只用已知目标, 保证能跑
# ----------------------------------------------------------------------
_MEALS: tuple[tuple[int, str], ...] = (
    (7 * 60, "hunger"), (12 * 60, "hunger"), (18 * 60, "hunger"),
)
_DRINKS: tuple[tuple[int, str], ...] = (
    (7 * 60, "thirst"), (12 * 60, "thirst"), (18 * 60, "thirst"),
)
_SLEEP: tuple[tuple[int, str], ...] = ((22 * 60, "energy"),)


def _pick(inp: PlannerInput, signal: str) -> KnownItem | None:
    """按需求选一个已知目标: 优先在家, 否则任意; 保持输入顺序(确定性)。"""
    cands = [k for k in inp.known if k.afford == signal and k.value > 0]
    if not cands:
        return None
    home = [k for k in cands if k.located == inp.home]
    return (home or cands)[0]


def template_plan(inp: PlannerInput) -> list[PlanEntry]:
    """规则模板: 三餐吃喝 + 晚上睡觉。缺失的目标直接跳过(交给 reflex 兜底)。"""
    entries: list[PlanEntry] = []
    seq = 0
    for minute, signal in (*_MEALS, *_DRINKS, *_SLEEP):
        item = _pick(inp, signal)
        if item is None:
            continue
        seq += 1
        entries.append(PlanEntry(
            f"t{seq}", inp.day_start_tick + minute, Interact(item.item_id)))
    entries.sort(key=lambda e: e.at_tick)      # 稳定: 同刻保持生成顺序
    return entries


# ----------------------------------------------------------------------
# LLM spec → PlanEntry(schema + 记忆校验)
# ----------------------------------------------------------------------
def entries_from_spec(spec: Any, inp: PlannerInput) -> list[PlanEntry]:
    """把 LLM 输出的 JSON spec 校验成 PlanEntry[]。

    spec: [{"id","at_minute","intent":"interact|move_to","target"|"dest"}, ...]
    非法(目标不在记忆 / 时间越界 / 结构错) → 丢弃该条(不崩)。
    """
    if not isinstance(spec, list):
        return []
    ids = inp.known_ids()
    locs = inp.known_locations()
    out: list[PlanEntry] = []
    for i, item in enumerate(spec):
        if not isinstance(item, dict):
            continue
        minute = _at_minute(item)
        if minute is None:
            continue
        eid = str(item.get("id") or f"llm{i}")
        kind = item.get("intent")
        if kind == "interact":
            target = item.get("target")
            if target not in ids:              # 红线: 只能引用记忆里的目标
                continue
            out.append(PlanEntry(eid, inp.day_start_tick + minute,
                                 Interact(str(target))))
        elif kind == "buy":
            target = item.get("target")
            if target not in ids:              # 只能买记忆里知道的商品
                continue
            qty = max(1, int(item.get("qty", 1)))
            out.append(PlanEntry(eid, inp.day_start_tick + minute,
                                 Buy(str(target), qty=qty)))
        elif kind == "move_to":
            dest = item.get("dest")
            if dest not in locs:
                continue
            out.append(PlanEntry(eid, inp.day_start_tick + minute,
                                 MoveTo(dest=str(dest))))
    out.sort(key=lambda e: e.at_tick)
    return out


def render_prompt(inp: PlannerInput) -> str:
    """构造 LLM prompt(确定性输出, 便于回放缓存)。"""
    payload = {
        "person_id": inp.person_id,
        "home": inp.home,
        "signals": {k: round(v, 3) for k, v in sorted(inp.signals.items())},
        "money": round(inp.money, 2),
        "known": [
            {"id": k.item_id, "at": k.located, "afford": k.afford,
             "value": round(k.value, 3), "price": k.price}
            for k in inp.known
        ],
        "failures": [dict(f) for f in inp.failures],
    }
    return (
        "你是城市 NPC 的日计划器。计划用\"和什么物体交互\"表达:"
        "每条写 {\"id\",\"at\",\"intent\":\"interact\","
        "\"target\":<known 里的 id>}; 执行器会自动先走到该物体的所在地。"
        "at 用标准时间 \"HH:MM\"(24 小时制)。"
        "只有\"不需任何交互的纯移动\"才用 "
        "{\"intent\":\"move_to\",\"dest\":<已知地点>}。\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def fingerprint(inp: PlannerInput) -> str:
    """输入指纹(缓存 key): 同输入 → 同计划, 回放不重调 API。"""
    payload = {
        "id": inp.person_id, "home": inp.home, "day": inp.day_start_tick,
        "signals": {k: round(v, 4) for k, v in sorted(inp.signals.items())},
        "money": round(inp.money, 2),
        "known": sorted(
            (k.item_id, k.located, k.afford, round(k.value, 4),
             round(k.price, 2), k.owner, k.stock) for k in inp.known),
        "failures": sorted(str(dict(f)) for f in inp.failures),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


# ----------------------------------------------------------------------
# 门面
# ----------------------------------------------------------------------
class Planner:
    """LLM 计划器: 有 client 走 LLM(带缓存), 否则/失败 → 规则模板。"""

    def __init__(self, client: LLMClient | None = None,
                 cache: dict[str, Any] | None = None) -> None:
        self._client = client
        self._cache = cache if cache is not None else {}

    def plan_day(self, inp: PlannerInput) -> PlanResult:
        if self._client is not None:
            key = fingerprint(inp)
            if key in self._cache:                       # 回放: 命中缓存
                return PlanResult(
                    entries_from_spec(self._cache[key], inp), "llm")
            try:
                raw = self._client.plan(render_prompt(inp))
                spec = json.loads(raw)
                entries = entries_from_spec(spec, inp)
                self._cache[key] = spec                  # 缓存原始响应
                return PlanResult(entries, "llm")
            except Exception:                            # 降级, 不停摆
                pass
        return PlanResult(template_plan(inp), "template")

    def plan_for_person(self, person, day_start_tick: int) -> PlanResult:
        """窄协议: 直接给 Person 生成次日计划(engine 0:00 调用)。"""
        return self.plan_day(build_input(person, day_start_tick))


def build_input(person, day_start_tick: int) -> PlannerInput:
    """从 Person(只读门面) 构造纯数据输入。npc 层内, 不触世界。"""
    known = tuple(
        KnownItem(
            item_id=r["item_id"], located=r.get("located", ""),
            afford=r.get("afford", ""), value=float(r.get("value", 0.0)),
            price=float(r.get("price", 0.0)), owner=r.get("owner", ""),
            stock=int(r.get("stock", 0)),
        )
        for r in person.memory_dicts()
    )
    return PlannerInput(
        person_id=person.person_id,
        home=person.home,
        day_start_tick=day_start_tick,
        signals=dict(person.signals),
        money=person.money,
        known=known,
        failures=tuple(person.failure_log()),
    )


class ScriptedPlanner(Planner):
    """固定日计划(演示/观察用): 每天把同一份脚本重新基准到 day_start。

    不查记忆/不校验(作者负责 target 存在)——它是"导演脚本", 不是 LLM 推理。
    用它替换 systems.planner 即可让场景"每天按同一张表"执行。
    """

    def __init__(self, plans: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        super().__init__(client=None)
        self._plans = {k: [dict(x) for x in v] for k, v in plans.items()}

    def plan_for_person(self, person, day_start_tick: int) -> PlanResult:
        spec = self._plans.get(person.person_id, [])
        entries: list[PlanEntry] = []
        for i, item in enumerate(spec):
            minute = _at_minute(item)
            if minute is None:
                continue
            eid = str(item.get("id") or f"s{i}")
            kind = item.get("intent")
            if kind == "interact" and item.get("target"):
                entries.append(PlanEntry(eid, day_start_tick + minute,
                                         Interact(str(item["target"]))))
            elif kind == "buy" and item.get("target"):
                qty = max(1, int(item.get("qty", 1)))
                entries.append(PlanEntry(eid, day_start_tick + minute,
                                         Buy(str(item["target"]), qty=qty)))
            elif kind == "move_to" and item.get("dest"):
                entries.append(PlanEntry(eid, day_start_tick + minute,
                                         MoveTo(dest=str(item["dest"]))))
        entries.sort(key=lambda e: e.at_tick)     # 稳定: 同刻保持脚本顺序
        return PlanResult(entries, "scripted")
