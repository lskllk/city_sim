# overlay_layer.gd —— 空间语义反馈(纯展示): 只框选【房间】。
#
#   选中 NPC: 绿框=当前所在房间, 橙框=意图目标所在房间
#   选中 房间/物品: 蓝框=焦点房间
# 物品不再逐个渲染, 因此不再画物品级标记。
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
		_frame(view["focus"], FOCUS_COLOR)
		return
	if view.has("cur_loc"):
		_frame(view["cur_loc"], CUR_COLOR)
	if view.has("target"):
		_frame(view["target"], TGT_COLOR)


## 当前选中 -> overlay 语义。无则返回 {}。
func _compute_input() -> Dictionary:
	match Store.sel_kind:
		"location":
			if Store.sel_location != "":
				return {"focus": Store.sel_location}
		"entity":
			var e := Store.entity(Store.sel_entity)
			if not e.is_empty():
				return {"focus": Protocol.s(e.get("loc", ""))}
		"npc":
			var n := Store.npc(Store.sel_npc)
			if n.is_empty():
				return {}
			var out := {"cur_loc": Protocol.s(n.get("loc", ""))}
			var intent := Protocol.as_dict(n.get("intent", {}))
			var tid := Protocol.s(intent.get("target", ""))
			if Store.rooms.has(tid):
				out["target"] = tid
			else:
				var te := Store.entity(tid)
				if not te.is_empty():
					out["target"] = Protocol.s(te.get("loc", ""))
			return out
	return {}


func _frame(loc_id: String, color: Color) -> void:
	if loc_id == "":
		return
	var r := Store.room(loc_id)
	if r.is_empty():
		return
	var rect := Rect2(
		Protocol.num(r.get("x")), Protocol.num(r.get("y")),
		Protocol.num(r.get("w")), Protocol.num(r.get("h"))
	)
	draw_rect(rect, Color(color.r, color.g, color.b, 0.9), false, 2.5)
