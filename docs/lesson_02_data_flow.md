# 第 2 课：点击“生成待审草稿”后发生了什么

这一课先使用默认的**离线规则模式**，无需 API 密钥。它能帮助你看清数据流，但它本身不是大模型 Agent。右上角应显示“合成数据 · 离线规则演示”。

## 亲手走一次 T-1001

1. 打开 `http://127.0.0.1:5173/`，选择 `T-1001`。客户问 `ORD-1001` 的包裹在哪里。
2. 点击“生成待审草稿”。Vue 的 `runDraft()` 调用 `POST /api/tickets/T-1001/draft`，请求结束后重新读取工单和列表。
3. FastAPI 的 `generate_draft()` 判断当前模式；离线模式进入 `draft_for_ticket()`。
4. 后端从工单取客户 `C-001`，用 `order_for_customer()` 查询 `ORD-1001`。SQL 同时要求订单号和客户号匹配。
5. 校验成功后，`tracking_for_customer()` 读取该订单的物流事件；`search_policies()` 按消息关键词、市场、SKU 和政策有效期筛选政策。
6. 后端把英文草稿、内部说明、工具结果、政策引用和风险标记写入 SQLite，并将工单置为“待审核”。页面中栏展示查询依据，右栏展示可编辑草稿。

前端视角的调用链：

```text
按钮 @click → runDraft() → POST /api/tickets/{id}/draft
                            ↓
                  订单归属校验 → 物流查询 → 政策检索
                            ↓
                  SQLite 保存草稿和依据
                            ↓
          GET /api/tickets/{id} → Vue 更新中栏和右栏
```

对照代码：[按钮和请求状态](../frontend/src/App.vue)、[HTTP 请求封装](../frontend/src/api.ts)、[后端接口与业务查询](../backend/app.py)。浏览器开发者工具的 **Network** 面板也能看到这三个请求；先看返回的 `tool_results`、`citations`、`risk_flags`，再对照页面。

## 再试 T-1003：为什么不显示物流？

`T-1003` 属于 `C-001`，却询问 `C-002` 的 `ORD-1002`。点击生成后，中栏应显示“订单不属于当前客户或无法核实”，不会显示 `ORD-1002` 的配送状态。关键判断在服务端 SQL：`WHERE id = ? AND customer_id = ?`。前端隐藏信息只是展示，真正防止泄露的是后端查询条件。

## 与模型工具调用的关系

离线模式由后端规则决定查询顺序。配置模型模式后，模型会提出 `get_order_summary`、`get_tracking_events`、`search_policies` 的调用请求；**后端仍负责校验参数和客户权限**。因此“模型想查什么”和“系统允许查什么”是两件事。模型调用代码见[第 1 课](lesson_01_tool_calling.md)。

当前政策检索使用 SQLite FTS5 词法匹配，尚未实现 Embedding RAG；目前也没有真实店铺 API、自动发送或退款能力。
