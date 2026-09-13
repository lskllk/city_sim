# page_empty.gd —— 空态页面(未选中任何东西)。
class_name InspEmptyPage
extends UiPage


func build() -> void:
	var l := UiKit.muted(self, "")
	l.text = "城市观察窗\n点建筑查看人员与物件"
	l.add_theme_font_size_override("font_size", 14)


func bind(_id: String) -> void:
	pass
