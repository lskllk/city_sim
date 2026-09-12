# CitySim Map Editor（L0 路网/建筑编辑器）

独立 Godot 项目，**PCB-layout 风格**的手动制图工具：摆建筑 + 连路 + 导出地图 JSON。
**只做作者态，不参与 simulation**；导出的 `citysim.map` 由后端 nav 层消费。

## 运行

```bash
"D:/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64_console.exe" --path godot_editor
# 或用 Godot 编辑器打开 godot_editor/project.godot
```

## 界面

```
┌ 菜单栏: 文件(新建/导入/导出) · 视图(适配内容) ──────────────┐
│                                       │ 工具: 选择/移动 · 画路 │
│                                       │ 资产: building 列表     │
│            编辑画布(栅格/路/建筑)      │ 栅格: 尺寸(m)          │
│                                       │ 属性: 选中只读展示      │
│                                       │ 删除选中               │
│ 状态栏: 节点/路段/建筑/错误计数 · 提示 ┘                    │
└─────────────────────────────────────────────────────────┘
```

## 操作

- **平移/缩放**：中键拖动 / 滚轮（以光标为中心）。
- **放建筑**：右侧资产列表选一个 → 画布点击（落点自动**栅格吸附**）。
- **连路**：切「画路」→ 连续点击落节点，相邻两点自动成路；右键/Esc 结束。
- **选择/移动**：切「选择/移动」→ 点建筑/节点拖动；`Delete` 删除。
- **导入/导出**：菜单 `文件 → 导入…/导出…`（`godot_editor/samples/demo.json` 可作示例）。

## 校验（最简 DRC）

`MapDoc.validate()`：建筑越界、建筑两两重叠（OBB SAT）、路段过短、建筑无邻近路节点。
错误以红色描边显示，计数在状态栏。

## 地图格式 `citysim.map` v1

```json
{
  "format": "citysim.map", "version": 1,
  "world": {"unit": "m", "bounds": [x, y, w, h], "grid": 1.0},
  "nodes":     {"n_001": {"xy": [x, y], "kind": "junction"}},
  "edges":     {"e_001": {"a": "n_001", "b": "n_002", "class": "local",
                          "width": 4.0, "speed": 1.3, "oneway": false,
                          "geom": [[x, y], [x, y]]}},
  "buildings": {"bld_001": {"type": "home_standard", "center": [x, y],
                            "size": [w, h], "rot": 0.0, "doors": [[x, y]]}}
}
```

- 单位：米。节点只放交叉口/端点；路的弯曲放 edge 的 `geom` 折线。
- 建筑 `type` 复用后端 `config/buildings/*.json`；新建时尺寸按 `面积 ∝ capacity` 自动算。
- 后端 nav 层未来从此图**自动派生**连通/寻路，不再手写距离矩阵。

## 尚未做（后续）

- 建筑门/接入点编辑；edge 属性（等级/宽度/单行）编辑面板。
- 撤销/重做；多选；吸附到已有节点/路边。
- 撤销生成器接入（Python 自动生成）——先手动。
