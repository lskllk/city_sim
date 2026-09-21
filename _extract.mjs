import fs from "node:fs";
const src = fs.readFileSync("wiki/gen.mjs", "utf8");
const m = src.match(/const ARTCATS = (\[[\s\S]*?)\n\];/);
if (!m) throw new Error("没找到 ARTCATS");
const ARTCATS = eval(m[1]);                    // 纯数据字面量，eval 安全
fs.writeFileSync("art/catalog.json", JSON.stringify({
  _note: "资产目录 —— 九大类的唯一真源。wiki 的美术页从这里生成；docs/asset-list.md 只讲为什么这么分。",
  _rule: "类别按【玩法属性】分，不按外观。判据见 docs/asset-list.md §二。",
  _gap: "sub 有 gap 字段 = 这一类还没有美术，gap 里的文字就是「这是什么/为什么重要」。",
  categories: ARTCATS,
}, null, 2) + "\n", "utf8");
console.log(`art/catalog.json ← ${ARTCATS.length} 个大类 · ${ARTCATS.reduce((n,c)=>n+c.subs.length,0)} 个子类`);
