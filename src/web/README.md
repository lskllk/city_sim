# src/web —— 前端（PixiJS）

```bash
python -m uvicorn citysim.game.server:app --port 8765
open http://127.0.0.1:8765/game/
```

后端把前端和美术一起发出去（`/game/` → 这里，`/art/` → `art/out/`），
所以**一条命令就够**，不用另开 dev server、不用 npm、没有构建步骤。

```
index.html      壳：主菜单 / 游戏
app.css         地图是彩色的、面板是一张安静的纸（规则见 art/style.json）
js/net.js       WebSocket：拆信封、指令、request/reply
js/store.js     世界状态：hello + 增量 snapshot 合并
js/world.js     Pixi：地面 / 道路 / 建筑 / 人物 / 相机 / 点击
js/panel.js     点一个人看穿他 —— 记忆卡（来源 / 置信度 / 多旧）
vendor/         PixiJS 8（本地，离线可用）
```

## 两条线上契约，踩过

**① 消息是信封，数据在 `payload` 里**

```jsonc
{"kind": "snapshot", "protocol_version": 2, "payload": {"type": "snapshot", ...}}
```

`net.js` 负责拆掉：上层直接看见 `{type, ...}`。

**② 指令形状是 `{name, args, req_id}`**，不是 `{type, ...args}`

```js
net.send("select", { npc: "npc_he_san" })
```

---

## 已经做的

- 主菜单（继续 / 选择场景 / 编辑器占位）+ 游戏
- 画出世界：地面平铺、道路（从 `map.nodes/edges` 描线 —— **路是图，路面是渲染结果**）、
  建筑（美术按**世界占地**缩放）、人物
- 相机：拖动平移、滚轮缩放（锚在鼠标）、`我的店` 回中、`F` 全图
- 点人 → 面板（状态条 / 在做 / 钱 / **他记得什么**：来源 · 置信度 · 多旧）
- 速率按钮（停 / 1× / 10× / 100× / 1000×）

## 还没做

- 物品（货架上的货）没画
- 气泡有代码但没人验证过位置对不对
- 人物朝向按位移猜的，没做真正的行走动画
- 广场/公共建筑用的是地面贴图，没做围栏

## 调试

控制台里有 `window.citysim`：

```js
citysim.store.npcs.size          // 世界里几个人
citysim.store.locations          // 6 个地点
citysim.pick("npc_he_san")       // 等于点了他一下
```
