# cand_row.gd —— 候选排名一行(名次 + 名称 + 归一化条 + 分数)。
extends HBoxContainer

const CHOSEN := Color("cfe4ff")
const NORMAL := Color("d7dde8")


func set_row(rank: int, label_text: String, ratio: float, score: float,
		top: bool, chosen: bool) -> void:
	%Rank.text = str(rank)
	%Name.text = label_text
	%Name.add_theme_color_override("font_color", CHOSEN if chosen else NORMAL)
	%Bar.value = clampf(ratio, 0.0, 1.0)
	%Score.text = "%.3f" % score
	var fill := StyleBoxFlat.new()
	fill.bg_color = Color("5bb0ff") if top else Color("2c3c52")
	fill.set_corner_radius_all(3)
	%Bar.add_theme_stylebox_override("fill", fill)
