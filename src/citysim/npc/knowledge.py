"""knowledge —— Fact/Source/双层知识库(M5 5.1)。

ArchetypeKB = 共享只读原型(INJECTED); KnowledgeBase = 每 NPC: archetype +
overlay(个体习得/覆盖) + tombstones(证伪的 fact_id)。

语义(m5-rectify T1/T2/T4/T7 后):
- fact_id 命名空间: 原型 `a:{subject}|{relation}|{n}`、overlay `o:{subject}|{relation}|{seq}`,
  refute/fact() 不再跨层误伤。
- query 为"逐事实覆盖": 按 (subject, relation, obj) 键合并 —— 原型(未 tombstone)
  先入, overlay 同键覆盖、不同键并存; 不再"overlay 一命中就整层遮蔽原型"。
- learn 为 upsert: 同键已存在且未 tombstone → 原位替换(取更高 confidence、刷新
  tick、保留 id); 否则新建。tick 显式传入, decay 不再兼任学习时钟。
- decay 按每 fact 的衰减基线(学习/上次衰减 tick)推进; half_life_ticks 必传。
- conf<0.05 视为不知道。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from citysim.core.types import SourceKind

_ARCHETYPES_DIR = Path(__file__).resolve().parents[3] / "config" / "archetypes"

_KNOWN_RELATIONS = ("located_at", "affords", "price_of")
CONF_UNKNOWN = 0.05
# 衰减只作用于经验习得(OBSERVED/TOLD), 注入常识(INJECTED)不变
_DECAYABLE_KINDS = ("OBSERVED", "TOLD")


def _obj_key(obj: Any) -> tuple[str, Any]:
    """事实合并键的 obj 部分: 字符串/数值按值, 其余按 repr。"""
    if isinstance(obj, str):
        return ("str", obj)
    if isinstance(obj, (int, float)):
        return ("num", float(obj))
    return ("repr", repr(obj))


def _arch_fact_id(subject: str, relation: str, n: int) -> str:
    return f"a:{subject}|{relation}|{n}"


def _ovl_fact_id(subject: str, relation: str, seq: int) -> str:
    return f"o:{subject}|{relation}|{seq}"


@dataclass(frozen=True, slots=True)
class Source:
    kind: SourceKind
    ref: tuple[str, ...] = ()   # TOLD→(npc_id, f:origin_id); INFERRED→前提fact_ids


@dataclass(frozen=True, slots=True)
class Fact:
    fact_id: str
    subject: str
    relation: str
    obj: Any
    confidence: float
    source: Source
    tick_learned: int = 0
    value: float = 0.0                       # affords 的数值(提供多少)


class ArchetypeKB:
    """共享只读原型知识。"""

    def __init__(self, facts: Iterable[Fact]) -> None:
        self.facts: tuple[Fact, ...] = tuple(facts)

    def query(self, subject: str | None = None,
              relation: str | None = None) -> tuple[Fact, ...]:
        out = []
        for f in self.facts:
            if subject is not None and f.subject != subject:
                continue
            if relation is not None and f.relation != relation:
                continue
            if f.confidence < CONF_UNKNOWN:
                continue
            out.append(f)
        return tuple(out)

    def __repr__(self) -> str:  # pragma: no cover
        return f"ArchetypeKB({len(self.facts)} facts)"


class KnowledgeBase:
    """每 NPC 的双层知识库。"""

    def __init__(self, archetype: ArchetypeKB | None = None) -> None:
        self.archetype: ArchetypeKB = archetype or ArchetypeKB([])
        self.overlay: dict[str, Fact] = {}
        self.tombstones: set[str] = set()
        self._seq: dict[tuple[str, str], int] = {}
        # 每 fact 的衰减基线(学习/上次衰减 tick); 随 decay 推进
        self._decayed_at: dict[str, int] = {}

    # --- 查询 ---------------------------------------------------------
    def _merged(self, subject: str | None, relation: str | None
                ) -> dict[tuple, Fact]:
        """逐事实合并视图: 键=(subject, obj, relation)。overlay 覆盖同键原型。"""
        merged: dict[tuple, Fact] = {}
        for f in self.archetype.query(subject, relation):
            if f.fact_id in self.tombstones:
                continue
            merged[(_obj_key(f.subject), _obj_key(f.obj), f.relation)] = f
        for f in self.overlay.values():
            if f.fact_id in self.tombstones:
                continue
            if f.confidence < CONF_UNKNOWN:
                continue
            if subject is not None and f.subject != subject:
                continue
            if relation is not None and f.relation != relation:
                continue
            merged[(_obj_key(f.subject), _obj_key(f.obj), f.relation)] = f
        return merged

    def query(self, subject: str | None = None,
              relation: str | None = None) -> tuple[Fact, ...]:
        """逐事实覆盖语义: 返回合并视图, 排序 (-confidence, fact_id) 稳定。"""
        return tuple(sorted(self._merged(subject, relation).values(),
                            key=lambda f: (-f.confidence, f.fact_id)))

    def all_facts(self) -> tuple[Fact, ...]:
        """当前"相信"的全部事实(viz 等单一语义源; 与 query 一致, 键去重)。"""
        return self.query()

    def fact(self, fact_id: str) -> Fact | None:
        return (self.overlay.get(fact_id)
                or next((f for f in self.archetype.facts
                         if f.fact_id == fact_id), None))

    def subjects(self, relation: str) -> frozenset[str]:
        return frozenset(f.subject for f in self.query(relation=relation))

    def overlay_fact_ids(self) -> frozenset[str]:
        """当前 overlay 全部 fact_id(含低置信待衰亡)。供观察方 diff 新知识。"""
        return frozenset(self.overlay)

    # --- 写入 ---------------------------------------------------------
    def _replace_or_new(self, subject: str, relation: str, obj: Any,
                        confidence: float, source: Source, tick: int,
                        value: float = 0.0) -> Fact:
        """upsert: 同键活跃 overlay 存在 → 原位替换(m5-rectify N2)。

        规则(来源不降级、时间才刷新):
          new > old → 以新来源/新 conf 覆盖, 刷新 tick(新鲜证据);
          new == old → 保留原来源(避免 OBSERVED 被同值 TOLD 顶掉溯源根),
                       仅刷新 tick(再次见到/同强度强化);
          new <  old → 低置信弱消息不覆盖、不刷新(防止 TOLD 0.8 把亲眼 1.0
                       的 conf 拉低或把衰减基线延长)。
        value 随事实一起更新(物品固有属性, 新观察到的即当前值)。
        """
        for f in self.overlay.values():
            if (f.subject == subject and f.relation == relation
                    and _obj_key(f.obj) == _obj_key(obj)
                    and f.fact_id not in self.tombstones):
                newc = max(0.0, min(1.0, float(confidence)))
                if newc > f.confidence:
                    up = Fact(fact_id=f.fact_id, subject=subject,
                              relation=relation, obj=obj, confidence=newc,
                              source=source, tick_learned=tick, value=value)
                    base = tick
                elif newc == f.confidence:
                    up = Fact(fact_id=f.fact_id, subject=subject,
                              relation=relation, obj=obj,
                              confidence=f.confidence, source=f.source,
                              tick_learned=tick, value=value)
                    base = tick
                else:
                    up = f                              # 弱消息: 完全不改
                    base = self._decayed_at.get(f.fact_id, f.tick_learned)
                self.overlay[f.fact_id] = up
                self._decayed_at[f.fact_id] = base
                return up
        seq = self._seq.get((subject, relation), 0) + 1
        self._seq[(subject, relation)] = seq
        fid = _ovl_fact_id(subject, relation, seq)
        conf = max(0.0, min(1.0, float(confidence)))
        fact = Fact(fact_id=fid, subject=subject, relation=relation, obj=obj,
                    confidence=conf, source=source, tick_learned=tick,
                    value=value)
        self.overlay[fid] = fact
        self._decayed_at[fid] = tick
        return fact

    def learn(self, subject: str, relation: str, obj: Any,
              confidence: float, source: Source, tick: int = 0,
              value: float = 0.0) -> Fact:
        if relation not in _KNOWN_RELATIONS:
            raise ValueError(
                f"未知关系 {relation!r} (已知: {_KNOWN_RELATIONS})")
        return self._replace_or_new(subject, relation, obj, confidence,
                                    source, tick, value)

    def refute(self, fact_id: str) -> None:
        """证伪(原型/已学事实) → 进 tombstones, 并从 overlay 删同名学习。"""
        self.tombstones.add(fact_id)
        self.overlay.pop(fact_id, None)
        self._decayed_at.pop(fact_id, None)

    def decay(self, now_tick: int, half_life_ticks: int) -> None:
        """仅 OBSERVED/TOLD 衰减: 每 fact 从学习/上次衰减基线 c*=0.5**(Δt/hl)。

        half_life_ticks 必传(运行时统一 config)。本方法不再兼任"学习时钟"。
        """
        for fid, f in list(self.overlay.items()):
            if f.source.kind not in _DECAYABLE_KINDS:
                continue
            base = self._decayed_at.get(fid, f.tick_learned)
            dt = max(0, now_tick - base)
            if dt <= 0:
                continue
            factor = 0.5 ** (dt / half_life_ticks)
            c = f.confidence * factor
            if c < CONF_UNKNOWN:
                del self.overlay[fid]
                self._decayed_at.pop(fid, None)
            else:
                self.overlay[fid] = Fact(
                    fact_id=f.fact_id, subject=f.subject,
                    relation=f.relation, obj=f.obj,
                    confidence=c, source=f.source,
                    tick_learned=f.tick_learned, value=f.value)
                self._decayed_at[fid] = now_tick

    # --- 追溯 ---------------------------------------------------------
    def trace(self, fact_id: str) -> tuple[Fact, ...]:
        """沿 source.ref(fact_ids) 递归展开成一棵(前序)事实树。"""
        seen: set[str] = set()
        out: list[Fact] = []

        def _walk(fid: str) -> None:
            if fid in seen:
                return
            seen.add(fid)
            f = self.fact(fid)
            if f is None:
                return
            out.append(f)
            for rid in f.source.ref:
                if rid.startswith("f:"):
                    _walk(rid[2:])

        _walk(fact_id)
        return tuple(out)

    def top_overlay_fact(self) -> "Fact | None":
        """传闻用: overlay 里 confidence 最高的一条(OBSERVED/TOLD/INFERRED)。"""
        candidates = [f for f in self.overlay.values()
                      if f.source.kind != "INJECTED"]
        if not candidates:
            return None
        return max(candidates, key=lambda f: f.confidence)

    def knows(self, subject: str, relation: str, obj: Any,
              min_conf: float = 0.3) -> bool:
        return any(f.subject == subject and f.relation == relation
                   and _obj_key(f.obj) == _obj_key(obj)
                   and f.confidence >= min_conf
                   for f in self.query(subject=subject, relation=relation))

    def __repr__(self) -> str:  # pragma: no cover
        return (f"KnowledgeBase(overlay={len(self.overlay)}, "
                f"tomb={len(self.tombstones)})")


# ----------------------------------------------------------------------
# Archetype 加载(config/archetypes/*.json, 5.2)
# ----------------------------------------------------------------------
def _facts_from(data: dict) -> tuple[str, tuple[Fact, ...]]:
    """单份 archetype json -> (archetype 名, facts)。id 命名空间 a:。"""
    name = data["archetype"]
    facts = tuple(
        Fact(fact_id=_arch_fact_id(k["subject"], k["relation"], i + 1),
             subject=k["subject"], relation=k["relation"], obj=k["obj"],
             confidence=float(k.get("confidence", 1.0)),
             source=Source(kind="INJECTED", ref=(name,)),
             value=float(k.get("value", 0.0)))
        for i, k in enumerate(data.get("knowledge", [])))
    return name, facts


def load_archetype(path: str | Path) -> tuple[dict[str, float], ArchetypeKB]:
    """读单个 archetype json -> (personality, ArchetypeKB)。"""
    with Path(path).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    _, facts = _facts_from(data)
    return (dict(data.get("personality", {})),
            ArchetypeKB(facts))


def load_archetypes(directory: str | Path | None = None) -> dict[str, ArchetypeKB]:
    """读目录全部 archetype json(与 load_archetype 同一解析)。"""
    d = _ARCHETYPES_DIR if directory is None else Path(directory)
    out: dict[str, ArchetypeKB] = {}
    for p in sorted(d.glob("*.json")):
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        name, facts = _facts_from(data)
        out[name] = ArchetypeKB(facts)
    return out

