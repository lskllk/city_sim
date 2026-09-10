# event_row.gd —— 一条 NPC 事件(#tick + 类型 + 单行摘要)。
extends HBoxContainer


func set_row(tick: int, type_text: String, type_color: Color, text: String) -> void:
	%Tick.text = "#%d" % tick
	%Type.text = type_text
	%Type.add_theme_color_override("font_color", type_color)
	%Text.text = text
