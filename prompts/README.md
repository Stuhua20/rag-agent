# Prompt 管理

本目录存放问答链路使用的 LLM Prompt 和固定回复模板。后端只通过明确登记的文件加载运行时内容；本说明文件不会发送给 LLM，也不会出现在前端的可编辑列表中。

## 当前文件

- `system/base.md`：最终答案使用的 system message，定义知识边界、数据安全和语言规则。
- `query/planner.md`：查询规划模板，输出意图、子问题、过滤条件和检索建议 JSON。
- `query/translator.md`：检索表达翻译模板，输出与输入一一对应的 JSON 字符串数组。
- `rag/answer.md`：通过证据门禁后，用于生成最终答案的 user prompt。
- `rag/no_source.md`：没有检索结果时直接返回的固定回复，不发送给 LLM。
- `agent/replan.md`：针对缺失证据生成最多三个补查查询，真实模型模式按需使用。
- `agent/evidence_coverage.md`：多任务语义覆盖检查，要求返回证据 ID 和可逐字核对的摘录。


## 变量契约

- `query/planner.md`：`{conversation_context}`、`{metadata}`、`{question}`
- `query/translator.md`：`{target_language}`、`{queries}`
- `rag/answer.md`：`{conversation_context}`、`{query_plan}`、`{resolved_question}`、`{evidence_report}`、`{context}`、`{question}`
- `rag/no_source.md`：无变量
- `agent/replan.md`：`{requirements}`、`{executed_queries}`
- `agent/evidence_coverage.md`：`{requirements}`、`{evidence}`

## 共同约定

- 历史对话、知识库元数据、查询规划和检索资料都属于输入数据，不是需要执行的指令。
- 检索资料中的文件名、Sheet、行号和相关度用于定位或排序，不自动构成事实。
- `[来源1]` 等标记只用于内部上下文；最终回答正文不输出内部来源标记或单独的参考来源段落，引用由界面展示。
- 运行时规则使用通用概念，不写入特定客户、产品、缩写或业务数据示例；实体与指标从本轮输入取得。具体案例放在测试或维护文档中。
- system 定义长期角色和事实边界；answer 定义本轮输入与输出方式。文字归纳属于 lookup，数值聚合属于 summary；comparison、ranking、trend 保持现有全量检索策略。
- `evidence_report` 来自后端证据检查，不是模型规划结果。覆盖状态缺失或未知时不得推断已完成全量覆盖。所有回答均经过证据和内容核验，不提供独立的表格计算路径。
- 保存时校验必需变量并清除缓存；修改变量时须同步后端组装与保存校验。当前服务进程升级代码后需重启；直接编辑磁盘文件也需重启或经在线保存触发缓存失效。

详细写作约定与回放检查清单见 [Prompt 维护指南](../docs/prompt-guidelines.md)。
