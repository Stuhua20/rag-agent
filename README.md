# Distributor-RAG

面向 Excel、CSV、文字型 PDF 和 Word（`.docx`）的轻量 RAG 知识库。支持文件上传、混合检索、带来源引用的流式问答，数据以本地 JSON 保存，适合学习、演示和小型知识库。

## 主要功能

- **文档管理**：多文件及文件夹批量上传、解析进度、内容预览、批量删除。
- **检索问答**：向量 / 关键词 / 混合检索，多轮上下文理解、中文提问扩展英文检索表达（需真实 LLM）。
- **知识库问答 Agent**：LangGraph编排、任务证据覆盖检查、按需补查及可折叠的执行进度。
- **会话与引用**：历史会话、新建与重命名、按会话选择检索文档、点击来源查看原文证据。
- **模型与提示词**：兼容 OpenAI 格式的 Embedding / Chat API，提供本地 mock 模式，支持页面配置和提示词编辑。

技术栈：FastAPI + Pydantic v2 + LangGraph；React 19 + TypeScript + Vite；本地 JSON 保存业务数据，SQLite 保存 Agent 运行状态，无需外部数据库或向量数据库。

## 快速开始

准备 Python 3.11、Node.js 和 pnpm，在项目根目录运行：

**macOS / Linux**

```bash
bash start.sh
```

**Windows（CMD / PowerShell）**

```powershell
.\start.bat
```

脚本会创建 Python 虚拟环境、安装依赖，并在缺少 `backend/.env` 时从模板创建，然后启动前后端。首次运行需要联网安装依赖。

