# LangGraph 表格数据分析 Agent 二期实施记录

> 历史归档：2026-10-19已按用户要求移除表格分析Agent及自动调度/聊天附件代码。本文记录历史设计与验收，不代表当前功能；参见[移除记录](表格分析Agent移除记录-2026-10-19.md)。

完成日期：2026-10-17。对应[二期实施方案](LangGraph表格数据分析Agent二期实施方案.md)。

首版已完成后端编排、结构化数据索引、确定性计算、聊天接入、前端结果与来源展示，并通过自动回归及真实模型验收。原知识问答模式保留。

## 一、如何使用

本地 `backend/.env` 已配置 `TABLE_AGENT_ENABLED=true`、`CHAT_RUNTIME=langgraph`。新进程读取该配置；此前已启动的后端需要重启，随后刷新前端。示例配置文件默认关闭表格功能，其他环境需要自行开启。模型接口继续使用项目原有设置。

1. 上传 `.xlsx` 或 `.csv`，等待文档入库成功。
2. 聊天页将模式切换为“表格分析”。
3. 选择一个文件及其中的一个 Sheet。旧文件首次使用点击“建立表格索引”；新上传的支持格式会尝试自动建立独立表格索引。
4. 显示“可分析”后提问。必要时设置表头行、列类型及单位后重建。
5. 回答中的分析卡片可展开结果、有效/缺失计数及筛选条件，查看原始行。占比及环比支持分子和分母/基期来源切换。

建议先问：

- 销售额合计、平均值、最大值和最小值分别是多少？
- 按地区统计销售额，再计算各地区销售额占比。
- 统计每个月的销售额，再计算销售额环比。
- 分别计算去重订单数、去重客户数和销售额，再用销售额除以去重订单数计算客单价。

复杂规划需关闭 LLM Mock 并配置真实模型。Mock 为有限的关键词演示规则，不代表真实规划能力。

## 二、实现结构

```text
backend/app/
  agents/table_analysis/
    contracts.py        # 需求、任务、步骤和计划的严格Pydantic契约
    state.py            # 小状态；不将完整源行放入checkpoint
    planner.py          # 需求提取、受限规划、覆盖检查、一次修复
    nodes.py            # 各节点、固定版本检查、质量状态、结果持久化
    graph.py            # 独立LangGraph状态图
    runtime.py          # 预算、占用控制、SSE和失败处理
  services/
    chat_dispatcher.py       # 显式模式分发
    run_coordinator.py       # QA和表格共享的会话占用/取消
    table_dataset_reader.py # CSV/XLSX原始值、类型、格式、异常读取
    table_dataset_builder.py# 指纹、配置、版本化建索引
    table_dataset_store.py  # 独立SQLite数据、结果和索引状态
    table_plan_validator.py # 计划字段、类型、任务和口径校验
    table_compute_service.py# Decimal白名单计算
    table_result_service.py # 确定性回答、分页、历史结果与行追溯
  routers/table_analysis.py
frontend/src/
  api/tableAnalysis.ts
  types/tableAnalysis.ts
  utils/analysisValues.ts
  components/
    AnalysisModeSelector.tsx
    TableTargetSelector.tsx
    TableAnalysisCard.tsx
    TableAnalysisSourcePanel.tsx
  styles/table-analysis.css
prompts/table_analysis/
  requirements.md / planner.md / repair.md / coverage.md
```

聊天服务、会话schema及接口、文档上传/删除流程、SSE解析器、回答组件和聊天页面完成相应接入。前端设置模式和目标会递增上下文版本；执行期间不能修改模式、范围或目标。同一会话中的QA和表格运行共用占用控制。

图流程为：表结构摘要 → 提取需求 → 生成计划 → 校验计划及需求覆盖 → 执行计算 → 核对任务和源行 → 保存结果。计划不合格最多修复一次。运行固定文档、Sheet、数据版本、文件指纹和会话上下文版本；过程中变化会中止，避免混用版本。

模型只输出声明式计划，不开放生成代码、SQL或任意工具执行。数值结果及最终Markdown表由程序产生，不新增模型解释节点。源单元格数值最多28位有效数字，计算使用34位Decimal上下文，页面按两位小数四舍五入展示；内部派生结果保留计算精度，标识符保留前导零。

## 三、支持能力和状态

| 能力 | 实现边界 |
|---|---|
| 表结构查看 | 列、类型、单位、行数、缺失与异常摘要 |
| 筛选 | 等于、集合、大小比较、日期区间、非空；AND组合 |
| 聚合 | sum、avg、min、max、行数、非空计数、去重计数 |
| 分组 | 最多两个列，或一个日期列按自然月分组 |
| 排名 | 完整聚合后排序、Top N，并列处提示稳定排序 |
| 占比 | 同一筛选范围内可加总指标的分组值/完整分组总额；拒绝用Top N后的合计作分母 |
| 派生指标 | 同一结果表两个数值指标的加减乘除；加减要求单位一致 |
| 月度环比 | 连续自然月、正数基期；缺月、首月或无效基期明确不可计算 |
| 多任务 | 保留可完成部分，阻塞任务及依赖标记原因 |
| 澄清 | 相同数据版本与会话上下文中的待确认问题可接收下一轮补充 |
| 结果与来源 | 结果分页、每个结果行的原始行号、分子/分母/基期、历史版本 |

