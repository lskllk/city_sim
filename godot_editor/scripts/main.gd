extends Control

const MV := preload("res://scripts/map_view.gd")
## main.gd —— 编辑器外壳: 菜单栏 / 左侧画布 / 右侧资产+属性 / 底栏状态。
## 只做 UI 编排, 数据在 MapDoc, 绘制在 MapView。

var _view
var _palette: ItemList
var _info: Label
var _status: Label
var _grid_spin: SpinBox
var _tool_btns: Array[Button] = []
var _type_keys: Array = []


func _ready() -> void:
	_build()
	MapDoc.changed.connect(_refresh_info)
	_refresh_info()
	_refresh_status("就绪 · 选一个资产放置, 或切到连线模式画路")


# ---------------------------------------------------------------------------
func _build() -> void:
	var root := VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 4)
	add_child(root)

	root.add_child(_build_menu())

	var hb := HBoxContainer.new()
	hb.size_flags_vertical = Control.SIZE_EXPAND_FILL
	hb.add_theme_constant_override("separation", 6)
	root.add_child(hb)

	_view = MV.new()
	_view.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_view.selection_changed.connect(_refresh_info)
	_view.status_message.connect(_refresh_status)
	hb.add_child(_view)

	hb.add_child(_build_right_panel())

	_status = Label.new()
	_status.text = "就绪"
	_status.add_theme_color_override("font_color", Color("8ea2b8"))
	root.add_child(_status)


func _build_menu() -> MenuBar:
	var mb := MenuBar.new()
	var file := PopupMenu.new()
	file.name = "文件"
	file.add_item("新建", 0)
	file.add_item("导入…", 1)
	file.add_item("导出…", 2)
	file.id_pressed.connect(_on_file_menu)
	mb.add_child(file)
	var viewm := PopupMenu.new()
	viewm.name = "视图"
	viewm.add_item("适配内容", 0)
	viewm.id_pressed.connect(func(id: int) -> void:
		if id == 0:
			_view.fit_to_content())
	mb.add_child(viewm)
	return mb


func _build_right_panel() -> VBoxContainer:
	var right := VBoxContainer.new()
	right.custom_minimum_size.x = 270
	right.add_theme_constant_override("separation", 6)

	right.add_child(_header("工具"))
	var tools := HBoxContainer.new()
	tools.add_theme_constant_override("separation", 4)
	_tool_btns.clear()
	_tool_btns.append(_tool_button("选择/移动", MV.Tool.SELECT))
	_tool_btns.append(_tool_button("画路", MV.Tool.ROAD))
	tools.add_child(_tool_btns[0])
	tools.add_child(_tool_btns[1])
	right.add_child(tools)

	right.add_child(_header("资产 · Building"))
	_palette = ItemList.new()
	_palette.custom_minimum_size.y = 200
	_palette.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_palette.item_selected.connect(_on_pick_type)
	right.add_child(_palette)

	right.add_child(_header("栅格 (m)"))
	_grid_spin = SpinBox.new()
	_grid_spin.min_value = 0.25
	_grid_spin.max_value = 50.0
	_grid_spin.step = 0.25
	_grid_spin.value = MapDoc.grid_size
	_grid_spin.value_changed.connect(func(v: float) -> void:
		MapDoc.grid_size = v
		_view.queue_redraw())
	right.add_child(_grid_spin)

	right.add_child(_header("属性"))
	_info = Label.new()
	_info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_info.custom_minimum_size.y = 120
	_info.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(_info)

	var del := Button.new()
	del.text = "删除选中 (Delete)"
	del.pressed.connect(func() -> void: _view._delete_selected())
	right.add_child(del)
	return right


func _tool_button(text: String, tool: int) -> Button:
	var b := Button.new()
	b.text = text
	b.toggle_mode = true
	b.pressed.connect(func() -> void:
		_view.set_tool(tool)
		_update_tool_buttons())
	return b


