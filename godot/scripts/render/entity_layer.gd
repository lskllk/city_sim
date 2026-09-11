# entity_layer.gd —— 地图上不再渲染 NPC 圆点。
#
# 改为: 点建筑 → 右侧 Inspector 列出"家里有谁" → 选中某人 → 下方出他的时间线。
# 本层保留空实现以兼容 WorldCanvas 的调用。
class_name EntityLayer
extends Node2D


func set_selected(_id: String) -> void:
	pass


func reconcile() -> void:
	pass


func apply_targets() -> void:
	pass


func pick_npc(_world_pos: Vector2) -> String:
	return ""


func pick_entity(_world_pos: Vector2) -> String:
	return ""
