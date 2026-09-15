# check_scripts.gd —— 全量脚本解析自检。
#
# 用法(仓库根):
#   godot --headless --path godot --script res://scripts/debug/check_scripts.gd
#
# 逐个 load() 所有 .gd: 有解析错误/找不到依赖的文件会打印出来并返回非 0。
# 作用: 编辑器里某个脚本解析失败时, 错误会以 "Could not resolve class X,
# because of a parser error" 的形式落到【引用它的那个文件】上, 很难定位。
# 这个脚本直接点名真正的坏文件。
extends SceneTree


func _initialize() -> void:
	var files: Array[String] = []
	_collect("res://", files)
	files.sort()
	var failed: Array[String] = []
	var n_gd := 0
	for f in files:
		if not f.ends_with(".gd"):
			continue
		n_gd += 1
		# 坑(踩过一次): 语法错的脚本 load() **不返回 null**, 而是返回一个
		# 无效的 GDScript(错误只打到 stderr) → 只判 null 的话这个自检永远绿,
		# 真正坏掉的文件反而报不出来。用 can_instantiate() 判有效性。
		var s: Variant = load(f)
		var bad := s == null or not (s is GDScript)
		if not bad:
			bad = not (s as GDScript).can_instantiate()
		if bad:
			failed.append(f)
	print("\n[check] 共 %d 个 .gd, 解析失败 %d 个" % [n_gd, failed.size()])
	for f in failed:
		print("   !! ", f)
	quit(1 if failed.size() > 0 else 0)


func _collect(dir: String, out: Array[String]) -> void:
	var d := DirAccess.open(dir)
	if d == null:
		return
	d.list_dir_begin()
	var n := d.get_next()
	while n != "":
		if not n.begins_with("."):
			var p := dir.path_join(n)
			if d.current_is_dir():
				_collect(p, out)
			else:
				out.append(p)
		n = d.get_next()
	d.list_dir_end()
