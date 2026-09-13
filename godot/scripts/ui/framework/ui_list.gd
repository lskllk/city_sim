# ui_list.gd —— 可复用行池(UI 框架层)。
#
# 目的: 列表数据变化时"只补行 / 只隐藏多行", 绝不销毁重建。
# 这是避免 hover 闪烁、点击丢失的根本手段; 所有列表(候选/记忆/事件/人员/物件)都用它。
class_name UiList
extends RefCounted

var _parent: Node
var _scene: PackedScene
var _rows: Array[Control] = []


func _init(parent: Node, scene: PackedScene) -> void:
	_parent = parent
	_scene = scene


## 取第 i 行(不足则实例化补齐), 并置为可见。返回的行由调用方 set_row(...)。
func row(i: int) -> Control:
	while _rows.size() <= i:
		var r: Control = _scene.instantiate()
		_parent.add_child(r)
		_rows.append(r)
	var r := _rows[i]
	r.visible = true
	return r


## 隐藏第 n 行及之后的多余行(保留实例, 下次复用, 不 free)。
func trim(n: int) -> void:
	for i in range(n, _rows.size()):
		_rows[i].visible = false


func size() -> int:
	return _rows.size()
