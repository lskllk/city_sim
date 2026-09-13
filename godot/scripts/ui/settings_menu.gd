# settings_menu.gd —— 设置界面(叠加层): 按 Settings 的 schema 自动生成。
#
# 用法: 实例化 settings_menu.tscn 并 add_child; 关闭时发 `closed` 信号由宿主释放。
# 左栏 = 分区, 右栏 = 该分区的设置行(控件类型由 schema 的 Type 决定)。
# 新增设置项无需改本文件(只改 app_settings.gd 的 register())。
extends Control

signal closed

var _cats: VBoxContainer
var _rows: VBoxContainer
var _current: String = ""


func _ready() -> void:
	_cats = %Categories
	_rows = %Rows
	%Close.pressed.connect(_close)
	%Reset.pressed.connect(func() -> void:
		Settings.reset_all()
		_build_categories())
	%MainMenu.pressed.connect(func() -> void: App.return_to_launcher())
	%MainMenu.visible = (App.state == App.State.GAME)
	Settings.schema_changed.connect(_build_categories)
	_build_categories()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		_close()


func _close() -> void:
	closed.emit()


# --- 分区 -----------------------------------------------------------------
func _build_categories() -> void:
	for c in _cats.get_children():
		c.queue_free()
	var secs := Settings.sections()
	for s in secs:
		var b := Button.new()
		b.text = Settings.section_label(s)
		b.toggle_mode = true
		b.focus_mode = Control.FOCUS_NONE
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.pressed.connect(_select_section.bind(s))
		_cats.add_child(b)
	if not secs.is_empty():
		_select_section(secs[0] if _current == "" else _current)


func _select_section(section: String) -> void:
	_current = section
	for b in _cats.get_children():
		b.button_pressed = (b.text == Settings.section_label(section))
	_build_rows()


# --- 设置行(按 Type 生成控件) --------------------------------------------
func _build_rows() -> void:
	for c in _rows.get_children():
		c.queue_free()
	for spec in Settings.entries(_current):
		_rows.add_child(_make_row(spec))


func _make_row(spec: Dictionary) -> Control:
	var section := str(spec["section"])
	var key := str(spec["key"])
	var value: Variant = Settings.get_value(section, key)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)

	var label := Label.new()
	label.text = str(spec["label"])
	label.tooltip_text = str(spec["hint"])
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(label)

	match int(spec["type"]):
		Settings.Type.BOOL:
			var cb := CheckButton.new()
			cb.button_pressed = bool(value)
			cb.toggled.connect(func(v: bool) -> void:
				Settings.set_value(section, key, v))
			row.add_child(cb)
		Settings.Type.INT:
			var sp := SpinBox.new()
			sp.min_value = -1000000
			sp.max_value = 1000000
			sp.step = 1
			sp.value = int(value)
			sp.value_changed.connect(func(v: float) -> void:
				Settings.set_value(section, key, int(v)))
			row.add_child(sp)
		Settings.Type.FLOAT:
			var sp := SpinBox.new()
			sp.min_value = -1000000
			sp.max_value = 1000000
			sp.step = 0.05
			sp.value = float(value)
			sp.value_changed.connect(func(v: float) -> void:
				Settings.set_value(section, key, v))
			row.add_child(sp)
		Settings.Type.ENUM:
			var choices: Array = spec["choices"]
			var ob := OptionButton.new()
			var sel := 0
			for i in range(choices.size()):
				var cv := _choice_value(choices[i])
				ob.add_item(_choice_label(choices[i]), i)
				if cv == str(value):
					sel = i
			ob.selected = sel
			ob.item_selected.connect(func(i: int) -> void:
				Settings.set_value(section, key, _choice_value(choices[i])))
			row.add_child(ob)
		_:
			var le := LineEdit.new()
			le.text = str(value)
			le.custom_minimum_size = Vector2(260, 0)
			le.text_submitted.connect(func(t: String) -> void:
				Settings.set_value(section, key, t))
			le.focus_exited.connect(func() -> void:
				Settings.set_value(section, key, le.text))
			row.add_child(le)
	return row


func _choice_value(ch: Variant) -> String:
	return str(ch["value"]) if typeof(ch) == TYPE_DICTIONARY else str(ch)


func _choice_label(ch: Variant) -> String:
	return str(ch["label"]) if typeof(ch) == TYPE_DICTIONARY else str(ch)
