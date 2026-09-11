# inspector.gd —— 选中实体检查器(只读)。
#
# 四区: Status / 候选排名 / 记忆 / Event Log。对应选中 NPC / Entity / Location。
# 行控件来自可编辑组件场景 scenes/components/*.tscn。
# 为控制节点数量, 刷新节流到 ~10Hz(snapshot 60Hz 不逐帧重建)。
class_name InspectorPanel
extends PanelContainer

const SECTION: PackedScene = preload("res://scenes/components/inspector_section.tscn")
const SIGNAL_ROW: PackedScene = preload("res://scenes/components/signal_row.tscn")
const CAND_ROW: PackedScene = preload("res://scenes/components/cand_row.tscn")
const MEM_ROW: PackedScene = preload("res://scenes/components/mem_row.tscn")
const EVENT_ROW: PackedScene = preload("res://scenes/components/event_row.tscn")
const KV_ROW: PackedScene = preload("res://scenes/components/kv_row.tscn")
const NPC_HEADER: PackedScene = preload("res://scenes/components/npc_header.tscn")

const MUTED := Color("7a8494")
const SIGNAL_ORDER := ["energy", "hunger", "thirst", "bladder", "fun", "hp"]

@onready var _body: VBoxContainer = %Body

var _dirty := true
var _accum := 0.0
var _last_key := ""      # 内容指纹: 不变则跳过重建(否则 hover 会被高频刷新打断)


func _ready() -> void:
	Store.snapshot_applied.connect(_mark_dirty)
	Store.selection_changed.connect(_mark_dirty)
	set_process(true)
	refresh()


func _mark_dirty() -> void:
	_dirty = true


func _process(delta: float) -> void:
	_accum += delta
	if _dirty and _accum >= 0.1:
		_accum = 0.0
		_dirty = false
		var key := _content_key()
		if key != _last_key:
			_last_key = key
			refresh()


## 当前选中要展示的内容指纹(选择/人员/物件/数值变化才重建)。
func _content_key() -> String:
	return "h%d|%s" % [Store.history.size(), _content_key_body()]


func _content_key_body() -> String:
	match Store.sel_kind:
		"npc":
			var n := Store.npc(Store.sel_npc)
			if n.is_empty():
				return "npc:"
			var sig := Protocol.as_dict(n.get("signals", {}))
			var sigk := ""
			for s in ["energy", "hunger", "thirst", "bladder", "fun", "hp"]:
				sigk += "%d," % int(round(Protocol.num(sig.get(s), 0.0) * 100.0))
			return "npc:%s|%s|%s|%s|%s|%d|%d" % [
				Store.sel_npc, n.get("activity", ""), n.get("money", ""),
				sigk, str(n.get("intent", {})),
				Protocol.as_array(n.get("memory", [])).size(),
				Protocol.as_array(n.get("events", [])).size(),
			]
		"entity":
			var e := Store.entity(Store.sel_entity)
			return "ent:%s|%s|%s" % [Store.sel_entity, e.get("stock", ""),
				e.get("claimed_by", "")]
		"location":
			var parts := PackedStringArray([Store.sel_location])
			var pids: Array = []
			for k in Store.npcs:
				if Protocol.s(Store.npcs[k].get("loc", "")) == Store.sel_location:
					pids.append(str(k))
			pids.sort()
			for k in pids:
				var n := Store.npc(str(k))
				parts.append("p:%s/%s/%s" % [n.get("name", ""), n.get("age", ""),
					n.get("role", "")])
			var eids: Array = []
			for k in Store.entities:
				if Protocol.s(Store.entities[k].get("loc", "")) == Store.sel_location:
					eids.append(str(k))
			eids.sort()
			for k in eids:
				var e := Store.entity(str(k))
				parts.append("e:%s/%s/%s" % [e.get("item_type", ""),
					e.get("stock", ""), e.get("price", "")])
			return "loc:" + "|".join(parts)
		_:
			return "empty"


