# ui_page.gd —— 页面基类(UI 框架层)。
#
# 生命周期铁律:
#   - build() 只调用一次(在 _ready), 用来摆放常驻控件;
#   - bind(id) 每个刷新节拍调用(默认 ~100ms), 只改属性, 绝不增删/重建控件;
#   - 页面实例常驻, 切换选中项时只切 visible, 不 new / 不 free。
# 子类只需实现 build() / bind(), 不会踩到"整页重建"导致的闪烁/点击丢失。
class_name UiPage
extends VBoxContainer


func _ready() -> void:
	add_theme_constant_override("separation", UiTheme.SEP)
	build()


## 子类实现: 构建常驻控件(只调用一次)。
func build() -> void:
	pass


## 子类实现: 按当前选中 id 原地更新数值。
func bind(_id: String) -> void:
	pass
