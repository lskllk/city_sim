"""knowledge —— Fact/Source/双层知识库(M5 5.1)。

ArchetypeKB = 共享只读原型(INJECTED); KnowledgeBase = 每 NPC: archetype +
overlay(个体习得/覆盖) + tombstones(证伪的原型 fact_id)。
语义: overlay 优先, tombstone 屏蔽原型; confidence<0.05 视为不知道。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from citysim.core.types import SourceKind

_ARCHETYPES_DIR = Path(__file__).resolve().parents[3] / "config" / "archetypes"

_KNOWN_RELATIONS = ("contains", "sells", "located_at", "price_of", "is_a")
CONF_UNKNOWN = 0.05


@dataclass(frozen=True, slots=True)
class Source:
    kind: SourceKind
    ref: tuple[str, ...] = ()       # TOLD→(npc_id,); INFERRED→前提fact_ids


@dataclass(frozen=True, slots=True)
class Fact:
    fact_id: str
    subject: str
    relation: str
    obj: Any
    confidence: float
    source: Source
    tick_learned: int = 0

    @property
    def root_sources(self) -> tuple[str, ...]:
        """追溯链根: 对 INJECTED/OBSERVED 返回自身; 递归由 export 展开。"""
        return ()


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


def _gen_fact_id(subject: str, relation: str, seq: int) -> str:
    return f"{subject}|{relation}|{seq}"


class KnowledgeBase:
    """每 NPC 的双层知识库。"""

    def __init__(self, archetype: ArchetypeKB | None = None,
                 *, now_tick: int = 0) -> None:
        self.archetype: ArchetypeKB = archetype or ArchetypeKB([])
        self.overlay: dict[str, Fact] = {}
        self.tombstones: set[str] = set()
        self._seq: dict[tuple[str, str], int] = {}
        self._now = now_tick

    # --- 查询 ---------------------------------------------------------
    def query(self, subject: str | None = None,
              relation: str | None = None) -> tuple[Fact, ...]:
        """overlay 优先; tombstone 屏蔽原型; conf<0.05 视为不知。"""
        ov = [f for f in self.overlay.values()
              if (subject is None or f.subject == subject)
              and (relation is None or f.relation == relation)
              and f.confidence >= CONF_UNKNOWN]
        if ov:
            return tuple(sorted(ov, key=lambda f: -f.confidence))
        arch = [f for f in self.archetype.query(subject, relation)
                if f.fact_id not in self.tombstones]
        return tuple(sorted(arch, key=lambda f: -f.confidence))

    def fact(self, fact_id: str) -> Fact | None:
        return (self.overlay.get(fact_id)
                or next((f for f in self.archetype.facts
                         if f.fact_id == fact_id), None))

    def subjects(self, relation: str) -> frozenset[str]:
        return frozenset(f.subject for f in self.query(relation=relation))

    # --- 写入 ---------------------------------------------------------
    def _new_fact(self, subject: str, relation: str, obj: Any,
                  confidence: float, source: Source) -> Fact:
        seq = self._seq.get((subject, relation), 0) + 1
        self._seq[(subject, relation)] = seq
        return Fact(fact_id=_gen_fact_id(subject, relation, seq),
                    subject=subject, relation=relation, obj=obj,
                    confidence=max(0.0, min(1.0, confidence)),
                    source=source, tick_learned=self._now)

    def learn(self, subject: str, relation: str, obj: Any,
              confidence: float, source: Source) -> Fact:
        assert relation in _KNOWN_RELATIONS, f"未知关系 {relation}"
        fact = self._new_fact(subject, relation, obj, confidence, source)
        self.overlay[fact.fact_id] = fact
        return fact

    def refute(self, fact_id: str) -> None:
        """证伪(原型/已学事实) → 进 tombstones, 并从 overlay 删同名学习。"""
        self.tombstones.add(fact_id)
        self.overlay.pop(fact_id, None)

    def decay(self, now_tick: int, half_life_ticks: int = 20160) -> None:
        """仅 overlay 中 OBSERVED/TOLD 衰减: c *= 0.5**(Δt/half_life)。"""
        dt = max(0, now_tick - self._now)
        self._now = now_tick
        if dt <= 0:
            return
        factor = 0.5 ** (dt / half_life_ticks)
        for fid, f in list(self.overlay.items()):
            if f.source.kind in ("OBSERVED", "TOLD"):
                c = f.confidence * factor
                if c < CONF_UNKNOWN:
                    del self.overlay[fid]
                else:
                    self.overlay[fid] = Fact(
                        fact_id=f.fact_id, subject=f.subject,
                        relation=f.relation, obj=f.obj,
                        confidence=c, source=f.source,
                        tick_learned=f.tick_learned)

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

    def __repr__(self) -> str:  # pragma: no cover
        return f"KnowledgeBase(overlay={len(self.overlay)}, tomb={len(self.tombstones)})"


# ----------------------------------------------------------------------
# Archetype 加载(config/archetypes/*.json, 5.2)
# ----------------------------------------------------------------------
def load_archetype(path: str | Path) -> tuple[dict[str, float], ArchetypeKB]:
    """读单个 archetype json -> (personality, ArchetypeKB)。

    知识统一打 Source(kind="INJECTED", ref=(archetype_name,))。
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    name = data["archetype"]
    facts = []
    for i, k in enumerate(data.get("knowledge", [])):
        facts.append(Fact(
            fact_id=_gen_fact_id(k["subject"], k["relation"], i + 1),
            subject=k["subject"], relation=k["relation"], obj=k["obj"],
            confidence=float(k.get("confidence", 1.0)),
            source=Source(kind="INJECTED", ref=(name,)),
        ))
    return (dict(data.get("personality", {})),
            ArchetypeKB(facts))


def load_archetypes(directory: str | Path | None = None) -> dict[str, ArchetypeKB]:
    d = _ARCHETYPES_DIR if directory is None else Path(directory)
    out: dict[str, ArchetypeKB] = {}
    for p in sorted(d.glob("*.json")):
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        facts = [Fact(fact_id=_gen_fact_id(k["subject"], k["relation"], i + 1),
                      subject=k["subject"], relation=k["relation"],
                      obj=k["obj"], confidence=float(k.get("confidence", 1.0)),
                      source=Source(kind="INJECTED", ref=(data["archetype"],)))
                 for i, k in enumerate(data.get("knowledge", []))]
        out[data["archetype"]] = ArchetypeKB(facts)
    return out

