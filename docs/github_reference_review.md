# CrossCare Agent：GitHub 参考项目审阅

核验日期：2026-10-15。只借鉴设计思路，不以第三方仓库为项目起点；代码采用独立实现。仓库活跃度是 GitHub 公开元数据的当日快照，不能代表代码质量。

| 项目 | 核验情况 | 值得借鉴 | 不直接采用的原因 |
|---|---|---|---|
| [HelpPilot](https://github.com/poysa213/HelpPilot) | MIT；2026-08-02 最近提交；约5 stars。LangGraph、Chroma+reranker、SQLite checkpoint、人工审批 | 将敏感操作与模型可调用工具分离；把检索引用和运行轨迹给审核人看 | [`get_order`按订单号查询](https://github.com/poysa213/HelpPilot/blob/main/helppilot/tools.py)，没有在SQL中强制当前客户所有权；且示例含模拟退款/发送，我们的MVP完全不提供这些动作。许可证正文版权人仍为占位符，不复制代码。 |
| [SupportCopilot](https://github.com/LaelaZorana/ecom-support-copilot) | MIT；2026-08-30 最近提交；约1 star。可离线运行、20条固定工单评测、模拟订单API | 固定seed和无密钥回放模式、政策引用、测试集随代码交付 | [`OrdersService.get`的邮箱参数可省略](https://github.com/LaelaZorana/ecom-support-copilot/blob/main/supportcopilot/orders.py)；我们的订单工具必须由服务端工单身份约束。它用TF-IDF检索，不等同Embedding RAG；README的ROI是合成集推算，不能转述成真实店铺成效。 |
| [AI Agent Service Toolkit](https://github.com/JoshuaC215/agent-service-toolkit) | MIT；2026-10-13仍更新；约4527 stars。FastAPI+LangGraph服务、流式接口、测试与部署 | API与Agent分层、运行状态/事件输出、端到端冒烟检查 | 多Agent、语音、MCP、Langfuse、Postgres/Mongo和Streamlit超出14天MVP；直接克隆会让项目变成框架配置展示。 |
| [Agent Inbox](https://github.com/langchain-ai/agent-inbox) | MIT；GitHub元数据在2026-10-15显示已归档 | 人工待审队列的信息结构与中断恢复交互 | 需要LangGraph部署和API key，且不是Vue工作台；只参考交互，不集成。 |
| [LangGraph官方中断文档](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/interrupts.mdx)及[SQLite checkpointer源码](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py) | 官方一手资料 | `interrupt`+持久化checkpoint支持人工恢复；中断恢复会重跑节点，副作用必须放在安全位置 | MVP初版先把审核作为数据库状态流；引入LangGraph持久中断时按官方语义实现并测试幂等。 |

## 我们的取舍

1. **产品差异：** 跨境英文售后、市场/SKU/有效期政策、订单/物流只读工具、Vue3审核台。所有演示数据明确标为合成，不自动发送、退款或上架。
2. **安全差异：** 模型或客户消息提供的订单号只作查询键，`customer_id`由已验证工单在服务端提供；SQL同时匹配订单和客户。没有客户匹配即不返回订单。第三方示例存在可省略身份或只按订单号查询的路径，因此不直接复用其工具实现。
3. **工程差异：** 首个可运行版本先完成本地工单→只读查询→政策检索→待审草稿→人工审核的闭环；随后补Embedding检索、模型Tool Calling、LangGraph checkpoint和固定评测。每一阶段都标明实际实现，不把离线模板当大模型Agent。

参考项目仅在审阅期间保存于本地；本仓库不包含它们的源码。
