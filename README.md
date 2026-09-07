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

### 2) Observatory 浏览器前端(React + Pixi)

后端只做 WS 推流端点(纯数据), UI 由独立 `frontend/` 提供:

```bash
# 一键(自动起后端+前端, 详见下)
bash dev.sh          # Git-Bash / Linux / macOS
双击 dev.cmd          # Windows cmd
```

分步手动起:

```bash
# 终端 A: 起后端
python -m uvicorn citysim.gateway.server:app --port 8765

# 终端 B: 起前端(dev, 自动代理 /ws 到 8765)
cd frontend && npm install && npm run dev
# 浏览器打开 http://localhost:5173
```

后端启动即暂停；点击 NPC / 地点 / 物品查看其行为、Why、知识、感知与事件。
退出：`dev.sh` 按 Ctrl+C 会同时停前后端；`dev.cmd` 关掉弹出的两个窗口即可。
日志在 `.logs/`。可用环境变量改端口：`BE_PORT` / `FE_PORT`；
如不想自动释放旧进程占用端口：`KILL_STALE=0 bash dev.sh`。

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
