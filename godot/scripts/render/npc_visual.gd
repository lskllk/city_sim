# npc_visual.gd —— 单个 NPC 的可视化(场景 scenes/world/npc_visual.tscn)。
#
# 只负责改颜色/选中环; 位置与平滑由 EntityLayer 驱动。
extends Node2D

@onready var _body: Polygon2D = $Body
@onready var _ring: Line2D = $Ring
@onready var _bubble: PanelContainer = $Bubble
@onready var _bubble_label: Label = $Bubble/BubbleLabel


func set_color(c: Color) -> void:
	_body.color = c


func set_selected(selected: bool) -> void:
	_ring.visible = selected


## 头顶气泡: 当前在做什么(空串则不显示)。
func set_activity(text: String) -> void:
	_bubble.visible = text != ""
	_bubble_label.text = text
