# person_row.gd —— 建筑"人员"表的一行(可点进 NPC): 姓名 / 年龄 / 角色 / 当前行为 / 生命条。
#
# 常驻复用: 由 UiList 管理, 每次只 set_row(...), 不重建。
extends Button

signal selected(id: String)

var npc_id := ""


func _ready() -> void:
	UiKit.apply_list_row(self)
	pressed.connect(func() -> void: selected.emit(npc_id))


func set_row(id: String, nm: String, age: String, role: String,
		behavior: String, hp: float) -> void:
	npc_id = id
	%Name.text = nm
	%Age.text = age
	%Role.text = role
	%Behavior.text = behavior
	var v := clampf(hp, 0.0, 1.0)
	%Bar.value = v
	%Bar.add_theme_stylebox_override("fill", UiKit.style_fill(UiKit.gauge_color(v)))
	%Pct.text = "%d%%" % roundi(v * 100.0)
