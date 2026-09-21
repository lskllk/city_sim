/** assets.js —— 贴图仓库。编辑器、游戏、预览共用同一份。
 *
 * 按需加载：先给 null，纹理到了自动补上（Pixi 的 Assets 自己有缓存）。
 * 缺图不算错 —— 调用方画个色块占位，看得见"这里少东西"，而不是静默不画。
 */
import { Assets } from '../vendor/pixi.min.mjs';

const memo = new Map();

export class Assets2 {
  constructor(manifest) { this.manifest = manifest; }

  /** 同步取。没加载过就排进队列，这次先返回 null。 */
  get(file) {
    if (memo.has(file)) return memo.get(file);
    memo.set(file, null);
    Assets.load("/art/" + file).then(t => memo.set(file, t)).catch(() => {});
    return null;
  }

  async loadAll(files) {
    const out = await Promise.allSettled(files.map(f => Assets.load("/art/" + f)));
    files.forEach((f, i) => memo.set(f, out[i].status === "fulfilled" ? out[i].value : null));
  }

  /** 预先加载地图要用的那几类（地面 / 建筑本体 / 落影）。 */
  async preloadMap() {
    const files = this.manifest.assets
      .filter(a => ["ground", "body", "shadow"].includes(a.sub)).map(a => a.file);
    await this.loadAll(files);
  }

  buildingTypes() { return this.manifest.buildingTypes || {}; }
}

export async function fetchManifest() {
  return (await fetch("/art/manifest.json")).json();
}
