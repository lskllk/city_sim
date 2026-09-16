"""WP-01: `core/ports.py` 契约(WorldPort / Ack / Deny / Grant)。

只钉三件事:
  1. 契约层是中立层 —— 不 import world / npc;
  2. 响应是可序列化纯数据(回放/测试);
  3. 端口的形状(动词齐全, 没有数据句柄)。
"""
from __future__ import annotations

import dataclasses
from typing import get_type_hints

import citysim.core.ports as ports


def test_contract_layer_does_not_import_world_or_npc() -> None:
    """契约层不得依赖 world / npc(否则中立层就没了)。"""
    src = (ports.__file__ or "")
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "import citysim.world" not in text
    assert "from citysim.world" not in text
    assert "import citysim.npc" not in text
    assert "from citysim.npc" not in text


def test_value_objects_are_frozen_and_comparable() -> None:
    a = ports.Grant(handle="h1", entity_id="food", signal="hunger",
                    value=0.5, duration_ticks=20)
    b = ports.Grant(handle="h1", entity_id="food", signal="hunger",
                    value=0.5, duration_ticks=20)
    assert a == b                                    # 可比较(回放要)
    assert dataclasses.asdict(a)["value"] == 0.5     # 可序列化
    try:
        a.value = 1.0                                 # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:                                             # pragma: no cover
        raise AssertionError("Grant 必须 frozen")


def test_deny_and_ack_shape() -> None:
    assert ports.Ack().ok is True
    assert ports.Ack(ok=False, reason="已满").reason == "已满"
    assert ports.Deny(reason="已空").reason == "已空"


def test_world_port_exposes_verbs_not_data() -> None:
    """端口只暴露动词; 不得出现把 world/entity 交出去的返回类型。"""
    hints = get_type_hints(ports.WorldPort.observe)
    assert hints["return"].__name__ == "Percept"
    for name in ("try_move", "try_take", "try_buy", "release", "consume",
                 "observe"):
        assert hasattr(ports.WorldPort, name), name
