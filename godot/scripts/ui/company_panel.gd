# company_panel.gd —— 公司运营界面(居中弹窗, 独立于右侧检查器)。
#
# 用户定的结构(先搭框架, 具体内容后做):
#   TabView 四个 tab:
#     1 实时监控   2 HR 管理   3 货物管理   4 价格调整
#
# 打开方式:
#   · 店铺【注册公司成功】→ 自动弹出
#   · 店铺详情里点「打开运营界面」→ 再打开
#
# 为什么用 CanvasLayer(layer=100): 挂在 autoload 上也一定浮在整个场景之上,
# 不会因为挂在节点树前面而被场景盖住。关闭只切 visible, 控件【只建一次】
# (页面/面板的铁律: 别在刷新里增删控件, 否则按钮闪烁点不中)。
extends CanvasLayer

static var instance = null                    # 由 App 创建, 页面用静态方法打开

var _dim: ColorRect
var _panel: PanelContainer
var _title: Label
var _sub: Label
var _tabs: TabContainer
var _cid := ""


## 页面侧的统一入口(没创建时不报错, 只是打不开)
static func open_company(cid: String) -> void:
	if instance != null and instance.has_method("open_for"):
		instance.call("open_for", cid)


func _ready() -> void:
	instance = self
	layer = 100
	_build()
	visible = false


func _build() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_STOP       # 弹窗时挡住底下的点击
	add_child(root)

	_dim = ColorRect.new()
	_dim.color = Color(0, 0, 0, 0.55)
	_dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(_dim)

	_panel = PanelContainer.new()
	_panel.custom_minimum_size = Vector2(760, 520)
	_panel.set_anchors_preset(Control.PRESET_CENTER)
	# 居中: 用锚点 + 固定尺寸(PRESET_CENTER 会把 pivot 放中间)
	_panel.offset_left = -380
	_panel.offset_right = 380
	_panel.offset_top = -260
	_panel.offset_bottom = 260
	root.add_child(_panel)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	_panel.add_child(box)

	# --- 标题行 ---
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	var tcol := VBoxContainer.new()
	tcol.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_title = Label.new()
	_title.add_theme_font_size_override("font_size", 18)
	tcol.add_child(_title)
	_sub = Label.new()
	_sub.add_theme_color_override("font_color", Color("7f8ea3"))
	tcol.add_child(_sub)
	head.add_child(tcol)
	var close := Button.new()
	close.text = "✕ 关闭"
	close.pressed.connect(close_panel)
	head.add_child(close)
	box.add_child(head)

	# --- 四个 tab(先只搭框架: 每个 tab 里一句说明) ---
	_tabs = TabContainer.new()
	_tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tabs.add_child(_tab("实时监控",
		"公司画布: 线路(销售前台) / 员工在不在岗 / 顾客排队"))
	_tabs.add_child(_tab("HR 管理",
		"员工名单 · 发布/撤回招聘 · 时薪 · 上下班时间 · 现金"))
	_tabs.add_child(_tab("货物管理",
		"在售货架与库存 · 工位(销售前台) · 向市场进货"))
	_tabs.add_child(_tab("价格调整",
		"逐条改售价(只改世界真值 —— 顾客要看见/听人说才知道)"))
	box.add_child(_tabs)


func _tab(title: String, hint: String) -> Control:
	var v := VBoxContainer.new()
	v.name = title
	v.add_theme_constant_override("separation", 6)
	var l := Label.new()
	l.text = "【%s】%s" % [title, hint]
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", Color("7f8ea3"))
	v.add_child(l)
	return v


func open_for(cid: String) -> void:
	_cid = cid
	var comp := Store.company(cid)
	_title.text = "%s" % Protocol.s(comp.get("name", cid)) if not comp.is_empty() \
		else "公司 %s" % cid
	var shops: Array = Protocol.as_array(comp.get("shops", []))
	_sub.text = "公司运营 · %s · 店铺 %s" % [cid,
		", ".join(shops.map(func(s): return Protocol.s(s)))]
	visible = true


func close_panel() -> void:
	visible = false
	_cid = ""


func _unhandled_key_input(event: InputEvent) -> void:
	if not visible or not (event is InputEventKey) or not event.pressed:
		return
	if (event as InputEventKey).keycode == KEY_ESCAPE:
		close_panel()
		get_viewport().set_input_as_handled()
