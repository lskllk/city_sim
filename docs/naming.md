# 命名规则（Naming）

> id 是机器标识（ASCII、稳定、全局唯一）；`name` 是展示（中文，随便改）。
> 规则是**可执行约束**：`tests/test_naming.py` 会强制校验。

## 0. 原则

1. **id ≠ name**：id 只给机器，展示名不进 id。
2. **前缀即命名空间**：**实例**（`loc_/ent_/npc_/plan_/org_`）带前缀；**类型**（item/building）不带全局前缀，用 `category_variant`。
3. id 只允许 `[a-z0-9_]`：小写、下划线、`^[a-z][a-z0-9_]*$`；禁止中文/空格/大写/驼峰。**id 定了不复用**。
4. `tags`（`edible`/`sleepable`/`toilet`…）是**语义标签**，不是 id，不随重命名改。

## 1. 实例 id（不带人名）

| 对象 | 结构 | 例 |
|---|---|---|
| 地点 | `<slug>_<NNN>` | `apt_001`、`apt_002`、`market_001`、`plaza_001`、`site_001` |
| 世界实体 | `<itemtype>_<NNN>` | `bed_basic_001`、`meal_simple_003`、`media_tv_002` |
| NPC | `npc_<姓拼音>_<名拼音>` | `npc_wang_er`、`npc_li_si` |
| 计划条目 | `plan_<npc>_<序号>` | `plan_npc_wang_er_01` |
| 组织(未来) | `org_<kind>_<slug>` | `org_shop_dongcheng` |

- **实体 id 不带人名/地点** —— 只 `类型 + 3 位编号`（同一类型全局递增）。归属/位置是 `owner`/`location` 字段，不进 id。
- 地点用**地点词 + 3 位编号**（按 slug 递增）；**地点/实体已不再用 `loc_`/`ent_` 前缀**。
- 编号统一 3 位（`001`），便于后续大规模生成/排序。

## 2. 类型 id（`category_variant`）

**物品类别**：`food / meal / drink / bed / toilet / seat / game / media / station / shop`
```
meal_simple   bed_basic   drink_dispenser   toilet_basic
media_tv      seat_bench  game_mahjong      station_workbench
food_apple    food_pear
```
**建筑类别**：`home / shop / work / public / school / clinic / farm`（kind）
```
home_standard  home_small  home_large
shop_small     shop_supermarket
work_site      work_office
public_plaza   school_basic   clinic_basic
```

## 3. 姓名规则

- 结构：`姓(1) + 名(1~2)`（`王二`、`李四`、`王小明`）。
- 字段：`surname` / `given` / `name`(=姓+名) / `id`(=`npc_<拼音>`)，另有 `gender` / `birthday`（独立字段，不进 id）。
- 数据：`config/names/names.json`（hanzi + pinyin）。
- 生成：`citysim.world.names.new_name(seed, gender)`，**同 seed 可复现**；`with_surname()` 用于兄弟姐妹/子女同姓。
- 年龄：`Person.age` 由 `birthday` 每天 0:00 重算（游戏纪元 `2026-01-01`）。

## 4. 强制校验

`tests/test_naming.py` 断言：
- 类型/实例 id 匹配字符集与前缀白名单；
- 全局唯一；
- `ent_<type>_<locslug>` 结构；
- 所有引用闭合（`at`/`owner`/`memory key`/`plan target`/`plan dest`/`travel`/`spawn_item.item_type`）。

## 5. 迁移

- `tools/rename_ids.py`(第一趟): 类型改 `category_variant`；实例改用语义前缀。
- `tools/renumber_ids.py`(第二趟): 地点/实体改为 `<slug>_<NNN>` / `<itemtype>_<NNN>`。
两脚本都改 `config/scenes/elm_lane.json`（含 owner/memory/plan/travel/home）。

> 遗留：`grocery` 物品类型已删除（历史占位）。
