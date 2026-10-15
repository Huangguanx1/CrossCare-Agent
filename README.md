# CrossCare Agent

跨境售后工单辅助系统。**当前为第一个可运行切片（v0.1）**：合成工单、只读订单/物流、带版本的政策词法检索、英文待审草稿与人工审核。草稿由明确标记的 `offline_rules` 生成；**尚未接入大模型、Embedding或LangGraph，不能把当前版本称为已完成AI Agent。**

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

## 验证

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
cd frontend
npm run build
```

测试覆盖订单归属、跨客户查询阻断、政策过滤、审核只修改本地状态。

## 项目边界与下一步

`GET /api/tickets`、`GET /api/tickets/{id}`、`POST /api/tickets/{id}/draft`、`POST /api/tickets/{id}/review`已经可用。当前词法检索提供离线基线；下一步将按[技术架构规划](docs/technical_architecture.md)加入真实模型Tool Calling、Embedding混合检索、LangGraph持久状态和固定评测。届时仍由后端强制客户订单所有权，不授予模型写订单、退款或外发消息能力。

设计参考见[GitHub项目审阅](docs/github_reference_review.md)。项目代码独立实现，未复制参考仓库源码。
