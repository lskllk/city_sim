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
		refresh()


# ---------------------------------------------------------------------------
# 组装
# ---------------------------------------------------------------------------
func refresh() -> void:
	_clear()
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
	l.text = "城市观察窗\n点选 NPC / 物件 / 建筑查看"
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

	# --- Event Log ---
	var events := Protocol.as_array(n.get("events", []))
	var ev_body := _section("Event Log")
	if events.is_empty():
		ev_body.add_child(_muted_label("暂无"))
	else:
		var limit := mini(15, events.size())
		for i in range(limit):
			var ev := Protocol.as_dict(events[events.size() - 1 - i])
			var kind := Protocol.s(ev.get("kind", Protocol.s(ev.get("type", ""))))
			var row: Control = EVENT_ROW.instantiate()
			ev_body.add_child(row)
			row.set_row(int(Protocol.num(ev.get("tick"))), Zh.event_zh(kind),
				_event_color(kind), _one_line(ev))


func _build_entity(id: String) -> void:
	var e := Store.entity(id)
	var head: Control = NPC_HEADER.instantiate()
	_body.add_child(head)
	head.set_header(
		Protocol.s(e.get("name", id)),
		"物件 · %s" % Store.name_of(Protocol.s(e.get("loc", "")))
	)
	var body := _section("Status")
	var tags := Protocol.as_array(e.get("tags", []))
	var tag_text := "—"
	if not tags.is_empty():
		var parts := PackedStringArray()
		for t in tags:
			parts.append(str(t))
		tag_text = " / ".join(parts)
	_add_kv(body, "类型", tag_text)
	_add_kv(body, "库存", str(int(Protocol.num(e.get("stock")))) if e.has("stock") else "—")
	var claimed := Protocol.s(e.get("claimed_by", ""))
	_add_kv(body, "使用中", Store.name_of(claimed) if claimed != "" else "否")
	_stub_sections()


func _build_location(id: String) -> void:
	var room := Store.room(id)
	var head: Control = NPC_HEADER.instantiate()
	_body.add_child(head)
	head.set_header(Protocol.s(room.get("name", id)), "建筑")

	var n_npc := 0
	for k in Store.npcs:
		if Protocol.s(Store.npcs[k].get("loc", "")) == id:
			n_npc += 1
	var n_ent := 0
	for k in Store.entities:
		if Protocol.s(Store.entities[k].get("loc", "")) == id:
			n_ent += 1
	var body := _section("Status")
	_add_kv(body, "NPC", str(n_npc))
	_add_kv(body, "物件", str(n_ent))
	_stub_sections()


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


func _label(text: String, font_size: int, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", font_size)
	l.add_theme_color_override("font_color", color)
	return l


func _muted_label(text: String) -> Label:
	return _label(text, 12, MUTED)


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
			var intent := Protocol.s(ev.get("intent", ""))
			var target := Protocol.s(ev.get("target", ""))
			return "决定 %s%s" % [intent, (" → %s" % target) if target != "" else ""]
		"perceived":
			var obs := Protocol.as_array(p.get("observed_entity_ids", []))
			return "感知 %d 物件" % obs.size()
		"interaction_done":
			return "完成 %s" % Protocol.s(p.get("entity", ""))
		"intent_failed":
			return "未遂：%s" % Protocol.s(p.get("why", ""))
		"bought":
			return "购买 %s" % Protocol.s(p.get("item", ""))
		_:
			return ""


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
		"intent_failed", "npc_died":
			return Color("e05252")
		"stock_changed":
			return Color("e8a34d")
		_:
			return MUTED


func _first_nonempty(a: String, b: String) -> String:
	return a if a != "" else b
