# Mind —— 情绪 / 关系 MVP 设计

> 状态：**M-E1（MVP）冻结，未实现**。上位文档：`docs/semantic_event.md`。
>
> 一句话：**情绪 = 短期、带靶；关系 = 长期、方向性；两者同属一个 `Mind`，共用同一次"评估"。**

---

## 0. 本版范围：只做闭环，不碰行为

一个必须写在前面的代码事实：

```text
brain.decide()      没有 plans 入参 —— plan_mult 未实现（world/drive.py:8 仍有 TODO）
_gather_candidates  fallback_need = 0.9 —— 正常状态下几乎不产生候选
```

**推论：现在把情绪偏置接进 `decide`，看不到任何效果。**

所以 M-E1 的边界是：

> **情绪只接 `信任 → believe → 传播`，不接 `decide`。**
> 行为偏置推迟到「计划表接进 decide」之后（见 §10 / 附录待办）。

---

## 1. 相对早期方案砍掉的东西

| 概念 | M-E1 | 理由 |
|---|---|---|
| `Mood`（valence / arousal） | ❌ 砍 | 派生量。有情绪列表就够，多一层多一个要维护的状态 |
| 6 种情绪 `kind` | ❌ 砍 | 只有语义层需要"生气"这个词。MVP 只存 `valence` |
| 4 个评估维度 | ❌ 砍 | 只留 `desirable`；`agency` 可由事件自带；`expected/controllable` 无消费者 |
| `config/appraisal.json` | ❌ 砍 | 2 条规则不值得建 JSON。**规则数 > 5 再抽出去** |
| `evidence` 环形缓冲 | ❌ 砍 | MVP 只要数字；可追溯留 M-E2 |
| 派生标签（朋友/敌人） | ❌ 砍 | 没有消费者 |
| 独立 `appraisal.py` | ❌ 砍 | 并进 `mind.py` |
| `familiarity` 标量 | ❌ 砍 | **"关系存在与否"本身就是门槛** |
| 情绪 → `decide` 偏置 | ❌ 砍 | 见 §0，依赖未完成的部分 |

**砍完剩下的最小集：**

```python
Emotion  = (target, valence, intensity, cause, halflife, tick)   # 短期、带靶
Relation = (liking, trust)                                       # 长期、方向性
```

---

## 2. 数据模型

```python
# 情绪条目：快变、带靶、必带 cause（可追溯）
Emotion:
    target: str        # npc_id | item_id | org_id | ""（无靶）
    valence: float     # -1..1
    intensity: float   # 0..1
    cause: str         # event_id / fact_id —— 必填
    halflife: int
    tick: int

# 关系：方向性、稀疏（key = other_id）
Relation:
    liking: float = 0.0    # -1..1
    trust: float  = 0.5    # 0..1，陌生人中性值，**不能是 0**（否则传播起不来）
```

- 都是可变 dataclass（要原地衰减），与 `MemItem` 一致。
- `Mind._relations` 是 `dict[other_id, Relation]`，**只存存在的对**，不开 N²。

---

## 3. `Mind` 类（一个 NPC 一份，统一心理）

情绪与关系**必须一起演化**（情绪累积成关系），拆成两个类就要互相引用。放一个类里天然闭环。

```python
# npc/mind.py —— npc 层，纯数据，不 import world
class Mind:
    _emotions: list[Emotion]
    _relations: dict[str, Relation]

    # --- 写 ---
    def feel(self, target, valence, intensity, cause, tick) -> None
        # 追加情绪；若 target 是人 → 同时动 Relation（这就是"桥"）
        #   Relation.liking += K_LIKE * valence * intensity
    def verify(self, other, ok: bool, tick) -> None
        # trust 的唯一来源：话应验 / 被推翻
        #   ok=True  → trust += K_TRUST
        #   ok=False → trust -= K_TRUST
    def step(self, tick, distress: float) -> None
        # 每 tick：情绪半衰衰减 + 过期删除
        #   注意：distress 只影响"新产生"的强度（见 §4），不凭空造情绪
    # --- 读 ---
    def trust(self, other) -> float
    def liking(self, other) -> float
    def bias(self, target) -> float          # 预留；M-E1 恒返回 1.0
```

- `Person` 新增 `self._mind = Mind()` + `person.mind` 只读属性。
- `bias()` 先留空实现，等计划表接进 `decide` 再填内容。
- **`feel()` 内部直接改 `Relation`** —— 关系不是独立系统，是情绪的历史积分。

---

## 4. 身体 → 心理

**一条原则：身体不产生情绪，只放大强度。**

```text
distress        = mean(1 - signal for signal in REFLEX_SIGNALS)   # 0..1
intensity_final = intensity_base × (1 + K × distress)             # K ≈ 0.5
```