# ---------------------------------------------------------------------------
# 组装
# ---------------------------------------------------------------------------
func refresh() -> void:
	_last_key = _content_key()
	_clear()
	if Store.can_go_back():
		_body.add_child(_back_button())
	match Store.sel_kind:
		"npc":
			var n := Store.npc(Store.sel_npc)
			if not n.is_empty():
				_build_npc(n)
				return
		"entity":
			if Store.entities.has(Store.sel_entity):
				_build_entity(Store.sel_entity)
				return
		"location":
			if Store.rooms.has(Store.sel_location):
				_build_location(Store.sel_location)
				return
	_build_empty()


func _clear() -> void:
	for c in _body.get_children():
		_body.remove_child(c)
		c.queue_free()


func _build_empty() -> void:
	var l := _label("城市观察窗", 14, MUTED)
	l.text = "城市观察窗\n点建筑查看人员与物件"
	_body.add_child(l)


func _build_npc(n: Dictionary) -> void:
	var head: Control = NPC_HEADER.instantiate()
	_body.add_child(head)
	head.set_header(
		Protocol.s(n.get("name", n.get("id", "NPC"))),
		"%s · %s" % [
			Store.name_of(Protocol.s(n.get("loc", ""))),
			_first_nonempty(Protocol.s(n.get("act_class")), Protocol.s(n.get("activity"))),
		]
	)

	# --- 当前行为 ---
	var act_body := _section("当前行为")
	_add_kv(act_body, "正在做", _activity_text(n))
	_add_kv(act_body, "金钱", "¥%d" % int(Protocol.num(n.get("money"))))
	var active := Protocol.as_dict(n.get("active", {}))
	if not active.is_empty():
		_add_kv(act_body, "剩余", "%d / %d tick" % [
			int(Protocol.num(active.get("remaining"))),
			int(Protocol.num(active.get("total")))])
	var cur_intent := Protocol.as_dict(n.get("intent", {}))
	_add_kv(act_body, "意图", "%s → %s" % [
		Protocol.s(cur_intent.get("kind", "—")),
		Store.name_of(Protocol.s(cur_intent.get("target", "")))])

	# --- Status ---
	var sig_body := _section("Status")
	var signals := Protocol.as_dict(n.get("signals", {}))
	var keys := _signal_keys(signals)
	if keys.is_empty():
		sig_body.add_child(_muted_label("—"))
	else:
		for k in keys:
			var v := clampf(Protocol.num(signals.get(k)), 0.0, 1.0)
			var row: Control = SIGNAL_ROW.instantiate()
			sig_body.add_child(row)
			row.set_row(Zh.signal_zh(k), v)

	# --- 候选排名 ---
	var cand_body := _section("候选排名 · 实时")
	var intent := Protocol.as_dict(n.get("intent", {}))
	var ranked := _unique_by_max(Protocol.as_array(intent.get("ranked", [])))
	if ranked.is_empty():
		cand_body.add_child(_muted_label("暂无候选(该 NPC 还没决策)"))
	else:
		var top := maxf(Protocol.num(ranked[0].get("score")), 1.0e-6)
		var intent_target := Protocol.s(intent.get("target", ""))
		var limit := mini(8, ranked.size())
		for i in range(limit):
			var r: Dictionary = ranked[i]
			var row: Control = CAND_ROW.instantiate()
			cand_body.add_child(row)
			row.set_row(i + 1, Store.name_of(Protocol.s(r.get("id"))),
				Protocol.num(r.get("score")) / top, Protocol.num(r.get("score")),
				i == 0, i == 0 and intent_target == Protocol.s(r.get("id")))

	# --- 记忆 ---
	var memory := Protocol.as_array(n.get("memory", []))
	var counts := int(Protocol.num(n.get("memory_counts"), float(memory.size())))
	var mem_body := _section("记忆 %d" % counts)
	if memory.is_empty():
		mem_body.add_child(_muted_label("空"))
	else:
		for m in memory:
			var row: Control = MEM_ROW.instantiate()
			mem_body.add_child(row)
			var d := Protocol.as_dict(m)
			row.set_row(
				Store.name_of(Protocol.s(d.get("item_id", ""))),
				Store.name_of(Protocol.s(d.get("located", ""))),
				Protocol.num(d.get("believe")), Protocol.num(d.get("remember"))
			)

	# --- Event Log(最近 80 条; 单行 "D1 08:00 | 类型 | 人话") ---
	var events := Protocol.as_array(n.get("events", []))
	var limit := mini(80, events.size())
	var ev_body := _section("Event Log · 最近 %d 条" % limit)
	if events.is_empty():
		ev_body.add_child(_muted_label("暂无"))
	else:
		for i in range(limit):
			var ev := Protocol.as_dict(events[events.size() - 1 - i])
			var kind := Protocol.s(ev.get("kind", Protocol.s(ev.get("type", ""))))
			var row: Control = EVENT_ROW.instantiate()
			ev_body.add_child(row)
			row.set_row(int(Protocol.num(ev.get("tick"))), Zh.event_zh(kind),
				_event_color(kind), _one_line(ev))


