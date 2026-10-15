# Excel RAG JSON Pipeline（Distributor-RAG）

一个面向 Excel / CSV 表格、文字型 PDF 和 `.docx` Word 文档的 RAG 知识库 MVP：上传文件 → 解析清洗 → 分块 → 向量化 → 混合检索 → LLM 带引用回答。

当前版本使用：

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + Pydantic v2 + openpyxl + PyMuPDF + python-docx + httpx |
| 前端 | React 19 + Vite + TypeScript + react-router-dom |
| 存储 | 本地 JSON 文件（无数据库、无向量数据库） |
| 模型 | OpenAI-compatible Embedding / Chat API，内置稳定 mock 兜底 |

设计原则：第一版不使用数据库、不使用向量数据库、不接入 Agent，所有状态落盘为本地 JSON，适合 MVP、学习、Demo 和小型表格知识库。

## 目录

- [1. 功能特性](#1-功能特性)
- [2. 目录结构](#2-目录结构)
- [3. 快速开始](#3-快速开始)
- [4. 使用指南](#4-使用指南)
- [5. 配置说明](#5-配置说明)
- [6. 架构与核心链路](#6-架构与核心链路)
- [7. 数据存储](#7-数据存储)
- [8. API 接口一览](#8-api-接口一览)
- [9. 当前限制](#9-当前限制)
- [10. 后续规划](#10-后续规划)

---

## 1. 功能特性

### 已实现

**文档入库**

- Excel（`.xlsx`）/ CSV / 文字型 PDF 上传，`.xls` / `.doc` 返回明确错误
- workbook、sheet、表头、行、列自动解析（自动定位表头行）
- PDF 按页提取文字块，常见单栏/双栏页面按版面阅读顺序重排后作为可检索的文档分区
- Word（`.docx`）按正文段落和表格行提取文字，作为可检索的文档分区
- 表格内容清洗（空值、换行、日期格式归一）
- 表格按行分块（chunk），保留行号与列信息
- mock embedding 与 OpenAI-compatible Embedding API 双支持
- 向量写入 `embeddings.json`，文档状态机：`uploaded → parsing → chunking → embedding → indexed / failed`

**检索与问答**

- 三种检索模式：`vector` / `keyword` / `hybrid`（默认混合模式）
- 每文档 chunk 数量限制，防止单文件霸榜
- 动态元数据驱动的 Query 理解 / 改写（意图、子查询、过滤条件、检索建议）
- 中文问题自动保留原问题并扩展英文检索表达，便于检索英文资料；扩展依赖真实 LLM，失败时回退原问题
- 多子查询分别检索、按 `chunk_id` 合并去重并排序
- Chat API + mock LLM / OpenAI-compatible Chat API 双支持
- SSE 流式输出
- 历史会话上下文（滑动窗口）参与 Query 理解与回答
- 用户原话与补全问题分离：`question` 用于展示和历史，`resolved_question` 用于检索、表格计算和核验；指代不明时先澄清
- 检索失败自动降级：Query 理解失败回退规则规划，无检索结果返回固定文案，问答链路不中断
- 文档式回答，下方按文件显示来源标签；点击可在右侧证据面板查看原文片段，窄屏使用抽屉（见 [回答展示说明](docs/answer-presentation.md)）

**工程配套**

- FastAPI 后端骨架 + React 类 GPT 工作台布局
- 上传页、文件库页、聊天页、提示词页、设置页
- Prompts 外置到 `prompts/` 目录，支持前端在线编辑、后端缓存即时失效
- conversations / messages 持久化，会话列表、切换和删除
- 文件列表、sheets、chunks、删除接口
- 测试 CSV 样例 + 一键 smoke test 脚本
- 前端构建产物可由后端直接托管（SPA fallback）

### 暂未实现

- 批量重建 embedding

---

## 2. 目录结构

```text
.venv/                        ← Python 虚拟环境（项目根目录）
backend/
  app/
    main.py                   ← FastAPI 入口，路由注册 + SPA 托管
    core/config.py            ← .env 环境变量加载
    routers/                  ← health / documents / chat / conversations / settings / prompts
    services/                 ← 业务逻辑（解析、清洗、分块、embedding、检索、LLM、会话等）
    schemas/                  ← Pydantic 请求/响应模型
    utils/                    ← id、时间、文件、相似度工具
  scripts/smoke_test.py       ← 一键冒烟测试
  scripts/p0_self_check.py    ← P0 关键链路自检
  data/                       ← 运行时 JSON 数据（自动初始化）
    knowledge/                ← 文档、分区、分块和向量
    conversations/            ← 会话和消息
    config/                   ← 运行时设置
  storage/original/           ← 上传的原始文件
  requirements.txt
  .env                        ← 环境变量（含 API key，已 gitignore）

frontend/
  src/
    pages/                    ← Chat / Upload / Documents / Prompts / Settings 五个页面
    components/               ← 聊天窗口、回答引用、上传、设置表单等组件
    api/                      ← 后端接口封装（含 SSE 流式解析）
    types/                    ← TS 类型定义
    styles/
  package.json

prompts/
  system/base.md              ← system message（角色与边界）
  query/planner.md            ← Query Planner 模板
  query/translator.md         ← 检索表达翻译模板
  rag/answer.md               ← 有检索结果时的回答模板
  rag/no_source.md            ← 无检索结果时的固定文案

samples/
  sales_sample.csv            ← 测试样例
```

---

## 3. 快速开始

### 3.1 环境要求

- Python 3.11
- Node.js + pnpm
- macOS 在终端（bash/zsh）中执行；Windows 在 CMD 或 PowerShell 中执行

### 3.2 启动后端

#### macOS 方式

进入项目根目录并激活虚拟环境：

```bash
cd /Users/stuhua/Desktop/Stuhua/Danmei/Distributor‌-RAG
source .venv/bin/activate
```

如果没有 `.venv`，先创建并安装依赖：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

启动后端：

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

验证健康检查：

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok"}
```

#### Windows 方式

进入项目根目录（把路径换成你的实际存放位置）并激活虚拟环境：

```powershell
cd C:\path\to\Distributor-RAG
.venv\Scripts\activate
```

> - CMD 用 `.venv\Scripts\activate.bat`，PowerShell 用 `.venv\Scripts\Activate.ps1`
> - PowerShell 若提示「禁止运行脚本」，先执行一次：`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

如果没有 `.venv`，先创建并安装依赖：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
```

启动后端：

```powershell
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

验证健康检查（Windows 10+ 自带 curl）：

```powershell
curl http://127.0.0.1:8000/api/health
# {"status":"ok"}
```

### 3.3 启动前端

#### macOS 方式

```bash
cd /Users/stuhua/Desktop/Stuhua/Danmei/Distributor‌-RAG/frontend
pnpm install
pnpm run dev --host 127.0.0.1 --port 5173
```

如果提示 `pnpm: command not found`，可以使用 Codex 自带的 pnpm：

```bash
/Users/stuhua/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pnpm install
/Users/stuhua/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pnpm run dev --host 127.0.0.1 --port 5173
```

如果还提示找不到 `node`：

```bash
PATH=/Users/stuhua/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH \
  /Users/stuhua/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pnpm run dev --host 127.0.0.1 --port 5173
```

#### Windows 方式

```powershell
cd C:\path\to\Distributor-RAG\frontend
pnpm install
pnpm run dev --host 127.0.0.1 --port 5173
```

如果提示 `pnpm 不是内部或外部命令`（或「无法将 pnpm 识别为 cmdlet」），先用 npm 安装 pnpm：

```powershell
npm install -g pnpm
```

打开前端：<http://127.0.0.1:5173/>

### 3.4 一键冒烟测试

项目自带测试样例 `samples/sales_sample.csv`，可用脚本快速验证上传、解析、embedding、检索、LLM 回答、messages 保存是否跑通（脚本会临时切到 mock 模式，结束后自动清理测试文档、会话并恢复原配置）。

macOS：

```bash
cd /Users/stuhua/Desktop/Stuhua/Danmei/Distributor‌-RAG
source .venv/bin/activate
cd backend
python scripts/smoke_test.py
```

Windows：

```powershell
cd C:\path\to\Distributor-RAG
.venv\Scripts\activate
cd backend
python scripts\smoke_test.py
```

正常输出：

```text
smoke test passed
```

---

## 4. 使用指南

### 4.1 上传文档

1. 启动后端与前端，打开前端页面。
2. 在「文件库」点击「上传」，多选 `.xlsx`、`.csv`、文字型 `.pdf` 或 `.docx` 文件，也可选择文件夹批量导入。
3. 检查清单后点击「开始上传」，查看文件传输和解析入库进度。
4. 在「文件库」点击文件右侧「查看」，打开文件详情弹窗，在「内容预览」分页查看解析内容，或切换「文件信息」查看来源、状态、时间等信息。

上传成功后，后端会写入 `documents.json` / `sheets.json` / `chunks.json` / `embeddings.json`，文档状态变为 `indexed`。

在文件库可直接勾选文件，或全选当前搜索结果；选中后在列表上方点击「删除所选」并确认，即可批量删除，也可「取消选择」。单个文件的删除入口位于行末「更多操作」菜单。改变搜索条件会清空勾选。删除会清理原文件和关联索引；部分失败时保留失败文件及原因，可再次删除重试。

文件详情弹窗的交互及代码结构见 [文件预览说明](docs/file-preview.md)。

### 4.2 聊天问答

先上传一个文件并确认状态为 `indexed`，然后：

1. 进入左侧「聊天」。
2. 输入与已上传文件相关的问题。
3. 中间展示流式回答，在回答卡片下方展开引用来源。
4. 左侧会话栏可切换、新建、删除历史会话。

如果知识库主要是英文资料，仍然可以只用中文提问。启用真实 LLM 后，Query Planner 会自动生成英文检索表达；最终回答仍遵循系统提示词使用中文。

也可以直接调用接口：

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "上海 甲公司 销售额是多少",
    "top_k": 5
  }'
```

返回示例：

```json
{
  "conversation_id": "conv_xxx",
  "answer": "根据已检索知识库资料，相关记录为：行 2：月份=1月；地区=上海；客户=甲公司；销售额=120000。",
  "sources": [
    {
      "chunk_id": "chunk_xxx",
      "file_name": "sales.csv",
      "sheet_name": "sales",
      "row_start": 2,
      "row_end": 4,
      "score": 0.56,
      "content": "文件：sales.csv\nSheet：sales\n行 2：..."
    }
  ]
}
```

Chat API 会同时把对话写入 `conversations.json` 与 `messages.json`。

### 4.3 页面一览

| 页面 | 路径 | 功能 |
|---|---|---|
| 聊天 | `/` | 流式问答、引用来源、历史会话管理 |
| 上传 | `/upload` | 多文件及文件夹上传，查看处理进度 |
| 文件库 | `/documents` | 文件列表、详情弹窗与解析内容分页、批量删除 |
| 提示词 | `/prompts` | 在线查看与编辑 `prompts/` 下的运行时 Prompt |
| 设置 | `/settings` | 模型配置、检索参数、API key 配置状态 |

---

## 5. 配置说明

配置分两层：**环境变量**（`backend/.env`，存敏感信息如 API key）和 **运行时设置**（`backend/data/config/settings.json`，可从前端设置页修改，不存 API key）。启动时自动初始化默认值。

### 5.1 运行时设置 `backend/data/config/settings.json`

```json
{
  "embedding": {
    "provider": "openai-compatible",
    "base_url": "https://api.example.com/v1",
    "model": "text-embedding-3-small",
    "mock": true,
    "normalize": true
  },
  "llm": {
    "provider": "openai-compatible",
    "base_url": "https://api.example.com/v1",
    "model": "gpt-4o-mini",
    "mock": true
  },
  "retrieval": {
    "top_k": 10,
    "chunk_size": 1200,
    "overlap": 100,
    "score_threshold": 0.2,
    "search_mode": "hybrid",
    "max_chunks_per_doc": 3,
    "full_scan_max_chunks": 200
  },
  "conversation": {
    "context_window": 10
  }
}
```

| 配置块 | 字段 | 说明 |
|---|---|---|
| `embedding` | `mock` | `true` 用本地 mock 向量（无需 API key，同文本恒定向量）；`false` 走真实 API |
| | `normalize` | 是否将向量归一化到单位长度 |
| `llm` | `mock` | `true` 用本地 mock 回答（基于检索 sources 拼接）；`false` 走真实 API；中文问题的英文检索扩展也依赖真实 LLM |
| `retrieval` | `search_mode` | `hybrid`（默认）/ `vector` / `keyword`，见 [6.4 检索模式](#64-检索模式) |
| | `top_k` | 默认返回条数 |
| | `score_threshold` | 分数门槛，低于该值的结果被过滤 |
| | `max_chunks_per_doc` | 单个文档最多贡献的 chunk 数，`0` 表示不限制 |
| | `full_scan_max_chunks` | 统计类问题允许进入模型上下文的最大全量 chunk 数，超过后明确提示资料不足 |
| `conversation` | `context_window` | 参与上下文理解的历史消息条数（0~50） |

### 5.2 接入真实 Embedding API

1. 编辑 `backend/.env`：

   ```env
   EMBEDDING_BASE_URL=https://你的接口地址/v1
   EMBEDDING_API_KEY=你的_api_key
   EMBEDDING_MODEL=text-embedding-3-small
   EMBEDDING_MOCK=false
   ```

2. 把 `settings.json` 中 `embedding.mock` 改为 `false`（或在前端设置页修改）。
3. 重启后端。

接口要求兼容 OpenAI embeddings 格式：

```http
POST /v1/embeddings
```

```json
{
  "model": "text-embedding-3-small",
  "input": ["文本1", "文本2"]
}
```

返回中读取 `data[*].embedding`。已适配 DashScope（逐条请求）。

### 5.3 接入真实 LLM API

1. 编辑 `backend/.env`：

   ```env
   LLM_BASE_URL=https://你的接口地址/v1
   LLM_API_KEY=你的_api_key
   LLM_MODEL=gpt-4o-mini
   LLM_MOCK=false
   ```

2. 把 `settings.json` 中 `llm.mock` 改为 `false`。
3. 重启后端。

接口要求兼容 OpenAI chat completions 格式（`POST /v1/chat/completions`），流式模式使用 SSE `stream: true`。

### 5.4 环境变量参考

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_NAME` | `Excel RAG JSON Pipeline` | 应用名 |
| `APP_ENV` | `development` | 运行环境 |
| `BACKEND_HOST` / `BACKEND_PORT` | `0.0.0.0` / `8000` | 后端监听地址 |
| `DATA_DIR` | `./data` | JSON 数据目录 |
| `STORAGE_DIR` | `./storage/original` | 原始文件存储目录 |
| `MAX_UPLOAD_MB` | `30` | 上传大小上限 |
| `FULL_SCAN_MAX_CHUNKS` | `200` | 统计类全量检索的最大 chunk 数 |
| `DEFAULT_CHUNK_SIZE` | `1200` | 分块字符数上限 |
| `DEFAULT_OVERLAP` | `100` | 分块重叠（预留） |
| `DEFAULT_TOP_K` | `5` | 默认检索条数 |
| `DEFAULT_SCORE_THRESHOLD` | `0.2` | 默认分数门槛 |
| `EMBEDDING_PROVIDER` | `openai-compatible` | Embedding 提供方 |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | 见上文 | Embedding 接口地址与模型 |
| `EMBEDDING_API_KEY` | 空 | **`EMBEDDING_MOCK=false` 时必填** |
| `EMBEDDING_MOCK` | `true` | 是否使用 mock 向量 |
| `EMBEDDING_DIM` | `384` | mock 向量维度 |
| `LLM_PROVIDER` | `openai-compatible` | LLM 提供方 |
| `LLM_BASE_URL` / `LLM_MODEL` | 见上文 | LLM 接口地址与模型 |
| `LLM_API_KEY` | 空 | **`LLM_MOCK=false` 时必填** |
| `LLM_MOCK` | `true` | 是否使用 mock 回答 |

---

## 6. 架构与核心链路

### 6.1 入库管线

`backend/app/services/document_pipeline.py`

```text
上传文件
  → 原始文件落盘 storage/original/
  → 解析（xlsx: openpyxl / csv: 内置 csv / pdf: PyMuPDF 按文字块和坐标恢复常见版面顺序 / docx: python-docx 提取段落和表格）
  → 清洗（空值、换行、日期归一）
  → 生成 sheet 记录（表头、行列数、内容类型）
  → 分块（表格按行、文字文档按内容块，默认 1200 字符/块）
  → 批量生成 embedding
  → 写入 documents / sheets / chunks / embeddings 四个 JSON
  → 文档状态 indexed
```

任一步骤失败会把文档标记为 `failed` 并记录 `error_message`。

### 6.2 问答管线

`backend/app/services/chat_service.py`

```text
用户问题
  → 构建历史会话上下文（滑动窗口）
  → 读取知识库动态元数据（文件名、Sheet 名、表头字段）
  → Query Planner：保留用户原话，输出补全问题 / 澄清状态 / 意图 / 子查询 / 中英文检索表达 / 过滤条件 / top_k
  → 指代或省略条件无法确认时返回澄清问题，不执行检索、统计或答案生成
  → 统计类问题优先全量扫描并做确定性计算；无法安全计算时进行受限全量检索
  → 普通问题多路检索：每个子查询分别检索，按分数合并去重和排序
  → 拼 Prompt（system + answer 模板 + 检索资料 + 问题）
  → LLM 流式生成回答，前端同步展示引用来源
```

流式接口在证据门禁通过后，将模型生成的每个文本片段通过 `delta` 事件即时发送给前端。生成中的正文是尚未校验的草稿；生成结束后执行答案校验，通过 `done.answer` 返回最终答案，前端替换草稿，历史记录也只保存最终答案。若校验发现无法核验的信息，最终正文会替换为提示文案。确定性计算、证据不足和问题澄清分支直接返回完整结果。

降级策略：Query 理解失败或 LLM 返回非 JSON 时，独立问题回退到基于原始问题的规则规划与检索；可识别的依赖上下文追问（如“那2月份呢？”、“它的销售额呢？”）返回澄清问题，避免丢失对象或时间条件。完全没有检索结果时直接返回固定文案「知识库中未找到明确依据。」。

聊天 API 仍只需提交 `question`，不需要客户端组装完整提示词。用户消息与会话标题保留原话；后台把原话、补全问题、历史、查询规划和知识库证据分别组装给模型。普通及 SSE 响应的 `quality.query_understanding` 会记录 `original_question`、`resolved_question`、`retrieval_queries`、`needs_clarification` 和 `clarification_question`，并随助手消息保存，便于检查问题被如何理解。历史和补全问题都不能代替知识库事实证据。

每个聊天会话可独立选择检索文档，支持全部文档或指定多个文档。选择随会话保存；范围切换后保留历史显示，模型上下文从新范围重新累计。实现、接口及边界说明见 [会话文档范围](docs/conversation-document-scope.md)。

### 6.3 Query Planner

相关文件：

- `backend/app/services/knowledge_metadata_service.py`：从本地 JSON 知识库读取动态元数据
- `backend/app/services/query_understanding_service.py`：调用 LLM 输出结构化 Query Plan，并提供规则兜底
- `prompts/query/planner.md`：约束 LLM 只输出结构化 Query Plan，不直接回答问题
- `prompts/query/translator.md`：将检索表达逐条翻译成目标语言，保持输入输出数量一致
- `prompts/rag/answer.md`：最终回答 Prompt，接收 Query Plan 与检索上下文

Query Plan 结构（LLM 输出的 `filters` 会经过白名单校验，只接受元数据中真实存在的值）：

```json
{
  "resolved_question": "用户原话，或结合明确历史补全后的完整问题",
  "needs_clarification": false,
  "clarification_question": "",
  "intent": "lookup | summary | comparison | ranking | trend | unknown",
  "sub_queries": ["可直接检索的子问题"],
  "retrieval_queries": ["原始问题或子问题", "英文检索表达（如需要）"],
  "filters": {
    "sheet_name": null
  },
  "retrieval": {
    "top_k": null,
    "need_full_scan": false
  }
}
```

这一步不写死业务字段：用户上传新 Excel / CSV / PDF / Word 后，只要文档进入 `indexed` 状态，Query Planner 会自动从最新的 `documents.json`、`sheets.json`、`chunks.json` 中读取可用字段和文档分区信息。检索条数还会按意图动态调整（如 ranking / summary 多取几条，lookup 少取）。

例如，上一轮问“A经销商1月份的销售额合计是多少？”，本轮问“那2月份呢？”，Planner 可输出 `resolved_question: "A经销商2月份的销售额合计是多少？"`。新时间覆盖旧时间，用户历史仍保存“那2月份呢？”。追问没有可用历史或历史存在多个可能指代对象时，应提出澄清；独立完整的问题不需要历史。规划结果缺少新字段时，独立问题保持兼容；上下文补全依赖规划模型，模型不可用时不会宣称已解析追问。

### 6.4 检索模式

`backend/app/services/retrieval_service.py`，由 `settings.json` 的 `retrieval.search_mode` 控制：

| 模式 | 打分方式 |
|---|---|
| `vector` | 问题向量与 chunk 向量的余弦相似度 |
| `keyword` | 问题去除疑问词后生成 n-gram 词项，按覆盖率 + 长词加成打分 |
| `hybrid`（默认） | 向量分数与关键词分数取最大值 |

通用行为：低于 `score_threshold` 的候选过滤；`max_chunks_per_doc` 限制单文档贡献；多子查询结果按 `chunk_id` 去重合并后再统一排序截断。`full_scan` 会保留完整候选集，不应用 Top K 和单文档截断。

### 6.5 Prompt 管理

- 运行时 Prompt 和固定回复模板集中在 `prompts/` 目录，后端只开放登记的五个文件
- Planner 使用 `{conversation_context}`、`{metadata}`、`{question}`；Translator 使用 `{target_language}`、`{queries}`；Answer 使用 `{conversation_context}`、`{query_plan}`、`{context}`、`{question}`
- 支持通过前端「提示词」页或 `PUT /api/prompts/{path}` 在线修改，保存后后端 Prompt 缓存即时失效
- `prompts/README.md` 只用于说明，不属于运行时 Prompt；使用说明、测试用例和版本历史不要混入运行时文件

---

## 7. 数据存储

所有运行时 JSON 数据位于 `backend/data/`，按用途分为三类，启动时自动初始化；自定义 `DATA_DIR` 时也使用相同的子目录结构：

| 文件 | 内容 |
|---|---|
| `knowledge/documents.json` | 上传文件基本信息（状态、元数据、行列统计） |
| `knowledge/sheets.json` | sheet 名、表头、行列数量等元信息 |
| `knowledge/chunks.json` | 文档 chunk（含文件名、分区名、行号、列名和值） |
| `knowledge/embeddings.json` | 每个 chunk 对应的向量及模型信息 |
| `config/settings.json` | 模型配置与检索参数（不保存 API key） |
| `conversations/conversations.json` | 对话列表 |
| `conversations/messages.json` | 用户与助手消息，及每条助手消息对应的 sources |

升级已有数据目录前，先停止后端并备份七个 JSON。首次启动会将旧根目录中的已知文件逐个迁入对应子目录，保留原始字节，不重新生成向量。若旧位置与新位置同时存在同名文件，启动会报错并停止迁移，不覆盖任何一份数据，也不初始化默认值；请备份并核对冲突文件后再启动。迁移中断后可以重新启动继续处理剩余旧文件；若出现同名冲突，则按上述方式处理。业务代码继续使用原有逻辑文件名，由存储层统一映射路径。

写入采用临时文件 + 原子替换（`os.replace`），并以线程锁保护单次写入。

---

## 8. API 接口一览

后端默认地址 `http://127.0.0.1:8000`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| POST | `/api/documents/upload` | 上传并解析（form-data：`file`、`file_name`、可选 `source_relative_path`） |
| GET | `/api/documents` | 文档列表（支持 `keyword` / `status` 过滤） |
| GET | `/api/documents/{id}` | 文档详情 |
| GET | `/api/documents/{id}/sheets` | 文档的 sheet 列表 |
| GET | `/api/documents/{id}/chunks` | chunk 分页列表（`page`、`page_size`） |
| DELETE | `/api/documents/{id}` | 删除文档及其 sheets / chunks / embeddings |
| POST | `/api/documents/{id}/reindex` | 重建索引 |
| GET / PUT | `/api/settings` | 读取 / 更新运行时设置（`secrets` 字段单独处理 API key） |
| GET | `/api/prompts` | 列出已登记的运行时 Prompt 和固定回复模板 |
| GET / PUT | `/api/prompts/{path}` | 读取 / 更新已登记的 Prompt 文件 |
| GET | `/api/conversations` | 会话列表 |
| POST | `/api/conversations` | 新建会话 |
| GET | `/api/conversations/{id}/messages` | 会话消息列表 |
| DELETE | `/api/conversations/{id}` | 删除会话及其消息 |
| POST | `/api/chat` | 问答（一次性返回） |
| POST | `/api/chat/stream` | 问答（SSE 流式，事件：`sources` / `delta` / `done` / `error`） |

---

## 9. 当前限制

- 当前版本适合 MVP、学习、Demo、小型表格知识库
- JSON 存储不适合大量文档或高并发写入（读-改-写操作未加跨请求锁）
- `.xlsx`、`.csv`、文字型 `.pdf` 和 `.docx` 已支持；`.xls` / `.doc` 会返回明确错误；扫描版/纯图片 PDF、图片 OCR 暂不支持
- PDF 文字提取依赖文件内嵌的文本层；如果 PDF 没有可提取文字，上传会失败并提示原因。常见双栏会按文字块坐标重排，复杂侧栏、脚注和图文混排仍可能需要人工确认
- Word 当前读取正文段落和表格，并识别标准分栏配置；文本框、浮动对象、图片中的文字和旧版二进制 `.doc` 暂不保证
- 不做复杂 Excel 公式计算，只读取单元格当前值
- 合并单元格、复杂多级表头只做基础兼容（以第一个非空行作为表头）
- mock LLM 只适合本地链路测试，真实效果需要接入真实 LLM API

## 10. 后续规划

- 实现重新入库 / 重建 embedding（`/reindex`）
- 将 `embeddings.json + cosine similarity` 迁移到 Qdrant / Chroma / Milvus
- 完善真实模型、SSE 异常和前端 E2E 测试覆盖
- 支持更复杂的表头识别（多级表头、合并单元格）
- 支持多轮对话记忆（当前仅以文本窗口形式参与 Query 理解）
