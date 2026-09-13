# 观察器 UI 分层与规范

目标：**轻量、可扩展、结构上不会出"闪烁 / 点不中 / 错乱"类 UI bug**。

核心一句话：**只有"结构"变化才动节点；"数值"变化只改属性。**

---

## 分层

```
Screen 层   App(autoload 状态机): LAUNCHER / GAME / EDITOR
            launcher.tscn / main.tscn / editor.tscn
Overlay 层  settings_menu / pause_menu（叠加在 Screen 上；未来弹窗走这里）
Page 层     UiPage 子类: build() 一次, bind(id) 原地刷新
            Inspector 的 Empty / Npc / Location / Entity 四个常驻页
Widget 层   可复用控件(UiKit 工厂 + components/*.tscn)
            set_row(...) 即"绑定接口"
Data 层     Store(只读镜像) + InspData(业务文案/取数 helper)
Theme 层    UiTheme（颜色/字号/间距/圆角唯一来源）
```

| 层 | 文件 |
|---|---|
| 框架 | `scripts/ui/framework/ui_theme.gd` · `ui_kit.gd` · `ui_list.gd` · `ui_page.gd` |
| 业务 | `scripts/ui/inspector/data.gd` · `page_empty/npc/location/entity.gd` |
| 面板 | `scripts/ui/inspector.gd` (`InspectorPanel`) |
| 控件 | `scripts/ui/components/*.gd` + `scenes/components/*.tscn` |
| 文案 | `scripts/ui/zh.gd` (`Zh`) |

数据流：

```
后端 snapshot(60Hz) → App → Store.apply_snapshot
InspectorPanel._process(每 100ms) → 切页(只切 visible) → page.bind(id)
page.bind → 原地 set_row / label.text / bar.value
列表变化 → UiList.row(i) 补行 / UiList.trim(n) 隐藏多余行
```

---

## 铁律（改 UI 必须遵守）

1. **页面常驻**：`UiPage` 子类只在 `_ready` 里 `build()` 一次；切换选中项只切 `visible`，**不 new / 不 free 页面**。
2. **bind 只改属性**：`bind(id)` 里禁止 `add_child` / `queue_free`（除行池内部补行）。
3. **列表用行池**：所有列表用 `UiList`，数量变化只 `row(i)` / `trim(n)`；**永不销毁行**。
4. **可点控件常驻**：返回键、按钮、可点行放在常驻结构里，绝不进入"刷新重建"路径。
5. **单一刷新节拍**：面板 100ms 调一次 `bind`，不做逐字段信号订阅。高频字段（hp/行为/库存/占用）天然安全。
6. **颜色/字号/间距只从 `UiTheme` 取**，不在组件里写死字面量。
7. **框架层不碰业务**：`UiKit` 不读 `Store`；业务取数放 `InspData`。

---

## 如何扩展

### 新增一个 Inspector 页面
1. 新建 `scripts/ui/inspector/page_xxx.gd`：
   ```gdscript
   class_name InspXxxPage
   extends UiPage

   func build() -> void:
       # 只在这里建常驻控件
   func bind(id: String) -> void:
       # 只在这里原地更新
   ```
2. 在 `inspector.gd::_ready()` 里 new 一个、加进 `stack`、登记到 `_pages`。
3. 在 `_update()` 的 `match kind` 里补 id 取值与 `_valid()`。

### 新增一种列表行
1. 参考 `components/person_row`：一个 `Button`，`signal selected(id)` + `set_row(...)`。
2. 页面用 `UiList.new(容器, 预加载的场景)`；`bind` 里 `row(i).set_row(...)`，最后 `trim(n)`。
3. 点击：`if not row.selected.is_connected(cb): row.selected.connect(cb)`（只连一次）。

### 改主题 / 换皮
只改 `ui_theme.gd`。组件不要写死颜色。

---

## 为什么这样就不会有"闪 / 点不中"

| 旧做法（bug 源） | 现做法 |
|---|---|
| `_content_key` 变了就 `_clear()` 全 free + 重建 | 页面常驻，只 `bind` 属性 |
| 返回键在重建中被销毁 | 返回键常驻，只切 `visible` |
| 列表行每次 new Button | `UiList` 行池，复用 |
| hp/行为/库存 进入"重建指纹" | 高频字段只走 `set_row`，与结构无关 |

---

## 后续可扩展（未做，留接口）

- **Overlay 栈**：把 `settings_menu` / `pause_menu` / 弹窗统一成 `push/pop` 栈，`Esc` 只给栈顶，模态遮罩——Screen 之上的标准做法。
- **ViewModel 层**：若将来要单测或多数据源，可在 Store 与 Page 之间加 `NpcVM/LocationVM/EntityVM`；Page 只依赖输入形状，替换成本低。
- **焦点/导航**：键盘/手柄焦点环。
- **动画/过渡**：页面切换渐入、行高亮过渡（retained 结构天然支持）。
