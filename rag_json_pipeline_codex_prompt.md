# Codex 开发提示词：Excel JSON RAG Pipeline MVP

下面这份提示词用于让 Codex 从 0 开始实现一个 **面向 Excel 文件的 RAG Pipeline MVP**。

项目第一版只聚焦 Excel / 表格类知识库：

- 优先支持 `.xlsx`
- 可选支持 `.xls`
- 支持 `.csv`
- 暂不支持 PDF / DOCX / 图片 OCR
- 不使用向量数据库
- 不使用数据库
- 所有数据保存到本地 JSON 文件
- Embedding 和 LLM 通过 OpenAI-compatible API 调用
- 必须提供 mock embedding 和 mock LLM，保证没有 API key 也能本地跑通
- 前端做成类似 ChatGPT / GPT 网站的聊天式界面

核心目标：先把 Excel 表格解析、结构化 chunk、JSON 向量检索、问答引用来源这条链路做稳定。

---

## 一、项目目标

做一个企业 Excel 知识库 RAG 系统，支持：

1. 用户上传 Excel / CSV 文件。
2. 后端解析 workbook、sheet、表头、行列数据。
3. 对表格内容进行清洗和结构化。
4. 把表格转换成适合检索的 chunks。
5. 调用 Embedding API，把每个 chunk 转成向量。
6. 将文档、sheet、chunk、embedding、会话、消息、设置保存到本地 JSON 文件。
7. 用户在前端聊天页面提问。
8. 后端调用 Embedding API，把用户问题转成向量。
9. 后端从本地 JSON 向量数据中计算相似度，找出 top_k 个相关 chunk。
10. 后端把相关 Excel 来源拼接进 prompt。
11. 后端调用 LLM API 生成回答。
12. 前端展示回答，并在右侧展示引用来源，包括文件名、sheet 名、行号、列名和 chunk 内容。

核心链路：

```text
上传 Excel/CSV
→ 解析 workbook/sheet/行列
→ 表格清洗
→ 表头识别
→ 行级/表格级 chunk
→ Embedding API 生成向量
→ 保存到 JSON
→ 用户提问
→ 问题向量化
→ JSON 相似度检索
→ 取 top_k chunks
→ 拼接 Prompt
→ LLM API 生成回答
→ 返回答案 + Excel 来源引用
```

---

## 二、技术栈要求

### 前端

使用：

- React
- TypeScript
- Vite
- CSS Modules 或普通 CSS
- 不强制使用 UI 框架
- 页面风格参考 ChatGPT / GPT 网站

前端页面包括：

1. 聊天问答页 `ChatPage`
2. Excel 上传页 `UploadPage`
3. 文件库页面 `DocumentsPage`
4. 系统设置页 `SettingsPage`

整体布局：

```text
┌─────────────────────────────────────────────────────┐
│ 顶部栏：系统名称 / 当前模型 / 设置入口                │
├───────────────┬───────────────────────┬─────────────┤
│ 左侧 Sidebar  │ 中间 Chat Window       │ 右侧 Sources │
│               │                       │             │
│ + 新建对话     │ 用户问题               │ 文件名        │
│ 会话列表       │ AI 回答                │ Sheet 名      │
│ 文件上传       │ 底部输入框             │ 行号 / 列名    │
│ 文件库         │                       │ chunk 内容    │
│ 设置           │                       │             │
└───────────────┴───────────────────────┴─────────────┘
```

### 后端

使用：

- Python
- FastAPI
- Uvicorn
- Pydantic
- pandas
- openpyxl
- xlrd，可选，用于 `.xls`
- httpx 或 requests
- numpy

不要使用：

- Qdrant / Chroma / Milvus / FAISS
- PostgreSQL / MySQL / MongoDB / SQLite
- LangChain，第一版尽量自己实现清晰的 Pipeline
- Agent / Agent Loop / 多智能体

