# inspector.gd —— 选中检查器(只读, retained + bind 架构)。
#
# 铁律(避免"闪 / 点不中"类 UI bug):
#   - 四个页面常驻, 一次构建; 切换选中项只切 visible, 不 new / 不 free;
#   - 每 ~100ms 只调 page.bind(id) 原地刷新数值, 绝不增删控件;
#   - 列表用 UiList 行池, 数量变化只补行/隐藏行;
#   - 返回键常驻, 只切 visible;
#   - 页面只读 Store, 通过 UiKit/InspData 组装。
class_name InspectorPanel
extends PanelContainer

const TICK := 0.1

var _pages: Dictionary = {}      # kind -> UiPage
var _cur: UiPage = null
var _back: Button
var _accum := 0.0


func _ready() -> void:
	var body: VBoxContainer = %Body

	# --- 常驻顶栏: 返回键 ---
	var top := HBoxContainer.new()
	body.add_child(top)
	_back = _make_back()
	_back.visible = false
	top.add_child(_back)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(spacer)

	# --- 常驻页面栈 ---
	var stack := VBoxContainer.new()
	stack.size_flags_vertical = Control.SIZE_EXPAND_FILL
	stack.add_theme_constant_override("separation", 0)
	body.add_child(stack)
	var empty := InspEmptyPage.new()
	var npc := InspNpcPage.new()
	var loc := InspLocationPage.new()
	var ent := InspEntityPage.new()
	for p: UiPage in [empty, npc, loc, ent]:
		p.visible = false
		stack.add_child(p)
	_pages = {"": empty, "npc": npc, "location": loc, "entity": ent}

	set_process(true)
	_update()


func _process(delta: float) -> void:
	_accum += delta
	if _accum < TICK:
		return
	_accum = 0.0
	_update()


func _update() -> void:
	var kind := Store.sel_kind
	var id := ""
	match kind:
		"npc":
			id = Store.sel_npc
		"location":
			id = Store.sel_location
		"entity":
			id = Store.sel_entity
	var page: UiPage = _pages.get(kind, _pages[""])
	if page == null or not _valid(kind, id):
		page = _pages[""]
	if page != _cur:
		if _cur != null:
			_cur.visible = false
		page.visible = true
		_cur = page
	_back.visible = Store.can_go_back()
	_cur.bind(id)


## 选中目标是否仍存在(死亡/移除后回退到空页, 不显示陈旧内容)。
func _valid(kind: String, id: String) -> bool:
	if id == "":
		return false
	match kind:
		"npc":
			return Store.npcs.has(id)
		"location":
			return Store.rooms.has(id)
		"entity":
			return Store.entities.has(id)
		_:
			return false


func _make_back() -> Button:
	var b := Button.new()
	b.text = "← 返回"
	b.flat = true
	b.focus_mode = Control.FOCUS_NONE
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	b.add_theme_font_size_override("font_size", 12)
	b.add_theme_color_override("font_color", Color("6fb7ff"))
	b.pressed.connect(func() -> void: Store.back())
	return b
