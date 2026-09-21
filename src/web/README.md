# src/web —— 前端（PixiJS）

```bash
python -m uvicorn citysim.game.server:app --port 8765
```

```
游戏      http://127.0.0.1:8765/game/
编辑器    http://127.0.0.1:8765/game/#editor
```

后端把前端和美术一起发出去（`/game/` → 这里，`/art/` → `art/out/`），
所以**一条命令就够**：不用 dev server、不用 npm、没有构建步骤。

## 设计从哪来

**UI = `proto/ui-prototype.html`（❄ 冻结的参考实现）**。
变量名、四角位置、`.pane`、`.plate`、按钮形态都照它，不自己发明。
一句话规则：**地图是彩色的，面板是一张安静的纸。**

**美术 = `art/out/`（全部资产）**。不画色块：
地面 `ground/*`、道路 `road/*`、建筑 `bld/*` + `_shadow` + `_lit`、
杂物 `props/*`、人物 `people/*`、物品 `items/*`。

## 文件

```
index.html      壳：地图视口 + 四角 HUD（游戏 / 编辑器各一套）
app.css         设计系统（取自 proto）
js/net.js       WebSocket：拆信封、指令
js/store.js     世界状态：hello + 增量 snapshot 合并
js/assets.js    贴图仓库（按需加载，共用一份）
js/view.js      相机 + 输入 + 屏幕纸片      ← 游戏/编辑器共用
js/maprender.js 地面 / 道路 / 建筑          ← 游戏/编辑器共用
js/mapdoc.js    地图文档模型（编辑器唯一真源）
js/world.js     游戏：人 + 气泡 + 点人
js/editor.js    编辑器：手柄 + 工具
js/panel.js     点人看穿他 —— 记忆卡
vendor/         PixiJS 8（本地，离线可用）
```

**渲染共用是硬要求**：`world.js` 和 `editor.js` 都用 `MapLayer`。
各写一份的话迟早"编辑器里看着对，进游戏不对"。

## 两条线上契约（踩出来的）

**① 消息是信封**：`{kind, protocol_version, payload}` —— 数据在 `payload` 里。
`net.js` 拆掉它，上层直接看见 `{type, ...}`。

**② 指令是 `{name, args, req_id}`**，不是 `{type, ...args}`。

## 相机：两个坑，都在 view.js

**① `apply()` 必须先 clamp 再写 transform。**
反了会怎样：渲染用 clamp【前】的相机，而 `toWorld` / `screenOf`（名牌、气泡定位）
用 clamp【后】的 `cam` —— **两边不是同一个数**。症状就是"名牌跑偏""地图不居中时缩放会漂"。

**② 平滑缩放的锚点必须在改 `k` 之前算。**

```js
const [wx, wy] = this.toWorld(z.sx, z.sy);   // ★ 先用当前的 k
this.cam.k += (z.k - this.cam.k) * 0.22;     // 再改 k
this.cam.x = wx*U - z.sx/this.cam.k;         // 把那个世界点钉回鼠标下
```

先改 k 再 toWorld，等于用"新 k + 旧相机"反推鼠标下的世界点 —— 不是原来那个点了。
测过：14 次滚轮能漂 25 世界单位。改对之后漂 **0.0000**。

## 输入模型（这里踩过两次，别改回去）

按下的那一刻就问上层："这个点你要不要接？"

```
onDown(世界点) → true   上层接了（拖房子 / 画路）→ 之后所有 move 都给它
               → false  没接 → 【默认就是平移相机】
```

原来的写法是"移动超过 4px 就转交上层" —— 结果相机一动 4px 就再也不动了
（拖动一卡一卡），而画路又永远等不到 pointerdown。
**两个 bug 同一个根因：把"拖"和"点"当成了互斥的两种模式。**
它们不是 —— 拖是默认，上层可以抢。

## 编辑器的六条规则

路是【图】不是线。数据 = `nodes{} + edges{} + buildings{}`。

