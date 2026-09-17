# citysim · 城市生活模拟内核

确定性、数据驱动的城市 / NPC 认知模拟。规则大量从 `config/` 的 JSON 导入 —— **改动优先改数据**。

## 安装

```bash
python -m pip install -e .            # 内核 + 测试(零第三方依赖)
python -m pip install -e ".[viz]"     # 额外: 观察器后端 (fastapi + uvicorn)
```

## 目录

```
src/citysim/
  core/     契约层: types(Percept/Intent/Notify/Command) · ports(5 个动词) · config
  npc/      认知侧: person(门面) · brain(决策) · memory · schedule · semantic · planner
  world/    世界侧: engine(tick 主循环) · world · market · interaction · perception · port
  sim/      loop.py(推进入口 run_tick + Systems 容器)
  gateway/  scenarios(场景→世界) · server(WS) · snapshot(世界→JSON)
config/     sim.toml + items/ · buildings/ · scenes/   ← 数值与内容都在这
godot/      观察器 + 编辑器(只渲染/发命令, 不算模拟)
tools/      观测脚本: sim_report · watch · narrate · soak_report …
tests/      pytest
```

## 跑起来

```bash
python tools/sim_report.py config/scenes/scene.json 30   # 无头跑 30 天, 出健康度报告

python tools/watch.py --npc 6 --ticks 2400               # 终端观察器(无依赖, 最快看行为)

python -m uvicorn citysim.gateway.server:app --port 8765 # 只跑后端

"D:/Godot_v4.7.2-stable_win64.exe" --path godot                              # 观察器
"D:/Godot_v4.7.2-stable_win64.exe" --path godot res://scenes/editor/editor.tscn  # 编辑器
```

观察器会自己拉起后端(端口已监听则跳过)、退出时收掉；日志在 `.logs/backend.log`。
编辑器导出的场景用 `set CITYSIM_SCENE=<路径>` 让观察器加载。

## 测试

```bash
python -m pytest                                # 全量
python -m pytest tests/test_import_layers.py    # 层隔离: npc/ 禁 import world/
python tools/sim_report.py <scene> <days>       # 改动后跑一遍, 看行为有没有变
```

## 两条红线

1. **`npc/` 严禁 `import citysim.world`** —— CI 会挂（`tests/test_import_layers.py`）。
   NPC 只能通过 `core/ports.py` 的 5 个动词向世界**请求**，世界只能通过
   `Person.notify()` / `Person.assign()` 对 NPC 说话。
2. **Godot 只渲染、只发命令，不算任何模拟**。