func _build_location(id: String) -> void:
	var room := Store.room(id)
	var people: Array = []
	for k in Store.npcs:
		if Protocol.s(Store.npcs[k].get("loc", "")) == id:
			people.append(str(k))
	people.sort()
	var items: Array = []
	for k in Store.entities:
		if Protocol.s(Store.entities[k].get("loc", "")) == id:
			items.append(str(k))
	items.sort()

	var head: Control = NPC_HEADER.instantiate()
	_body.add_child(head)
	var cap := int(Protocol.num(room.get("capacity"), 0.0))
	head.set_header(Protocol.s(room.get("name", id)),
		"%s · %d/%d 人 · %d 物件" % [
			Zh.kind_zh(Protocol.s(room.get("kind", ""))),
			people.size(), cap, items.size()])

	# 人员(表头 + 可点行)
	var pbody := _section("人员 %d" % people.size())
	_add_cols_row(pbody, ["姓名", "年龄", "角色"], null, true)
	if people.is_empty():
		pbody.add_child(_muted_label("无人"))
	else:
		for k in people:
			var n := Store.npc(k)
			var age := Protocol.num(n.get("age"), -1.0)
			_add_cols_row(pbody, [
				Protocol.s(n.get("name", k)),
				"—" if age < 0.0 else str(int(age)),
				Zh.role_zh(Protocol.s(n.get("role", ""))),
			], func() -> void: Store.select("npc", k))

	# 物件(表头 + 可点行 → 详情)
	var ibody := _section("物件 %d" % items.size())
	_add_cols_row(ibody, ["名称", "数量", "价格"], null, true)
	if items.is_empty():
		ibody.add_child(_muted_label("无"))
	else:
		for k in items:
			var e := Store.entity(k)
			_add_cols_row(ibody, [
				_item_name(e, k), _qty_txt(e), _price_txt(e),
			], func() -> void: Store.select("entity", k))


func _build_entity(id: String) -> void:
	var e := Store.entity(id)
	var head: Control = NPC_HEADER.instantiate()
	_body.add_child(head)
	head.set_header(Protocol.s(e.get("name", id)),
		"%s · %s" % [_item_name(e, id), Store.name_of(Protocol.s(e.get("loc", "")))])

	var body := _section("属性")
	_add_kv(body, "id", id)
	_add_kv(body, "类型", "%s（%s）" % [Protocol.s(e.get("item_type", "—")),
		_item_name(e, id)])
	_add_kv(body, "地点", Store.name_of(Protocol.s(e.get("loc", ""))))
	_add_kv(body, "库存", _qty_txt(e))
	_add_kv(body, "价格", _price_txt(e))
	var owner := Protocol.s(e.get("owner", ""))
	_add_kv(body, "归属", Store.name_of(owner) if owner != "" else "公共")
	var claimed := Protocol.s(e.get("claimed_by", ""))
	_add_kv(body, "使用中", Store.name_of(claimed) if claimed != "" else "否")
	_add_kv(body, "交互时长", "%d tick" % int(Protocol.num(e.get("duration_ticks"))))
	var tags := Protocol.as_array(e.get("tags", []))
	_add_kv(body, "标签", " / ".join(tags) if not tags.is_empty() else "—")
	var aff := Protocol.as_dict(e.get("affordances", {}))
	if not aff.is_empty():
		var parts := PackedStringArray()
		for ek in aff:
			parts.append("%s %+.2f" % [Zh.signal_zh(str(ek)), Protocol.num(aff[ek])])
		_add_kv(body, "信号效果", "，".join(parts))
	for eff_name in ["on_start", "on_complete"]:
		var effs := Protocol.as_array(e.get(eff_name, []))
		if not effs.is_empty():
			_add_kv(body, eff_name, str(effs))
	_stub_sections()


