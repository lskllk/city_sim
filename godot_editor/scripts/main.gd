extends Control

const MV := preload("res://scripts/map_view.gd")
## main.gd —— 编辑器外壳: 菜单 / 画布 / 右侧(工具+资产+检查器)。
##
## 交互(对齐观察器 Inspector 的信息架构):
##   默认: 工具(选择/画路) + 资产·Building + 栅格 + 空检查器
##   点建筑: 检查器 → 权限 / 人员(可新增随机) / 物件(可新增)
##   点人员/物件行: 下钻到详情, 编辑后「保存」
## 数据在 MapDoc, 绘制在 MapView; 本文件只做编排。

const MUTED := Color("7f8ea3")
const HEADER := Color("6fb7ff")

var _view
var _palette: ItemList
var _status: Label
var _base_page: VBoxContainer
var _detail_page: VBoxContainer
var _inspector: VBoxContainer
var _grid_spin: SpinBox
var _tool_btns: Array[Button] = []
var _type_keys: Array = []
var _item_type_keys: Array = []

var _context_building := ""     # 当前详情所属建筑

# 详情表单控件(每次重建时重新赋值)
var _f_name: LineEdit
var _f_gender: OptionButton
var _f_age: SpinBox
var _f_role: OptionButton
var _f_money: SpinBox
var _f_hunger: SpinBox
var _f_energy: SpinBox
var _f_fun: SpinBox
var _f_traits: LineEdit
var _f_bname: LineEdit
var _f_item_type: OptionButton
var _f_stock: SpinBox
var _f_price: SpinBox
var _f_owner: OptionButton
var _f_owner_ids: Array = []


func _ready() -> void:
	_build()
	MapDoc.changed.connect(_on_doc_changed)
	_show_page(false)
	_refresh_status("先画路 → 放建筑 → 点建筑加人物/物件 → 文件▸导出场景")


# ---------------------------------------------------------------------------
func _build() -> void:
	var root := VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 4)
	add_child(root)
	root.add_child(_build_menu())

	var hb := HBoxContainer.new()
	hb.size_flags_vertical = Control.SIZE_EXPAND_FILL
	hb.add_theme_constant_override("separation", 6)
	root.add_child(hb)

	_view = MV.new()
	_view.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_view.selection_changed.connect(_on_selection_changed)
	_view.status_message.connect(_refresh_status)
	hb.add_child(_view)

	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size.x = 300
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.add_child(_build_right_panel())
	hb.add_child(scroll)

	_status = Label.new()
	_status.text = "就绪"
	_status.add_theme_color_override("font_color", Color("8ea2b8"))
	root.add_child(_status)


func _build_menu() -> MenuBar:
	var mb := MenuBar.new()
	var file := PopupMenu.new()
	file.name = "文件"
	file.add_item("新建", 0)
	file.add_item("导入地图…", 1)
	file.add_item("导出地图…", 2)
	file.add_item("导出场景… (给观察器)", 3)
	file.id_pressed.connect(_on_file_menu)
	mb.add_child(file)
	var viewm := PopupMenu.new()
	viewm.name = "视图"
	viewm.add_item("适配内容", 0)
	viewm.id_pressed.connect(func(id: int) -> void:
		if id == 0:
			_view.fit_to_content())
	mb.add_child(viewm)
	return mb


