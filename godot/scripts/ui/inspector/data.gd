# data.gd —— Inspector 业务 helper(文案/取数, 纯静态)。
#
# 只给 inspector 页面用; 与 UI 框架(UiKit/UiList/UiPage)解耦。
# 依赖 Store / Protocol / Zh(均为全局单例/class_name)。
class_name InspData
extends RefCounted

const SIGNAL_ORDER := ["energy", "hunger", "thirst", "bladder", "fun", "hp"]


static func activity_text(n: Dictionary) -> String:
	var cls := Protocol.s(n.get("act_class", "idle"))
	var act := Protocol.s(n.get("activity", ""))
	match cls:
		"move":
			var tv := Protocol.as_dict(n.get("travel", {}))
			return "前往 %s" % Store.name_of(Protocol.s(tv.get("to", "")))
		"eat":
			return act_with("吃饭", act)
		"sleep":
			return act_with("睡觉", act)
		"toilet":
			return "上厕所"
		"drink":
			return "喝水"
		"fun":
			return act_with("娱乐", act)
		_:
			return "空闲"


static func act_with(prefix: String, act: String) -> String:
	return prefix + (" · " + act if act != "" else "")


static func home_text(n: Dictionary) -> String:
	var home := Protocol.s(n.get("home", ""))
	return Store.name_of(home) if home != "" else "-"


static func access_text(room: Dictionary) -> String:
	var owner := Protocol.s(room.get("owner", ""))
	var open_to := Protocol.as_array(room.get("open_to", []))
	var pub: Variant = room.get("public", null)
	if pub == null:
		pub = owner == "" and open_to.is_empty()
	if bool(pub):
		return "公共"
	var names := PackedStringArray()
	if owner != "":
		names.append(Store.name_of(owner))
	for x in open_to:
		var nm := Store.name_of(Protocol.s(x))
		if nm != "" and not names.has(nm):
			names.append(nm)
	return "、".join(names) if not names.is_empty() else "受限"


static func item_name(e: Dictionary, fallback: String) -> String:
	var t := Protocol.s(e.get("item_type", ""))
	if t != "" and Zh.item_zh(t) != t:
		return Zh.item_zh(t)
	return Protocol.s(e.get("name", fallback), fallback)


static func qty_txt(e: Dictionary) -> String:
	var s := int(Protocol.num(e.get("stock"), -1.0))
	return "∞" if s < 0 else str(s)


static func price_txt(e: Dictionary) -> String:
	var p := Protocol.num(e.get("price"), 0.0)
	return "—" if p <= 0.0 else "¥%d" % int(p)


static func user_text(e: Dictionary) -> String:
	var claimed := Protocol.s(e.get("claimed_by", ""))
	return Store.name_of(claimed) if claimed != "" else "--"


static func signal_keys(signals: Dictionary) -> Array:
	var keys := []
	for k in SIGNAL_ORDER:
		if signals.has(k):
			keys.append(k)
	for k in signals:
		if not SIGNAL_ORDER.has(k):
			keys.append(k)
	return keys


static func unique_by_max(rows: Array) -> Array:
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
		return a["id"] < b["id"])
	return out


static func one_line(ev: Dictionary) -> String:
	var p := Protocol.as_dict(ev.get("payload", {}))
	var kind := Protocol.s(ev.get("kind", Protocol.s(ev.get("type", ""))))
	match kind:
		"decision":
			return action_text(Protocol.s(ev.get("intent", "")),
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


static func action_text(intent: String, target: String) -> String:
	var e := Store.entity(target)
	var itype := Protocol.s(e.get("item_type", "")) if not e.is_empty() else ""
	return Zh.action_text(intent, Store.name_of(target), itype)


static func event_color(kind: String) -> Color:
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
			return UiTheme.TEXT_DIM


static func first_nonempty(a: String, b: String) -> String:
	return a if a != "" else b
