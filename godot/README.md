# CitySim Observatory · Godot 前端

方案 A 的观察器前端：**Godot 只做只读观察**，Python 内核仍是唯一权威模拟。
通过现有 `citysim.gateway` 的 WebSocket 订阅 `hello / snapshot / event`，
并回发 `set_speed / step / reset` 命令。前端不计算任何 simulation。

## 运行

```bash
# 1) 起后端(与浏览器前端共用同一端点)
python -m uvicorn citysim.gateway.server:app --port 8765

# 2) 用 Godot 打开本目录并运行(或命令行直接跑)
"D:/Godot_v4.7.2-stable_win64.exe" --path D:/sim_city/godot
```

- WS 端点默认 `ws://127.0.0.1:8765/ws`，可用环境变量 `CITYSIM_WS_URL` 覆盖。
- 无头集成冒烟：`CITYSIM_SMOKE=1` 时挂载 `scripts/debug/smoke_probe.gd`，
  轮换选中 NPC/实体/地点以走完 Inspector 构建路径。

## 静态场景(可直接在编辑器里改)

布局与组件全部是 `.tscn` 节点树，脚本只挂逻辑，不动态搭 UI：

```
scenes/
  main.tscn                     布局总装: HBox( WorldCanvas | Inspector )
  components/
    inspector_section.tscn      折叠区段(标题+分隔线+内容容器)
    npc_header.tscn             Inspector 顶部标题
    signal_row.tscn             信号条(名称+进度条+百分比)
    cand_row.tscn               候选排名行
    mem_row.tscn                记忆行
    event_row.tscn              事件行
    kv_row.tscn                 键值行
  world/
    npc_visual.tscn             NPC 圆点 + 选中环(Polygon2D / Line2D)
    entity_visual.tscn          实体方块 + emoji Label
resources/
  ui_font.tres / emoji_font.tres  系统字体(CJK / Emoji), 可在编辑器改字体名
  theme.tres                      默认 UI 主题
```

## 脚本(只做逻辑)

```
scripts/
  main.gd                      入口: WS 生命周期 + 消息 dispatch(镜像 App.tsx)
  protocol/protocol.gd         消息解析 + 宽容取值
  net/ws_client.gd  (autoload Net)        WebSocketPeer + 重连(backoff)
  net/commands.gd   (autoload Commands)   命令发送单例(镜像 commands.ts)
  state/store.gd    (autoload Store)      世界/模拟/选择 只读镜像
  sim/interpolation.gd         纯视觉插值
  render/camera.gd             pan / zoom / fit(镜像 Camera.ts)
  render/world_canvas.gd       相机+三层+HUD+输入(镜像 WorldView/SimulationStage)
  render/map_layer.gd          街区矩形(数据驱动, _draw)
  render/entity_layer.gd       实体/NPC 实例的 reconcile/平滑/拾取
  render/overlay_layer.gd      选中高亮(数据驱动, _draw)
  render/npc_visual.gd, entity_visual.gd   单实例可视化
  ui/inspector.gd              Inspector(实例化 components/*)
  ui/components/*.gd           行控件的 set_row(...)
  ui/{fonts,zh,emojis}.gd      字体入口 / 文案映射 / emoji 注册表镜像
  debug/smoke_probe.gd         无头冒烟探针
```

## 数据流

```
Net --message_received--> main.dispatch --> Store --signals--> WorldCanvas / Inspector
UI --Commands.cmd--> sender --> Net.send --> backend
```

`Store` 只存后端 snapshot 提供的世界真值，不含任何 simulation 逻辑。