func _header(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_color_override("font_color", Color("6fb7ff"))
	return l


# ---------------------------------------------------------------------------
func _fill_palette() -> void:
	_palette.clear()
	_type_keys = MapDoc.building_types.keys()
	_type_keys.sort()
	for k in _type_keys:
		var t: Dictionary = MapDoc.building_types[k]
		_palette.add_item("%s  (%s · cap%s)" % [
			String(t.get("name", k)), k, str(t.get("capacity", "?"))])


func _on_pick_type(index: int) -> void:
	if index < 0 or index >= _type_keys.size():
		return
	_view.placing_type = String(_type_keys[index])
	_view.set_tool(MV.Tool.PLACE)
	_update_tool_buttons()
	_refresh_status("放置: %s" % _view.placing_type)


func _update_tool_buttons() -> void:
	_tool_btns[0].button_pressed = _view.tool == MV.Tool.SELECT
	_tool_btns[1].button_pressed = _view.tool == MV.Tool.ROAD


func _refresh_info() -> void:
	if _info == null:
		return
	var lines: Array[String] = []
	match _view.sel_kind:
		"building":
			var b: Dictionary = MapDoc.buildings.get(_view.sel_id, {})
			if not b.is_empty():
				var c: Vector2 = b["center"]
				var s: Vector2 = b["size"]
				lines.append("建筑 %s" % _view.sel_id)
				lines.append("类型: %s" % String(b["type"]))
				lines.append("名称: %s" % MapDoc.type_display(String(b["type"])))
				lines.append("位置: (%.1f, %.1f)" % [c.x, c.y])
				lines.append("尺寸: %.1f × %.1f m" % [s.x, s.y])
		"node":
			var n: Dictionary = MapDoc.nodes.get(_view.sel_id, {})
			if not n.is_empty():
				var p: Vector2 = n["xy"]
				lines.append("节点 %s" % _view.sel_id)
				lines.append("类型: %s" % String(n["kind"]))
				lines.append("位置: (%.1f, %.1f)" % [p.x, p.y])
		"edge":
			var e: Dictionary = MapDoc.edges.get(_view.sel_id, {})
			if not e.is_empty():
				lines.append("路段 %s" % _view.sel_id)
				lines.append("%s → %s" % [String(e["a"]), String(e["b"])])
				lines.append("等级: %s" % String(e["class"]))
				lines.append("宽 %.1f m · 速 %.1f m/s" % [float(e["width"]), float(e["speed"])])
		_:
			lines.append("未选中")
			lines.append("")
			lines.append("在右侧选资产 → 点画布放置")
			lines.append("或点\"画路\" → 连续点击落节点连线")
	_info.text = "\n".join(lines)


func _refresh_status(msg: String) -> void:
	if _status != null:
		_status.text = msg


# ---------------------------------------------------------------------------
func _on_file_menu(id: int) -> void:
	match id:
		0:
			MapDoc.new_map()
			_view.fit_to_content()
			_refresh_status("已新建空白地图")
		1:
			_show_dialog(false)
		2:
			_show_dialog(true)


func _show_dialog(save: bool) -> void:
	var d := FileDialog.new()
	d.access = FileDialog.ACCESS_FILESYSTEM
	d.file_mode = FileDialog.FILE_MODE_SAVE_FILE if save \
		else FileDialog.FILE_MODE_OPEN_FILE
	d.add_filter("*.json", "CitySim Map")
	d.use_native_dialog = false
	d.size = Vector2i(760, 520)
	add_child(d)
	if save:
		d.current_file = "map.json"
		d.file_selected.connect(func(p: String) -> void:
			if MapDoc.save_map(p):
				_refresh_status("已导出: " + p)
			else:
				_refresh_status("导出失败: " + p)
			d.queue_free())
	else:
		d.file_selected.connect(func(p: String) -> void:
			if MapDoc.load_map(p):
				_view.fit_to_content()
				_refresh_status("已导入: " + p)
			else:
				_refresh_status("导入失败: " + p)
			d.queue_free())
	d.canceled.connect(d.queue_free)
	d.popup_centered()


func _notification(what: int) -> void:
	if what == NOTIFICATION_READY:
		_fill_palette()
		_update_tool_buttons()
