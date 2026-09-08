"""知识图导出(M5 5.4): JSON + DOT。事实来源统一 kb.all_facts()。"""
from __future__ import annotations

_EDGE_COLOR = {"OBSERVED": "green",
               "TOLD": "blue", "INFERRED": "orange"}


def _add_node(nodes: list[dict], seen: set[str], nid: str, label: str,
              kind: str) -> None:
    if nid not in seen:
        seen.add(nid)
        nodes.append({"id": nid, "label": label, "kind": kind})


def export_kb_json(kb) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()
    for f in kb.all_facts():
        _add_node(nodes, seen, f.subject, str(f.subject), "entity")
        if isinstance(f.obj, str):
            _add_node(nodes, seen, f.obj, f.obj, "concept")
        else:  # 非 str obj(价格等字面量) → 字面量节点, 避免边悬空
            oid = f"lit:{f.obj!r}"
            _add_node(nodes, seen, oid, str(f.obj), "literal")
        edges.append({
            "src": f.subject, "dst": f.obj if isinstance(f.obj, str)
            else f"lit:{f.obj!r}", "relation": f.relation,
            "confidence": round(f.confidence, 3),
            "source_kind": f.source.kind, "tick": f.tick_learned,
        })
    return {"nodes": nodes, "edges": edges}


def export_kb_dot(kb) -> str:
    lines = ["digraph kb {"]
    for f in kb.all_facts():
        color = _EDGE_COLOR.get(f.source.kind, "gray")
        lines.append(
            f'  "{f.subject}" -> "{f.obj}" '
            f'[label="{f.relation} c={f.confidence:.2f}" '
            f'color="{color}"];')
    lines.append("}")
    return "\n".join(lines)

