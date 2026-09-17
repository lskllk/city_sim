"""world.model —— 世界的静态定义: 世界【长什么样】。

  buildings    建筑类型库 + 面积∝容量自动布局
  roads        路网 + 最短路(A* / 几何)
  itemdefs     物品定义(config/items/*.json, 加载即校验)
  companies    公司: 店铺属于它、钱进它的账、工资从它出

这些是【名词】—— 从 config/场景 加载或算出来, 不主动做事。
"""