后端需要按 `router / service / schema / utils` 分层，不要把所有逻辑写进 `main.py`。

---

## 三、项目目录结构

请按下面结构创建项目：

```text
excel-rag-json-pipeline/
  README.md
  .gitignore

  backend/
    app/
      main.py

      core/
        config.py

      routers/
        health.py
        documents.py
        chat.py
        conversations.py
        settings.py

      services/
        excel_parser_service.py
        csv_parser_service.py
        table_cleaner_service.py
        table_chunker_service.py
        embedding_service.py
        json_store_service.py
        retrieval_service.py
        llm_service.py
        document_pipeline.py
        chat_service.py

      schemas/
        document.py
        chat.py
        conversation.py
        settings.py

      utils/
        file_utils.py
        id_utils.py
        time_utils.py
        similarity.py

    data/
      documents.json
      sheets.json
      chunks.json
      embeddings.json
      conversations.json
      messages.json
      settings.json

    storage/
      original/

    requirements.txt
    .env.example

  frontend/
    index.html
    package.json
    tsconfig.json
    vite.config.ts

    src/
      main.tsx
      App.tsx

      pages/
        ChatPage.tsx
        UploadPage.tsx
        DocumentsPage.tsx
        SettingsPage.tsx

      components/
        Sidebar.tsx
        TopBar.tsx
        ChatWindow.tsx
        MessageList.tsx
        MessageInput.tsx
        SourcePanel.tsx
        FileUploader.tsx
        DocumentTable.tsx
        SheetPreview.tsx
        SettingsForm.tsx

      api/
        client.ts
        chat.ts
        documents.ts
        conversations.ts
        settings.ts

      types/
        chat.ts
        document.ts
        conversation.ts
        settings.ts

      styles/
        global.css
        layout.css
```

---

## 四、后端环境变量

提供 `backend/.env.example`：

```env
APP_NAME=Excel RAG JSON Pipeline
APP_ENV=development
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

DATA_DIR=./data
STORAGE_DIR=./storage/original
MAX_UPLOAD_MB=30

EMBEDDING_PROVIDER=openai-compatible
EMBEDDING_BASE_URL=https://api.example.com/v1
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_MOCK=true
EMBEDDING_DIM=384

LLM_PROVIDER=openai-compatible
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=your_llm_api_key
LLM_MODEL=gpt-4o-mini
LLM_MOCK=true

DEFAULT_TOP_K=5
DEFAULT_CHUNK_SIZE=1200
DEFAULT_OVERLAP=100
DEFAULT_SCORE_THRESHOLD=0.2
DEFAULT_PERMISSION_LEVEL=1
```

要求：

1. `EMBEDDING_MOCK=true` 时使用稳定 mock embedding，同一文本每次生成相同向量。
2. `LLM_MOCK=true` 时使用 mock answer，方便本地跑通。
3. 真实 API 部分要封装好，但没有 key 不影响项目启动。
4. API key 只从 `.env` 读取，不写入 `settings.json`，也不暴露给前端。

---

## 五、JSON 数据结构设计

所有 JSON 文件放在：

```text
backend/data/
```

后端启动时自动创建缺失文件。

### 1. documents.json

保存上传文件基本信息：

```json
[
  {
    "id": "doc_001",
    "file_name": "sales_2026.xlsx",
    "original_name": "销售数据2026.xlsx",
    "file_type": "xlsx",
    "doc_type": "销售报表",
    "department": "销售部",
    "permission_level": 1,
    "status": "indexed",
    "storage_path": "storage/original/doc_001.xlsx",
    "sheet_count": 3,
    "chunk_count": 42,
    "row_count": 1200,
    "column_count": 18,
    "error_message": null,
    "created_at": "2026-06-25T10:00:00",
    "updated_at": "2026-06-25T10:05:00"
  }
]
```

文档状态：

```text
uploaded
parsing
parsed
chunking
embedding
indexed
failed
```

