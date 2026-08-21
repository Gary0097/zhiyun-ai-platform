# 订单与交付风险 PawApp

安装后成为 QwenPaw 桌面应用，数据保存在当前 Agent Workspace 的 `data/ai-os.sqlite`。

提供两个只读 Tool：

- `orders_query`：查询全部订单或按订单号、状态、风险筛选。
- `orders_delivery_risk`：返回红黄绿风险汇总和需要关注的订单。

测试话术：`调用订单工具查询全部订单，并告诉我哪些存在交付风险。`
