"""gateway —— 纯数据桥: 场景 JSON → 世界, 世界 → JSON。

    scenarios.py   场景 → (World + Systems + rng)   —— 只组装, 不做决策
    snapshot.py    世界 → dict                       —— 纯读投影

**没有传输, 没有游戏判断, 也没有台词模板。** FastAPI/WebSocket 在 `citysim/game/server.py`, 经营动作在 `citysim/game/actions.py`,
台词模板在 `citysim/game/lines.py`。这里只依赖 stdlib + citysim, 所以
`citysim.api` 能安全地把它挂到门面上(内核保持零第三方依赖)。

铁律(见 design 第三节): snapshot 禁止 build_percept(会清空 NPC 信箱) /
禁止碰 rng_pool / 禁止写内核字段; 事件只从 systems.ui_events 尾读。

注意: 本包【不可以】import `citysim.api` —— api 反过来依赖本包, 会成环。
gateway 是内核的一部分, 不是门外的消费者。
"""
