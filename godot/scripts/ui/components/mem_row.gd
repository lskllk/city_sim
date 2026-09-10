# mem_row.gd —— 一条记忆(item 行)。
extends VBoxContainer


func set_row(item_name: String, located: String, believe: float, remember: float) -> void:
	%ItemName.text = item_name
	%Located.text = "@ %s" % located
	%Believe.text = "信:%d%%" % roundi(believe * 100.0)
	%Remember.text = "记:%d%%" % roundi(remember * 100.0)
