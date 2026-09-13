# kv_row.gd —— 键值行(左键右值)。
extends HBoxContainer


func set_row(k: String, v: String) -> void:
	%Key.text = k
	%Value.text = v


## 供 UI 框架原地绑定: 返回"值"Label。
func value_label() -> Label:
	return %Value
