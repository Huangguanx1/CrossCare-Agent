# 第 1 课：从前端事件流理解 Tool Calling

本课只新增一项能力：让模型**请求**三个只读工具，工具是否执行、能看到什么数据，仍由后端决定。无 API 密钥时项目继续使用离线规则；后端测试使用假模型响应，不产生调用费用。

## 先看调用链

```text
Vue runDraft() → POST /api/tickets/{id}/draft
  → 模型读取工单并请求工具
  → 后端校验工具名、参数和工单归属
  → SQLite 查询订单/物流/政策
  → 工具结果回传给模型
  → 模型提交 JSON 草稿
  → Pydantic 校验，后端保存为待审核
```

可以把 `run_tool_loop()` 想成一个异步请求协调器，把 `input_items` 想成不断追加事件的状态数组。不同的是，模型输出的 `function_call` 只是一个**请求对象**，类似前端派发 action；真正查询数据库的是后端的 `execute_tool()`。参考[官方 OpenAI Docs：Function calling](https://developers.openai.com/api/docs/guides/function-calling)。

| 代码位置 | 职责 | 类比 |
|---|---|---|
| [`frontend/src/App.vue`](../frontend/src/App.vue) 的 `runDraft` | 用户触发、更新界面状态 | 点击事件处理函数 |
| [`backend/model_agent.py`](../backend/model_agent.py) 的 `run_tool_loop` | 接收工具请求、回传工具结果、限制调用轮数 | 请求协调器 |
| [`backend/app.py`](../backend/app.py) 的 `execute_tool` | 强制当前工单的订单归属、市场和 SKU | 服务端鉴权与业务规则 |
| `save_draft` | 保存模型草稿和真实工具证据 | 持久化状态 |

## 最重要的权限边界

模型的 `get_order_summary` 参数只有 `order_id`，没有 `customer_id`。后端从工单取 `customer_id`，并用 `WHERE id = ? AND customer_id = ?` 查询订单。模型请求其他订单号时，后端只返回 `found: false`，不会把订单状态或物流事件送给模型。即使模型后来编造了“已送达”，后端也会用安全答复覆盖该草稿。

`search_policies` 同样不接受模型传入市场或 SKU：后端从当前客户和已核实订单确定过滤条件。政策引用由实际检索结果生成，模型不能自己指定引用 ID。

## 亲手验证

在项目根目录运行：

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

观察 `test_model_calls_read_only_tools_and_keeps_real_citations`：假模型一次请求三个工具，第二轮拿到结果后返回草稿。再看 `test_model_cannot_read_another_customers_order`：假模型请求 T-1003 中不属于当前客户的 `ORD-1002`，测试要求工具结果没有配送事实，最终草稿也不能声称“已送达”。

学习时可以暂时在测试的假模型里把订单号改成 `ORD-9999`，预测风险标记和工具结果，再运行测试核对。不要先改生产代码。

## 本课的边界

- 这是真实的工具调用代码路径，但在线模型尚未使用真实密钥验收；测试只证明应用侧的调用协议和权限边界。
- 仍用 SQLite FTS5 做词法检索；这不是 Embedding RAG。
- 还没有 LangGraph checkpoint、失败恢复或固定效果评测。下一课先补可回放的模型输出与失败样例，再增加状态图。
