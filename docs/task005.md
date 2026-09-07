设计冻结（必须遵守）
1. Node

新增空间节点概念。

Node 是：

空间中的一个区域容器。

不是建筑类型，不负责行为。

数据：

SpatialNode
{
    id: str

    position: tuple[float,float]

    capacity: int

    entities: list[str]
}

禁止增加：

type
affordance
effect
behavior
rule

原因：

Node 只是空间容器。

2. Edge

新增空间连接。

Edge 是：

两个 Node 之间的空间连接。

数据：

SpatialEdge
{
    id: str

    from_node: str

    to_node: str

    width: float
}

禁止增加：

traffic
speed
cost
vehicle

这些未来再做。

3. World 改造

当前：

可能类似：

location_id

升级为：

locations: dict[str, SpatialNode]

edges: dict[str, SpatialEdge]

World 成为：

空间事实唯一来源

增加：

distance(node_a,node_b)

计算：

sqrt(
(x1-x2)^2+
(y1-y2)^2
)

不要保存 distance。

4. Entity 改造

保持现有 Entity。

只增加：

node_id: str

表示：

Entity 当前属于哪个空间区域。

例如：

market_node

    apple_entity
    shelf_entity
    cashier_entity

不要改变：

affordance
effect
interaction

保持现有架构。

5. NPC 改造

本 TASK 不实现道路移动。

只增加空间状态基础：

Person:

新增：

node_id: str

表示：

NPC 当前所在空间节点。

保留：

position

如果已有 position：

不要删除。

6. Scene 数据升级

修改：

config/scenes/elm_lane.json

增加：

locations:
[
 {
   "id":"home_001",
   "position":[100,100],
   "capacity":20
 }
]


edges:
[
 {
   "id":"road_001",
   "from":"home_001",
   "to":"market_001",
   "width":5
 }
]

现有：

locations/entities/npcs

保持兼容。

7. Snapshot 增加空间信息

gateway/snapshot.py

增加：

{
 "nodes":[
   {
    "id":"",
    "position":[],
    "capacity":
   }
 ],

 "edges":[
   {
    "id":"",
    "from":"",
    "to":"",
    "width":
   }
 ]
}

用于未来前端渲染。

8. 前端

本 TASK：

不重做 UI

只要求：

snapshot 可以拿到：

nodes
edges

即可。

禁止：

PixiJS
地图重构
动画
拖拽

留给 TASK006。

测试要求

新增：

tests/test_spatial_graph.py

覆盖：

Node
创建成功
position 正确
Edge
连接 Node
Distance

例如：

A(0,0)

B(3,4)

distance=5
Entity

验证：

entity.node_id

正确。

Replay

保持：

test_replay.py

通过。

Import Layer

保持：

test_import_layers.py

通过。

完成标准

必须满足：

World
 |
 +-- SpatialNode
 |
 +-- SpatialEdge
 |
 +-- Entity location
 |
 +-- NPC location

形成最小空间闭环。

但是：

不实现：

pathfinding
travel animation
traffic
physics
输出要求

完成后报告：

修改文件列表
新增文件列表
测试结果
当前空间模型说明
明确列出未实现内容