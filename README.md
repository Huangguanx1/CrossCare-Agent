# CrossCare Agent

跨境售后工单辅助系统。**当前为学习版 v0.2**：合成工单、只读订单/物流、带版本的政策词法检索、英文待审草稿与人工审核。默认使用 `offline_rules`；配置 OpenAI API 后，可使用 `openai_tool_calling` 让模型请求三个只读工具。**尚未实现 Embedding RAG、LangGraph 持久状态或完整效果评测。**

所有客户、订单、物流和政策均为自编合成演示数据。批准草稿只改变本地数据库状态，系统没有真实发送、退款、上架或店铺API权限。

## 运行

需要 Python 3.11+、Node.js 20+。PowerShell：

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.\backend\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

另开终端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。API文档：`http://127.0.0.1:8000/docs`。默认数据库在 `data/crosscare.sqlite3`，首次启动自动建库和生成合成演示数据；删除该数据库后重启可重置。只绑定本地回环地址，不应直接暴露到公网。

### 可选：模型工具调用

默认无需密钥，适合先学习业务链路。若要调用 OpenAI Responses API，在**启动后端的同一个 PowerShell 终端**设置模型和密钥，然后再启动后端：

```powershell
$env:CROSSCARE_MODEL = '<你的 Responses API 工具调用模型 ID>'
$env:OPENAI_API_KEY = Read-Host 'OpenAI API key' -MaskInput
```

`GET /api/health` 的 `draft_mode` 会显示当前模式。密钥只留在后端进程环境变量，不写入代码或浏览器；不要提交 `.env`。配置了其中一项却漏掉另一项时，生成接口会返回配置错误，不会偷偷切回离线草稿。模型请求会发送**合成工单内容**到 OpenAI API，可能产生费用；项目未在真实 API 密钥下做过在线验收。

从前端视角理解这一步，请看[第 1 课：模型工具调用](docs/lesson_01_tool_calling.md)。
如果想先弄清页面按钮背后的数据流，请按[第 2 课：从点击到草稿](docs/lesson_02_data_flow.md)操作，无需模型密钥。

## 验证

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
cd frontend
npm run build
```

测试覆盖订单归属、跨客户查询阻断、政策过滤、模型工具调用和审核状态。模型测试使用假响应，不调用外部 API。

## 项目边界与下一步

`GET /api/tickets`、`GET /api/tickets/{id}`、`POST /api/tickets/{id}/draft`、`POST /api/tickets/{id}/review`已经可用。当前词法检索提供离线基线，模型模式提供受控 Tool Calling；下一步将按[技术架构规划](docs/technical_architecture.md)加入 Embedding 混合检索、LangGraph 持久状态和固定评测。后端始终强制客户订单所有权，不授予模型写订单、退款或外发消息能力。模型可能产生事实错误，因此回复始终只是待审草稿。

设计参考见[GitHub项目审阅](docs/github_reference_review.md)。项目代码独立实现，未复制参考仓库源码。
