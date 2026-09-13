# item_row.gd —— 建筑"物件"表的一行(可点进物件): 名称 / 数量 / 价格 / 使用者。
#
# 常驻复用: 由 UiList 管理, 每次只 set_row(...), 不重建。
extends Button

signal selected(id: String)

var entity_id := ""


func _ready() -> void:
	UiKit.apply_list_row(self)
	pressed.connect(func() -> void: selected.emit(entity_id))


func set_row(id: String, nm: String, qty: String, price: String,
		user: String) -> void:
	entity_id = id
	%Name.text = nm
	%Qty.text = qty
	%Price.text = price
	%User.text = user
