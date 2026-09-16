# WP-01 `core/ports.py` 契约

- 状态：done
- 阶段：Step 1
- 依赖：WP-00（选项不影响接口形状）
- 大小：S

## 目标

在**中立层**（`core/`，`npc/` 与 `world/` 都能 import）定义 world→NPC 的唯一契约。
`npc/` 只依赖这里的抽象，不 import `citysim.world`（铁律 5）。

## 改动

新增 `src/citysim/core/ports.py`：

```python
class WorldPort(Protocol):
    def observe(self, pid: str) -> Percept: ...
    def try_move(self, pid: str, dest: str) -> Ack: ...
    def try_take(self, pid: str, entity_id: str) -> Grant | Deny: ...
    def try_buy(self, pid: str, item_id: str, qty: int) -> Ack: ...   # 异步: 只表示"已入队"
    def release(self, pid: str, handle: str) -> Ack: ...
    def consume(self, pid: str, handle: str) -> Ack: ...
```

值对象（frozen dataclass）：

```python
@dataclass(frozen=True)
class Ack:   ok: bool; reason: str = ""
@dataclass(frozen=True)
class Deny:  reason: str
@dataclass(frozen=True)
class Grant:
    handle: str                 # world 签发的持有凭证(不透明)
    entity_id: str
    signal: str                 # "hunger"
    value: float
    duration_ticks: int
    pending: tuple[dict, ...] = ()   # on_start 编译结果(结构化, 不用 op 字符串)
    on_done: tuple[dict, ...] = ()   # on_complete 编译结果
```

## 验收

- `core/ports.py` 不 import `citysim.world`、不 import `citysim.npc`。
- `tests/test_import_layers.py` 仍绿。
- 单元测试：`Grant`/`Deny` 可 `dataclasses.asdict`、可比较（回放要）。

## 风险

- `Percept` 从 `core/types.py` 引入 → 注意不要造循环 import（types 不依赖 ports）。
- `handle` 的生成/校验规则留到 WP-02/14，本票只定字段。
