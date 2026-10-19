# LangGraph 知识库问答 Agent 一期实施记录

日期：2026-10-17  
状态：一期代码已实现，离线与浏览器验证通过；真实模型效果尚待评估。

## 1. 已实现能力

- 使用真实 LangGraph StateGraph 编排理解、检索、覆盖检查、补查、生成、校验和最终保存。
- 同步与 SSE 入口共用图节点，保留 `CHAT_RUNTIME=legacy` 回退。
- 每次运行独立 run_id，文档范围、历史版本及过滤条件在本轮固定。
- 将现有检索、片段读取和确定性表格统计包装为受控工具；模型不能调用任意代码或读取任意路径。
- 最多首轮加两轮补查，查询数、工具调用、嵌套模型调用和总耗时均受预算约束。
- 简单问答复用规则检查；复杂任务按需进行模型覆盖判断，并校验证据 ID 和逐字摘录。
- 覆盖不足、无法消歧、超过六项任务、预算耗尽时给出明确的受控答复。
- 保留真实正文增量，最终答案经校验后替换草稿；关键错误不发送成功 done。
- SQLite 自动保存 checkpoint 与运行摘要；JSON 最终消息按 run_id 和角色在单进程内去重。
- 同一会话的并发请求在 SSE 建立前返回 409；关闭流、删除会话和文档失效有独立处理。
- 前端增加可折叠执行过程，支持当前进度、失败、依据不足、澄清及历史回显。
- 新增两份可在线管理的 Agent 提示词与 20 条合成验收样例。

## 2. 实际目录

以 `/Users/stuhua/Desktop/code file/rag-agent` 为项目根目录：

```text
backend/app/agents/
  contracts.py                 # 参数、任务、覆盖与工具结果
  budget.py                    # ContextVar 共享调用/时间预算
  knowledge_qa/               # 2026-10-18统一迁入独立包
    __init__.py
    state.py                  # 可序列化图状态
    graph.py                  # 图结构和条件路由
    nodes.py                  # 节点业务逻辑
    runtime.py                # 运行身份、占用、取消、事件适配
    tools.py                  # 工具白名单与范围控制
    evidence_coverage.py      # 任务拆分与证据覆盖
backend/app/services/agent_run_store.py
backend/tests/test_knowledge_qa_graph.py
backend/tests/fixtures/knowledge_qa_cases.json
prompts/agent/replan.md
prompts/agent/evidence_coverage.md
frontend/src/components/AgentProgress.tsx
frontend/src/utils/chatStream.ts
frontend/src/styles/agent-progress.css
frontend/tests/chatStream.test.ts
```

现有 ChatService、模型服务、Embedding、检索、JSON 存储、生命周期、聊天路由和前端消息消费按需接入；knowflow-agent 的业务代码未改动。

## 3. 运行方式

从项目根目录运行 `bash start.sh`，Windows 使用 `start.bat`。本次已经创建根目录 `.venv` 并安装后端依赖，前端锁文件依赖也已安装；脚本仍负责首次创建缺少的 `.env`。

默认配置：

| 变量 | 默认值 | 含义 |
|---|---|---|
| `CHAT_RUNTIME` | `langgraph` | 新图；改为 legacy 并重启可回退 |
| `AGENT_MAX_RETRIEVAL_ROUNDS` | `3` | 包含首轮，最多 3 轮 |
| `AGENT_MAX_SECONDS` | `180` | 合作式总执行时间预算 |
| `AGENT_MAX_LLM_CALLS` | `8` | 包含规划、翻译、覆盖检查、补查和生成 |
| `AGENT_MAX_TOOL_CALLS` | `8` | 工具调用总数 |

业务数据继续保存在原 JSON 目录。DATA_DIR 下自动新增 `agent/runs.sqlite` 和 `agent/checkpoints.sqlite`，已被既有数据目录忽略规则覆盖，不提交本地数据库。

依赖验证使用 Python 3.11、LangGraph 1.2.4、checkpoint 4.3.0、SQLite checkpoint 3.1.0、Pydantic 2.10.4；框架版本写入运行依赖，pytest 9.1.1 写入开发依赖。

## 4. 验证结果

