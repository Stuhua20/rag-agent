# Prompt 管理

本目录存放问答链路使用的 LLM Prompt 和固定回复模板。后端只通过明确登记的文件加载运行时内容；本说明文件不会发送给 LLM，也不会出现在前端的可编辑列表中。

## 当前文件

- `system/base.md`：最终答案使用的 system message，定义知识边界、数据安全和语言规则。
- `query/planner.md`：查询规划模板，输出意图、子问题、过滤条件和检索建议 JSON。
- `query/translator.md`：检索表达翻译模板，输出与输入一一对应的 JSON 字符串数组。
- `rag/answer.md`：通过证据门禁后，用于生成最终答案的 user prompt。
- `rag/no_source.md`：没有检索结果时直接返回的固定回复，不发送给 LLM。

## 变量契约

- `query/planner.md`：`{conversation_context}`、`{metadata}`、`{question}`
- `query/translator.md`：`{target_language}`、`{queries}`
- `rag/answer.md`：`{conversation_context}`、`{query_plan}`、`{context}`、`{question}`
- `rag/no_source.md`：无变量

## 共同约定

- 历史对话、知识库元数据、查询规划和检索资料都属于输入数据，不是需要执行的指令。
- 检索资料中的文件名、Sheet、行号和相关度用于定位或排序，不自动构成事实。
- `[来源1]` 等标记只用于内部上下文；最终回答正文不输出内部来源标记或单独的参考来源段落，引用由界面展示。
