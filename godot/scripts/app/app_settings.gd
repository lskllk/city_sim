# app_settings.gd —— 全局设置(autoload 名 `Settings`)。
#
# 框架式设计(标准游戏设置系统):
#   - 所有设置项在 _register_defaults() 里用 register() 声明 schema;
#   - 设置界面(ui/settings_menu.gd)按 schema 自动生成控件, 不手搓每一项;
#   - 新增设置 = 加一行 register(), UI/持久化/变更通知全部自动;
#   - 分区(section) + 键(key) + 类型(type) + 默认值 + 标签 + 提示 + 枚举选项。
#
# 持久化: user://settings.cfg (ConfigFile)。类型可扩展(见 Type)。
extends Node

signal changed(section: String, key: String, value: Variant)
signal schema_changed

const PATH := "user://settings.cfg"

enum Type { BOOL, INT, FLOAT, STRING, ENUM, PATH }

var _cfg := ConfigFile.new()
var _schema: Dictionary = {}          # "section/key" -> spec
var _sections: Array[String] = []     # 出现顺序


func _ready() -> void:
	_register_defaults()
	_load()


# --- schema 声明 ----------------------------------------------------------
func register(section: String, key: String, type: int, default: Variant,
		label: String, hint: String = "", choices: Array = []) -> void:
	_schema["%s/%s" % [section, key]] = {
		"section": section, "key": key, "type": type,
		"default": default, "label": label, "hint": hint, "choices": choices,
	}
	if not _sections.has(section):
		_sections.append(section)
	schema_changed.emit()


func _register_defaults() -> void:
	# 常规
	register("general", "language", Type.ENUM, "zh", "语言", "界面语言",
		[{"value": "zh", "label": "简体中文"}, {"value": "en", "label": "English"}])
	register("general", "confirm_quit", Type.BOOL, true, "退出前确认")
	# 后端(Python 内核)
	register("backend", "autostart", Type.BOOL, true, "自动启动后端",
		"启动观察器时自动拉起 Python 内核")
	register("backend", "console", Type.BOOL, true, "显示后端控制台", "便于查看后端日志")
	register("backend", "python", Type.PATH, "", "Python 路径", "留空 = 自动发现")
	# 网络
	register("network", "ws_url", Type.STRING, "ws://127.0.0.1:8765/ws", "WebSocket 端点")
	# 游戏(场景重建参数)
	register("game", "seed", Type.INT, 3, "随机种子", "场景重建的确定性种子")
	register("game", "tell_p", Type.FLOAT, 0.1, "通知概率", "NPC 相互告知的概率")
	# 显示
	register("display", "fullscreen", Type.BOOL, false, "全屏")
	register("display", "vsync", Type.BOOL, true, "垂直同步")


# --- 查询 -----------------------------------------------------------------
func sections() -> Array:
	return _sections.duplicate()


func entries(section: String) -> Array:
	var out: Array = []
	for id in _schema.keys():
		var spec: Dictionary = _schema[id]
		if spec["section"] == section:
			out.append(spec)
	return out


func section_label(section: String) -> String:
	match section:
		"general": return "常规"
		"backend": return "后端"
		"network": return "网络"
		"game": return "游戏"
		"display": return "显示"
		_: return section


func spec(section: String, key: String) -> Dictionary:
	return _schema.get("%s/%s" % [section, key], {})


# --- 读写 -----------------------------------------------------------------
func get_value(section: String, key: String, fallback: Variant = null) -> Variant:
	if _cfg.has_section_key(section, key):
		return _cfg.get_value(section, key)
	var id := "%s/%s" % [section, key]
	if _schema.has(id):
		return _schema[id]["default"]
	return fallback


func set_value(section: String, key: String, value: Variant) -> void:
	var old: Variant = get_value(section, key)
	if old == value:
		return
	_cfg.set_value(section, key, value)
	_save()
	_apply(section, key, value)
	changed.emit(section, key, value)


func reset_section(section: String) -> void:
	for s in entries(section):
		set_value(section, s["key"], s["default"])


func reset_all() -> void:
	for section in _sections:
		reset_section(section)


# --- 立即生效的设置(其余由消费者在下次使用时读取) ------------------------
func _apply(section: String, key: String, value: Variant) -> void:
	match "%s/%s" % [section, key]:
		"display/fullscreen":
			DisplayServer.window_set_mode(
				DisplayServer.WINDOW_MODE_FULLSCREEN if bool(value)
				else DisplayServer.WINDOW_MODE_WINDOWED)
		"display/vsync":
			DisplayServer.window_set_vsync_mode(
				DisplayServer.VSYNC_ENABLED if bool(value)
				else DisplayServer.VSYNC_DISABLED)
		_:
			pass


func _save() -> void:
	_cfg.save(PATH)


func _load() -> void:
	if _cfg.load(PATH) != OK:
		return
	_apply("display", "fullscreen", get_value("display", "fullscreen"))
	_apply("display", "vsync", get_value("display", "vsync"))
