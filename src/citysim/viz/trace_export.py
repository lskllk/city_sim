"""决策追溯链导出(M5 5.4)。"""
from __future__ import annotations


def export_trace_chain(kb, used_fact_ids) -> dict:
    """used_fact_ids -> 各 fact -> source.ref 递归展开(fact 树前序)。"""
    facts = []
    seen: set[str] = set()
    for fid in used_fact_ids:
        for f in kb.trace(fid):
            if f.fact_id in seen:
                continue
            seen.add(f.fact_id)
            facts.append({
                "id": f.fact_id, "subject": f.subject,
                "relation": f.relation, "obj": f.obj,
                "confidence": round(f.confidence, 3),
                "source_kind": f.source.kind, "source_ref": list(f.source.ref),
                "tick": f.tick_learned,
            })
    return {"facts": facts}