| 验证 | 结果 |
|---|---|
| 后端完整测试 | 119 passed，另有 68 个 subtests 通过 |
| 兼容性基线 | 原有 70 项测试使用明确的 legacy 模式继续验证 |
| 新图测试 | 49 项，包含 20 条参数化合成样例 |
| 前端聊天流测试 | 5 passed：分包、CRLF、UTF-8、完整最终结果、错误与旧协议 |
| 前端上传测试 | 4 passed |
| TypeScript 与 Vite 构建 | 通过 |
| Python 语法编译 | 通过 |
| 依赖一致性 | pip check 通过 |
| 补丁空白检查 | git diff --check 通过 |
| 冒烟测试 | 独立临时数据目录中通过，输出 smoke test passed |

关键行为测试包括：只召回一方资料时定向补查、只有公司名不能覆盖付款条件、分任务保留日期和指标、单会话占用、文档删除、会话删除、执行取消、无依据数字替换、预算终止、全量扫描不完整时禁止宣称完整，以及最终消息成功但运行摘要失败时标记 needs_reconciliation。

运行命令（根目录，Python 命令以项目虚拟环境为准）：

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m compileall -q backend/app
.venv/bin/python -m pip check
```

前端目录运行：

```bash
pnpm run test:chat
pnpm run test:upload
pnpm run build
```

测试输出中仍有来自 Starlette/AnyIO、PyMuPDF SWIG 和 Node 模块类型推断的弃用或提示信息，未导致测试或构建失败。未安装额外 linter，未将语法编译和测试表述为完整静态类型检查或依赖漏洞审计。

## 5. 浏览器验证

Browser 插件未提供，按前端验证技能使用已有 Playwright，并把 Chromium 放在临时目录。后端使用独立临时 DATA_DIR/STORAGE_DIR 和 mock，未向真实知识库上传测试材料。

- 测试地址：前端 `http://127.0.0.1:15173/`，后端 `http://127.0.0.1:18000/`。
- 页面标题为“知识库检索工具”，页面有实际内容，无框架错误覆盖层。
- 桌面尺寸 1440×1000，移动端尺寸 390×844，无横向溢出。
- 上传合成 CSV，限定到该文件，合计得到 377000，覆盖 4 条记录。
- 展开执行过程，确认理解、检索、覆盖、生成、校验和保存步骤可见。
- 打开来源面板，刷新后历史答案与执行摘要继续显示。
- 再发送事实查询，在生成完成前观察到进度与部分正文，最终答案包含 120000。
- 两次问答后控制台无应用错误。

截图保存在仓库外：

- [桌面完成状态](</Users/stuhua/.codex/visualizations/2026/10/17/01a14956-44a3-7c82-805c-71905f80e6b6/rag-agent-desktop.png>)
- [移动端状态](</Users/stuhua/.codex/visualizations/2026/10/17/01a14956-44a3-7c82-805c-71905f80e6b6/rag-agent-mobile.png>)
- [流式生成中](</Users/stuhua/.codex/visualizations/2026/10/17/01a14956-44a3-7c82-805c-71905f80e6b6/rag-agent-streaming.png>)

## 6. 已知边界与下一步

1. 验收样例验证的是合成资料上的流程、范围和证据契约；规划使用固定返回，mock 回答不代表真实模型的完整问答质量。尚未调用用户的真实模型或 Embedding 服务，也没有真实模型准确率与费用结论。
2. 仍需使用目标模型，在独立留出样例上评估自然语言规划、语义覆盖、冲突处理和复杂问题答案；部署前按实际延迟和调用量调整预算。
3. 首期支持单后端进程；同一会话串行，JSON 消息与 SQLite 没有跨存储事务。网络重发会创建新 run_id；跨进程幂等和故障恢复不在本期承诺内。
4. checkpoint 已落盘，进程重启后旧 running 记录标记 interrupted；尚未开放恢复、断点续传和人工暂停接口。
5. 时间预算在节点、请求和流式增量处合作式检查。正在阻塞的 I/O 可能等待超时后才退出，不承诺即时取消。
6. 片段数与字符数受限，但尚无通用的模型 token 容量适配器。需要按部署模型核对总上下文容量；暂不记录精确 token 用量。
7. 表格能力继续沿用已支持的规则统计，复杂日期过滤、任意跨表计算、同比环比和完整文档对比仍需后续专项能力。
8. 本次没有提交、推送或部署。临时验证服务在交付前停止，启动项目请使用常规启动脚本。

下一阶段建议先做目标模型验收，再根据真实问题决定扩展表格分析 Agent，而非立即增加更多角色。