- 饿 / 累 → 同一件事反应更烈（hanger）。
- 反向同理：需求被满足时缺口越大，带来的 `valence` 越强——同一个公式，
  因为 `intensity_base` 本来就应由"事件带来的改善量"决定。
- `distress` 由 `Person` 现成的 `_signals` 算出，加一个纯函数 `distress(signals)`。

### 验证（三条，按重要性排序）

1. **反例测试（最重要）**：无任何事件，跑 `mind.step()` 一千 tick → `_emotions` 始终为空。
   **这条是防止它日后退化回 Sims 4 的 mood 系统。**
2. **单元测试**：同一事件，`need=0.1` vs `need=0.9` → `intensity_final` 比值符合公式。
3. **行为测试**：在既有 `tests/test_behavior_soak.py` 上加一条——7 天模拟里，
   `distress` 高的 NPC 对同一源的信任跌幅 > `distress` 低的。

---

## 5. 关系：预置骨架 + 自然生长（两个都要）

- **全自然生长** → t=0 满城陌生人，这个环是空的：没东西可测、社交前几小时死寂、世界没有结构。
- **全预置** → 静态，没有生命，等于写了另一套脚本。
- **→ 混合：预置只放"有理由的边"（同住 / 同事 / 邻居），约 1~5%；其余全靠演化。**

预置是**数据**，放 scene JSON（`config/scenes/*.json`）：

```json
"relations": [
  {"a": "npc_wang_er", "b": "npc_li_si", "liking": 0.3, "trust": 0.5, "why": "coworker"}
]
```

两条硬规则：

1. **一行只写一个方向**，要对称就写两行。**不要自动双向**——不对称才是重点。
2. **陌生人 `trust` 默认 0.5（中性）**，不是 0。

---

## 6. MVP 闭环与验收标准

```text
王哥告诉李四「苹果降价了」
  → 李四写入记忆：believe = mind.trust(王哥) × 内容新鲜度
  → 李四到店，感知与记忆冲突
  → mind.verify(王哥, ok=False) → trust(王哥) ↓
  → mind.feel(王哥, valence=-1) → liking(王哥) ↓
  → 下次 believe(王哥的话) 更低
```

**验收标准（全程不碰 `decide`）：**

1. 同一条谣言，从**高信任源**与**低信任源**发出，李四的 `believe` 明显不同。
2. 被推翻一次后，**同一个源的后续消息** `believe` 下降。
3. §4 的三条验证全过（尤其第 1 条反例测试）。

---

## 7. 传播（M-E1 一并实现）

> 目标：把 `信任 → believe` 接上，形成传播链。
> **不追求保真，只求「有关系多说、没关系少说」。**

### 7.1 现状（代码事实）

- `engine.py::_notify_due` 是空壳 TODO，但**已挂在 `intent is Idle` 那一刻**（`engine.py` tick 内）
  → 「人闲着才聊八卦」的钩子现成，不用改架构。
- `EventBus` 有 `audience` 路由，`build_percept` 已把事件放进 `Percept.events` → 投递管道现成。
- **但没有任何代码消费 `told` 事件**（`Person.perceive` 只看 `percept.visible`）。
- **`MemItem` 没有 `source`** → 不知道这话是谁说的。这是地基，先加。

### 7.2 规则（三条）

```text
说话概率 = tell_p × social_weight(对方)
说什么   = 对方不知道的、且不是他说的 → 取 believe 最高的那条
信多少   = 话说者的 believe × 听者.trust(话说者)
```

第一条就是「有关系多说、没关系少说」；第三条是「信任是传播里唯一的社会权重」。

### 7.3 代码

```python
# npc/mind.py
def social_weight(self, other: str) -> float:
    r = self._relations.get(other)
    return 0.1 if r is None else 0.3 + 0.7 * r.trust
```

```python
# world/engine.py
def _notify_due(world, systems, npc):
    loc = world.loc_of(npc.person_id)
    for other_id in sorted(world.npcs):
        if other_id == npc.person_id or world.loc_of(other_id) != loc:
            continue
        other = world.npcs[other_id]
        if systems.rng.random() >= systems.tell_p * npc.mind.social_weight(other_id):
            continue
        row = _pick_tell(npc, other_id, other)
        if row is None:
            continue
        other.note(row.item_id,
                   believe=row.believe * other.mind.trust(npc.person_id),
                   source=npc.person_id, tick=world.clock_tick)
        world.bus.publish(world.bus.make(
            world.clock_tick, "told", npc.person_id,
            {"audience": [other_id], "item_id": row.item_id,
             "from": npc.person_id}))


def _pick_tell(speaker, other_id, other):
    """对方不知道的、且不是他说的 → 取 believe 最高的那条。"""
    best = None
    for row in sorted(speaker.mem.items(), key=lambda r: r.item_id):
        if row.source == other_id or other.mem.get(row.item_id) is not None:
            continue
        if best is None or row.believe > best.believe:
            best = row
    return best
```

