# fonts.gd —— 字体资源入口。
#
# 实际字体在 resources/{ui_font,emoji_font}.tres(可在编辑器里直接改字体名/回退),
# 本类只做类型化访问, 供 Node2D 的 _draw 使用(Control 走 project.godot 的 Theme)。
class_name Fonts
extends RefCounted

const UI: SystemFont = preload("res://resources/ui_font.tres")
const EMOJI: SystemFont = preload("res://resources/emoji_font.tres")


static func ui_font() -> Font:
	return UI


static func emoji_font() -> Font:
	return EMOJI
