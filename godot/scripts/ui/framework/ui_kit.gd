# ui_kit.gd —— UI 组件工厂(纯静态, 通用, 不依赖任何业务数据)。
#
# 只负责"把常驻控件拼出来", 不读 Store / 不含文案。业务放 feature 层(inspector/data.gd)。
# 配合 UiList(行池) 与 UiPage(常驻页面), 构成"retained + bind"的轻量 UI 框架。
class_name UiKit
extends RefCounted

const SECTION := preload("res://scenes/components/inspector_section.tscn")
const SIGNAL_ROW := preload("res://scenes/components/signal_row.tscn")
const CAND_ROW := preload("res://scenes/components/cand_row.tscn")
const MEM_ROW := preload("res://scenes/components/mem_row.tscn")
const EVENT_ROW := preload("res://scenes/components/event_row.tscn")
const KV_ROW := preload("res://scenes/components/kv_row.tscn")
const NPC_HEADER := preload("res://scenes/components/npc_header.tscn")

# 列表列宽(表头与行共用)。
const W_AGE := 34.0
const W_ROLE := 64.0
const W_HP := 84.0
const W_QTY := 46.0
const W_PRICE := 64.0


# --- 结构 -----------------------------------------------------------------
## 区段(标题 + 分隔线 + 内容容器), 返回区段根(可 set_title + body())。
static func section(parent: Node, title: String) -> Control:
	var sec: Control = SECTION.instantiate()
	parent.add_child(sec)
	sec.set_title(title)
	return sec


## 页面顶部标题(名称 + 副标题), 返回可 set_header 的控件。
static func header(parent: Node) -> Control:
	var h: Control = NPC_HEADER.instantiate()
	parent.add_child(h)
	return h


## 键值行; 返回可原地更新的"值"Label。
static func kv(parent: Node, key: String) -> Label:
	var row: Control = KV_ROW.instantiate()
	parent.add_child(row)
	row.set_row(key, "—")
	return row.value_label()


static func muted(parent: Node, text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", UiTheme.FS_BODY)
	l.add_theme_color_override("font_color", UiTheme.TEXT_DIM)
	parent.add_child(l)
	return l


## 轻量表头: specs = [[文本, 宽(0=弹性), 对齐], ...]。
static func column_header(parent: Node, specs: Array) -> HBoxContainer:
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", UiTheme.ROW_SEP)
	parent.add_child(hb)
	for spec in specs:
		var l := Label.new()
		l.text = str(spec[0])
		l.add_theme_font_size_override("font_size", UiTheme.FS_HEAD)
		l.add_theme_color_override("font_color", UiTheme.TEXT_DIM)
		l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		var w := float(spec[1]) if spec.size() > 1 else 0.0
		l.horizontal_alignment = int(spec[2]) if spec.size() > 2 else HORIZONTAL_ALIGNMENT_LEFT
		if w > 0.0:
			l.custom_minimum_size.x = w
			l.size_flags_horizontal = Control.SIZE_FILL
		else:
			l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		hb.add_child(l)
	return hb


# --- 样式 -----------------------------------------------------------------
static func style_fill(color: Color) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(3)
	return sb


## 进度条/生命条按值取色(<25% 红, <50% 橙, 其余绿)。
static func gauge_color(v: float) -> Color:
	if v < 0.25:
		return UiTheme.BAD
	if v < 0.5:
		return UiTheme.WARN
	return UiTheme.OK


## 统一可点列表行(Button)的样式: 常态透明 + 悬浮/按下高亮 + 无焦点框。
## 注意: 绝不能用 flat=true —— Godot 4 里 flat 会连 hover/pressed 样式一起不画。
static func apply_list_row(btn: Button) -> void:
	btn.flat = false
	btn.focus_mode = Control.FOCUS_NONE
	btn.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	btn.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
	btn.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	var hover := StyleBoxFlat.new()
	hover.bg_color = UiTheme.ROW_HOVER
	hover.set_corner_radius_all(UiTheme.RADIUS)
	btn.add_theme_stylebox_override("hover", hover)
	var pressed := StyleBoxFlat.new()
	pressed.bg_color = UiTheme.ROW_PRESSED
	pressed.set_corner_radius_all(UiTheme.RADIUS)
	btn.add_theme_stylebox_override("pressed", pressed)
	# 子控件不得拦截鼠标(ProgressBar 默认 STOP, 会挡住整行 hover/点击)。
	_ignore_mouse(btn)


static func _ignore_mouse(n: Node) -> void:
	for c in n.get_children():
		if c is Control:
			(c as Control).mouse_filter = Control.MOUSE_FILTER_IGNORE
			_ignore_mouse(c)
