# 08 — _kb_go_intent 跳过当前地点 + located_at 纠错

**What to build:** KB 说 X located_at 当前所在地但 X 不在视野（被搬走/原型错）时，NPC 每 30 tick"旅行"到原地打转，hunger 掉到 0（S4/S5 必触发）。修两处：① decide 跳过 `loc == 当前地点` 的源；② 感知对"KB 说 X 在此地、此地却看不到 X"refute located_at，让错误知识被纠正而非永远不去。

**Blocked by:** 04, 07

**Status:** ready-for-agent

- [ ] `_kb_go_intent` 对 `loc == percept.location_id` 的源 continue
- [ ] consolidate：当前地点感知不到 KB 声明的容器时 refute 其 located_at
- [ ] S4/S5 剧本不再原地打转（新增断言：无连续同地 move_to）
- [ ] 全量 pytest 绿
