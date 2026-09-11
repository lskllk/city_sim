# 建筑抽象设计语言（Building Abstraction）

> 前端（观察器）如何"抽象地"表达一座建筑。核心：**三条正交通道**。

## 0. 三条正交通道

| 视觉通道 | 编码 | 实现 |
|---|---|---|
| **色相 + 纹路** | 建筑**类别**（kind） | `map_layer._kind_color` + `_draw_pattern` |
| **面积** | 建筑**容量**（capacity，能容多少人） | 后端 `world/buildings.py` 自动布局算 w/h |
| **红度（明度）** | **当前占用填充率** `n / capacity` | `map_layer` fill lerp → 红 |

一句话：**是什么看颜色，能装多少看大小，现在多挤看红不红。**

## 1. 类别词典

| kind | 底色 | 纹路 | 例（容量） |
|---|---|---|---|
| `home` 住所 | 暖褐 `#7a5a3a` | 横条 `h` | 小屋3 / 住所6 / 大宅12 |
| `shop` 商业 | 青绿 `#2f7d78` | 竖条 `v` | 店铺24 / 超市100 |
| `work` 工作 | 赭橙 `#8a5a34` | 斜条 `diag` | 工地40 / 办公楼200 |
| `public` 公共 | 石板蓝 `#42557f` | 点阵 `dots` | 广场60 |
| `school` 学校 | 紫 `#6b5a8a` | 点阵 | 学校120 |
| `clinic` 医疗 | 冷青 `#3f7d8a` | 十字 `plus` | 诊所40 |

底色承担主要辨识；纹路是冗余通道（色盲友好 / 缩小可辨），保持简单低透明度。

## 2. 尺寸函数：面积 ∝ 容量

```
面积 = scale² × capacity
边长 = scale × sqrt(capacity × aspect)     # aspect 为类别长宽比
```

人占的是地面 → 用**面积**编码容量（不是边长）。校验：`test_buildings.py` 断言
`面积/容量` 在所有建筑上一致、market(100) 面积 ≈ 住所(6) 的 `100/6` 倍。

## 3. 类型库 + 场景

**类型库** `config/buildings/*.json`（可批量复用/修改）：
```json
{"type":"supermarket","name":"超市","kind":"shop","capacity":100,"pattern":"v","aspect":1.4}
```

**场景** `config/scenes/*.json` 的 `locations` 只写类型，**不写坐标**：
```json
"locations": {
  "apt_101": {"type":"home"},              // 无 name → 门牌号 "101 号"
  "market":  {"type":"supermarket", "name":"大超市"}
}
```

### 展示名解析（`build_locations`）
门牌号是**地点自己的稳定标识**，不跟 owner/人不走：owner 可死可搬，门牌不随。
```
显示名 = 显式 name            // 商铺/广场的语义名，如 "大超市"
         > id 序号派生门牌号   // apt_001 → "1 号"（零配置，加新房自动有号）
         > 类型名              // 兜底，如 "住所"
```

## 4. 自动布局

`world/buildings.py::build_locations(data)`：
1. 解析 `type` → `kind/capacity/pattern/aspect`（可被 location 覆盖）；
2. 单位尺寸 `w=sqrt(cap*aspect)`, `h=sqrt(cap/aspect)`；
3. 按 `(kind, -capacity, id)` 排序（**同类聚成片区**）；
4. shelf 打包（横向排、超宽换行，街道间隙 `GAP`）；
5. **整体等比缩放**铺进画布（等比缩放不破坏面积∝容量）+ 居中。

产出写回 `world.locations`，随 `hello` 下发给前端。

## 5. 渲染层次

```
┌───────────────────────────────┐
│▒▒ 纹路(kind) ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒│  ← 底色+纹路 = 类别
│            1 号                │  ← 名字(门牌号/语义名, 居中, 有红色时白色)
│                        [1/6]  │  ← 占用角标 = 填充率
└───────────────────────────────┘  ← 边框: 空=类别色, 越满越红
```
- **点建筑** → Inspector 列出「人员 + 物件清单」。
- **选中环**（overlay）: 绿=NPC 当前所在, 橙=意图目标, 蓝=点选焦点。

## 6. 扩展点

- 新类别：加 `config/buildings/<type>.json` + `map_layer._kind_color` 一个分支。
- 容量上限将来可作世界规则（拥挤/排队），现在只作视觉。
