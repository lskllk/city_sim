# page_location.gd —— 建筑详情(观察器)。
#
# 模板【按建筑类型绑定】(用户定的口径, 和编辑器同一套):
#   商铺 shop → 公司(可进"公司运营"页) + 线路(前台/在岗/排队) + 在店里的人
#               + 物件(含【在售库存】与【工位/销售前台】—— 交易靠它)
#   住宅 home → 楼层 + 住户 + 家里的东西
#   其它      → 权限 + 在场的人 (市场多一行"无限库存 · 只有公司能采购")
#
# 招牌信息【已从详情移除】(那是经营手段 → 归公司运营页的"广告", 后续做)。
#
# 铁律: 页面常驻; bind() 只改数值, 不重建控件(见 ui_page.gd)。
class_name InspLocationPage
extends UiPage

const PERSON_ROW := preload("res://scenes/components/person_row.tscn")
## 公司运营弹窗: 用 preload 调它的静态入口(不依赖 class_name 的全局类表)
const CompanyPanelScript := preload("res://scripts/ui/company_panel.gd")
const ITEM_ROW := preload("res://scenes/components/item_row.tscn")

var _header: Control
var _floor_sec: Control
var _floor_sel: OptionButton
var _cur_bid := ""
var _cur_floor := 1
var _room: Dictionary = {}

var _perm: Label
var _cap: Label
var _cap_row: Control
var _p_sec: Control
var _p: UiList
var _p_empty: Label
var _i_sec: Control
var _i: UiList
var _i_empty: Label
var _comp_sec: Control
var _comp_body: VBoxContainer

# 公司段: 两种形态的控件【各建一次】(未注册 / 已注册), bind 只切 visible + 改文字。
# —— 铁律: bind() 绝不增删控件, 否则按钮每 100ms 被重建一次 = 闪烁 + 点不中。
var _reg_hint: Label
var _reg_name: LineEdit
var _reg_btn: Button
var _go_btn: Button
var _msg: Label                       # 上一步命令的结果(后端应答)
var _seen_reply := 0


