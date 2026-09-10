# signal_row.gd —— 单条信号条(名称 + 进度条 + 百分比)。
extends HBoxContainer


func set_row(label_text: String, v: float) -> void:
	%Name.text = label_text
	%Bar.value = v
	%Value.text = "%d%%" % roundi(v * 100.0)
	var fill := StyleBoxFlat.new()
	fill.bg_color = _color(v)
	fill.set_corner_radius_all(3)
	%Bar.add_theme_stylebox_override("fill", fill)


func _color(v: float) -> Color:
	if v < 0.25:
		return Color("e05252")
	if v < 0.5:
		return Color("e8a34d")
	return Color("3ddc84")
