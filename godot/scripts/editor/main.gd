extends Control

const MV := preload("res://scripts/editor/map_view.gd")
## 同项目引用观察器资产样式(建筑底色/徽记): 唯一权威, 不再走 AssetStyle 桥。
const BuildingStyle := preload("res://scripts/shared/building_style.gd")
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
var _del_selected_btn: Button
var _tool_btns: Array[Button] = []
var _type_keys: Array = []
var _item_type_keys: Array = []

var _context_building := ""     # 当前详情所属建筑
var _dirty := false            # 有未导出修改(退出前确认)

# 详情表单控件(每次重建时重新赋值)
var _f_name: LineEdit
var _f_gender: OptionButton
var _f_age: SpinBox
var _f_role: OptionButton
var _f_money: SpinBox
var _f_hunger: SpinBox
var _f_energy: SpinBox
var _f_traits: LineEdit
var _f_bname: LineEdit
var _f_item_type: OptionButton
var _f_stock: SpinBox
var _f_price: SpinBox
var _f_owner: OptionButton
var _f_owner_ids: Array = []
var _f_mem_item: OptionButton      # 额外记忆: 选一个场景里的物件
var _f_mem_believe: SpinBox        # 他有多信这条
var _mem_item_ids: Array = []      # 与 _f_mem_item 的条目一一对应


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
	root.add_child(_build_topbar())

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
	file.add_separator()
	file.add_item("导入场景…", 1)
	file.add_item("导出场景…", 2)
	file.add_separator()
	file.add_item("返回主菜单", 3)
	file.id_pressed.connect(_on_file_menu)
	mb.add_child(file)
	var viewm := PopupMenu.new()
	viewm.name = "视图"
	viewm.add_item("适配内容", 0)
	viewm.id_pressed.connect(func(id: int) -> void:
		if id == 0:
			_view.fit_to_content())
	mb.add_child(viewm)
	# 工具: 老场景一键修名的入口(载入时已自动修一遍, 这里是手动兜底)
	var toolm := PopupMenu.new()
	toolm.name = "工具"
	toolm.add_item("重排重复的建筑名", 0)
	toolm.id_pressed.connect(func(id: int) -> void:
		if id == 0:
			var n := MapDoc.dedupe_building_names()
			_refresh_status(("已把 %d 栋建筑的默认名交回自动编号" % n) if n > 0
				else "没有需要重排的建筑名"))
	mb.add_child(toolm)
	return mb