### 2. sheets.json

保存 Excel sheet 元信息和表头信息：

```json
[
  {
    "id": "sheet_001",
    "document_id": "doc_001",
    "sheet_name": "华东区销售",
    "sheet_index": 1,
    "header_row": 1,
    "headers": ["月份", "地区", "客户", "产品", "销售额", "负责人"],
    "row_count": 520,
    "column_count": 6,
    "created_at": "2026-06-25T10:02:00"
  }
]
```

### 3. chunks.json

保存适合检索的表格 chunk。

第一版推荐以“行级 chunk + 小批量行 chunk”为主：

- 每一行转换成一段可读文本。
- 多行上下文可以合并成一个 chunk，但要保留起止行号。
- chunk 内容必须包含列名，避免 LLM 看不懂单元格值的含义。

```json
[
  {
    "id": "chunk_001",
    "document_id": "doc_001",
    "sheet_id": "sheet_001",
    "chunk_index": 1,
    "chunk_type": "table_rows",
    "sheet_name": "华东区销售",
    "row_start": 2,
    "row_end": 6,
    "columns": ["月份", "地区", "客户", "产品", "销售额", "负责人"],
    "title": "华东区销售 第2-6行",
    "content": "文件：销售数据2026.xlsx\nSheet：华东区销售\n行 2：月份=1月；地区=上海；客户=甲公司；产品=A产品；销售额=120000；负责人=张三\n行 3：...",
    "token_count": 860,
    "metadata": {
      "file_name": "sales_2026.xlsx",
      "doc_type": "销售报表",
      "department": "销售部",
      "permission_level": 1,
      "sheet_name": "华东区销售",
      "row_start": 2,
      "row_end": 6
    },
    "created_at": "2026-06-25T10:03:00"
  }
]
```

### 4. embeddings.json

保存 chunk 向量：

```json
[
  {
    "chunk_id": "chunk_001",
    "document_id": "doc_001",
    "sheet_id": "sheet_001",
    "embedding_model": "text-embedding-3-small",
    "vector": [0.012, -0.084, 0.153],
    "metadata": {
      "file_name": "sales_2026.xlsx",
      "doc_type": "销售报表",
      "department": "销售部",
      "permission_level": 1,
      "sheet_name": "华东区销售",
      "row_start": 2,
      "row_end": 6
    },
    "created_at": "2026-06-25T10:04:00"
  }
]
```

### 5. conversations.json

```json
[
  {
    "id": "conv_001",
    "title": "华东区销售查询",
    "created_at": "2026-06-25T11:00:00",
    "updated_at": "2026-06-25T11:05:00"
  }
]
```

### 6. messages.json

```json
[
  {
    "id": "msg_001",
    "conversation_id": "conv_001",
    "role": "user",
    "content": "华东区 1 月销售额最高的客户是谁？",
    "sources": [],
    "created_at": "2026-06-25T11:00:00"
  },
  {
    "id": "msg_002",
    "conversation_id": "conv_001",
    "role": "assistant",
    "content": "根据销售数据，华东区 1 月销售额最高的客户是甲公司。",
    "sources": [
      {
        "chunk_id": "chunk_001",
        "file_name": "sales_2026.xlsx",
        "sheet_name": "华东区销售",
        "row_start": 2,
        "row_end": 6,
        "score": 0.89,
        "content": "行 2：月份=1月；地区=上海；客户=甲公司；产品=A产品；销售额=120000；负责人=张三"
      }
    ],
    "created_at": "2026-06-25T11:01:00"
  }
]
```

### 7. settings.json

```json
{
  "embedding": {
    "provider": "openai-compatible",
    "base_url": "https://api.example.com/v1",
    "model": "text-embedding-3-small",
    "mock": true
  },
  "llm": {
    "provider": "openai-compatible",
    "base_url": "https://api.example.com/v1",
    "model": "gpt-4o-mini",
    "mock": true
  },
  "retrieval": {
    "top_k": 5,
    "chunk_size": 1200,
    "overlap": 100,
    "score_threshold": 0.2
  }
}
```

