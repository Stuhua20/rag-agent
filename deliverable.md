# P0 处理结果

已处理 P0-2、P0-3、P0-4，并完成自检。

## P0-2：统计类问题不再静默使用 Top K

- 明确的合计、平均、计数、分组排名、时间趋势问题，优先按索引中的行数据做全量确定性计算。
- 统计扫描按“文档 + Sheet + 行号”去重，避免 chunk overlap 造成重复计数。
- 无法安全结构化计算的统计/比较问题，进入全量召回；超过 `full_scan_max_chunks` 时返回明确的“资料不足以支持完整计算”，不使用截断结果冒充全量结果。
- 普通“销售额是多少”不会因为包含“多少”而误触发全量统计。

## P0-3：入库失败、上传上限和向量一致性

- 后端按 `MAX_UPLOAD_MB` 分块复制并强制限制文件大小，前端同步显示 30MB 上限。
- 解析、分块或向量化任一步失败时，清理当前文档的 sheets/chunks/embeddings 和原始文件，再标记文档为 `failed`。
- 写入 Embedding 前校验返回数量和向量维度，避免部分向量被静默写入。
- 上传权限等级增加 1~3 范围校验；运行时 chunk size/overlap 配置真正作用于分块器。

## P0-4：配置、运行时设置和 `.env`

- 默认运行时设置补齐 `normalize`、`search_mode`、`max_chunks_per_doc`、`full_scan_max_chunks` 等字段。
- 设置 PUT 使用 Pydantic 类型/范围校验，并采用深度合并，避免保存部分设置时覆盖其他配置。
- 增加 `python-dotenv` 依赖并恢复 `.env.example`；API key 仍只保存在 `.env`，设置接口只返回是否已配置。

## 验证结果

- `./.venv/bin/python backend/scripts/p0_self_check.py`：通过
- `../.venv/bin/python scripts/smoke_test.py`：通过
- `./.venv/bin/python -m compileall -q backend/app backend/scripts`：通过
- `pnpm run build`：通过（TypeScript + Vite production build）
- `git diff --check`：通过
- 当前索引数据实测：`GQ总计`完成全量计算，`GQ最高的经销商`完成全量排名。

## P2-8：前端异常处理

- 文件库加载失败会保留已有列表、显示错误提示并提供“重试”；初次加载失败不会再显示误导性的空列表。
- Sheet/Chunk 预览使用并行请求，失败时显示内嵌错误和重试入口，避免未捕获 Promise。
- 删除文件改用确认弹窗；删除失败保留当前状态并给出错误提示，删除成功后即使列表刷新失败也会明确提示。
- SSE 客户端校验响应体、事件字段和 `done` 事件；服务端 error、网络断流和提前结束都会转成用户可见的中断提示，并保留已生成的部分回答。

## P2-9：文档、代码和 UI 漂移

- README 已改为描述回答卡片下方展开引用来源，移除旧的右侧引用表述。
- Prompt 目录说明和提示词页面不再展示已删除的来源格式说明；README 的后续规划同步为真实待办。

## P2-10：清理未使用代码和运行产物

- 删除未被引用的 `SourcePanel`、旧 `PromptBuilder` 及其导出文件、未接入主链路的 `source_format.md`。
- 删除已结束 Cloudflare quick tunnel 的日志、PID 和空配置；PID 已确认不存在。
- `.gitignore` 增加对应运行时文件规则，避免后续污染工作区。

## P2 验证

- `pnpm run build`：通过（TypeScript + Vite production build）
- `./.venv/bin/python -m compileall -q backend/app backend/scripts`：通过
- `../.venv/bin/python scripts/smoke_test.py`：通过
- `./.venv/bin/python backend/scripts/p0_self_check.py`：通过
- `git diff --check`：通过

# Evidence Gate + Answer Verifier 实现结果

已将检索充分性判断和生成后校验接入 REST 与 SSE 问答链路。

## 行为

- Evidence Gate 检查来源是否存在、相关度是否达到当前检索门槛，以及 comparison/ranking/trend 是否完成所需全量扫描。排名和趋势至少需要两个独立证据单元；比较问题会逐一核对问题中明确提到的常见组织对象是否都出现在来源，单一来源也可以承载完整的双对象比较。
- 全量扫描超限或证据不足时，返回“资料不足/请缩小范围”的说明和已检索到的部分来源，不调用 LLM 生成事实答案。
- Answer Verifier 对普通生成回答核对文件名、常见组织实体和数字；表格回答会检查实体与数字能否在同一数据行找到。内部 `[来源N]` 或 chunk 标记会被清理。
- 表格确定性计算由代码基于全量记录完成，校验时保留计算结果，不要求最终合计数必须逐字出现在原始行里。
- `quality` 审计信息写入 assistant 消息，并通过 REST 响应及 SSE `done` 返回；旧会话记录仍可读取，新增字段为可选扩展。
- 为确保未校验草稿不显示给用户，SSE 先发送引用，再缓冲模型输出；校验完成后发送最终回答正文。等待期间前端继续显示思考状态。

## 变更范围

- 新增 `backend/app/services/answer_quality_service.py` 和隔离式专项检查 `backend/scripts/answer_quality_self_check.py`。
- 更新 `ChatService` 的 Gate / Verifier 接入、全量检索状态传递和消息审计字段；REST 响应增加 `quality`。
- 前端消息类型支持读取可选的 `quality` 字段；既有 `done` 回调将最终正文写回消息。
- Mock 回答器按独占行的提示段落标记提取用户问题，避免把答案规范内容带进模拟回答。

## 验证

- `./.venv/bin/python backend/scripts/answer_quality_self_check.py`：通过
- `./.venv/bin/python backend/scripts/p0_self_check.py`：通过
- `backend/scripts/smoke_test.py`（临时 JSON 数据目录和临时文件存储）：通过
- `./.venv/bin/python -m compileall -q backend/app backend/scripts`：通过
- `frontend` 目录执行 `pnpm run build`：通过
- `git diff --check`：通过

## 已知边界

Verifier 使用规则匹配，不能证明每条自然语言陈述都与证据语义一致；数字和实体规则对格式差异较保守，可能出现误拦。逐 token 流式效果也因服务端校验缓冲而改为最终答案一次展示。