空值不补零；全空数值输出不可计算；无效数值、缺失公式缓存或无效筛选字段阻塞对应计算。读取Excel已保存的公式缓存，不执行公式；存在缓存公式时提示缓存新鲜度需确认。Excel百分数与文本百分数保留口径，混合不明比例不静默计算。疑似合计、小计行要求明确排除条件。

状态包含 `answered`、`partially_answered`、`clarification_required`、`unsupported`、`calculation_failed`。只有全部任务完成，`analysis_check.passed`才为真。异常或取消走SSE错误，不能误报成功。

## 四、存储、接口与配置

`DATA_DIR/table_analysis/tables.sqlite` 保存数据集元信息、原始/类型化行、活动版本、索引状态及结果。旧版本保留供历史结果追溯；相同文件指纹与配置重复建立索引为幂等操作。表格索引失败不回滚已经成功的QA文档入库。删除文件清理其表格版本、行及计算结果，删除会话清理相应结果。

| 接口 | 用途 |
|---|---|
| `GET /api/analysis/capabilities` | 功能是否开启、格式 |
| `GET /api/documents/{id}/tables` | Sheet、状态及当前数据集 |
| `POST /api/documents/{id}/table-index` | 建立/重建索引及列配置 |
| `GET /api/analysis/results/{run_id}/{result_id}` | 保存结果分页 |
| `GET /api/analysis/results/{run_id}/{result_id}/rows` | 原始行分页、结果行及来源部分筛选 |

会话新增 `agent_mode`、`table_target`。消息及SSE完成事件新增可选`analysis`；旧会话和原SSE字段继续兼容。结果读取要求运行、结果、已保存回答、会话和文档匹配，并核对原范围；沿用现有单用户本地应用边界，没有新增多租户鉴权。

默认上限：`TABLE_MAX_ROWS=50000`、`TABLE_MAX_COLUMNS=100`、`TABLE_MAX_CELLS=2000000`、`TABLE_MAX_GROUPS=2000`、`TABLE_AGENT_MAX_SECONDS=180`。每轮最多8次模型及8次工具调用。超过数据上限拒绝建部分索引，超过分组上限拒绝截断统计。

## 五、验收记录

所有端到端验收使用合成数据和临时的DATA_DIR/STORAGE_DIR，没有向现有用户文件或聊天记录写入测试内容。验收文件包含6条销售明细、3个月、2个地区、3个客户、6个不同订单。

| 检查 | 结果 |
|---|---|
| 后端完整回归 | 152 passed，另68个subtests通过；含33项表格测试用例（参数化后数量） |
| 前端测试 | SSE 6项、数值展示2项、上传4项，全部通过 |
| 类型检查与生产构建 | `tsc && vite build`通过 |
| Python语法、依赖及差异检查 | compileall、pip check、git diff --check通过 |
| 真实模型CSV四题 | 基础多指标、地区占比、月度环比、去重数及客单价通过，每题3次模型调用 |
| 浏览器Excel验收 | 建索引→真实模型统计→结构化结果→原始行→刷新恢复历史，通过 |
| 浏览器CSV验收 | 同会话切换文件→地区占比→每行来源→分子3行/分母6行，通过 |
| 浏览器控制台 | 验收时未发现error/warn |

金标准：总额1100、平均183.33、最大300、最小100；华东/华西各550、各50%；月度300/400/400，2月环比33.33%、3月0，1月缺少基期为部分可计算；去重订单6、客户3、客单价183.33。单元测试还覆盖零分母、全空、无效日期、无效数值、公式缓存、百分数、合并表头、独立任务部分完成、版本变化、跨范围目标、删除清理以及高精度聚合/派生后续计算。

复现命令（项目根目录）：

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m pip check
.venv/bin/python -m compileall -q backend/app
git diff --check
cd frontend
npm run test:chat
npm run test:analysis
npm run test:upload
npm run build
```

验收截图：

- [CSV分子源行](/Users/stuhua/.codex/visualizations/2026/10/17/01a14956-44a3-7c82-805c-71905f80e6b6/table-agent-share-source.png)
- [Excel来源面板](/Users/stuhua/.codex/visualizations/2026/10/17/01a14956-44a3-7c82-805c-71905f80e6b6/table-agent-source.png)

## 六、首版限制和后续准备

- 单后端进程、一次一个Sheet；跨表JOIN、同比、预测、写回Excel、导出报告及自动选择Agent尚未实现。
- 只支持平面单行唯一表头。合并单元格、多行表头、不同口径单位自动换算需要先整理原文件；单位设置是注明口径，不改变原值。
- 原始读取和计算仍有内存中的行集。行数/分组上限属于保护阈值，尚未做5万行或极端分组的性能承诺，尤其占比来源较多时需要额外空间。
- 历史结果保留版本，尚无自动版本回收策略；有长期大量使用需求时需增加保留期和清理机制。
- JSON会话与SQLite结果没有跨库事务。运行异常会标记失败/待核对，结果需已提交消息才可读取；没有实现完整持久化补偿队列和启动时孤儿数据自动对账。表格建索引中断可识别并要求重建。
- checkpoint用于记录及排障；尚无对外恢复API。澄清支持待确认问题的下一轮补充，不能把任意历史统计结果自动当作新的隐含计算输入。
- 真实模型验收覆盖了本次合成场景，仍可能误解复杂自然语言口径。上线到更多业务文件前，应补充相应金标准和用户明确的单位、去重键、日期口径。
- 测试存在Starlette/SWIG弃用提示及Node模块类型提示；不影响本次测试与构建。

本轮保留已有未提交改动；没有提交或推送Git。
