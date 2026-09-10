# emojis.gd —— emoji 语义注册表(镜像前端 emojis.ts / 后端 citysim/emojis.py)。
#
# 单一真源在 tools/gen_emoji_registry.py; 本文件是观察器侧镜像, 新增语义时同步。
class_name Emojis
extends RefCounted

const EMOJI := {
	"bed": "🛏️",
	"box": "📦",
	"cart": "🛒",
	"food": "🍱",
	"meal": "🍽️",
	"relaxed": "😌",
	"toilet": "🚽",
	"tool": "🔧",
	"tv": "📺",
	"walk": "🚶",
	"water": "🚰",
}


static func get_icon(key: String, fallback: String = "•") -> String:
	return EMOJI.get(key, fallback)