## 顶栏: 菜单 + 右侧「主菜单」按钮(显式退出入口)。
func _build_topbar() -> HBoxContainer:
	var bar := HBoxContainer.new()
	bar.add_theme_constant_override("separation", 6)
	bar.add_child(_build_menu())
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.add_child(spacer)
	var home := Button.new()
	home.text = "⌂ 主菜单"
	home.tooltip_text = "返回启动界面"
	home.pressed.connect(_leave_to_menu)
	bar.add_child(home)
	return bar


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

	# --- 人口: 一键填满(所有住宅的每一层) ---
	_base_page.add_child(_header("人口"))
	var fill := Button.new()
	fill.text = "填满住户 (所有住宅)"
	fill.tooltip_text = "给每栋住宅的每一层补满随机居民(到每层容量; 已有住户不重复填)"
	fill.pressed.connect(_on_fill_residents)
	_base_page.add_child(fill)

	_base_page.add_child(_header("选中"))
	_del_selected_btn = Button.new()
	_del_selected_btn.text = "删除选中 (Del)"
	_del_selected_btn.disabled = true
	_del_selected_btn.pressed.connect(func() -> void: _view.delete_selected())
	_base_page.add_child(_del_selected_btn)

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

	# --- 吸附开关(2 个选项) ---
	var snap_grid := CheckBox.new()
	snap_grid.text = "吸附到栅格"
	snap_grid.button_pressed = MapDoc.grid_snap
	snap_grid.tooltip_text = "关闭后落点不被栅格对齐(仍保留节点/门口/路中吸附)"
	snap_grid.toggled.connect(func(on: bool) -> void:
		MapDoc.grid_snap = on
		_view.queue_redraw())
	_base_page.add_child(snap_grid)

	var snap_net := CheckBox.new()
	snap_net.text = "吸附路网/门口"
	snap_net.button_pressed = MapDoc.net_snap
	snap_net.tooltip_text = "画路时自动吸到 已有节点 > 建筑门口 > 道路中心线"
	snap_net.toggled.connect(func(on: bool) -> void:
		MapDoc.net_snap = on
		_view.queue_redraw())
	_base_page.add_child(snap_net)
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
	_dirty = true
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
		_palette.set_item_custom_fg_color(i, BuildingStyle.kind_color(String(t.get("kind", ""))))


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
	if _del_selected_btn != null:
		_del_selected_btn.disabled = not (_view.sel_kind in ["node", "edge"])


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
	var kind := String(MapDoc.building_types.get(String(b["type"]), {}).get("kind", ""))
	# 楼层: 先夹取当前编辑层(换建筑 → 回 1 层), 再按【当前层】取人员/物件。
	MapDoc.clamp_cur_floor(bid)
	var floors: int = MapDoc.unit_ids(bid).size()
	var cur_unit := MapDoc.unit_of(bid, MapDoc.cur_floor)
	var people: Array = MapDoc.npcs_at_unit(cur_unit) if floors > 1 else MapDoc.npcs_at(bid)
	var items: Array = MapDoc.items_at_unit(cur_unit) if floors > 1 else MapDoc.items_at(bid)
	var all_people: Array = MapDoc.npcs_at(bid)
	var all_items: Array = MapDoc.items_at(bid)

	_inspector.add_child(_to_base_button())
	var title := Label.new()
	title.text = MapDoc.building_name(bid)
	title.add_theme_font_size_override("font_size", 16)
	_inspector.add_child(title)
	var sub := Label.new()
	if floors > 1:
		sub.text = "%s · 共 %d 层 (第 %d 层 %d 人 · %d 物件)" % [
			Zh.kind_zh(kind), floors, MapDoc.cur_floor, people.size(), items.size()]
	else:
		sub.text = "%s · %d 人 · %d 物件" % [Zh.kind_zh(kind), people.size(), items.size()]
	sub.add_theme_color_override("font_color", MUTED)
	_inspector.add_child(sub)

	var del_b := Button.new()
	del_b.text = "删除建筑"
	del_b.pressed.connect(func() -> void:
		MapDoc.remove_building(bid)
		_view.clear_selection())
	_inspector.add_child(del_b)

	# 名称
	var nsec := _section("基本")
	_f_bname = LineEdit.new()
	# 起过名才填进去; 没起过就【留空 + 灰字提示自动编号】——
	# 把默认名写进 text 会在保存时把它烤成固定值, 于是同类型全同名。
	_f_bname.text = (String(b.get("name", "")) if MapDoc.has_custom_name(bid) else "")
	_f_bname.placeholder_text = MapDoc.default_building_name(bid)
	_f_bname.tooltip_text = "留空 = 自动编号（%s）。取名后同类型的其它楼不受影响。" % [
		MapDoc.default_building_name(bid)]
	var save_btn := Button.new()
	save_btn.text = "保存名称"
	save_btn.pressed.connect(func() -> void:
		MapDoc.set_building_name(bid, _f_bname.text.strip_edges())
		_refresh_status("已命名 %s" % MapDoc.building_name(bid)))
	nsec.add_child(_f_bname)
	nsec.add_child(save_btn)
	_kv(nsec, "类型", String(b["type"]))
	var s: Vector2 = b["size"]
	_kv(nsec, "尺寸", "%.1f × %.1f m" % [s.x, s.y])
	_inspector.add_child(nsec)

	# 楼层(多住户单元: 导出为 bld_007_f1..fN 子地点)
	var fsec := _section("楼层")
	var fnum := _spin(1, MapDoc.MAX_FLOORS, 1)
	fnum.value = int(b.get("floors", 1))
	fnum.value_changed.connect(func(v: float) -> void: MapDoc.set_floors(bid, int(v)))
	fsec.add_child(_lrow("楼层数", fnum))
	if floors > 1:
		var fsel := OptionButton.new()
		for i in range(1, floors + 1):
			fsel.add_item("第 %d 层" % i)
		fsel.selected = MapDoc.cur_floor - 1
		fsel.item_selected.connect(func(i: int) -> void: MapDoc.set_cur_floor(bid, i + 1))
		fsec.add_child(_lrow("编辑层", fsel))
		_kv(fsec, "容量", "每层 %d 人 · 共 %d 人" % [
			MapDoc.unit_capacity(bid), MapDoc.total_capacity(bid)])
		_kv(fsec, "已住", "%d 人 · %d 物件" % [all_people.size(), all_items.size()])
		var cp := Button.new()
		cp.text = "复制本层物件 → 其它层"
		cp.tooltip_text = "把当前编辑层的物件复制到该栋其它楼层(owner 改为目标层户主)"
		cp.pressed.connect(func() -> void:
			var n := MapDoc.copy_floor_items(bid, MapDoc.cur_floor)
			_refresh_status("已复制第 %d 层 %d 件物件到其它层" % [MapDoc.cur_floor, n]))
		fsec.add_child(cp)
	var purge := Button.new()
	purge.text = "清理无效引用"
	purge.tooltip_text = "清掉指向已不存在地点的住所/物件(减层、导入旧数据后遗留)"
	purge.pressed.connect(func() -> void:
		var r: Dictionary = MapDoc.purge_invalid_refs()
		_refresh_status("清理: %d 人解除住所 / 删除 %d 件物件" % [
			r.get("npcs", 0), r.get("items", 0)]))
	fsec.add_child(purge)
	_inspector.add_child(fsec)

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
	if floors > 1:
		_kv(acc, "容量", "共 %d 人 (每层 %d)" % [
			MapDoc.total_capacity(bid), MapDoc.unit_capacity(bid)])
	else:
		_kv(acc, "容量", "%d 人" % MapDoc.unit_capacity(bid))
	_inspector.add_child(acc)

	# 人员
	var psec := _section("人员 %d" % people.size())
	var ph := HBoxContainer.new()
	var add_p := Button.new()
	add_p.text = "＋ 新增随机"
	add_p.pressed.connect(func() -> void: _add_person(bid))
	# 到上限就不允许再加(每层容量 = 该类型单层容量)
	var cap_u := MapDoc.unit_capacity(bid)
	add_p.disabled = people.size() >= cap_u
	add_p.tooltip_text = "本层 %d/%d 人" % [people.size(), cap_u]
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
				Zh.role_zh(String(n.get("role", "")))],
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

	# 认知(批量): “让所有人 / 让这一家知道那家店在卖什么”
	# 想【只给某一个人】注入 → 点住户进人物详情 → 「额外记忆」
	var ksec := _section("认知（批量）")
	ksec.add_child(_muted("只给某一个人注入 → 点住户进他的详情, 用「额外记忆」"))
	var kunit := MapDoc.target_unit(bid)
	var kpeople := MapDoc.npcs_at_unit(kunit)
	var shop_ids: Array = MapDoc.shops()
	# 有住户 → 告诉“这一家”；没住户(商铺/公共) → 等于打广告
	var kwho_all := kpeople.is_empty()
	if kwho_all:
		ksec.add_child(_muted("让 NPC 一开始就知道这里的货(= 广告 / 听人说)"))
	else:
		ksec.add_child(_muted("让【这一家】一开始就知道某家店的货(= 告诉他去哪买)"))
	var kbel := _spin(0.1, 1.0, 0.05)
	kbel.value = 0.8
	ksec.add_child(_lrow("相信度", kbel))
	var kshop_sel: OptionButton = null
	var kshop_ids: Array = []
	if kwho_all:
		kshop_ids = [String(bid)]
	else:
		kshop_ids = shop_ids.duplicate()
		if kshop_ids.is_empty():
			kshop_ids = [String(bid)]          # 场景里还没有卖东西的楼
		kshop_sel = OptionButton.new()
		for sid in kshop_ids:
			kshop_sel.add_item("%s (在卖)" % MapDoc.building_name(String(sid)))
		kshop_sel.selected = 0
		ksec.add_child(_lrow("哪家店", kshop_sel))
	var kadd := Button.new()
	kadd.text = ("让所有人知道这里的货" if kwho_all
		else "让这一家人知道这家店的货")
	kadd.tooltip_text = ("该层没有住户 → 相当于打广告: 全城 NPC 初始就知道。"
		if kwho_all else
		"只让【这一层这一家人】知道那家店在卖什么(不吵到别人)。")
	kadd.pressed.connect(func() -> void:
		var src := String(bid)
		if kshop_sel != null and kshop_sel.selected >= 0 and kshop_sel.selected < kshop_ids.size():
			src = String(kshop_ids[kshop_sel.selected])
		MapDoc.add_knowledge(bid, kbel.value, src)
		_refresh_status("已记录认知: %s ← 知道 %s 的货 (%.2f)" % [
			("所有人" if kwho_all else MapDoc.unit_display(kunit)),
			MapDoc.unit_display(src), kbel.value]))
	ksec.add_child(kadd)
	var krules := MapDoc.knowledge_at(bid)
	if krules.is_empty():
		ksec.add_child(_muted("尚未告诉任何人"))
	else:
		for ki in krules:
			var kr: Dictionary = MapDoc.knowledge[ki]
			var krow := HBoxContainer.new()
			var klb := Label.new()
			klb.text = MapDoc.knowledge_label(kr)
			klb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			krow.add_child(klb)
			var kdel := Button.new()
			kdel.text = "删除"
			kdel.pressed.connect(func() -> void:
				MapDoc.remove_knowledge(ki)
				_refresh_status("已删除一条认知规则"))
			krow.add_child(kdel)
			ksec.add_child(krow)
	_inspector.add_child(ksec)


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
	for r in MapDoc.role_options():
		_f_role.add_item("无" if r == "" else Zh.role_zh(String(r)))
	_f_role.selected = maxi(0, MapDoc.role_options().find(String(n.get("role", ""))))
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
	_f_traits = LineEdit.new()
	_f_traits.text = ",".join((n.get("traits", {}) as Dictionary).keys())
	_f_traits.placeholder_text = "特质, 逗号分隔"
	pers.add_child(_lrow("特质", _f_traits))
	_inspector.add_child(pers)

	# —— 额外记忆: 只给【这个人】注入认知(别人不知道) ——
	# P8: 玩家的手只碰世界真值; 但编辑器是【作者态】, 可以写某个 NPC 的知识
	# (出生时是空白记忆, 其余靠感知/传闻 —— 这里只是给他一条初始认知)。
	var msec := _section("额外记忆")
	msec.add_child(_muted("只写【他一个人的知识】: 他知道哪个地方在卖什么、多少钱。"
		+ "
这是他的记忆, 不是世界真值 —— 也不会同步给同屋的人。"))
	var mem := MapDoc.memory_of(pid)
	if mem.is_empty():
		msec.add_child(_muted("（暂无 —— 出生是空白记忆, 靠感知自己学）"))
	else:
		var mids: Array = mem.keys()
		mids.sort()
		for iid in mids:
			var rec: Dictionary = mem[String(iid)]
			var mrow := HBoxContainer.new()
			var mlb := Label.new()
			mlb.text = MapDoc.memory_label(String(iid), rec)
			mlb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			mlb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			mrow.add_child(mlb)
			var medit := Button.new()
			medit.text = "改"
			medit.tooltip_text = "把这一条载入下面的表单, 改完点「添加 / 更新」"
			medit.pressed.connect(func() -> void:
				_load_memory_form(String(iid), rec))
			mrow.add_child(medit)
			var mdel := Button.new()
			mdel.text = "删"
			mdel.pressed.connect(func() -> void:
				MapDoc.remove_memory(pid, String(iid))
				_refresh_status("已删除一条记忆: %s" % iid))
			mrow.add_child(mdel)
			msec.add_child(mrow)
	# 新增 / 覆盖
	_f_mem_item = OptionButton.new()
	_mem_item_ids.clear()
	var iids: Array = MapDoc.items.keys()
	iids.sort()
	var n_orphan := 0
	for iid in iids:
		var it: Dictionary = MapDoc.items[iid]
		var iat := String(it.get("at", ""))
		if not MapDoc.is_valid_at(iat):
			n_orphan += 1        # 没地点(或地点已删) → 他走不到, 注了也是死记忆
			continue
		_f_mem_item.add_item("%s @ %s" % [
			MapDoc.item_display(String(it.get("type", ""))),
			MapDoc.unit_display(iat)])
		_mem_item_ids.append(String(iid))
	if _mem_item_ids.is_empty():
		_f_mem_item.add_item("（场景里还没有可注入的物件）")
	if n_orphan > 0:
		msec.add_child(_muted("跳过 %d 个不在任何地点里的物件 —— 它们 NPC 去不了, "
			% n_orphan + "注了也用不上; 「清理无效引用」可以删掉它们"))
	msec.add_child(_lrow("物件", _f_mem_item))
	_f_mem_believe = _spin(0.1, 1.0, 0.05)
	_f_mem_believe.value = 0.8
	_f_mem_believe.tooltip_text = ("他有多信这条: 1.0 = 亲眼见过; "
		+ "0.6~0.8 = 听说的(和 knowledge 段一个意思)")
	msec.add_child(_lrow("相信度", _f_mem_believe))
	var madd := Button.new()
	madd.text = "添加 / 更新这条记忆"
	madd.tooltip_text = ("自动带上该物件能解什么/在哪/价钱/库存 —— "
		+ "只由你定他信不信。同一条再写一次就是改。")
	madd.pressed.connect(func() -> void: _save_memory(pid))
	msec.add_child(madd)
	if not mem.is_empty():
		var mclr := Button.new()
		mclr.text = "清空他的记忆 (%d 条)" % mem.size()
		mclr.pressed.connect(func() -> void:
			MapDoc.clear_memory(pid)
			_refresh_status("已清空 %s 的额外记忆" % pid))
		msec.add_child(mclr)
	_inspector.add_child(msec)

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


## 把某条记忆载入下面的表单(改它就是改这一条 —— item_id 是键)。
func _load_memory_form(iid: String, rec: Dictionary) -> void:
	var idx := _mem_item_ids.find(iid)
	if idx >= 0 and _f_mem_item != null:
		_f_mem_item.selected = idx
	if _f_mem_believe != null:
		_f_mem_believe.value = float(rec.get("believe", 0.8))
	_refresh_status("已载入 %s —— 改完点「添加 / 更新」" % iid)


func _save_memory(pid: String) -> void:
	if _f_mem_item == null or _mem_item_ids.is_empty():
		_refresh_status("场景里还没有物件可注入")
		return
	var idx := _f_mem_item.selected
	if idx < 0 or idx >= _mem_item_ids.size():
		return
	var iid := String(_mem_item_ids[idx])
	MapDoc.add_memory(pid, iid, _f_mem_believe.value)
	_refresh_status("已写入 %s 的记忆: %s" % [MapDoc.npc_display(pid), iid])


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
		"role": String(MapDoc.role_options()[_f_role.selected]),
		"money": _f_money.value,
		"personality": {"hunger": _f_hunger.value, "energy": _f_energy.value},
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
	_kv(sec, "所在", MapDoc.unit_display(String(it.get("at", ""))))
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
	var r: Dictionary = MapDoc.add_resident(bid)
	if not bool(r.get("ok", false)):
		_refresh_status("%s %s" % [MapDoc.unit_display(String(r.get("unit", bid))),
			r.get("reason", "新增失败")])
		return
	var pid := String(r["pid"])
	# 新增不进人物编辑页: 留在建筑页, 新人在【人员】列表里
	_refresh_status("已在 %s 新增 %s" % [MapDoc.unit_display(String(r["unit"])), pid])


func _add_item(bid: String) -> void:
	var idx := _f_item_type.selected
	if idx < 0 or idx >= _item_type_keys.size():
		return
	var unit := MapDoc.target_unit(bid)
	var iid := MapDoc.add_item(String(_item_type_keys[idx]), unit)
	if iid != "":
		# 新增不进物件编辑页: 留在建筑页, 新物件在【物件】列表里
		_refresh_status("已在 %s 新增 %s" % [MapDoc.unit_display(unit), iid])


## 一键填满: 所有住宅的每一层补满随机居民。
func _on_fill_residents() -> void:
	var r: Dictionary = MapDoc.fill_residents()
	_refresh_status("填满住户: %d 栋住宅 / %d 个单元, 新增 %d 人" % [
		r.get("homes", 0), r.get("units", 0), r.get("added", 0)])


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
			_dirty = false
			_refresh_status("已新建空白地图")
		1:
			_show_scene_dialog(false)
		2:
			_show_scene_dialog(true)
		3:
			_leave_to_menu()


## 退出编辑器回启动界面; 有未导出修改时先确认。
func _leave_to_menu() -> void:
	if not _dirty:
		App.return_to_launcher()
		return
	var d := ConfirmationDialog.new()
	d.title = "返回主菜单"
	d.dialog_text = "有尚未导出的修改，确定返回主菜单？"
	d.ok_button_text = "返回"
	d.cancel_button_text = "取消"
	d.confirmed.connect(func() -> void:
		d.queue_free()
		App.return_to_launcher())
	d.canceled.connect(d.queue_free)
	add_child(d)
	d.popup_centered()


## 场景导入/导出共用一个对话框; 默认目录锁定 config/scenes。
func _show_scene_dialog(save: bool) -> void:
	var d := FileDialog.new()
	d.access = FileDialog.ACCESS_FILESYSTEM
	d.file_mode = FileDialog.FILE_MODE_SAVE_FILE if save \
		else FileDialog.FILE_MODE_OPEN_FILE
	d.add_filter("*.json", "CitySim Scene")
	d.use_native_dialog = false
	d.size = Vector2i(760, 520)
	var dir := MapDoc.scenes_dir()
	if DirAccess.dir_exists_absolute(dir):
		d.current_dir = dir
	add_child(d)
	if save:
		d.current_file = MapDoc.scene_name + ".json"
		d.file_selected.connect(func(p: String) -> void:
			if MapDoc.save_scene(p, p.get_file().get_basename()):
				_dirty = false
				_refresh_status("已导出场景: " + p)
			else:
				_refresh_status("导出失败: " + p)
			d.queue_free())
	else:
		d.file_selected.connect(func(p: String) -> void:
			var j: Variant = JSON.parse_string(FileAccess.get_file_as_string(p))
			if j is Dictionary and MapDoc.load_scene_dict(j):
				_view.fit_to_content()
				_view.clear_selection()
				_dirty = false
				_refresh_status("已导入场景: " + p)
			else:
				_refresh_status("导入失败(不是场景文件): " + p)
			d.queue_free())
	d.canceled.connect(d.queue_free)
	d.popup_centered()
	d.canceled.connect(d.queue_free)
	d.popup_centered()


func _notification(what: int) -> void:
	if what == NOTIFICATION_READY:
		_fill_palette()
		_item_type_keys = MapDoc.item_types.keys()
		_item_type_keys.sort()
		_update_tool_buttons()