func _item_name(e: Dictionary, fallback: String) -> String:
	var t := Protocol.s(e.get("item_type", ""))
	if t != "" and Zh.item_zh(t) != t:
		return Zh.item_zh(t)
	return Protocol.s(e.get("name", fallback), fallback)


func _qty_txt(e: Dictionary) -> String:
	var s := int(Protocol.num(e.get("stock"), -1.0))
	return "∞" if s < 0 else str(s)


func _price_txt(e: Dictionary) -> String:
	var p := Protocol.num(e.get("price"), 0.0)
	return "—" if p <= 0.0 else "¥%d" % int(p)


## 统一列表行: 第 0 列弹性左对齐, 后两列固定宽(右/左); 有 on_click 则可点+hover 高亮。
const COL_W := [0.0, 54.0, 84.0]
const COL_ALIGN := [0, 2, 0]
const ROW_H := 26

func _add_cols_row(body: VBoxContainer, texts: Array, on_click: Variant,
		is_header: bool = false) -> void:
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 10)
	hb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var tint := Color("7f8ea3") if is_header else Color("c7d2e2")
	for i in texts.size():
		var l := Label.new()
		l.text = str(texts[i])
		l.add_theme_font_size_override("font_size", 12)
		l.add_theme_color_override("font_color", tint)
		l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		l.horizontal_alignment = COL_ALIGN[i] if i < COL_ALIGN.size() else 0
		l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		l.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var w: float = COL_W[i] if i < COL_W.size() else 0.0
		if w > 0.0:
			l.custom_minimum_size.x = w
			l.size_flags_horizontal = Control.SIZE_FILL
		else:
			l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		hb.add_child(l)

	if is_header:
		body.add_child(hb)
		return

	var btn := Button.new()
	btn.focus_mode = Control.FOCUS_NONE
	btn.custom_minimum_size.y = ROW_H
	btn.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	btn.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
	var hover := StyleBoxFlat.new()
	hover.bg_color = Color("1a2230")
	hover.set_corner_radius_all(4)
	btn.add_theme_stylebox_override("hover", hover)
	btn.add_theme_stylebox_override("pressed", hover)
	if on_click is Callable:
		btn.pressed.connect(on_click)
	body.add_child(btn)
	btn.add_child(hb)
	hb.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	hb.offset_left = 6.0
	hb.offset_right = -6.0


func _stub_sections() -> void:
	_section("Decision").add_child(_muted_label("无决策"))
	_section("Cognitive Memory").add_child(_muted_label("无"))
	_section("Event Log").add_child(_muted_label("暂无"))


# ---------------------------------------------------------------------------
# 组件装配辅助
# ---------------------------------------------------------------------------
func _section(title: String) -> VBoxContainer:
	var sec: Control = SECTION.instantiate()
	_body.add_child(sec)
	sec.set_title(title)
	return sec.body()


func _add_kv(body: VBoxContainer, k: String, v: String) -> void:
	var row: Control = KV_ROW.instantiate()
	body.add_child(row)
	row.set_row(k, v)


## 返回上一界面(如 王二家 → 王二 后回退)。
func _back_button() -> Button:
	var b := Button.new()
	b.text = "← 返回"
	b.flat = true
	b.focus_mode = Control.FOCUS_NONE
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	b.add_theme_font_size_override("font_size", 12)
	b.add_theme_color_override("font_color", Color("6fb7ff"))
	b.pressed.connect(func() -> void: Store.back())
	return b


