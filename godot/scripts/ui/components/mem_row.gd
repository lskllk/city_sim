# mem_row.gd —— 一条记忆(单行): 物品名 + 地点 + 【所属】+ 「信/记」进度条。
#
# 所属(owner): 公共 / 自己 / 自家 / 公司·X / 某个人的 —— 一眼看出“这条东西谁能用”。
extends HBoxContainer


func set_row(item_name: String, located: String, owner_text: String,
		believe: float, remember: float) -> void:
	%ItemName.text = item_name
	%Located.text = ("@ %s" % located) if located != "" else ""
	%Owner.text = owner_text
	%Owner.visible = owner_text != ""
	var b := clampf(believe, 0.0, 1.0)
	var r := clampf(remember, 0.0, 1.0)
	%BelieveBar.value = b * 100.0
	%RememberBar.value = r * 100.0
	%BelieveBar.tooltip_text = "信 %d%%" % roundi(b * 100.0)
	%RememberBar.tooltip_text = "记 %d%%" % roundi(r * 100.0)