---

## 六、后端服务设计

### 1. json_store_service.py

实现 JSON 文件读写服务。

要求：

1. 自动初始化 JSON 文件。
2. 支持读取列表型和对象型 JSON。
3. 支持按 id 查询。
4. 支持新增、更新、删除。
5. 写文件时使用临时文件再 rename，避免数据损坏。
6. 使用进程内锁保护写入，降低并发写入覆盖风险。
7. 保持简单，不做复杂数据库抽象。

建议方法：

```python
class JsonStoreService:
    def read_json(self, file_name: str):
        pass

    def write_json(self, file_name: str, data):
        pass

    def list_items(self, file_name: str):
        pass

    def get_item(self, file_name: str, item_id: str):
        pass

    def add_item(self, file_name: str, item: dict):
        pass

    def update_item(self, file_name: str, item_id: str, updates: dict):
        pass

    def delete_item(self, file_name: str, item_id: str):
        pass
```

### 2. excel_parser_service.py

实现 Excel 解析。

支持：

```text
xlsx
xls，可选
```

要求：

1. 使用 `openpyxl` 解析 `.xlsx`。
2. `.xls` 如环境支持可用 `xlrd`；如果依赖不可用，应返回清晰错误。
3. 读取每个 sheet。
4. 自动识别表头行，第一版可以默认使用第一行非空行作为表头。
5. 保留 sheet 名、行号、列名、单元格值。
6. 跳过完全空行和完全空列。
7. 日期、金额、编号、百分比不要过度清洗。
8. 解析失败时抛出清晰异常。

统一输出结构：

```json
{
  "document_id": "doc_001",
  "file_name": "sales_2026.xlsx",
  "sheets": [
    {
      "sheet_name": "华东区销售",
      "sheet_index": 1,
      "header_row": 1,
      "headers": ["月份", "地区", "客户", "产品", "销售额"],
      "rows": [
        {
          "row_number": 2,
          "values": {
            "月份": "1月",
            "地区": "上海",
            "客户": "甲公司",
            "产品": "A产品",
            "销售额": "120000"
          }
        }
      ]
    }
  ]
}
```

### 3. csv_parser_service.py

实现 CSV 解析。

要求：

1. 支持 `.csv`。
2. 自动处理 UTF-8 / UTF-8-SIG，必要时尝试 GBK。
3. CSV 统一当作一个 sheet，sheet 名可以是文件名。
4. 第一行默认作为表头。
5. 输出结构与 Excel parser 一致。

### 4. table_cleaner_service.py

实现表格清洗。

要求：

1. 去除单元格首尾空白。
2. 统一换行符。
3. 空值统一为空字符串。
4. 保留编号、日期、金额、百分比、中文列名。
5. 不要把数字随意转成浮点导致编号损坏。
6. 不要过度清洗，避免丢失业务信息。

### 5. table_chunker_service.py

实现表格 chunk。

默认参数：

```text
chunk_size = 1200
overlap = 100
```

要求：

1. 优先按 sheet 分组。
2. 每行转换为 `列名=值` 的可读文本。
3. 多行累积到 chunk_size 附近形成一个 chunk。
4. 超长单行可以单独作为 chunk。
5. 每个 chunk 必须包含文件名、sheet 名、行号范围、列名列表。
6. token_count 第一版可以用字符数近似。
7. chunk id 使用稳定格式，例如 `chunk_<uuid>`。

### 6. embedding_service.py

实现 Embedding API 调用。

要求：

1. 支持 OpenAI-compatible embeddings API。
2. 支持 mock embedding。
3. 提供 `embed_text` 和 `embed_batch`。
4. mock embedding 需要稳定，同一文本每次向量一致。
5. mock embedding 不要完全随机，尽量让相似文本有一点相似度。
6. 默认向量维度 384。

