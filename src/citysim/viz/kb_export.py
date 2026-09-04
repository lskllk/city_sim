"""知识图导出(M5 5.4): JSON + DOT。"""
from __future__ import annotations

from citysim.npc.knowledge import CONF_UNKNOWN

_EDGE_COLOR = {"INJECTED": "gray", "OBSERVED": "green",
               "TOLD": "blue", "INFERRED": "orange"}


def _all_facts(kb):
    out = list(kb.overlay.values())
    out += [f for f in kb.archetype.facts if f.fact_id not in kb.tombstones]
    return [f for f in out if f.confidence >= CONF_UNKNOWN]


def export_kb_json(kb) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()

    def _add(kind: str, nid: str, label: str) -> None:
        if nid not in seen_nodes:
            seen_nodes.add(nid)
            nodes.append({"id": nid, "label": label, "kind": kind})

    for f in _all_facts(kb):
        _add("entity", f.subject, f.subject)
        if isinstance(f.obj, str) and f.obj:
            _add("concept", f.obj, f.obj)
        edges.append({
            "src": f.subject, "dst": f.obj, "relation": f.relation,
            "confidence": round(f.confidence, 3),
            "source_kind": f.source.kind, "tick": f.tick_learned,
        })
    return {"nodes": nodes, "edges": edges}


def export_kb_dot(kb) -> str:
    lines = ["digraph kb {"]
    for f in _all_facts(kb):
        color = _EDGE_COLOR.get(f.source.kind, "gray")
        lines.append(
            f'  "{f.subject}" -> "{f.obj}" '
            f'[label="{f.relation} c={f.confidence:.2f}" '
            f'color="{color}"];')
    lines.append("}")
    return "\n".join(lines)
