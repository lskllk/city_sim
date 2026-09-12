# CitySim Editor（世界编辑器：路网/建筑/人物/物件）

独立 Godot 项目，**PCB-layout 风格**的手动制图工具：连路 + 摆建筑 + 放人物/物件。
**只做作者态，不参与 simulation**；导出**场景 JSON**后交给后端 / 观察器加载。

渲染（建筑底色/徽记/名称）不自己维护，运行时加载观察器项目
`godot/scripts/render/building_style.gd`（唯一权威），见 `scripts/building_style_loader.gd`。

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
- **先画路**：切「画路」→ 连续点击。规则：**一头一尾才落节点**——首点只记待定点，
  点到第二个点真正成路时才建节点；右键/Esc 取消（只取消当前连线，不会留下悬空点）。
  点到已有道路上会自动打断出 T/十字节点。
- **放建筑**：右侧资产列表选一个 → 画布点击。**必须先有路**；建筑主门会自动朝向
  最近道路并把墙面贴到路沿。拖动松手后也会重新对齐。
- **点建筑 → 进入详情页**（整栏替换基础页，非追加；布局对齐观察器 Inspector）：
  - 顶部可给建筑命名（保存名称）；
  - 「权限」：由住户自动决定（首个=户主，其余=同住）；
  - 「人员」：点「＋ 新增随机」在此建筑新增一个随机人物（自动 home=该建筑），
    行可点 → 进入人物详情；
  - 「物件」：选类型后「＋ 新增」放入该建筑，行可点 → 进入物件详情。
- **详情页**：人物（姓名/性别/年龄/角色/资金/性格/特质 + 保存/重滚/删除）、
  物件（库存/售价/归属 + 保存/删除）；「‹ 建筑」返回到建筑详情。
- **返回建筑/道路模式**：详情页顶部「‹ 返回 (建筑/道路)」，或点画布空白处 / 未选中。
- **选择/移动**：切「选择」→ 点建筑/节点/NPC 标记；`Delete` 删除。
- **导入/导出**：菜单 `文件 → 导入地图…/导出地图…/导出场景…`。
  - `导出地图…` = `citysim.map`（路网+建筑，nav 用）；
  - `导出场景…` = 后端 `config/scenes` 格式（含 locations/npcs/entities），交给观察器。

## 导出场景 → 观察器

`文件 → 导出场景…` 产出可直接被后端加载的 JSON：

```
locations: 建筑按 OBB 外接矩形写成显式 x/y/w/h（后端 build_locations 原样保留）
npcs:      人物（id/name/gender/birthday/role/money/home/personality/traits）
entities:  物件（type/at/owner/stock/price）
canvas:    地图 bounds，观察器按它适配相机
travel:    建筑中心直线距离粗估（缺省 20）
map:       原始路网（供后续观察器画路）
```

让观察器加载它（后端环境变量）：

```bash
set CITYSIM_SCENE=godot_editor\scene.json
python -m uvicorn citysim.gateway.server:app --port 8765
# 或直接跑 godot\run_backend.cmd
```

## 校验（最简 DRC）

`MapDoc.validate()`：建筑越界、建筑两两重叠（OBB SAT）、路段过短、进出口未对齐道路、
人物住所/物件所在建筑不存在。错误以红色描边显示，计数在状态栏。

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

- 建筑改名 / 编辑属性面板（现在名称取类型名；数据层已支持 `building.name`）。
- 人物初值信号（init）、初始记忆、日计划（plans）编辑。
- 物件拖拽换建筑；edge 属性（等级/宽度/单行）编辑面板。
- 撤销/重做；多选；吸附到已有节点/路边。
- 观察器渲染导出场景里的路网（当前只渲染建筑/人物/物件）。
- 由路网拓扑自动算 travel 距离（现为直线粗估）。