OpenAI-compatible 请求格式：

```json
{
  "model": "text-embedding-3-small",
  "input": "要向量化的文本"
}
```

返回读取：

```text
data[0].embedding
```

### 7. similarity.py

实现余弦相似度：

```python
def cosine_similarity(a: list[float], b: list[float]) -> float:
    pass
```

要求：

1. 使用 numpy。
2. 处理空向量。
3. 处理维度不一致。
4. 返回 float。

### 8. retrieval_service.py

实现 JSON 向量检索。

流程：

```text
用户问题
→ embed_text(question)
→ 读取 embeddings.json
→ 按 filters 过滤 metadata
→ 计算 cosine similarity
→ 排序
→ 取 top_k
→ 根据 chunk_id 从 chunks.json 取原文
→ 返回 sources
```

支持 filters：

```json
{
  "department": "销售部",
  "doc_type": "销售报表",
  "sheet_name": "华东区销售",
  "permission_level": 1
}
```

权限规则：

```text
只返回 chunk.permission_level <= user.permission_level 的内容
```

返回格式：

```json
[
  {
    "chunk_id": "chunk_001",
    "document_id": "doc_001",
    "sheet_id": "sheet_001",
    "file_name": "sales_2026.xlsx",
    "sheet_name": "华东区销售",
    "row_start": 2,
    "row_end": 6,
    "score": 0.89,
    "content": "行 2：月份=1月；地区=上海；客户=甲公司；销售额=120000"
  }
]
```

### 9. llm_service.py

实现 LLM API 调用。

要求：

1. 支持 OpenAI-compatible chat completions API。
2. 支持 mock answer。
3. 提供 `generate_answer(prompt: str) -> str`。
4. mock answer 应基于传入 context 做简单返回，不要完全随机。

### 10. document_pipeline.py

串联 Excel 入库流程：

```text
创建 document 记录
→ 保存原始文件
→ 状态 uploaded
→ 解析 workbook/sheet，状态 parsing
→ 清洗表格，状态 parsed
→ 保存 sheets.json
→ 表格 chunk，状态 chunking
→ 保存 chunks.json
→ 调用 embedding API，状态 embedding
→ 保存 embeddings.json
→ 更新 document.sheet_count/chunk_count/row_count/column_count
→ 状态 indexed
```

要求：

1. 任意步骤失败，document.status 更新为 failed。
2. error_message 记录失败原因。
3. 删除文档时同时删除：
   - documents.json 里的文档记录
   - sheets.json 里的 sheet 记录
   - chunks.json 里的 chunks
   - embeddings.json 里的 embeddings
   - storage/original 下的原文件
4. 第一版同步处理，不需要任务队列。

### 11. chat_service.py

问答流程：

```text
接收用户问题
→ 创建或读取 conversation
→ 保存 user message
→ retrieval_service.search
→ 如果没有 sources，返回“知识库中未找到明确依据”
→ 拼接 prompt
→ 调用 llm_service.generate_answer
→ 保存 assistant message
→ 返回 answer + sources
```

Prompt 模板：

```text
你是企业 Excel 知识库助手。

请严格根据【已检索表格资料】回答用户问题。
如果资料中没有明确答案，请回答“知识库中未找到明确依据”。
不要编造资料中没有的信息。
回答要简洁清楚。
如果涉及数字，请优先引用表格中的原始值。
回答最后必须列出参考来源。

【已检索表格资料】
{context}

【用户问题】
{question}
```

context 拼接格式：

```text
[来源 1]
文件名：sales_2026.xlsx
Sheet：华东区销售
行号：2-6
内容：行 2：月份=1月；地区=上海；客户=甲公司；销售额=120000
```

---

## 七、后端 API 设计

### 1. 健康检查

```http
GET /api/health
```

返回：

```json
{ "status": "ok" }
```

