# page_company.gd —— 公司运营(观察器里的独立一页)。
#
# 用户定的结构:
#   HR 管理   —— 员工 / 招聘发布 / 时薪 / 营业时间 / 现金
#   价格管理  —— 旗下店铺在售品类的售价(改价 = 只改世界真值; 顾客要【看见】才知道)
#   (广告以后加在这个页里)
#
# 页面常驻, bind() 只改数值, 不重建控件(见 ui_page.gd 的铁律)。
class_name InspCompanyPage
extends UiPage

const PERSON_ROW := preload("res://scenes/components/person_row.tscn")

var _header: Control
var _cur := ""                 # 当前公司 id

var _cash: Label
var _hours: Label
var _hire_lb: Label
var _staff: UiList
var _staff_empty: Label
var _hire_n: SpinBox
var _wage: SpinBox
var _open_m: SpinBox
var _close_m: SpinBox
var _cash_in: SpinBox
var _hire_btn: Button
var _cancel_btn: Button
var _save_btn: Button

# 价格管理: 懒增长的行池(每行 = 名称 + 售价输入 + 保存)
var _price_rows: Array = []        # [{box, label, spin, btn, entity_id}]
var _price_sec: Control
var _msg: Label                     # 上一步命令的结果(后端应答)
var _seen_reply := 0


func build() -> void:
	_header = UiKit.header(self)
	_msg = UiKit.muted(self, "")

	# ---------------- HR 管理 ----------------
	var hr := UiKit.section(self, "HR 管理")
	_cash = UiKit.kv(hr.body(), "现金")
	_hours = UiKit.kv(hr.body(), "营业 / 时薪")
	_hire_lb = UiKit.kv(hr.body(), "招聘")

	_staff = UiList.new(hr.body(), PERSON_ROW)
	_staff_empty = UiKit.muted(hr.body(), "还没有员工 —— 发布招聘, 等每天撮合一次")

	var hrow := HBoxContainer.new()
	hrow.add_theme_constant_override("separation", 6)
	var l1 := Label.new()
	l1.text = "招几人"
	hrow.add_child(l1)
	_hire_n = _spin(0, 99, 1)
	hrow.add_child(_hire_n)
	_hire_btn = Button.new()
	_hire_btn.text = "发布招聘"
	_hire_btn.tooltip_text = "发布之后, 每天新的一天那一刻与【有意愿的 NPC】撮合(外面只做媒婆)"
	_hire_btn.pressed.connect(func() -> void:
		Commands.cmd("company_hire", {"company": _cur, "slots": int(_hire_n.value),
			"wage_per_hour": _wage.value}))
	hrow.add_child(_hire_btn)
	_cancel_btn = Button.new()
	_cancel_btn.text = "撤回"
	_cancel_btn.pressed.connect(func() -> void:
		Commands.cmd("company_hire", {"company": _cur, "slots": 0}))
	hrow.add_child(_cancel_btn)
	hr.body().add_child(hrow)

	var prow := HBoxContainer.new()
	prow.add_theme_constant_override("separation", 6)
	prow.add_child(_small("现金"))
	_cash_in = _spin(0, 1000000, 100)
	prow.add_child(_cash_in)
	prow.add_child(_small("时薪"))
	_wage = _spin(1, 500, 1)
	prow.add_child(_wage)
	hr.body().add_child(prow)
	var trow := HBoxContainer.new()
	trow.add_theme_constant_override("separation", 6)
	trow.add_child(_small("开门(分)"))
	_open_m = _spin(0, 1439, 30)
	trow.add_child(_open_m)
	trow.add_child(_small("关门(分)"))
	_close_m = _spin(1, 1440, 30)
	trow.add_child(_close_m)
	_save_btn = Button.new()
	_save_btn.text = "保存"
	_save_btn.pressed.connect(func() -> void:
		Commands.cmd("company_update", {"company": _cur, "cash": _cash_in.value,
			"wage_per_hour": _wage.value, "open_minute": int(_open_m.value),
			"close_minute": int(_close_m.value)}))
	trow.add_child(_save_btn)
	hr.body().add_child(trow)

	# ---------------- 价格管理 ----------------
	_price_sec = UiKit.section(self, "价格管理")
	UiKit.muted(_price_sec.body(),
		"改价只改世界真值 —— 顾客要【到店看见】或【听人说】才会知道新价")


func _small(t: String) -> Label:
	var l := Label.new()
	l.text = t
	return l


func _spin(mn: float, mx: float, step: float) -> SpinBox:
	var s := SpinBox.new()
	s.min_value = mn
	s.max_value = mx
	s.step = step
	return s


