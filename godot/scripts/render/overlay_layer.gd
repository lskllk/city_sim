# overlay_layer.gd —— 空间语义反馈(纯展示)。
#
#   NPC 选中: 高亮当前 location + intent target(地点框 / 实体标记)
#   Location / Entity 选中: 高亮所在地点 + 实体标记
# 镜像前端 engine/pixi/OverlayRenderer.ts + SimulationStage.overlayInputOf。
class_name OverlayLayer
extends Layer2D

const CUR_COLOR := Color("3ddc84")
const TGT_COLOR := Color("ffc24d")
const FOCUS_COLOR := Color("6fb7ff")


func refresh() -> void:
	queue_redraw()


func _draw() -> void:
	var view := _compute_input()
	if view.is_empty():
		return

	if view.has("focus"):
		var f: Dictionary = view["focus"]
		_frame(f.get("loc_id", ""), FOCUS_COLOR)
		if f.has("at"):
			_marker(f["at"], FOCUS_COLOR)
		return

	if view.has("cur_loc"):
		_frame(view["cur_loc"], CUR_COLOR)
	if view.has("target") and view["target"] != null:
		var t: Dictionary = view["target"]
		_frame(t.get("loc_id", ""), TGT_COLOR)
		if t.has("at"):
			_marker(t["at"], TGT_COLOR)


## 当前选中 -> overlay 语义(镜像 overlayInputOf)。无则返回 {}。
func _compute_input() -> Dictionary:
	match Store.sel_kind:
		"location":
			if Store.sel_location != "":
				return {"focus": {"loc_id": Store.sel_location}}
		"entity":
			var e := Store.entity(Store.sel_entity)
			if not e.is_empty():
				var focus := {"loc_id": Protocol.s(e.get("loc", ""))}
				var at: Variant = _at_of(e)
				if at != null:
					focus["at"] = at
				return {"focus": focus}
		"npc":
			var n := Store.npc(Store.sel_npc)
			if n.is_empty():
				return {}
			var out := {"cur_loc": Protocol.s(n.get("loc", ""))}
			var intent := Protocol.as_dict(n.get("intent", {}))
			var tid := Protocol.s(intent.get("target", ""))
			if tid != "":
				if Store.rooms.has(tid):
					out["target"] = {"loc_id": tid}
				else:
					var te := Store.entity(tid)
					if not te.is_empty():
						var t := {"loc_id": Protocol.s(te.get("loc", ""))}
						var at2: Variant = _at_of(te)
						if at2 != null:
							t["at"] = at2
						out["target"] = t
			return out
	return {}


func _at_of(d: Dictionary) -> Variant:
	var p: Variant = d.get("position", null)
	if typeof(p) == TYPE_ARRAY and (p as Array).size() >= 2:
		return Interp.to_vec2(p)
	return null


func _frame(loc_id: String, color: Color) -> void:
	var r := Store.room(loc_id)
	if r.is_empty():
		return
	var rect := Rect2(
		Protocol.num(r.get("x")), Protocol.num(r.get("y")),
		Protocol.num(r.get("w")), Protocol.num(r.get("h"))
	)
	draw_rect(rect, Color(color.r, color.g, color.b, 0.9), false, 2.5)


func _marker(p: Variant, color: Color) -> void:
	draw_arc(p, 7.0, 0.0, TAU, 32, color, 1.0, true)
