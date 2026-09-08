# World ↔ Person 解耦契约（重设计草案）

> 状态：**设计草案，未实现**。目标：把"物理世界"与"Person"彻底解耦，为换新 Person 开路。
> 核心一句话：**上帝(World)全知地执行"过程"，但只改世界物理、只发事件，绝不写 Person；Person 只消化事件、产出意图。**

---

## 1. 原则（三条硬规则）
1. **上帝视角 = World（全知执行器）**：它持有全部物理，跑移动/交互/成交这些"过程"。世界不存在"它不能知道的事"。
2. **上帝只改"世界物理"，不改 Person**：执行移动时改的是 World 的位置表，不是 Person 字段；后果一律用**事件**投送。
3. **依赖单向**：`world → types → person`；person 永不 import world。交换物全是**不可变值**。

---

## 2. 状态归属裁定
| 状态 | 归谁 | 说明 |
|---|---|---|
| 实体 / 库存 / 营业 / **真实位置** | **World** | 物理真源 |
| 可交互(claim/占用/耗时/移动推进) | **World** | 上帝仲裁/执行 |
| 生理 signals / 钱 / 记忆 / "以为位置" | **Person** | 内心状态，自持私有 |
| "该何时再想"(定时重评唤醒) | **Person 自报 next_review** | 世界只维护按各自自报的唤醒队列; 基于自身清醒度/急迫度 |
| 身体每 tick 演化(心跳/代谢) | 世界每 tick **广播** → Person 内部做 | 上帝不改 signals，只发节拍; Person 没在想时身体照常演化 |
| 行动完成/失败(即时唤醒) | 世界动作结束 → 事件唤醒 | Person 可即时决定是否 re-think |

> 关键：Person **不持有真实坐标**。它只有"以为的 located"（由 Percept/事件更新，可能滞后）。世界要移动 NPC = 改自己的位置表。

---

## 3. 数据契约（core.types，最小可复用集）
现状 `types.py` 大多已具备，微调即可：
- `EntityView` —— 一个可交互物体对外的**只读快照**（现成）。
- `Percept` —— 世界按 NPC 位置组装的感知包：`location`(我在哪，由世界算好)、`visible`(附近物体)、`events`(信箱事件)、`tick/hour`。
- `Intent` —— `Idle | MoveTo(dest) | Interact(target) | Buy(item)`（现成）。
- `Event` —— 结果事件，带 kind + payload（现成 EventBus）。

**需新增/调整**：把"我在哪"放进 Percept（感知时由世界给，Person 不另存世界坐标）。

---

## 4. 两侧协议（world 不 import npc）

```python
# ---------- World（上帝 / 全知执行器，持有物理）----------
class World(Protocol):
    def position_of(self, npc) -> Vec          # 物理位置(上帝持有)
    def sense_for(self, npc) -> Percept        # 依位置算可见 + 收集信箱事件
    def apply(self, npc, intent: Intent) -> list[Event]
        # 执行意图: move(渐进) / interact(claim+耗时) / buy(成交)
        # 只改世界物理; 返回要投给 npc 的结果事件
    def tick(self): ...                        # ① 广播心跳(全体身体演化) ② 唤醒队列按 Person 自报到点
                                               #    ③ 推进所有进行中的移动/交互(世界时钟)

# ---------- Person（具身能力：感知 + motion + 自我调度）----------
class Person(Protocol):
    def perceive(self, percept: Percept) -> None   # Sense: 消化(记记忆/更新以为状态)
    def act(self, ctx) -> Intent                    # Motion: 决定 MoveTo/Interact/Buy/Idle
    def next_review(self, now: Tick, cfg) -> Tick   # 自报下次"想"的时间(基于自身清醒/急迫/当前行动)
    def heartbeat(self, tick, cfg) -> None          # 身体每 tick 演化(世界广播, 上帝不改 signals)
```

---

## 5. 时序：单 tick 决策 / 多 tick 进行
```
[单 tick 决策]
  World.sense_for(npc) ──Percept──▶ Person.perceive   (更新记忆/以为)
                                     Person.act() ──Intent──▶ World.apply → 事件 → 进信箱

[多 tick 移动/交互 = 世界进程]
  World.apply 登记进行中的 move/interact(由世界推进, 上帝视角)
  每 tick World.tick(): 推进进度 → 完成/失败 → 发 Event(到达/交互完成/intent_failed) → 下轮 sense 带给 Person
```
进行中不重复 decision；世界持续推进，完成时用事件告知 Person。

---

## 6. 事件墙（结果通道，World→Person）
建议最小集：`arrived` / `interaction_done` / `intent_failed`(why) / `bought` / `stock_changed` / `told` /（可选 `perceived`）。
Person 只从这些事件里知道自己行动的后果，不反向查世界。

---

## 7. 现状 → 目标的差异（改造清单）
现状其实已接近此模型（percept→decide→intent + EventBus），只是被三处耦合坏了：
1. **真实位置被塞进 Person**，世界 loop 直接 `npc.position/location_id = ...` → 改：位置移出 Person 归 World，世界只改自己的位置表。
2. **世界(loop)直调 `brain.decide`、直写 `npc.kb/last_intent`** → 改：决策收进 `Person.act()`，世界只 `apply(intent)`。
3. **世界直改 `npc.signals`(代谢/交互/效果)** → 改：世界只发"心跳/事件"，Person 内部自己 `apply_metabolism/add_signal`。

`types.py` 现有 EntityView/Percept/Intent/Event 基本够用，主要是把"位置"语义与上述执行边界理清。

---

## 8. 开放问题（实现前定）
- **死亡**：signals 归 Person，若内部 hp 归零，由谁宣布死亡并把它移出世界？（建议：Person 产 `IAmDead` 事件 或 世界在感知到某 npc 不再应声后回收——二选一需定。）
- **感知范围/能见度**由 World 按位置与几何算(region 局部 or 视线)，Person 无权指定，但可"请求更多信息"(下轮感知带回)。
- **生理的 cfg(代谢 deltas/节律)**由世界每 tick 下发(心跳带当前时刻/配置)，Person 用其演化——配置来源归谁要定。
- **兜底最低唤醒频率**：Person 不能"自报太远"导致饿死/不响应——需世界设一个上限(最迟唤醒) 或 极端兜底唤醒，二者取一。
- 全事件(纯解耦) vs 方法门面(折中) 两档，见主线讨论。

---

## 结论
"上帝(World)执行过程，事件墙告诉 Person，Person 消化并决定下一步"——**过程归上帝、消化归 Person、只隔一道消息墙**。这样换新 Person 只需实现 `perceive/act/heartbeat`，World/sim 不动。