### 2. 文件上传

```http
POST /api/documents/upload
```

使用 `multipart/form-data`。

字段：

```text
file
file_name
doc_type
department
permission_level
```

支持文件：

```text
.xlsx
.xls
.csv
```

返回：

```json
{
  "document_id": "doc_001",
  "status": "indexed",
  "sheet_count": 3,
  "chunk_count": 42
}
```

### 3. 文件列表

```http
GET /api/documents
```

支持 query：

```text
keyword
status
department
doc_type
```

### 4. 文件详情

```http
GET /api/documents/{document_id}
```

### 5. 文件 sheets

```http
GET /api/documents/{document_id}/sheets
```

### 6. 文件 chunks

```http
GET /api/documents/{document_id}/chunks?page=1&page_size=50
```

### 7. 删除文件

```http
DELETE /api/documents/{document_id}
```

### 8. 重新入库

```http
POST /api/documents/{document_id}/reindex
```

第一版可以先预留，返回 not implemented，但接口要存在。

### 9. 聊天问答

```http
POST /api/chat
```

请求：

```json
{
  "conversation_id": "conv_001",
  "question": "华东区 1 月销售额最高的客户是谁？",
  "top_k": 5,
  "filters": {
    "department": "销售部",
    "doc_type": "销售报表",
    "sheet_name": "华东区销售",
    "permission_level": 1
  }
}
```

返回：

```json
{
  "conversation_id": "conv_001",
  "answer": "根据销售数据，华东区 1 月销售额最高的客户是甲公司。",
  "sources": [
    {
      "chunk_id": "chunk_001",
      "file_name": "sales_2026.xlsx",
      "sheet_name": "华东区销售",
      "row_start": 2,
      "row_end": 6,
      "score": 0.89,
      "content": "行 2：月份=1月；地区=上海；客户=甲公司；销售额=120000"
    }
  ]
}
```

### 10. 会话与设置

```http
GET /api/conversations
POST /api/conversations
GET /api/conversations/{conversation_id}/messages
DELETE /api/conversations/{conversation_id}
GET /api/settings
PUT /api/settings
```

---

## 八、前端页面设计

### 1. ChatPage

功能：

1. 输入问题并发送。
2. 调用 `/api/chat`。
3. 展示用户消息。
4. 展示 AI 回答。
5. 展示 sources。
6. loading 时显示“正在检索 Excel 知识库并生成回答...”。
7. 如果没有来源，显示“暂无引用来源”。
8. 支持新建会话。
9. 支持切换历史会话。

### 2. SourcePanel

展示本次回答引用来源：

- 文件名
- Sheet 名
- 行号范围
- 相似度
- chunk 内容
- 支持点击展开

### 3. UploadPage

字段：

```text
文件选择
文件名称
文档类型
所属部门
权限等级
上传按钮
```

功能：

1. 调用 `/api/documents/upload`。
2. 上传后显示状态。
3. 上传成功后显示 document_id、sheet_count、chunk_count。
4. 上传失败时显示错误信息。

### 4. DocumentsPage

功能：

1. 调用 `/api/documents` 展示文件列表。
2. 支持搜索文件名。
3. 支持按 status 过滤。
4. 支持按 department 过滤。
5. 点击文件可查看 sheets 和 chunks。
6. 支持删除文件。
7. 显示字段：
   - 文件名
   - 文件类型
   - 文档类型
   - 部门
   - 权限等级
   - 状态
   - sheet 数量
   - chunk 数量
   - 上传时间
   - 操作

### 5. SettingsPage

功能：

1. 展示 settings.json。
2. 可编辑：
   - Embedding base_url
   - Embedding model
   - Embedding mock
   - LLM base_url
   - LLM model
   - LLM mock
   - top_k
   - chunk_size
   - overlap
   - score_threshold
3. 调用 `/api/settings` 保存。

注意：

