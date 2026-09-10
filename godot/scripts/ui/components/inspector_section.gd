# inspector_section.gd —— Inspector 折叠区段模板(标题 + 分隔线 + 内容容器)。
extends VBoxContainer


func set_title(t: String) -> void:
	$Head.text = t


func body() -> VBoxContainer:
	return $Body
