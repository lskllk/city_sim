/** assets.js —— 贴图仓库。编辑器、游戏、预览共用同一份。
 *
 * 按需加载：先给 null，纹理到了自动补上（Pixi 的 Assets 自己有缓存）。
 * 缺图不算错 —— 调用方画个色块占位，看得见"这里少东西"，而不是静默不画。
 */
import { Assets } from '../vendor/pixi.min.mjs';

const memo = new Map();

export class Assets2 {
  constructor(manifest) {
    this.manifest = manifest;
    // ★ 版本号：每有一张贴图到货就 +1。
    //   画地图的代码是"数据没变就只画一次"，而贴图是**懒加载**的 ——
    //   第一次画的时候还没到货，就永远画不上（踩过：道路中线一直不出现）。
    //   把 version 掺进缓存 key，贴图一到就会重画一次。
    this.version = 0;
  }

  /** 同步取。没加载过就排进队列，这次先返回 null。 */
  get(file) {
    if (memo.has(file)) return memo.get(file);
    memo.set(file, null);
    Assets.load("/art/" + file)
      .then(t => { memo.set(file, t); this.version++; })
      .catch(() => {});
    return null;
  }

  async loadAll(files) {
    const out = await Promise.allSettled(files.map(f => Assets.load("/art/" + f)));
    files.forEach((f, i) => memo.set(f, out[i].status === "fulfilled" ? out[i].value : null));
    this.version++;
  }

  /** 预先加载地图 + 编辑器要用的那几类。
   *  ★ 这里漏一个类，症状都是"永远不出现"而不是"报错"：
   *    · 漏 road  → 道路的中线虚线不画（地图只画一次，等不到懒加载）
   *    · 漏 props → 摆放预览变成兜底方框（长得像"预览太大了"）
   *    所以宁可多加载：反正就 26 张。 */
  async preloadMap() {
    const files = this.manifest.assets
      .filter(a => ["ground", "road", "body", "shadow", "lit", "props", "world",
                    "portrait", "iworld", "iempty", "attach", "fx"].includes(a.sub))
      .map(a => a.file);
    await this.loadAll(files);
  }

  buildingTypes() { return this.manifest.buildingTypes || {}; }
}

export async function fetchManifest() {
  return (await fetch("/art/manifest.json")).json();
}