func _label(text: String, font_size: int, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", font_size)
	l.add_theme_color_override("font_color", color)
	return l


func _muted_label(text: String) -> Label:
	return _label(text, 12, MUTED)


func _activity_text(n: Dictionary) -> String:
	var cls := Protocol.s(n.get("act_class", "idle"))
	var act := Protocol.s(n.get("activity", ""))
	match cls:
		"move":
			var tv := Protocol.as_dict(n.get("travel", {}))
			return "前往 %s" % Store.name_of(Protocol.s(tv.get("to", "")))
		"eat":
			return _act_with("吃饭", act)
		"sleep":
			return _act_with("睡觉", act)
		"toilet":
			return "上厕所"
		"drink":
			return "喝水"
		"fun":
			return _act_with("娱乐", act)
		_:
			return "空闲"


func _act_with(prefix: String, act: String) -> String:
	return prefix + (" · " + act if act != "" else "")


# ---------------------------------------------------------------------------
# 纯函数辅助(镜像 Inspector.tsx)
# ---------------------------------------------------------------------------
func _signal_keys(signals: Dictionary) -> Array:
	var keys := []
	for k in SIGNAL_ORDER:
		if signals.has(k):
			keys.append(k)
	for k in signals:
		if not SIGNAL_ORDER.has(k):
			keys.append(k)
	return keys


func _unique_by_max(rows: Array) -> Array:
	var best := {}
	for r in rows:
		var d := Protocol.as_dict(r)
		var id := Protocol.s(d.get("id"))
		if id == "":
			continue
		var score := Protocol.num(d.get("score"))
		if not best.has(id) or score > best[id]:
			best[id] = score
	var out := []
	for id in best:
		out.append({"id": id, "score": best[id]})
	out.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		if a["score"] != b["score"]:
			return a["score"] > b["score"]
		return a["id"] < b["id"]
	)
	return out


func _one_line(ev: Dictionary) -> String:
	var p := Protocol.as_dict(ev.get("payload", {}))
	var kind := Protocol.s(ev.get("kind", Protocol.s(ev.get("type", ""))))
	match kind:
		"decision":
			return _action_text(Protocol.s(ev.get("intent", "")),
				Protocol.s(ev.get("target", "")))
		"perceived":
			var obs := Protocol.as_array(p.get("observed_entity_ids", []))
			return "感知 %d 物件" % obs.size()
		"interaction_done":
			return "完成 · %s" % Store.name_of(Protocol.s(p.get("entity", "")))
		"interaction_aborted":
			return "中止 · %s" % Store.name_of(Protocol.s(p.get("entity", "")))
		"intent_failed":
			return "未遂：%s" % Protocol.s(p.get("why", ""))
		"bought":
			return "买 %s ×%s" % [Store.name_of(Protocol.s(p.get("item", ""))),
				str(p.get("qty", 1))]
		_:
			return ""


## 意图 -> 人话(查不到货物类型时回退到物品名)。
func _action_text(intent: String, target: String) -> String:
	var e := Store.entity(target)
	var itype := Protocol.s(e.get("item_type", "")) if not e.is_empty() else ""
	return Zh.action_text(intent, Store.name_of(target), itype)


func _event_color(kind: String) -> Color:
	match kind:
		"decision":
			return Color("5bb0ff")
		"perceived":
			return Color("7fe0a8")
		"learned":
			return Color("8fc7ff")
		"told":
			return Color("d0a6ff")
		"bought":
			return Color("ffd24d")
		"interaction_done":
			return Color("a8b6c8")
		"interaction_aborted":
			return Color("c08b6a")
		"intent_failed", "npc_died":
			return Color("e05252")
		"stock_changed":
			return Color("e8a34d")
		_:
			return MUTED


func _first_nonempty(a: String, b: String) -> String:
	return a if a != "" else b