- API key 不写入 settings.json。
- API key 不在前端展示。
- 前端设置页只展示模型配置和检索参数。

---

## 九、前端视觉风格要求

整体参考 ChatGPT 网站：

1. 左侧 Sidebar。
2. 中间聊天区简洁干净。
3. 底部固定输入框。
4. 消息区域可滚动。
5. 用户消息和 AI 消息视觉区分。
6. 右侧引用来源面板可滚动。
7. 页面整体清楚、稳定、好用。
8. 支持基本响应式，窄屏时右侧来源栏折叠到下方。
9. 不要做营销落地页，首页就是可用的聊天工作台。

---

## 十、开发阶段要求

请按阶段实现，不要一次性把所有东西写乱。

### 阶段一：项目骨架

完成：

1. 创建 backend 和 frontend 目录。
2. FastAPI 基础服务。
3. React + Vite 基础项目。
4. 前后端联通。
5. `/api/health` 可用。
6. 初始化 data JSON 文件。
7. README 写明启动方式。

验收：

```text
后端能启动
前端能启动
前端能调用 /api/health
data 目录下 JSON 文件自动存在
```

### 阶段二：GPT 风格前端静态页面

完成：

1. Sidebar。
2. TopBar。
3. ChatPage。
4. SourcePanel。
5. UploadPage。
6. DocumentsPage。
7. SettingsPage。
8. 前端路由。

可以先用 mock 数据。

验收：

```text
前端页面可以切换
布局接近 GPT 聊天网站
聊天区、左侧栏、右侧来源栏都存在
```

### 阶段三：Excel 上传 + 解析 + 分块

完成：

1. `/api/documents/upload`
2. `excel_parser_service`
3. `csv_parser_service`
4. `table_cleaner_service`
5. `table_chunker_service`
6. `document_pipeline` 前半部分
7. documents.json 写入
8. sheets.json 写入
9. chunks.json 写入
10. DocumentsPage 展示真实文件列表
11. 支持查看文件 sheets 和 chunks

验收：

```text
能上传 xlsx/csv
xls 如果依赖可用也支持，否则返回清晰错误
能识别 sheet、表头、行号、列名
能生成 table chunks
documents.json 有记录
sheets.json 有记录
chunks.json 有记录
前端文件库能看到结果
```

### 阶段四：Embedding API + embeddings.json

完成：

1. embedding_service
2. mock embedding
3. 真实 embedding API 适配
4. embeddings.json 写入
5. document 状态更新为 indexed

验收：

```text
上传 Excel 后自动生成 embedding
embeddings.json 有向量
没有真实 API key 时 mock 模式也能跑通
```

### 阶段五：JSON 相似度检索 + Chat API

完成：

1. retrieval_service
2. cosine_similarity
3. `/api/chat`
4. chat_service
5. conversations.json
6. messages.json

验收：

```text
用户提问后，系统可以从 JSON 向量里找 top_k chunks
返回 answer 和 sources
sources 包含文件名、sheet 名、行号范围
messages.json 保存聊天记录
```

### 阶段六：LLM API + 前端真实问答

完成：

1. llm_service
2. mock LLM
3. 真实 LLM API 适配
4. ChatPage 接真实 `/api/chat`
5. SourcePanel 展示真实 sources

验收：

```text
用户在前端提问
后端完成检索
LLM 返回回答
前端显示答案和 Excel 引用来源
```

### 阶段七：完善体验和文档

完成：

1. README 完整说明。
2. `.env.example` 完整。
3. 错误提示优化。
4. loading 状态优化。
5. 添加测试 Excel / CSV 文件。
6. 添加简单测试脚本或说明。
7. 删除文件功能。
8. 设置页可用。

验收：

```text
新用户按 README 可以启动项目
可以上传 Excel/CSV
可以提问
可以看到来源
可以删除文件
```

---

## 十一、README 要求

README 中写清楚：

