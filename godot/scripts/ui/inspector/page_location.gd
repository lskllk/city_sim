# page_location.gd —— 建筑详情页(常驻, 原地 bind): 权限 / 人员 / 物件。
class_name InspLocationPage
extends UiPage

const PERSON_ROW := preload("res://scenes/components/person_row.tscn")
const ITEM_ROW := preload("res://scenes/components/item_row.tscn")

var _header: Control
var _perm: Label
var _cap: Label
var _cap_row: Control
var _p_sec: Control
var _p: UiList
var _p_empty: Label
var _i_sec: Control
var _i: UiList
var _i_empty: Label


func build() -> void:
	_header = UiKit.header(self)

	var a: VBoxContainer = UiKit.section(self, "权限").body()
	_perm = UiKit.kv(a, "进入权限")
	_cap = UiKit.kv(a, "容量")
	_cap_row = _cap.get_parent()

	_p_sec = UiKit.section(self, "人员")
	UiKit.column_header(_p_sec.body(), [
		["姓名", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["年龄", UiKit.W_AGE, HORIZONTAL_ALIGNMENT_RIGHT],
		["角色", UiKit.W_ROLE, HORIZONTAL_ALIGNMENT_LEFT],
		["当前行为", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["生命", UiKit.W_HP, HORIZONTAL_ALIGNMENT_LEFT],
	])
	_p = UiList.new(_p_sec.body(), PERSON_ROW)
	_p_empty = UiKit.muted(_p_sec.body(), "无人")

	_i_sec = UiKit.section(self, "物件")
	UiKit.column_header(_i_sec.body(), [
		["名称", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["数量", UiKit.W_QTY, HORIZONTAL_ALIGNMENT_RIGHT],
		["价格", UiKit.W_PRICE, HORIZONTAL_ALIGNMENT_LEFT],
		["使用者", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
	])
	_i = UiList.new(_i_sec.body(), ITEM_ROW)
	_i_empty = UiKit.muted(_i_sec.body(), "无")


func bind(id: String) -> void:
	var room := Store.room(id)
	if room.is_empty():
		return
	var people := _people_at(id)
	var items := _items_at(id)

	_header.set_header(Protocol.s(room.get("name", id)),
		"%s · %d/%d 人 · %d 物件" % [
			Zh.kind_zh(Protocol.s(room.get("kind", ""))),
			people.size(), int(Protocol.num(room.get("capacity"), 0.0)),
			items.size()])

	_perm.text = InspData.access_text(room)
	var pub: Variant = room.get("public", true)
	_cap_row.visible = not bool(pub)
	_cap.text = "%d 人" % int(Protocol.num(room.get("capacity"), 0.0))

	# --- 人员(行池) ---
	_p_sec.set_title("人员 %d" % people.size())
	_p_empty.visible = people.is_empty()
	for i in people.size():
		var k := String(people[i])
		var n := Store.npc(k)
		var age := Protocol.num(n.get("age"), -1.0)
		var hp := clampf(Protocol.num(
			Protocol.as_dict(n.get("signals", {})).get("hp"), 1.0), 0.0, 1.0)
		var r := _p.row(i)
		if not r.selected.is_connected(_on_person):
			r.selected.connect(_on_person)
		r.set_row(k, Protocol.s(n.get("name", k)),
			"—" if age < 0.0 else str(int(age)),
			Zh.role_zh(Protocol.s(n.get("role", ""))),
			InspData.activity_text(n), hp)
	_p.trim(people.size())

	# --- 物件(行池) ---
	_i_sec.set_title("物件 %d" % items.size())
	_i_empty.visible = items.is_empty()
	for i in items.size():
		var k := String(items[i])
		var e := Store.entity(k)
		var r := _i.row(i)
		if not r.selected.is_connected(_on_item):
			r.selected.connect(_on_item)
		r.set_row(k, InspData.item_name(e, k), InspData.qty_txt(e),
			InspData.price_txt(e), InspData.user_text(e))
	_i.trim(items.size())


func _people_at(id: String) -> Array:
	var out: Array = []
	for k in Store.npcs:
		if Protocol.s(Store.npcs[k].get("loc", "")) == id:
			out.append(str(k))
	out.sort()
	return out


func _items_at(id: String) -> Array:
	var out: Array = []
	for k in Store.entities:
		if Protocol.s(Store.entities[k].get("loc", "")) == id:
			out.append(str(k))
	out.sort()
	return out


func _on_person(id: String) -> void:
	Store.select("npc", id)


func _on_item(id: String) -> void:
	Store.select("entity", id)
