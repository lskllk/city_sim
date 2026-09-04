"""gateway —— 前端观察器(display_m5_ui G0~G4)。

snapshot.py = 纯读世界 → JSON。铁律见 design: 禁止 build_percept / 碰 rng /
写内核字段; 事件只从 systems.log_lines 尾读。本模块只依赖 stdlib + citysim。
"""
