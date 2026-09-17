# page_empty.gd —— 空态页面(未选中任何东西): 【城市总览】。
#
# 点空白处 → 这里。回答"这城现在多大": 建筑 / 住宅(床位) / 公司 / 人 / 店 / 物件…
# 纯读 Store 镜像, 不碰 simulation(铁律)。
class_name InspEmptyPage
extends UiPage

var _box: VBoxContainer


func build() -> void:
	var l := UiKit.muted(self, "城市观察窗 · 点建筑看人员与物件")
	l.add_theme_font_size_override("font_size", 13)
	_box = VBoxContainer.new()
	_box.add_theme_constant_override("separation", 6)
	add_child(_box)


func bind(_id: String) -> void:
	for c in _box.get_children():
		_box.remove_child(c)
		c.queue_free()

	# --- 建筑: 楼层单元(part_of)不算独立建筑 ---
	var n_bld := 0
	var n_home := 0
	var n_shop := 0
	var n_market := 0
	var n_units := 0
	var beds := 0
	for lid in Store.rooms:
		var r: Dictionary = Store.rooms[lid]
		if Protocol.s(r.get("part_of", "")) != "":
			n_units += 1                    # 多楼层的子地点
			continue
		n_bld += 1
		match Protocol.s(r.get("kind", "")):
			"home":
				n_home += 1
				beds += int(Protocol.num(r.get("capacity", 0)))
			"shop":
				n_shop += 1
			"market":
				n_market += 1

	# --- 公司 / 员工 / 注册了的店 ---
	var n_staff := 0
	var reg := {}
	for c in Store.companies:
		var cd: Dictionary = c
		n_staff += Protocol.as_array(cd.get("staff", [])).size()
		for sid in Protocol.as_array(cd.get("shops", [])):
			reg[Protocol.s(sid)] = true

	# --- 物件: 家具(fixture) vs 货 ---
	var n_decor := 0
	for e in Store.entities.values():
		if Protocol.as_array((e as Dictionary).get("tags", [])).has("fixture"):
			n_decor += 1
	var n_goods := Store.entities.size() - n_decor

	# --- 人 / 无住所 ---
	var homeless := 0
	for pid in Store.npcs:
		var h := Protocol.s(Protocol.as_dict(Store.npcs[pid]).get("home", ""))
		if h == "" or not Store.rooms.has(h):
			homeless += 1

	var sec := UiKit.section(_box, "城市总览")
	UiKit.kv(sec.body(), "建筑").text = "%d 栋%s" % [n_bld,
		("  (%d 个楼层单元)" % n_units) if n_units > 0 else ""]
	UiKit.kv(sec.body(), "住宅").text = "%d 栋 · 床位 %d" % [n_home, beds]
	UiKit.kv(sec.body(), "商铺").text = "%d 栋 · 已注册公司 %d" % [n_shop, reg.size()]
	if n_market > 0:
		UiKit.kv(sec.body(), "市场").text = "%d 栋" % n_market
	UiKit.kv(sec.body(), "公司").text = "%d 家 · 员工 %d 人" % [Store.companies.size(), n_staff]
	UiKit.kv(sec.body(), "居民").text = "%d 人%s" % [Store.npcs.size(),
		("  ← 无住所 %d" % homeless) if homeless > 0 else ""]
	UiKit.kv(sec.body(), "物件").text = "%d 件 (货 %d / 家具 %d)" % [
		Store.entities.size(), n_goods, n_decor]

	var sim := UiKit.section(_box, "模拟")
	UiKit.kv(sim.body(), "时间").text = "第 %d 天 %s" % [Store.day, Store.clock]
	UiKit.kv(sim.body(), "场景").text = Store.scenario if Store.scenario != "" else "—"

	UiKit.muted(_box, "点建筑看人员与物件 · 点人/物件看详情")