1. 项目介绍。
2. 技术栈。
3. 目录结构。
4. 后端启动方式。
5. 前端启动方式。
6. 环境变量说明。
7. 如何开启 mock 模式。
8. 如何接入真实 Embedding API。
9. 如何接入真实 LLM API。
10. 如何上传 Excel / CSV。
11. 如何提问。
12. JSON 文件结构说明。
13. 当前限制。
14. 后续如何迁移到向量数据库。

---

## 十二、当前版本限制

README 中必须明确说明：

1. 当前版本使用 JSON 保存向量，适合 MVP、学习、Demo、小型表格知识库。
2. 不适合大量 Excel 文件。
3. 不适合高并发。
4. 检索性能不如专业向量数据库。
5. JSON 并发写入能力有限。
6. `.xls` 支持取决于运行环境和依赖。
7. 不支持扫描件、图片、PDF、DOCX。
8. 不做复杂 Excel 公式计算，只读取单元格当前值。
9. 合并单元格、复杂多级表头第一版只做基础兼容。
10. 后续可以把 `embeddings.json + cosine similarity` 替换成 Qdrant / Chroma / Milvus。

---

## 十三、最终验收标准

最终项目需要满足：

1. 可以启动 FastAPI 后端。
2. 可以启动 React 前端。
3. 前端界面类似 GPT 网站。
4. 可以上传 `.xlsx` 和 `.csv`。
5. 后端能解析 workbook、sheet、行、列。
6. 后端能识别基础表头。
7. 后端能清洗表格内容。
8. 后端能生成 table chunks。
9. sheets 能保存到 `sheets.json`。
10. chunks 能保存到 `chunks.json`。
11. 能调用 Embedding API 或 mock embedding。
12. embeddings 能保存到 `embeddings.json`。
13. 用户提问时能生成问题向量。
14. 能在 JSON 向量中计算相似度。
15. 能返回 top_k chunks。
16. sources 包含文件名、sheet 名、行号范围和 chunk 内容。
17. 能调用 LLM API 或 mock LLM。
18. 前端能展示回答。
19. 前端能展示 Excel 引用来源。
20. 会话记录能保存。
21. 文件库能展示上传文件。
22. 能查看某个文件的 sheets 和 chunks。
23. 能删除文件及其 sheets、chunks、embeddings。

---

## 十四、执行要求

开始执行时遵守：

1. 先检查当前仓库是否已有代码。
2. 如果是空仓库，就从 0 创建。
3. 第一版聚焦 Excel / CSV RAG。
4. 不要引入向量数据库。
5. 不要引入关系型或文档数据库。
6. 不要引入 Agent。
7. 不要引入 Agent Loop。
8. 不要把所有代码写在一个文件里。
9. 优先保证项目可以运行。
10. 优先保证代码结构清晰。
11. 每完成一个阶段，请说明：
    - 修改了哪些文件
    - 实现了哪些功能
    - 如何启动
    - 如何测试
    - 下一阶段建议做什么

---

## 十五、请先执行的内容

请先实现阶段一、阶段二、阶段三。

也就是先完成：

1. 项目骨架。
2. FastAPI 后端。
3. React + Vite 前端。
4. GPT 风格页面布局。
5. JSON 文件初始化。
6. Excel / CSV 上传。
7. workbook / sheet 解析。
8. 表格清洗。
9. 表格 chunk 分块。
10. documents.json、sheets.json、chunks.json 保存。
11. 文件库页面展示真实文件。
12. 查看文件 sheets 和 chunks。

暂时不要实现真实 Embedding API、真实 LLM API 和完整 Chat API。

但是可以先创建对应 service 文件和占位函数，方便后续继续开发。

完成后请告诉我：

1. 项目结构。
2. 启动方式。
3. 已实现功能。
4. 如何测试上传 Excel / CSV。
5. 当前还没有实现的功能。
6. 下一步如何继续实现 Embedding API + embeddings.json。
