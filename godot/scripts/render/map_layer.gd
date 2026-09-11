# map_layer.gd —— 建筑几何 helper(房间的绘制已移交 map_labels.gd 的屏幕坐标矢量层)。
#
# 保留: 世界画布尺寸 + 命中测试(世界坐标)。不做任何绘制。
class_name MapLayer
extends Node2D


func rebuild() -> void:
	pass


func world_size() -> Vector2:
	return Vector2(
		Protocol.num(Store.canvas.get("w"), 1280.0),
		Protocol.num(Store.canvas.get("h"), 800.0)
	)


## 命中测试: 返回包含该世界点的 location id, 否则 ""。
func hit_test(p: Vector2) -> String:
	for id in Store.rooms:
		var r: Dictionary = Store.rooms[id]
		var x := Protocol.num(r.get("x"))
		var y := Protocol.num(r.get("y"))
		var w := Protocol.num(r.get("w"))
		var h := Protocol.num(r.get("h"))
		if p.x >= x and p.x <= x + w and p.y >= y and p.y <= y + h:
			return id
	return ""
