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

## 编辑器的五条规则

路是【图】不是线。数据 = `nodes{} + edges{} + buildings{}`。

```
① 吸附优先级  既有节点 > 建筑门 > 道路中心线 > 栅格
② 门即节点    画路终点吸到门 → 生成 door_of 节点，跟着房子走
③ 没有边的节点不存在                      pruneOrphans()
④ 必须先有路才能摆房                      规则强制，不是提示
⑤ 建筑自动贴边 松手 → 门朝最近的路 + 墙贴路沿（沿【法线】推，不是沿路推）
```

⑤ 的"沿法线推"是修出来的：点正好落路上时，最近点 = 它自己，
往哪边推都是猜的 —— 原来推到了路的延长线上（房子压在路里）。

## 验收工具（我看不到浏览器，靠这三个）

```bash
# 起一个带调试口的 Chrome
"/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless --disable-gpu --remote-debugging-port=9222 about:blank &

node tools/shot.mjs "http://127.0.0.1:8765/game/#editor" _e.png 10 1400 880
python tools/ascii_shot.py _e.png 20        # 截图转 ASCII —— 位置对不对一眼看出
node tools/cdp.mjs "<url>" 8 "表达式"        # 在页面里求值 / 派事件
```

**为什么要 ASCII**：数颜色像素只能证明"有东西"，证明不了"位置对"。
ASCII 是低分辨率的眼睛 —— 铺满没有、路连没连上、面板压没压住地图，一眼就看出来。

## 还没做

- 物品（货架上的货）没画
- 杂物（树/长椅/路灯）编辑器还不能摆 —— 场景里也还没有 `props` 段
- 道路是硬边拼接（没有 autotile 集，见 `docs/asset-list.md` A3）
- 人物没有真正的行走动画（只有朝向）
- 场景"选择"列表、一键启动 `.cmd`
