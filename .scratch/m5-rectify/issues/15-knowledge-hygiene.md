# 15 — knowledge/viz/契约卫生批次

**What to build:** knowledge.py / viz / 契约层一批小硬伤：
- `learn` 的 `assert relation in _KNOWN_RELATIONS` 在 `-O` 下失效 → 改 `raise ValueError`
- `load_archetype / load_archetypes` 两份几乎相同解析 → 后者复用前者
- `kb_export.export_kb_json` 对非 str obj（如价格浮点）边悬空 → dst 统一 str(obj) 或节点 kind="literal"
- `Person.kb: Any` → TYPE_CHECKING 下 `KnowledgeBase | None` 强类型

**Blocked by:** 01, 04

**Status:** ready-for-agent

- [ ] 上述四项落地
- [ ] 全量 pytest 绿