func build() -> void:
	_header = UiKit.header(self)

	# 楼层(仅住宅显示)
	_floor_sec = UiKit.section(self, "楼层")
	_floor_sec.visible = false
	_floor_sel = OptionButton.new()
	_floor_sel.item_selected.connect(_on_floor_picked)
	_floor_sec.body().add_child(_floor_sel)

	var a: VBoxContainer = UiKit.section(self, "权限").body()
	_perm = UiKit.kv(a, "进入权限")
	_cap = UiKit.kv(a, "容量")
	_cap_row = _cap.get_parent()

	# 公司(商铺): 未注册 → 只有【注册公司】; 注册了 → 只有【打开运营界面】。
	# 其他经营信息(线路/员工/货物/价格)全在【弹窗里的运营界面】, 这里一律不显示。
	_comp_sec = UiKit.section(self, "公司")
	_comp_body = _comp_sec.body()
	_reg_hint = UiKit.muted(_comp_body, "没注册公司的店【不能卖、不能招人】")
	_reg_name = LineEdit.new()
	_comp_body.add_child(_reg_name)
	_reg_btn = Button.new()
	_reg_btn.text = "注册公司（现金 ¥1000）"
	_reg_btn.pressed.connect(func() -> void:
		Commands.cmd("register_company", {"location": _cur_bid,
			"name": _reg_name.text.strip_edges()}))
	_comp_body.add_child(_reg_btn)
	_go_btn = Button.new()
	_go_btn.text = "打开运营界面"
	_go_btn.pressed.connect(func() -> void:
		CompanyPanelScript.open_company(Protocol.s(_room.get("company", ""))))
	_comp_body.add_child(_go_btn)
	_msg = UiKit.muted(_comp_body, "")

	# 在店里的人(全部类型都显示)
	_p_sec = UiKit.section(self, "在店里的人")
	UiKit.column_header(_p_sec.body(), [
		["姓名", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["年龄", UiKit.W_AGE, HORIZONTAL_ALIGNMENT_RIGHT],
		["角色", UiKit.W_ROLE, HORIZONTAL_ALIGNMENT_LEFT],
		["当前行为", 0.0, HORIZONTAL_ALIGNMENT_LEFT],
		["生命", UiKit.W_HP, HORIZONTAL_ALIGNMENT_LEFT],
	])
	_p = UiList.new(_p_sec.body(), PERSON_ROW)
	_p_empty = UiKit.muted(_p_sec.body(), "无人")

	# 物件(在售库存 / 工位 / 货架) —— 商铺也有: 交易靠工位
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
	_room = room
	var bid := Store.building_of(id)
	if bid != _cur_bid:
		_cur_bid = bid
		_cur_floor = 1
	var multi := Store.is_multi(bid)
	var is_home := Zh.kind_zh(Protocol.s(room.get("kind", ""))) == "住所"
	_floor_sec.visible = multi and is_home
	if _floor_sec.visible:
		var nf := Store.floor_units(bid)
		_cur_floor = clampi(_cur_floor, 1, nf)
		if _floor_sel.item_count != nf:
			_floor_sel.clear()
			for i in range(1, nf + 1):
				_floor_sel.add_item("第 %d 层" % i)
		if _floor_sel.selected != _cur_floor - 1:
			_floor_sel.select(_cur_floor - 1)
	if is_home:
		Store.set_floor(_cur_floor)
	_render()


func _on_floor_picked(i: int) -> void:
	_cur_floor = i + 1
	Store.set_floor(_cur_floor)
	_render()


func _render() -> void:
	var bid := _cur_bid
	var multi := Store.is_multi(bid)
	var unit := Store.unit_of(bid, _cur_floor)
	var unit_room := Store.room(unit)
	if unit_room.is_empty():
		unit_room = _room
	var kind := Protocol.s(_room.get("kind", ""))
	var is_home := Zh.kind_zh(kind) == "住所"
	var is_shop := kind == "shop"
	# 商铺: 详情只留 基础/权限/公司(经营在弹窗里); 住宅/其它照旧
	var people := _at(Store.npcs, unit if is_home else bid)
	var items := _at(Store.entities, unit if is_home else bid)

	var cap := int(Protocol.num(unit_room.get("capacity"), 0.0))
	var title := Protocol.s(_room.get("name", bid))
	if is_home and multi:
		title = "%s · %d层" % [title, _cur_floor]
	# 商铺的副标题只写类型 —— 人数/物件数都归运营界面, 这里"其他什么都不要"
	_header.set_header(title, Zh.kind_zh(kind) if is_shop else
		"%s · %d 人 · %d 物件" % [Zh.kind_zh(kind), people.size(), items.size()])

	_sync_company(kind, bid)

	_perm.text = InspData.access_text(unit_room)
	_cap_row.visible = not bool(unit_room.get("public", true))
	_cap.text = "%d 人" % cap

	# --- 在店里的人(商铺不显示: 顾客/店员都在运营界面的"实时监控"里) ---
	_p_sec.visible = not is_shop
	_p_sec.set_title(("住户 %d" if is_home else "在店里的人 %d") % people.size())
	_p_empty.visible = people.is_empty()
	for i in people.size():
		var k := String(people[i])
		var n := Store.npc(k)
		var age := Protocol.num(n.get("age"), -1.0)
		var hp := clampf(Protocol.num(
			Protocol.as_dict(n.get("signals", {})).get("hp"), 1.0), 0.0, 1.0)
		var work := Protocol.as_dict(n.get("work", {}))
		var act := Protocol.s(n.get("activity", ""))
		if Protocol.s(work.get("station", "")) != "" and act == "working":
			act = "在岗"
		elif Protocol.s(work.get("station", "")) != "":
			act = "店员·不在岗"
		_p.row(i).set_row(k, String(n.get("name", k)),
			"—" if age < 0.0 else str(int(age)),
			Zh.role_zh(Protocol.s(n.get("role", ""))), act, hp)
	_p.trim(people.size())

	# --- 物件(商铺不显示: 货物/工位都在运营界面的"货物管理"里) ---
	_i_sec.visible = not is_shop
	_i_sec.set_title("物件 %d" % items.size())
	_i_empty.visible = items.is_empty()
	for i in items.size():
		var e := Store.entity(String(items[i]))
		var st := int(Protocol.num(e.get("stock", 1.0)))
		var pr := Protocol.num(e.get("price", 0.0))
		var lane := Store.entity(String(items[i]))
		var qty := "∞" if st < 0 else str(st)
		if Protocol.s(e.get("item_type", "")) == "station_counter":
			qty = "工位"                      # 销售前台: 交易靠它
		_i.row(i).set_row(String(items[i]), String(e.get("name", items[i])),
			qty, "—" if pr <= 0.0 else "¥%d" % int(pr),
			Store.name_of(Protocol.s(e.get("claimed_by", ""))))
	_i.trim(items.size())


## 公司段(商铺): 未注册 → 注册按钮; 注册了 → 打开运营界面。
## ★ 只切 visible / 改文字 —— 绝不在这里 new/free(否则按钮闪烁点不中)
func _sync_company(kind: String, bid: String) -> void:
	if _msg != null and Commands.reply_seq != _seen_reply:
		_seen_reply = Commands.reply_seq
		var r: Dictionary = Commands.last_reply
		var ok := bool(r.get("ok", false))
		var why := Protocol.s(r.get("why", ""))
		_msg.text = ("✓ 成功" if ok else "✗ %s" % (why if why != "" else "失败"))
		_msg.add_theme_color_override("font_color",
			Color("7fe0a8") if ok else Color("e05252"))
		# 注册成功 → 【直接进入运营界面】(用户定的流程)
		var new_cid := Protocol.s(Protocol.as_dict(r.get("data", {})).get("company", ""))
		if ok and new_cid != "":
			CompanyPanelScript.open_company(new_cid)      # 注册成功 → 直接进运营界面
	var cid := Protocol.s(_room.get("company", ""))
	_comp_sec.visible = kind == "shop"
	if kind != "shop":
		return
	var registered := cid != ""
	_reg_hint.visible = not registered
	_reg_name.visible = not registered
	_reg_btn.visible = not registered
	_go_btn.visible = registered
	_comp_sec.set_title("公司 · %s" % (cid if registered else "未注册"))
	if not registered and not _reg_name.has_focus():
		_reg_name.placeholder_text = "%s 公司" % Protocol.s(_room.get("name", bid))


func _at(d: Dictionary, unit: String) -> Array:
	var out: Array = []
	for k in d:
		var rec: Dictionary = d[k]
		var loc := Protocol.s(rec.get("loc", ""))
		if loc == unit or Store.building_of(loc) == unit:
			out.append(String(k))
	out.sort()
	return out
