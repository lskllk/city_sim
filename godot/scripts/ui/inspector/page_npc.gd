# page_npc.gd —— NPC 详情页(常驻, 原地 bind)。
class_name InspNpcPage
extends UiPage

var _header: Control
var _act: Dictionary = {}          # key -> Label
var _remain_row: Control
var _sig_rows: Array[Control] = []
var _cand_sec: Control
var _cand: UiList
var _cand_empty: Label
var _mem_sec: Control
var _mem: UiList
var _mem_empty: Label
var _ev_sec: Control
var _ev: UiList
var _ev_empty: Label


func build() -> void:
	_header = UiKit.header(self)

	var a: VBoxContainer = UiKit.section(self, "当前行为").body()
	_act["doing"] = UiKit.kv(a, "正在做")
	_act["home"] = UiKit.kv(a, "住址")
	_act["money"] = UiKit.kv(a, "金钱")
	_act["remain"] = UiKit.kv(a, "剩余")
	_remain_row = _act["remain"].get_parent()
	_act["intent"] = UiKit.kv(a, "意图")

	var sig: VBoxContainer = UiKit.section(self, "Status").body()
	for i in InspData.SIGNAL_ORDER.size():
		var r: Control = UiKit.SIGNAL_ROW.instantiate()
		sig.add_child(r)
		_sig_rows.append(r)

	_cand_sec = UiKit.section(self, "候选排名 · 实时")
	_cand = UiList.new(_cand_sec.body(), UiKit.CAND_ROW)
	_cand_empty = UiKit.muted(_cand_sec.body(), "暂无候选（该 NPC 还没决策）")

	_mem_sec = UiKit.section(self, "记忆")
	_mem = UiList.new(_mem_sec.body(), UiKit.MEM_ROW)
	_mem_empty = UiKit.muted(_mem_sec.body(), "空")

	_ev_sec = UiKit.section(self, "Event Log")
	_ev = UiList.new(_ev_sec.body(), UiKit.EVENT_ROW)
	_ev_empty = UiKit.muted(_ev_sec.body(), "暂无")


func bind(id: String) -> void:
	var n := Store.npc(id)
	if n.is_empty():
		return
	_header.set_header(Protocol.s(n.get("name", id)),
		"%s · %s" % [Store.name_of(Protocol.s(n.get("loc", ""))),
			InspData.first_nonempty(Protocol.s(n.get("act_class")),
				Protocol.s(n.get("activity")))])

	_act["doing"].text = InspData.activity_text(n)
	_act["home"].text = InspData.home_text(n)
	_act["money"].text = "¥%d" % int(Protocol.num(n.get("money")))
	var active := Protocol.as_dict(n.get("active", {}))
	_remain_row.visible = not active.is_empty()
	if not active.is_empty():
		_act["remain"].text = "%d / %d tick" % [
			int(Protocol.num(active.get("remaining"))),
			int(Protocol.num(active.get("total")))]
	var intent := Protocol.as_dict(n.get("intent", {}))
	_act["intent"].text = "%s → %s" % [Protocol.s(intent.get("kind", "—")),
		Store.name_of(Protocol.s(intent.get("target", "")))]

	var signals := Protocol.as_dict(n.get("signals", {}))
	var keys := InspData.signal_keys(signals)
	for i in _sig_rows.size():
		var key := String(keys[i]) if i < keys.size() else ""
		_sig_rows[i].visible = key != ""
		if key != "":
			_sig_rows[i].set_row(Zh.signal_zh(key),
				clampf(Protocol.num(signals.get(key)), 0.0, 1.0))

	# --- 候选排名(行池, 最多 8) ---
	var ranked := InspData.unique_by_max(Protocol.as_array(intent.get("ranked", [])))
	var limit := mini(8, ranked.size())
	var target := Protocol.s(intent.get("target", ""))
	var top := 1.0e-6
	if limit > 0:
		top = maxf(Protocol.num(ranked[0].get("score")), 1.0e-6)
	for i in limit:
		var r := _cand.row(i)
		var rid := Protocol.s(ranked[i].get("id", ""))
		var score := Protocol.num(ranked[i].get("score"))
		r.set_row(i + 1, Store.name_of(rid), score / top, score,
			i == 0, i == 0 and target == rid)
	_cand.trim(limit)
	_cand_empty.visible = limit == 0
	_cand_sec.set_title("候选排名 · 实时" if limit == 0
		else "候选排名 · 实时 (%d)" % limit)

	# --- 记忆(行池) ---
	var memory := Protocol.as_array(n.get("memory", []))
	var counts := int(Protocol.num(n.get("memory_counts"), float(memory.size())))
	for i in memory.size():
		var d := Protocol.as_dict(memory[i])
		_mem.row(i).set_row(
			Store.name_of(Protocol.s(d.get("item_id", ""))),
			Store.name_of(Protocol.s(d.get("located", ""))),
			Protocol.num(d.get("believe")), Protocol.num(d.get("remember")))
	_mem.trim(memory.size())
	_mem_empty.visible = memory.is_empty()
	_mem_sec.set_title("记忆 %d" % counts)

	# --- 事件(行池, 最近 N) ---
	var events := Protocol.as_array(n.get("events", []))
	var elimit := mini(80, events.size())
	for i in elimit:
		var ev := Protocol.as_dict(events[events.size() - 1 - i])
		var kind := Protocol.s(ev.get("kind", Protocol.s(ev.get("type", ""))))
		_ev.row(i).set_row(int(Protocol.num(ev.get("tick"))), Zh.event_zh(kind),
			InspData.event_color(kind), InspData.one_line(ev))
	_ev.trim(elimit)
	_ev_empty.visible = elimit == 0
	_ev_sec.set_title("Event Log · 最近 %d 条" % elimit)
