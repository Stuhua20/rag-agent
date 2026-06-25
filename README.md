# Excel RAG JSON Pipeline

这是一个面向 Excel / CSV 文件的 RAG MVP 项目。

当前版本使用：

- 后端：FastAPI
- 前端：React + Vite + TypeScript
- 存储：本地 JSON 文件
- Excel 解析：openpyxl
- 向量生成：OpenAI-compatible Embedding API 或稳定 mock embedding

项目第一版不使用数据库，不使用向量数据库，不接入 Agent。

## 已实现功能

- FastAPI 后端骨架
- React + Vite 前端骨架
- 类 GPT 的工作台布局
- JSON 数据文件自动初始化
- Excel / CSV 上传
- workbook、sheet、表头、行、列解析
- 表格内容清洗
- 表格 chunk 分块
- mock embedding 向量生成
- OpenAI-compatible Embedding API 适配
- `embeddings.json` 写入
- JSON 余弦相似度检索
- Chat API
- mock LLM 回答
- OpenAI-compatible Chat Completions API 适配
- 前端真实问答
- 右侧引用来源展示
- conversations / messages 保存
- 文件列表、sheets、chunks、删除接口
- 上传页、文件库页、设置页、聊天页

暂未实现：

- 流式输出
- 完整历史会话切换
- 批量重建 embedding

## 目录结构

```text
backend/
  app/
    main.py
    core/
    routers/
    services/
    schemas/
    utils/
  data/
  storage/original/
  requirements.txt
  .env.example

frontend/
  src/
    pages/
    components/
    api/
    types/
    styles/
  package.json
```

## 后端启动

进入后端目录：

```bash
cd /Users/stuhua/Desktop/Stuhua/Danmei/Distributor‌-RAG/backend
```

如果已经有 `.venv`，直接激活：

```bash
source .venv/bin/activate
```

如果没有 `.venv`，先创建并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

启动后端：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

验证健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

正常返回：

```json
{"status":"ok"}
```

## 前端启动

进入前端目录：

```bash
cd /Users/stuhua/Desktop/Stuhua/Danmei/Distributor‌-RAG/frontend
```

如果你的电脑已经安装了 `pnpm`：

```bash
pnpm install
pnpm run dev --host 127.0.0.1 --port 5173
```

如果终端提示 `pnpm: command not found`，可以使用 Codex 自带的 pnpm：

```bash
/Users/stuhua/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pnpm install
/Users/stuhua/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pnpm run dev --host 127.0.0.1 --port 5173
```

如果还提示找不到 `node`，使用：

```bash
PATH=/Users/stuhua/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH /Users/stuhua/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pnpm run dev --host 127.0.0.1 --port 5173
```

打开前端：

