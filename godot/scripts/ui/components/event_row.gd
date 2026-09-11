# event_row.gd —— 一条 NPC 事件(#tick + 类型 + 单行摘要)。
extends HBoxContainer


func set_row(tick: int, type_text: String, type_color: Color, text: String) -> void:
	var day := tick / 1440 + 1          # 一天 1440 tick
	var m := tick % 1440
	%Tick.text = "D%d %02d:%02d" % [day, m / 60, m % 60]
	%Type.text = type_text
	%Type.add_theme_color_override("font_color", type_color)
	%Text.text = text
