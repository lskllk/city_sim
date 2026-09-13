# npc_visual.gd —— 单个 NPC 的可视化(场景 scenes/world/npc_visual.tscn)。
#
# 只负责改颜色/选中环; 位置与平滑由 EntityLayer 驱动。
extends Node2D

@onready var _body: Polygon2D = $Body
@onready var _ring: Line2D = $Ring
@onready var _bubble: PanelContainer = $Bubble
@onready var _bubble_label: Label = $Bubble/BubbleLabel

## 圆点多边形半径为 7(世界单位); 路网场景里建筑才 8~22 单位 → 缩到 ~3.9 才不遮住房子。
const BODY_SCALE := 0.55


func _ready() -> void:
	_body.scale = Vector2(BODY_SCALE, BODY_SCALE)
	_ring.scale = Vector2(BODY_SCALE, BODY_SCALE)
	# 气泡仍走世界坐标; 随圆点变小把底边拉近头顶
	_bubble.offset_top = -32.0
	_bubble.offset_bottom = -8.0


func set_color(c: Color) -> void:
	_body.color = c


func set_selected(selected: bool) -> void:
	_ring.visible = selected


## 头顶气泡: 当前在做什么(空串则不显示)。
func set_activity(text: String) -> void:
	_bubble.visible = text != ""
	_bubble_label.text = text