- 前端：[http://127.0.0.1:5173](http://127.0.0.1:5173)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

macOS / Linux 按 `Ctrl+C` 同时停止前后端；Windows 分别关闭两个服务窗口。

<details>
<summary>手动启动（分别在两个终端运行）</summary>

后端（macOS / Linux，从项目根目录执行）：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env  # 仅首次创建，已有配置时跳过
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows 使用 `python -m venv .venv`，PowerShell 激活命令为 `.\.venv\Scripts\Activate.ps1`，CMD 为 `.venv\Scripts\activate.bat`；复制配置使用 `copy backend\.env.example backend\.env`。

前端（从项目根目录执行）：

```bash
cd frontend
pnpm install
pnpm run dev --host 127.0.0.1 --port 5173
```

</details>

## 使用方式

1. 打开「文件库」，上传 `.xlsx`、`.csv`、文字型 `.pdf` 或 `.docx`，等待状态变为 `indexed`。
2. 进入「聊天」，选择全部文档或指定文档后提问；可点击回答下方的来源查看证据。
3. 在「设置」调整模型和检索参数，在「提示词」编辑运行时模板。

可先上传 [销售样例](samples/sales_sample.csv)，提问“上海甲公司的销售额是多少？”。默认 mock 模式无需 API key，用于验证流程；实际问答效果需配置真实模型。

当前聊天仅使用知识库问答Agent。表格分析Agent及其自动找表、聊天附件、分组/占比/环比和原始行分析面板已移除；文件库仍可上传Excel/CSV进行文档检索；不再提供表格数值计算工具。

## 配置模型

推荐在「设置」页分别填写 Embedding 和 LLM 的接口地址、模型名称、API key，并关闭各自的 mock 开关。

| 配置位置 | 用途 |
|---|---|
| `backend/.env` | API key、数据目录、上传大小上限等环境配置，完整说明见 [配置模板](backend/.env.example) |
| `backend/data/config/settings.json` | 模型地址、模型名、mock 开关、检索参数和历史窗口，由设置页保存 |

API key 单独写入 `.env`；已有运行时设置会优先于对应环境默认值，手动修改 `.env` 后需重启后端。切换 Embedding 模型或从 mock 改为真实向量后，需删除并重新上传相关文档以生成匹配的索引。

## 项目结构

```text
backend/
  app/                # API 路由、文档解析、检索与问答服务
  scripts/            # 冒烟测试与关键链路自检
  tests/              # 后端测试
  data/               # knowledge/、conversations/、config/ 下的 JSON 数据
  storage/original/   # 上传的原始文件
frontend/src/         # 聊天、文件库、上传、提示词、设置页面
prompts/              # 系统提示词、查询规划、翻译和回答模板
docs/                 # 专题设计与交互说明
samples/              # 测试样例
start.sh / start.bat   # 启动脚本
```

核心流程：上传 → 解析清洗 → 分块 → 向量化 → 混合检索 → 生成并校验回答 → 展示引用。

Agent核心代码按能力放在独立包中：

```text
backend/app/agents/
  knowledge_qa/       # 知识库问答：runtime、graph、nodes、state、tools、evidence_coverage
  budget.py           # 共享预算控制
  contracts.py        # 任务、工具及证据的数据契约
```

知识库问答入口为 `knowledge_qa/runtime.py`，编排见 `graph.py`，节点逻辑见 `nodes.py`。运行记录、会话占用及底层数据服务位于 `backend/app/services/`。

默认 `CHAT_RUNTIME=langgraph`：理解问题 → 检索 → 证据检查 → 按需补查 → 回答与校验。补查继承本轮固定文档范围；没有足够证据时说明缺口。设置 `CHAT_RUNTIME=legacy` 并重启可回退原问答链路。

Agent 配置在 `backend/.env`：`AGENT_MAX_RETRIEVAL_ROUNDS=3`（含首轮，最大为 3）、`AGENT_MAX_SECONDS=180`、`AGENT_MAX_LLM_CALLS=8`、`AGENT_MAX_TOOL_CALLS=8`。模型及工具调用共用本轮预算。运行库自动保存在 DATA_DIR 下的 `agent/`，无需手动建库；checkpoint 初期用于记录与排障，尚无对外恢复接口。

升级旧版数据前请停止后端并备份 `backend/data/`。首次启动会将旧根目录中的 JSON 自动迁入对应子目录；新旧位置存在同名文件时会报错，需核对并解决冲突后再启动。

## 验证

激活项目虚拟环境后，在项目根目录运行：

```bash
python backend/scripts/smoke_test.py
```

成功输出 `smoke test passed`。脚本临时使用 mock 模式，验证上传、索引、问答和消息保存，结束后清理测试数据并恢复设置。

安装 `backend/requirements-dev.txt` 后，可在根目录执行 `PYTHONPATH=backend python -m pytest backend/tests -q`。原有测试显式验证 legacy 兼容契约，新图套件显式启用 LangGraph；其中包含 17 条问答合成验收样例。同时验证旧表格会话继续知识问答，以及退役接口和输入不再启用。前端在其目录执行 `pnpm run test:chat`、`pnpm run test:upload` 和 `pnpm run build`。

## 当前限制

- JSON 存储适合小规模使用，不适合大量文档和高并发写入。
- Agent 首期支持单后端进程，同一会话一次只执行一个运行；JSON 消息与 SQLite 没有跨存储事务，网络重试不保证自动去重。
- mock 用于流程验证，复杂任务的真实语义理解、冲突检查和答案质量需配置真实模型后评估。
- 不支持 `.xls`、`.doc`、扫描版 PDF 和图片 OCR；复杂 PDF 版面、Word 浮动对象及多级表头的解析可能不完整。
- Excel 读取已有单元格值，不执行公式计算。
- 重建索引接口 `/api/documents/{id}/reindex` 尚未实现，当前返回 `501`。

## 相关文档

- [批量上传](docs/batch-upload.md) · [文件预览](docs/file-preview.md)
- [聊天体验](docs/chat-experience.md) · [流式输出](docs/chat-streaming.md) · [回答与引用](docs/answer-presentation.md)
- [会话文档范围](docs/conversation-document-scope.md) · [会话重命名](docs/chat-renaming.md)
- [提示词说明](prompts/README.md) · [提示词编写规范](docs/prompt-guidelines.md)
- [表格分析Agent移除记录](开发文档/表格分析Agent移除记录-2026-10-19.md)