func _build_right_panel() -> VBoxContainer:
	var right := VBoxContainer.new()
	right.custom_minimum_size.x = 290
	right.add_theme_constant_override("separation", 6)

	# --- 基础页: 工具 + 资产 + 栅格(建筑/道路模式) ---
	_base_page = VBoxContainer.new()
	_base_page.add_theme_constant_override("separation", 6)

	_base_page.add_child(_header("工具"))
	var tools := HBoxContainer.new()
	tools.add_theme_constant_override("separation", 4)
	_tool_btns.clear()
	_tool_btns.append(_tool_button("选择", MV.Tool.SELECT))
	_tool_btns.append(_tool_button("画路", MV.Tool.ROAD))
	for b in _tool_btns:
		tools.add_child(b)
	_base_page.add_child(tools)

	_base_page.add_child(_header("资产 · Building"))
	_palette = ItemList.new()
	_palette.custom_minimum_size.y = 140
	_palette.item_selected.connect(_on_pick_type)
	_base_page.add_child(_palette)

	_base_page.add_child(_header("栅格 (m)"))
	_grid_spin = SpinBox.new()
	_grid_spin.min_value = 0.25
	_grid_spin.max_value = 50.0
	_grid_spin.step = 0.25
	_grid_spin.value = MapDoc.grid_size
	_grid_spin.value_changed.connect(func(v: float) -> void:
		MapDoc.grid_size = v
		_view.queue_redraw())
	_base_page.add_child(_grid_spin)
	right.add_child(_base_page)

	# --- 详情页: 整体替换基础页, 带返回 ---
	_detail_page = VBoxContainer.new()
	_detail_page.add_theme_constant_override("separation", 8)
	_detail_page.visible = false
	_inspector = VBoxContainer.new()
	_inspector.add_theme_constant_override("separation", 8)
	_detail_page.add_child(_inspector)
	right.add_child(_detail_page)
	return right


func _show_page(detail: bool) -> void:
	_base_page.visible = not detail
	_detail_page.visible = detail
	if detail:
		_rebuild_inspector()


func _on_doc_changed() -> void:
	if _detail_page.visible:
		_rebuild_inspector()


func _tool_button(text: String, tool: int) -> Button:
	var b := Button.new()
	b.text = text
	b.toggle_mode = true
	b.pressed.connect(func() -> void:
		_view.set_tool(tool)
		_update_tool_buttons())
	return b


func _header(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_color_override("font_color", HEADER)
	return l


func _update_tool_buttons() -> void:
	var order := [MV.Tool.SELECT, MV.Tool.ROAD]
	for i in _tool_btns.size():
		_tool_btns[i].button_pressed = _view.tool == order[i]


# ---------------------------------------------------------------------------
# 建筑资产
# ---------------------------------------------------------------------------
func _fill_palette() -> void:
	_palette.clear()
	_type_keys = MapDoc.building_types.keys()
	_type_keys.sort()
	for i in _type_keys.size():
		var k: String = String(_type_keys[i])
		var t: Dictionary = MapDoc.building_types[k]
		_palette.add_item("%s  (%s · cap%s)" % [
			String(t.get("name", k)), k, str(t.get("capacity", "?"))])
		_palette.set_item_custom_fg_color(i, AssetStyle.kind_color(String(t.get("kind", ""))))


func _on_pick_type(index: int) -> void:
	if index < 0 or index >= _type_keys.size():
		return
	if MapDoc.edges.is_empty():
		_refresh_status("规则: 请先画路, 再摆放建筑")
		return
	_view.placing_type = String(_type_keys[index])
	_view.set_tool(MV.Tool.PLACE)
	_update_tool_buttons()
	_refresh_status("放置: %s" % MapDoc.type_display(_view.placing_type))


# ---------------------------------------------------------------------------
# 检查器(观察器式: 建筑 → 人员/物件 → 详情)
# ---------------------------------------------------------------------------
func _on_selection_changed() -> void:
	var detail := false
	match _view.sel_kind:
		"building":
			_context_building = _view.sel_id
			detail = MapDoc.buildings.has(_view.sel_id)
		"npc":
			var n: Dictionary = MapDoc.npcs.get(_view.sel_id, {})
			var h := String(n.get("home", ""))
			if MapDoc.buildings.has(h):
				_context_building = h
			detail = MapDoc.npcs.has(_view.sel_id)
		"item":
			var it: Dictionary = MapDoc.items.get(_view.sel_id, {})
			var a := String(it.get("at", ""))
			if MapDoc.buildings.has(a):
				_context_building = a
			detail = MapDoc.items.has(_view.sel_id)
	_show_page(detail)


func _clear_inspector() -> void:
	for c in _inspector.get_children():
		_inspector.remove_child(c)
		c.queue_free()


func _rebuild_inspector() -> void:
	if _inspector == null:
		return
	_clear_inspector()
	match _view.sel_kind:
		"npc":
			if MapDoc.npcs.has(_view.sel_id):
				_build_person(_view.sel_id)
				return
		"item":
			if MapDoc.items.has(_view.sel_id):
				_build_item(_view.sel_id)
				return
	if _context_building != "" and MapDoc.buildings.has(_context_building):
		_build_building(_context_building)
	else:
		var hint := Label.new()
		hint.text = "点建筑查看人员与物件\n\n流程: 画路 → 放建筑 → 点建筑加人/物件"
		hint.add_theme_color_override("font_color", MUTED)
		_inspector.add_child(hint)


func _section(title: String) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 2)
	var l := Label.new()
	l.text = title
	l.add_theme_color_override("font_color", HEADER)
	v.add_child(l)
	return v


