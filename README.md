# citysim · 城市生活模拟内核

确定性、数据驱动的城市 / NPC 认知模拟。NPC 与世界解耦：`npc/`(认知侧，纯数据 + 决策 + 双层知识库) 与 `world/`(世界侧) 通过 `core/types.py` 的数据契约交互，规则大量从 `config/` 下的 JSON 导入，改动优先改数据。

- Python ≥ 3.10
- 内核零第三方依赖（仅条件依赖 tomli<3.11）
- 观察器 / 前端额外依赖 `fastapi`、`uvicorn`（见下方安装）

## 目录速览

```
src/citysim/
  core/      信号全集 + 契约类型(types.py) + SimConfig(config/sim.toml)
  npc/       person(纯数据) · brain(决策纯函数) · knowledge(双层知识库)
  world/     世界容器 + 物品/副作用/交互/感知/事件/调度
  sim/       推进入口 run_tick
  gateway/   FastAPI+WS 只读观察器
config/      sim.toml + items/archetypes/scenes 数据(改数值首选)
tools/       终端观察 / 叙事 / 压力脚本
tests/       pytest 测试
```

## 安装

```bash
git clone <repo-url> && cd sim_city

# 仅跑内核/测试:
python -m pip install -e .

# 观察器前端(带 viz 可选依赖):
python -m pip install -e ".[viz]"
```

## 运行

### 1) 终端观察器(无依赖，最快看行为)

```bash
python tools/watch.py --npc 6 --ticks 2400 --period 240
python tools/watch.py --1x          # 真实节拍 2 tick/s
```

### 2) Godot 观察器 / 编辑器

后端只做 WS 推流端点(纯数据), UI 是 `godot/` 这一个 Godot 项目里的两个场景:

- 观察器: `scenes/main.tscn`(连 `/ws`, 渲染世界 + Inspector)
- 编辑器: `scenes/editor/editor.tscn`(画路网/摆建筑/放人物物件, 导出场景 JSON)

```bash
# 一键(见 run.cmd)
run.cmd              # 后端 + 观察器
run.cmd editor       # 只打开编辑器(不启动后端)
run.cmd backend      # 只起后端

# 或手动:
python -m uvicorn citysim.gateway.server:app --port 8765
"D:/Godot_v4.7.2-stable_win64.exe" --path godot
"D:/Godot_v4.7.2-stable_win64.exe" --path godot res://scenes/editor/editor.tscn
```

Godot 观察器启动时会自己拉起后端(见 `godot/scripts/net/backend.gd`), 端口已在监听则跳过；
退出时收掉自己拉起的进程。后端启动即暂停；点建筑 → 右侧选人 / 看物件。
编辑器导出场景后, 用环境变量让观察器加载它: `set CITYSIM_SCENE=godot\samples\scene.json`。

### 3) 叙事 / 压力工具(可选)

```bash
python tools/narrate.py --days 3            # 事件流译成人话(供人工 review)
python tools/soak.py                        # 7 天行为统计
python tools/scarcity_check.py              # 稀缺竞争观察
```

## 测试

```bash
python -m pytest                      # 全部测试(默认 src、tools 在 path)
python -m pytest tests/test_import_layers.py   # 层隔离(npc 禁 import world)
python -m pytest tests/test_replay.py          # seed 固定回放确定性
python -m pytest tests/test_behavior_soak.py   # 7 天行为安全网
```

## 常见排查

- **数据改哪**：魔法数值改 `config/sim.toml`；物品副作用改 `config/items/*.json`；NPC 原型常识改 `config/archetypes/*.json`；场景装配改 `config/scenes/elm_lane.json`。
- **认知侧红线**：`npc/` 严禁 `import citysim.world`，违反会被 `test_import_layers.py` 挂。
- **goap 残留缓存**：`src/citysim/npc/__pycache__/goap*.pyc` 为删除 GOAP 前的陈旧产物，可 `rm -rf src/citysim/npc/__pycache__` 清理。
