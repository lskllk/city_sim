# kv_row.gd —— 键值行(左键右值)。
extends HBoxContainer


func set_row(k: String, v: String) -> void:
	%Key.text = k
	%Value.text = v
