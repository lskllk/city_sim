"""knowledge —— Fact/Source/单层知识库(M5 5.1, 单层化后)。

单层语义(去掉共享 INJECTED 原型层后): 每 NPC 只持一份 overlay(个体习得)。
所有知识都来自 obs(OBSERVED) 或 told(TOLD)/推断(INFERRED), 无"出生常识"层。

- fact_id 命名空间: overlay `o:{subject}|{relation}|{seq}`; refute 走 tombstone。
- query 直接取 overlay(conf>=CONF_UNKNOWN 且未 tombstone), 不再有原型合并。
- learn 为 upsert: 同键已存在且未 tombstone → 原位替换(取更高 confidence、刷新
  tick、保留 id); 否则新建。tick 显式传入。
- decay 按每 fact 的衰减基线推进; half_life_ticks 必传。
- conf<CONF_UNKNOWN 视为不知道。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from citysim.core.types import SourceKind

_KNOWN_RELATIONS = ("located_at", "affords", "price_of")
CONF_UNKNOWN = 0.05
_DECAYABLE_KINDS = ("OBSERVED", "TOLD")


def _obj_key(obj: Any) -> tuple[str, Any]:
    """事实合并键的 obj 部分: 字符串/数值按值, 其余按 repr。"""
    if isinstance(obj, str):
        return ("str", obj)
    if isinstance(obj, (int, float)):
        return ("num", float(obj))
    return ("repr", repr(obj))


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


class KnowledgeBase:
    """每 NPC 的单层知识库(overlay 是唯一事实集合)。"""

    def __init__(self) -> None:
        self.overlay: dict[str, Fact] = {}
        self.tombstones: set[str] = set()
        self._seq: dict[tuple[str, str], int] = {}
        # 每 fact 的衰减基线(学习/上次衰减 tick); 随 decay 推进
        self._decayed_at: dict[str, int] = {}

    # --- 查询 ---------------------------------------------------------
    def query(self, subject: str | None = None,
              relation: str | None = None) -> tuple[Fact, ...]:
        """单层: 取 overlay(conf>=CONF_UNKNOWN 且未 tombstone), 按 subject/relation 筛。"""
        out = []
        for f in self.overlay.values():
            if f.fact_id in self.tombstones:
                continue
            if f.confidence < CONF_UNKNOWN:
                continue
            if subject is not None and f.subject != subject:
                continue
            if relation is not None and f.relation != relation:
                continue
            out.append(f)
        return tuple(sorted(out, key=lambda f: (-f.confidence, f.fact_id)))

    def all_facts(self) -> tuple[Fact, ...]:
        """当前"相信"的全部事实(viz 等单一语义源; 与 query 一致)。"""
        return self.query()

    def fact(self, fact_id: str) -> Fact | None:
        return self.overlay.get(fact_id)

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
          new <  old → 低置信弱消息不覆盖、不刷新(防止弱消息拉低强证据
                       或把衰减基线延长)。
        value 随事实一起更新。
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
        """证伪 → 进 tombstones, 并从 overlay 删同名学习。"""
        self.tombstones.add(fact_id)
        self.overlay.pop(fact_id, None)
        self._decayed_at.pop(fact_id, None)

    def decay(self, now_tick: int, half_life_ticks: int) -> None:
        """仅 OBSERVED/TOLD 衰减: 每 fact 从学习/上次衰减基线 c*=0.5**(Δt/hl)。"""
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
        candidates = list(self.overlay.values())
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
