# 启动界面与设置框架

观察器现在有标准的"主菜单 → 选择场景 / 进入编辑器 → 进入游戏"流程。本文说明结构与扩展点。

## 启动流程

```
scenes/launcher.tscn (main_scene)
   ├─ 列 <仓库根>/config/scenes/*.json → 选中 → App.start_game(rel)
   │        │  (发 reset{scenario:rel} 给后端)
   │        ▼
   │   scenes/main.tscn (观察器) ── Esc ──▶ 暂停菜单 ──▶ 设置 ──▶ 返回主菜单
   │
   └─ 「地图编辑器」→ App.open_editor()
            ▼
        scenes/editor/editor.tscn ── 文件▸返回主菜单 / 顶栏「⌂ 主菜单」
            └─ 有未导出修改时弹确认框
```

- `App` 在启动时就把 `Net` 连上(后端由 `Backend` 自动拉起), 所以点"开始"后立即
  用 `reset` 命令让后端加载所选场景, 无需重启后端进程。
- `return_to_launcher()` 会先 `set_speed pause`, 再清空 `Store`, 切回启动界面;
  观察器与编辑器都走这一个出口。
- 编辑器不依赖后端; `MapDoc` 是 autoload, 来回切换不丢当前编辑内容。

## 组成

| 文件 | autoload/场景 | 职责 |
|---|---|---|
| `scripts/app/app.gd` | autoload `App` | 状态机(LAUNCHER/GAME) + WS 消息分发 + 场景切换 |
| `scripts/app/app_settings.gd` | autoload `Settings` | 设置 schema + 持久化(`user://settings.cfg`) |
| `scripts/app/scene_catalog.gd` | autoload `SceneCatalog` | 扫描场景目录 |
| `scripts/ui/launcher.gd` + `scenes/launcher.tscn` | 主菜单 | 场景列表 / 详情 / 开始 / 编辑器 / 设置 / 退出 |
| `scripts/editor/main.gd` + `scenes/editor/editor.tscn` | 编辑器 | 制图/摆建筑/加人物物件; 顶栏/菜单可返回主菜单 |
| `scripts/ui/settings_menu.gd` + `scenes/settings_menu.tscn` | 叠加层 | 按 schema 自动生成设置界面 |
| `scripts/ui/pause_menu.gd` + `scenes/pause_menu.tscn` | 游戏内 Esc | 继续 / 设置 / 返回主菜单 / 退出 |

`main.gd` 只做渲染初始化 + 挂载菜单层; WS 生命周期/分发都在 `App`, 因此场景来回切换
不会重复连接信号。

## 扩展点

### 1. 新增可选场景
把编辑器导出的 `.json` 放进仓库根 `config/scenes/`, 启动界面点"刷新"即可。
如需扫描别的目录(如 Workshop), 往 `SceneCatalog.sources` 里加相对路径。

### 2. 新增一条设置
只改 `app_settings.gd::_register_defaults()`:

```gdscript
register("gameplay", "auto_pause", Settings.Type.BOOL, false, "失焦自动暂停")
```

设置界面会自动出现对应分区/控件并持久化。类型: `BOOL / INT / FLOAT / STRING /
ENUM / PATH`。需要"立即生效"的设置在 `_apply()` 里加一个 case。

### 3. 新增设置分区
`register()` 传入新的 section 即可; 分区显示名在 `section_label()` 里加一个 `match`。

### 4. 读取设置
任何地方 `Settings.get_value("section", "key", default)`; 变更监听 `Settings.changed`。

### 5. 新增菜单入口
暂停菜单(`pause_menu.tscn`)或主菜单(`launcher.tscn`)加按钮并在脚本里接线;
需要跳转统一走 `App.start_game()` / `App.open_editor()` / `App.return_to_launcher()`。

## 优先级

端点/解释器等运行时参数取值优先级:
`环境变量(CITYSIM_WS_URL / CITYSIM_PYTHON / …)` > `Settings(user://settings.cfg)` > 默认值。
`CITYSIM_NO_AUTOSTART=1` 始终禁止自动拉起后端。