### 7.4 为什么不用 `hops`

`_pick_tell` 里「对方已知就不说」**本身就是天然衰减器**：消息传开后能说的人越来越少，链条自己停。
代价是会饱和（最后全城都知道）——合理。将来做营销/口碑时，靠已有的 `remember` 遗忘机制再加回来。

### 7.5 覆盖范围

`_notify_due` 只在 `Idle` 时触发，而 `fallback_need=0.9` 让大多数 NPC 长期 Idle，
所以传播不会被饿死。**等计划表接进 `decide` 后 Idle 变少，`tell_p` 需要重调。**

### 7.6 坑

1. **确定性**：遍历与 `npcs_at` 必须排序；`rng` 必须来自 `systems`，否则 `test_replay.py` 会飘。
2. **同 tick 连锁**：`build_percept` 已先 drain 事件 → 听者下一 tick 才收到，天然隔断。
   **别去「优化」掉它。**
3. **信箱 `maxlen=64`**：全城活跃时会丢消息。先观察。
4. `source` 不是传播带来的额外负担 —— `verify()` 更新信任时需要知道「该怪谁」。

### 7.7 验收

1. 高信任关系之间消息传得快；陌生人之间基本不传。
2. B 收到的 `believe` 被 `B.trust(A)` 打过折。
3. 同一条消息不会来回传。

---

## 8. 代码落点

| 文件 | 改动 | 量 |
|---|---|---|
| `npc/mind.py` | **新建**：`Mind` / `Emotion` / `Relation` / `distress()` | ~80 行 |
| `npc/person.py` | 加 `_mind` + property；`note()` 支持 `believe`/`source` | 小 |
| `npc/memory.py` | `MemItem` 加 `source: str = ""` | 1 行 |
| `sim/loop.py` | 决策前 `mind.step()`；事件后 `mind.feel()/verify()`；`Systems` 加 `rng`/`tell_p` | ~5 行 |
| `world/engine.py` | 填 `_notify_due` + `_pick_tell` | ~25 行 |
| `world/world.py` | `npcs_at(loc)`（排序返回），或内联 | 小 |
| `gateway/snapshot.py` | 只读导出情绪/关系（供 Inspector） | ~5 行 |
| `config/scenes/*.json` + `gateway/scenarios.py` | 预置 `relations` 段 | 小 |
| `core/types.py` | 可选：`EmotionView` / `RelationView` 契约 | 视需要 |

**`brain.py` 不动**（因为 M-E1 不接偏置）。

---

## 9. 铁律

1. 情绪**只做偏置**，永不删除候选（M-E1 干脆不接 `decide`）。
2. 每条情绪必带 `cause`（可追溯）。
3. 关系只存**存在的对**（稀疏，别开 N²）。
4. 标签派生，不存储。
5. `npc/` 不 import `world`。
6. 身体**不产生**情绪，只放大强度。

---

## 10. 分期

| 阶段 | 内容 | 前置 |
|---|---|---|
| **M-E1** | `Mind` + `Emotion`/`Relation` + `distress` + 信任应验路径（§6）+ 传播（§7） | 无 |
| M-E2 | `kind` 词表 + `evidence` 环 + 派生标签 + `appraisal.json` 规则表 | 语义层要词时 |
| M-E3 | 情绪偏置接进 `decide`（`emotion_mult`） | **计划表接进 `decide` 之后** |

---

## 11. 待定 / 非目标

**待定**
- `trust` 的主来源最终定为「话应验率」（信息战）还是「行为互利」（人情社会）——
  M-E1 先按 **应验率** 实现（能直接接上传播）。
- `belief` 新鲜度的具体衰减曲线（可先复用 `SimConfig.half_life_ticks`）。

**非目标（暂缓）**
- 情绪影响表情 / 语音 / 动画。
- 关系影响行为规则（如"朋友之间不抢生意"）——没有 `decide` 接入点。
- 群体情绪 / 舆论场。

---

## 附录：跨文档待办

- [ ] **计划表生成 —— 用本地算法策略，不用 LLM。**（下一轮讨论）
  影响面：`npc/planner.py` / `npc/schedule.py` / `brain.decide` 的 `plan_mult`。
  **M-E3 依赖此项。**
- [ ] `semantic_event.md` §11：听觉范围（同 location vs 半径）——先按 location，接口留半径位。