func _kv(parent: Control, key: String, value: String) -> void:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 8)
	var k := Label.new()
	k.text = key
	k.custom_minimum_size.x = 64
	k.add_theme_color_override("font_color", MUTED)
	var v := Label.new()
	v.text = value
	v.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(k)
	h.add_child(v)
	parent.add_child(h)


func _row_button(text: String, on_click: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.flat = true
	b.add_theme_color_override("font_color", Color("c7d2e2"))
	b.pressed.connect(on_click)
	return b


func _header_row(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", 12)
	l.add_theme_color_override("font_color", MUTED)
	return l


func _build_building(bid: String) -> void:
	var b: Dictionary = MapDoc.buildings[bid]
	var people: Array = MapDoc.npcs_at(bid)
	var items: Array = MapDoc.items_at(bid)
	var kind := String(MapDoc.building_types.get(String(b["type"]), {}).get("kind", ""))

	_inspector.add_child(_to_base_button())
	var title := Label.new()
	title.text = MapDoc.building_name(bid)
	title.add_theme_font_size_override("font_size", 16)
	_inspector.add_child(title)
	var sub := Label.new()
	sub.text = "%s · %d 人 · %d 物件" % [AssetStyle.kind_zh(kind), people.size(), items.size()]
	sub.add_theme_color_override("font_color", MUTED)
	_inspector.add_child(sub)

	# 名称
	var nsec := _section("基本")
	_f_bname = LineEdit.new()
	_f_bname.text = MapDoc.building_name(bid)
	var save_btn := Button.new()
	save_btn.text = "保存名称"
	save_btn.pressed.connect(func() -> void:
		MapDoc.set_building_name(bid, _f_bname.text)
		_refresh_status("已命名 %s" % _f_bname.text))
	nsec.add_child(_f_bname)
	nsec.add_child(save_btn)
	_kv(nsec, "类型", String(b["type"]))
	var s: Vector2 = b["size"]
	_kv(nsec, "尺寸", "%.1f × %.1f m" % [s.x, s.y])
	_inspector.add_child(nsec)

	# 权限(由此居住的人决定: 首个=户主, 其余=同住)
	var acc := _section("权限")
	var owner := ""
	var mates: Array = []
	for i in people.size():
		if i == 0:
			owner = String(MapDoc.npcs[people[i]].get("name", people[i]))
		else:
			mates.append(String(MapDoc.npcs[people[i]].get("name", people[i])))
	var access := "公共"
	if people.size() > 0:
		access = owner + (" 及 " + "、".join(mates) if not mates.is_empty() else " (户主)")
	_kv(acc, "进入权限", access)
	_kv(acc, "容量", "%d 人" % int(MapDoc.building_types.get(
		String(b["type"]), {}).get("capacity", 0)))
	_inspector.add_child(acc)

	# 人员
	var psec := _section("人员 %d" % people.size())
	var ph := HBoxContainer.new()
	var add_p := Button.new()
	add_p.text = "＋ 新增随机"
	add_p.pressed.connect(func() -> void: _add_person(bid))
	ph.add_child(add_p)
	psec.add_child(ph)
	psec.add_child(_header_row("姓名            年龄   角色"))
	if people.is_empty():
		psec.add_child(_muted("无人 —— 点上方新增"))
	else:
		for pid in people:
			var n: Dictionary = MapDoc.npcs[pid]
			psec.add_child(_row_button("%s    %d    %s" % [
				String(n.get("name", pid)), MapDoc.age_of(n),
				AssetStyle.role_zh(String(n.get("role", "")))],
				func() -> void: _view.select("npc", String(pid))))
	_inspector.add_child(psec)

	# 物件
	var isec := _section("物件 %d" % items.size())
	var ih := HBoxContainer.new()
	_f_item_type = OptionButton.new()
	_f_item_type.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_f_item_type.item_selected.connect(func(_i: int) -> void: pass)
	for k in _item_type_keys:
		_f_item_type.add_item("%s" % MapDoc.item_display(String(k)))
	var add_i := Button.new()
	add_i.text = "＋ 新增"
	add_i.pressed.connect(func() -> void: _add_item(bid))
	ih.add_child(_f_item_type)
	ih.add_child(add_i)
	isec.add_child(ih)
	isec.add_child(_header_row("名称            数量   价格"))
	if items.is_empty():
		isec.add_child(_muted("无 —— 选类型后新增"))
	else:
		for iid in items:
			var it: Dictionary = MapDoc.items[iid]
			var st := int(it.get("stock", 1))
			psec_append(isec, _row_button("%s    %s    %s" % [
				MapDoc.item_display(String(it.get("type", ""))),
				"∞" if st < 0 else str(st),
				"—" if float(it.get("price", 0.0)) <= 0.0 else "¥%d" % int(it.get("price", 0.0))],
				func() -> void: _view.select("item", String(iid))))
	_inspector.add_child(isec)


## 小工具: 给容器追加一个已构造的控件(避免嵌套表达式过长)。
func psec_append(parent: Control, c: Control) -> void:
	parent.add_child(c)


func _muted(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_color_override("font_color", MUTED)
	return l


# --- 人员详情 ------------------------------------------------------------
func _build_person(pid: String) -> void:
	var n: Dictionary = MapDoc.npcs[pid]
	_inspector.add_child(_back_button())
	var title := Label.new()
	title.text = String(n.get("name", pid))
	title.add_theme_font_size_override("font_size", 16)
	_inspector.add_child(title)
	var sub := Label.new()
	sub.text = "人物 · %s" % pid
	sub.add_theme_color_override("font_color", MUTED)
	_inspector.add_child(sub)

	var basic := _section("基本")
	_f_name = LineEdit.new()
	_f_name.text = String(n.get("name", ""))
	basic.add_child(_lrow("姓名", _f_name))
	_f_gender = OptionButton.new()
	_f_gender.add_item("男")
	_f_gender.add_item("女")
	_f_gender.selected = 1 if String(n.get("gender", "")) == "female" else 0
	basic.add_child(_lrow("性别", _f_gender))
	_f_age = _spin(0, 120, 1)
	_f_age.value = MapDoc.age_of(n)
	basic.add_child(_lrow("年龄", _f_age))
	_f_role = OptionButton.new()
	for r in MapDoc.ROLES:
		_f_role.add_item(AssetStyle.role_zh(r))
	_f_role.selected = maxi(0, MapDoc.ROLES.find(String(n.get("role", ""))))
	basic.add_child(_lrow("角色", _f_role))
	_f_money = _spin(0, 1000000, 10)
	_f_money.value = float(n.get("money", 0.0))
	basic.add_child(_lrow("资金", _f_money))
	_inspector.add_child(basic)

	var pers := _section("性格 / 特质")
	var p: Dictionary = n.get("personality", {})
	_f_hunger = _spin(0.5, 2.0, 0.1)
	_f_hunger.value = float(p.get("hunger", 1.0))
	pers.add_child(_lrow("食欲", _f_hunger))
	_f_energy = _spin(0.5, 2.0, 0.1)
	_f_energy.value = float(p.get("energy", 1.0))
	pers.add_child(_lrow("精力", _f_energy))
	_f_fun = _spin(0.5, 2.0, 0.1)
	_f_fun.value = float(p.get("fun", 1.0))
	pers.add_child(_lrow("娱乐", _f_fun))
	_f_traits = LineEdit.new()
	_f_traits.text = ",".join((n.get("traits", {}) as Dictionary).keys())
	_f_traits.placeholder_text = "特质, 逗号分隔"
	pers.add_child(_lrow("特质", _f_traits))
	_inspector.add_child(pers)

	var btns := HBoxContainer.new()
	var save := Button.new()
	save.text = "保存"
	save.pressed.connect(func() -> void: _save_person(pid))
	var rnd := Button.new()
	rnd.text = "重滚"
	rnd.pressed.connect(func() -> void:
		MapDoc.randomize_npc(pid)
		_refresh_status("已重滚 %s" % pid))
	var del := Button.new()
	del.text = "删除"
	del.pressed.connect(func() -> void:
		MapDoc.remove_npc(pid)
		_back_to_building())
	btns.add_child(save)
	btns.add_child(rnd)
	btns.add_child(del)
	_inspector.add_child(btns)


func _save_person(pid: String) -> void:
	var n: Dictionary = MapDoc.npcs.get(pid, {})
	var birthday := _birthday_for_age(int(_f_age.value), String(n.get("birthday", "")))
	var traits := {}
	for t in _f_traits.text.split(","):
		var k := t.strip_edges()
		if k != "" and k != "role":
			traits[k] = true
	MapDoc.update_npc(pid, {
		"name": _f_name.text,
		"gender": "female" if _f_gender.selected == 1 else "male",
		"birthday": birthday,
		"role": String(MapDoc.ROLES[_f_role.selected]),
		"money": _f_money.value,
		"personality": {"hunger": _f_hunger.value, "energy": _f_energy.value,
			"fun": _f_fun.value},
		"traits": traits})
	_refresh_status("已保存 %s" % pid)


# --- 物件详情 ------------------------------------------------------------
func _build_item(iid: String) -> void:
	var it: Dictionary = MapDoc.items[iid]
	_inspector.add_child(_back_button())
	var title := Label.new()
	title.text = MapDoc.item_display(String(it.get("type", "")))
	title.add_theme_font_size_override("font_size", 16)
	_inspector.add_child(title)
	var sub := Label.new()
	sub.text = "物件 · %s" % iid
	sub.add_theme_color_override("font_color", MUTED)
	_inspector.add_child(sub)

	var sec := _section("属性")
	_kv(sec, "类型", String(it.get("type", "")))
	_kv(sec, "所在", MapDoc.building_name(String(it.get("at", ""))))
	_f_stock = _spin(-1, 1000000, 1)
	_f_stock.value = int(it.get("stock", 1))
	sec.add_child(_lrow("库存", _f_stock))
	_f_price = _spin(0, 1000000, 1)
	_f_price.value = float(it.get("price", 0.0))
	sec.add_child(_lrow("售价", _f_price))
	_f_owner = OptionButton.new()
	_f_owner_ids = [""]
	_f_owner.add_item("(公共)")
	for pid in MapDoc.npcs:
		_f_owner_ids.append(pid)
		_f_owner.add_item(String(MapDoc.npcs[pid].get("name", pid)))
	_f_owner.selected = maxi(0, _f_owner_ids.find(String(it.get("owner", ""))))
	sec.add_child(_lrow("归属", _f_owner))
	_inspector.add_child(sec)

	var btns := HBoxContainer.new()
	var save := Button.new()
	save.text = "保存"
	save.pressed.connect(func() -> void: _save_item(iid))
	var del := Button.new()
	del.text = "删除"
	del.pressed.connect(func() -> void:
		MapDoc.remove_item(iid)
		_back_to_building())
	btns.add_child(save)
	btns.add_child(del)
	_inspector.add_child(btns)


func _save_item(iid: String) -> void:
	var owner := ""
	if _f_owner.selected >= 0 and _f_owner.selected < _f_owner_ids.size():
		owner = String(_f_owner_ids[_f_owner.selected])
	MapDoc.update_item(iid, {
		"stock": int(_f_stock.value), "price": _f_price.value, "owner": owner})
	_refresh_status("已保存 %s" % iid)


# --- 新增 / 返回 ---------------------------------------------------------
func _add_person(bid: String) -> void:
	var pid := MapDoc.add_npc(bid)
	if pid != "":
		_view.select("npc", pid)
		_refresh_status("已在 %s 新增 %s (自动开放权限)" % [bid, pid])


func _add_item(bid: String) -> void:
	var idx := _f_item_type.selected
	if idx < 0 or idx >= _item_type_keys.size():
		return
	var iid := MapDoc.add_item(String(_item_type_keys[idx]), bid)
	if iid != "":
		_view.select("item", iid)
		_refresh_status("已在 %s 新增 %s" % [bid, iid])


func _to_base_button() -> Button:
	var b := Button.new()
	b.text = "‹ 返回 (建筑/道路)"
	b.pressed.connect(func() -> void: _view.clear_selection())
	return b


func _back_button() -> Button:
	var b := Button.new()
	b.text = "‹ %s" % (MapDoc.building_name(_context_building) \
		if _context_building != "" else "返回")
	b.pressed.connect(_back_to_building)
	return b


func _back_to_building() -> void:
	if _context_building != "" and MapDoc.buildings.has(_context_building):
		_view.select("building", _context_building)
	else:
		_view.clear_selection()
		_rebuild_inspector()


# --- 控件小工具 ----------------------------------------------------------
func _lrow(label: String, c: Control) -> Control:
	var h := HBoxContainer.new()
	var l := Label.new()
	l.text = label
	l.custom_minimum_size.x = 52
	l.add_theme_color_override("font_color", MUTED)
	c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(l)
	h.add_child(c)
	return h


func _spin(mn: float, mx: float, step: float) -> SpinBox:
	var s := SpinBox.new()
	s.min_value = mn
	s.max_value = mx
	s.step = step
	return s


func _birthday_for_age(age: int, existing: String) -> String:
	var md := "01-01"
	var parts := existing.split("-")
	if parts.size() >= 3 and int(parts[1]) >= 1 and int(parts[1]) <= 12:
		md = "%02d-%02d" % [int(parts[1]), int(parts[2])]
	return "%04d-%s" % [2026 - age, md]


# ---------------------------------------------------------------------------
func _refresh_status(msg: String) -> void:
	if _status != null:
		_status.text = msg


func _on_file_menu(id: int) -> void:
	match id:
		0:
			MapDoc.new_map()
			_view.fit_to_content()
			_view.clear_selection()
			_refresh_status("已新建空白地图")
		1:
			_show_dialog(false)
		2:
			_show_dialog(true)
		3:
			_show_scene_dialog()


func _show_scene_dialog() -> void:
	var d := FileDialog.new()
	d.access = FileDialog.ACCESS_FILESYSTEM
	d.file_mode = FileDialog.FILE_MODE_SAVE_FILE
	d.add_filter("*.json", "CitySim Scene")
	d.use_native_dialog = false
	d.size = Vector2i(760, 520)
	d.current_file = "scene.json"
	d.file_selected.connect(func(p: String) -> void:
		if MapDoc.save_scene(p, "editor_scene"):
			_refresh_status("已导出场景: " + p)
		else:
			_refresh_status("导出失败: " + p)
		d.queue_free())
	d.canceled.connect(d.queue_free)
	add_child(d)
	d.popup_centered()


func _show_dialog(save: bool) -> void:
	var d := FileDialog.new()
	d.access = FileDialog.ACCESS_FILESYSTEM
	d.file_mode = FileDialog.FILE_MODE_SAVE_FILE if save \
		else FileDialog.FILE_MODE_OPEN_FILE
	d.add_filter("*.json", "CitySim Map")
	d.use_native_dialog = false
	d.size = Vector2i(760, 520)
	add_child(d)
	if save:
		d.current_file = "map.json"
		d.file_selected.connect(func(p: String) -> void:
			if MapDoc.save_map(p):
				_refresh_status("已导出地图: " + p)
			else:
				_refresh_status("导出失败: " + p)
			d.queue_free())
	else:
		d.file_selected.connect(func(p: String) -> void:
			if MapDoc.load_map(p):
				_view.fit_to_content()
				_view.clear_selection()
				_refresh_status("已导入: " + p)
			else:
				_refresh_status("导入失败: " + p)
			d.queue_free())
	d.canceled.connect(d.queue_free)
	d.popup_centered()


func _notification(what: int) -> void:
	if what == NOTIFICATION_READY:
		_fill_palette()
		_item_type_keys = MapDoc.item_types.keys()
		_item_type_keys.sort()
		_update_tool_buttons()
		if not AssetStyle.available():
			_refresh_status("警告: 未找到观察器资产样式, 底色退化为中性灰")
		else:
			_refresh_status("资产样式来自观察器: %s" % AssetStyle.source_path())