```
① 两点法     按下起点 → 拖 → 松开终点。★ 整个过程不碰数据，松手才提交
             → "没画成"就真的什么都没留下（不会攒孤儿节点）
② 吸附       节点 / 门 / 路中线 / 栅格。★ 节点与门【比距离】，不是无条件让节点赢
             （踩过：门在鼠标下 1.2m，被 11m 外的节点抢走）
③ 拆边       起点落在既有路的中段 → 那条路拆成两条，于是变成三条路四个节点
④ 门即节点   房子贴好后自动把门接进路网：门上已有节点就【认领】，没有就新建；
             节点带 door_of，挪房子门跟着走
⑤ 没有边的节点不存在                      pruneOrphans()
⑥ 必须先有路才能摆房；松手自动贴边        门朝最近的路 + 墙贴路沿
```

⑥ 的贴边退开的是【墙】，不是中心：
```
back = 半路宽 + 半【自身进深】 + 0.3
```
   只退半个路宽的话退的是"中心" —— 小房子整个压在路里，
   21.9m 的店会盖住路 10m。用户："被吸附在中心而不是门口"。

   还有一条：点正好落路上时最近点 = 它自己，往哪边推都是猜的 ——
   所以用路的【法线】（`nearestRoad` 返回 dir 和 normal），不是沿路推。

## 道路怎么画的（圆角 + 融合）

三层各司其职，照归档的 Godot 版（`shared/building_style.gd`）：

```
一条路径 + cap/join="round"   凸角自然成圆；一条路径是为了不让接缝叠出白线
顶点圆盘（半径 = 半宽）        补 T / 十字的破边
路口【倒角】多边形            相邻两条入射路之间的缺口 —— 这才是"倒圆角"
```

倒角算法（`_fillets`）：每个节点收集入射方向，按角度排序，相邻两个方向之间
算一段**与两条边都相切**的弧：

```
r  = half × 0.5
cc = pos + rot(d0, φ/2) × (half+r)/sin(φ/2)     ← 圆心
t1 = pos + d0×tang + rot(d0,+90°)×half          ← 切点
t2 = pos + d1×tang + rot(d1,−90°)×half
多边形 = [节点, t1, …弧…, t2]      ★ 填在路段之后，同色叠加
```

90° 时 `t1=(1.5h,h)` `t2=(h,1.5h)` `圆心=(1.5h,1.5h)`，`|cc−t1| = 0.5h = r` ✓ 相切。
**这不是"在节点上放个圆盘"** —— 圆盘补不了缺口，缺口要的是与两条边都相切的弧。

另外两条：`α 近直行（φ≈π）和近同向（φ≈0）跳过`（本来就没缺口）；
`β 中线虚线只给 ≥6m 的路画`（4m 小弄堂摆一条只是噪声）。

## 验收工具（我看不到浏览器，靠这三个）

```bash
# 起一个带调试口的 Chrome
"/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless --disable-gpu --remote-debugging-port=9222 about:blank &

node tools/shot.mjs "http://127.0.0.1:8765/game/#editor" _e.png 10 1400 880
python tools/ascii_shot.py _e.png 20        # 截图转 ASCII —— 位置对不对一眼看出
node tools/cdp.mjs "<url>" 8 "表达式"        # 在页面里求值 / 派真 pointer 事件
node tools/cdp.mjs "<url>" 8 --eval-file tools/regress_editor.mjs   # 编辑器全量回归（13 项）
```

**为什么要 ASCII**：数颜色像素只能证明"有东西"，证明不了"位置对"。
ASCII 是低分辨率的眼睛 —— 铺满没有、路连没连上、面板压没压住地图，一眼就看出来。

## 还没做

- 物品（货架上的货）没画
- 杂物（树/长椅/路灯）编辑器还不能摆 —— 场景里也还没有 `props` 段
- 道路是硬边拼接（没有 autotile 集，见 `docs/asset-list.md` A3）
- 人物没有真正的行走动画（只有朝向）
- 场景"选择"列表、一键启动 `.cmd`