func bind(id: String) -> void:
	_cur = id
	if Commands.reply_seq != _seen_reply:
		_seen_reply = Commands.reply_seq
		var r0: Dictionary = Commands.last_reply
		var ok0 := bool(r0.get("ok", false))
		var why0 := Protocol.s(r0.get("why", ""))
		_msg.text = ("✓ 成功" if ok0 else "✗ %s" % (why0 if why0 != "" else "失败"))
		_msg.add_theme_color_override("font_color",
			Color("7fe0a8") if ok0 else Color("e05252"))
	var comp := InspData.company(id)
	if comp.is_empty():
		_header.set_header("公司", "（等下一帧快照）")
		return
	var shops: Array = Protocol.as_array(comp.get("shops", []))
	var nm := Protocol.s(comp.get("name", id))
	_header.set_header(nm, "公司 · %s"% id)
	_cash.text = "¥%.0f" % Protocol.num(comp.get("cash", 0.0))
	var open_m := int(Protocol.num(comp.get("open_minute", 480)))
	var close_m := int(Protocol.num(comp.get("close_minute", 1140)))
	_hours.text = "%02d:%02d - %02d:%02d · ¥%.0f/时" % [
		open_m / 60, open_m % 60, close_m / 60, close_m % 60,
		Protocol.num(comp.get("wage_per_hour", 0.0))]
	var hire_on := bool(comp.get("hiring_open", false))
	var slots := int(Protocol.num(comp.get("hiring_slots", 0)))
	_hire_lb.text = ("招 %d 人（等撮合）" % slots) if hire_on else "未发布"
	_hire_btn.text = "发布招聘" if not hire_on else "更新招聘"

	# 员工列表: 借 person_row 用(名字 / 时薪 / 在岗)
	var staff: Array = Protocol.as_array(comp.get("staff", []))
	_staff_empty.visible = staff.is_empty()
	for i in staff.size():
		var sid := Protocol.s(staff[i])
		var npc := Store.npc(sid)
		var work := Protocol.as_dict(npc.get("work", {}))
		var on_duty := Protocol.s(work.get("station", "")) != ""
		_staff.row(i).set_row(sid, String(Store.name_of(sid)),
			"¥%.0f/时" % Protocol.num(comp.get("wage_per_hour", 0.0)),
			Zh.role_zh(Protocol.s(npc.get("role", "worker"))),
			("在岗" if on_duty else "不在岗"),
			clampf(Protocol.num(Protocol.as_dict(npc.get("signals", {})).get("hp"), 1.0), 0.0, 1.0))
	_staff.trim(staff.size())

	# 价格管理: 公司在售的品类(跨旗下店铺)
	var rows := 0
	for sh in shops:
		for e in Store.entities.values():
			var d: Dictionary = e
			if Protocol.s(d.get("loc", "")) != Protocol.s(sh):
				continue
			if Protocol.num(d.get("price", 0.0)) <= 0.0:
				continue
			_set_price_row(rows, Protocol.s(d.get("id", "")),
				Protocol.s(d.get("name", "")), Protocol.num(d.get("price", 0.0)),
				Protocol.s(d.get("loc", "")))
			rows += 1
	for i in range(rows, _price_rows.size()):
		_price_rows[i]["box"].visible = false


func _set_price_row(i: int, eid: String, nm: String, price: float,
		loc: String) -> void:
	while _price_rows.size() <= i:
		var box := HBoxContainer.new()
		box.add_theme_constant_override("separation", 6)
		var lb := Label.new()
		lb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		box.add_child(lb)
		var sp := _spin(0.0, 9999.0, 1.0)
		box.add_child(sp)
		var bt := Button.new()
		bt.text = "改价"
		box.add_child(bt)
		# 行内的按钮/输入框只建一次, 之后只改数据(不重建 → 不闪、不丢焦点)
		(bt as Button).pressed.connect(func() -> void:
			var r: Dictionary = _price_rows[_row_of(bt)]
			Commands.cmd("set_price", {"entity": r["entity_id"], "price": r["spin"].value}))
		_price_sec.body().add_child(box)
		_price_rows.append({"box": box, "label": lb, "spin": sp, "btn": bt,
			"entity_id": eid})
	var r: Dictionary = _price_rows[i]
	r["box"].visible = true
	r["entity_id"] = eid
	(r["label"] as Label).text = "%s · %s" % [nm, Store.room(loc).get("name", loc)]
	if not (r["spin"] as SpinBox).has_focus():
		(r["spin"] as SpinBox).value = price


func _row_of(btn: Button) -> int:
	for i in _price_rows.size():
		if _price_rows[i]["btn"] == btn:
			return i
	return -1
