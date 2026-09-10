# npc_header.gd —— Inspector 顶部标题(名称 + 副标题)。
extends VBoxContainer


func set_header(title: String, sub: String) -> void:
	%Title.text = title
	%Sub.text = sub