[http://127.0.0.1:5173/](http://127.0.0.1:5173/)

## 如何测试上传

1. 启动后端。
2. 启动前端。
3. 打开前端页面。
4. 点击左侧「上传」。
5. 选择 `.xlsx` 或 `.csv` 文件。
6. 填写文档类型、部门、权限等级。
7. 点击「上传并解析」。
8. 打开「文件库」。
9. 点击文件右侧「查看」。
10. 查看解析出的 sheets 和 chunks。

上传成功后，后端会写入：

- `backend/data/documents.json`
- `backend/data/sheets.json`
- `backend/data/chunks.json`
- `backend/data/embeddings.json`

文档状态会变成：

```text
indexed
```

## 如何测试聊天问答

先上传一个 `.xlsx` 或 `.csv` 文件，确认文件状态是 `indexed`。

前端测试：

1. 打开 [http://127.0.0.1:5173/](http://127.0.0.1:5173/)。
2. 进入左侧「聊天」。
3. 输入和已上传表格相关的问题。
4. 中间会展示回答。
5. 右侧会展示引用来源。

也可以直接调用接口：

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "上海 甲公司 销售额是多少",
    "top_k": 5,
    "filters": {
      "department": "销售部",
      "permission_level": 1
    }
  }'
```

返回示例：

```json
{
  "conversation_id": "conv_xxx",
  "answer": "根据已检索表格资料，相关记录为：行 2：月份=1月；地区=上海；客户=甲公司；销售额=120000。\n\n参考来源：sales.csv / sales",
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

Chat API 会同时写入：

- `backend/data/conversations.json`
- `backend/data/messages.json`

## Mock Embedding

默认使用 mock embedding。

mock embedding 的特点：

- 不需要 API key
- 同一段文本每次生成相同向量
- 向量会写入 `backend/data/embeddings.json`
- 适合本地开发和链路测试

相关配置在 `backend/data/settings.json`：

```json
{
  "embedding": {
    "provider": "openai-compatible",
    "base_url": "https://api.example.com/v1",
    "model": "text-embedding-3-small",
    "mock": true
  }
}
```

## 接入真实 Embedding API

复制环境变量示例：

```bash
cd /Users/stuhua/Desktop/Stuhua/Danmei/Distributor‌-RAG/backend
cp .env.example .env
```

编辑 `.env`：

```env
EMBEDDING_BASE_URL=https://你的接口地址/v1
EMBEDDING_API_KEY=你的_api_key
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_MOCK=false
```

同时把 `backend/data/settings.json` 里的：

```json
"mock": false
```

然后重启后端。

接口要求兼容 OpenAI embeddings 格式：

```http
POST /v1/embeddings
```

请求格式：

```json
{
  "model": "text-embedding-3-small",
  "input": ["文本1", "文本2"]
}
```

返回中会读取：

```text
data[*].embedding
```

## Mock LLM

默认使用 mock LLM。

mock LLM 的特点：

- 不需要 API key
- 会基于已检索 sources 生成简单回答
- 适合本地开发和链路测试

相关配置在 `backend/data/settings.json`：

```json
{
  "llm": {
    "provider": "openai-compatible",
    "base_url": "https://api.example.com/v1",
    "model": "gpt-4o-mini",
    "mock": true
  }
}
```

## 接入真实 LLM API

复制环境变量示例：

```bash
cd /Users/stuhua/Desktop/Stuhua/Danmei/Distributor‌-RAG/backend
cp .env.example .env
```

编辑 `.env`：

```env
LLM_BASE_URL=https://你的接口地址/v1
LLM_API_KEY=你的_api_key
LLM_MODEL=gpt-4o-mini
LLM_MOCK=false
```

同时把 `backend/data/settings.json` 里的：

```json
"mock": false
```

然后重启后端。

接口要求兼容 OpenAI chat completions 格式：

```http
POST /v1/chat/completions
```

## JSON 文件说明

`backend/data/documents.json`

保存上传文件基本信息。

`backend/data/sheets.json`

保存 sheet 名、表头、行列数量等元信息。

`backend/data/chunks.json`

保存表格 chunk。chunk 内容会包含文件名、sheet 名、行号、列名和值。

`backend/data/embeddings.json`

保存每个 chunk 对应的 embedding 向量。

`backend/data/settings.json`

保存模型配置和检索参数，但不保存 API key。

`backend/data/conversations.json`

保存对话列表。

`backend/data/messages.json`

保存用户和助手消息，以及每条助手消息对应的 sources。

## 当前限制

- 当前版本适合 MVP、学习、Demo、小型表格知识库。
- JSON 不适合大量文档或高并发写入。
- `.xlsx` 和 `.csv` 已支持，`.xls` 当前会返回明确错误。
- 不支持 PDF、DOCX、图片 OCR。
- 不做复杂 Excel 公式计算，只读取单元格当前值。
- 合并单元格、复杂多级表头只做基础兼容。
- 已实现 LLM 回答，但 mock LLM 只适合本地链路测试，真实效果需要接入真实 LLM API。
- 前端已支持真实问答，但暂未实现流式输出和完整历史会话切换。

## 下一阶段

下一阶段建议实现：

```text
阶段七：完善体验和文档
```

目标：

- 优化错误提示和 loading 状态
- 添加测试 Excel / CSV 文件
- 完善历史会话切换
- 支持重新入库 / 重建 embedding
- 补充更多使用说明
