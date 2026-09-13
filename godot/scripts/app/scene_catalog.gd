# scene_catalog.gd —— 场景目录(autoload 名 `SceneCatalog`)。
#
# 扫描 <仓库根>/config/scenes/*.json, 供启动界面列"可选场景"。
# 只读: 解析 JSON 取显示名 + 规模统计, 不改任何文件。
# 未来扩展(Workshop/多目录)只需往 sources 里加目录。
extends Node

const DIR_REL := "config/scenes"

# 可扩展的扫描目录(相对仓库根)。UI 会去重后列出。
var sources: Array[String] = [DIR_REL]


func repo_root() -> String:
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()


func scenes_dir() -> String:
	return repo_root().path_join(DIR_REL)


## 返回 [{rel, abs, name, npcs, entities, locations, ok, error}], 按 name 排序。
func list_scenes() -> Array:
	var out: Array = []
	var seen: Dictionary = {}
	for rel_dir in sources:
		var dir := repo_root().path_join(rel_dir)
		if not DirAccess.dir_exists_absolute(dir):
			continue
		for fn in DirAccess.get_files_at(dir):
			if fn.get_extension().to_lower() != "json":
				continue
			var abs := dir.path_join(fn)
			if seen.has(abs):
				continue
			seen[abs] = true
			out.append(_inspect(rel_dir.path_join(fn), abs))
	out.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return String(a["name"]).naturalnocasecmp_to(String(b["name"])) < 0)
	return out


func _inspect(rel: String, abs: String) -> Dictionary:
	var e := {
		"rel": rel, "abs": abs, "name": rel.get_file().get_basename(),
		"npcs": 0, "entities": 0, "locations": 0, "ok": false, "error": "",
	}
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(abs))
	if typeof(data) != TYPE_DICTIONARY:
		e["error"] = "JSON 解析失败"
		return e
	var d: Dictionary = data
	e["ok"] = true
	e["name"] = str(d.get("display_name", d.get("scene", e["name"])))
	e["npcs"] = _count(d.get("npcs"))
	e["entities"] = _count(d.get("entities"))
	e["locations"] = _count(d.get("locations"))
	return e


func _count(v: Variant) -> int:
	match typeof(v):
		TYPE_ARRAY:
			return (v as Array).size()
		TYPE_DICTIONARY:
			return (v as Dictionary).size()
		_:
			return 0
