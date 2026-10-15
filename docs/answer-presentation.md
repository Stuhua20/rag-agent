# 文档式回答与来源证据

聊天回答按文档排版，保留 Markdown 标题、列表、表格和代码块，移除原先回答卡片的边框、阴影与重复标题。较宽的表格在正文内部横向滚动。

## 来源交互

- 回答下方按文件显示来源标签，同一文件的多个命中片段归并成一个标签，并显示片段数。
- 点击标签查看该文件的首个命中片段，也可通过“查看来源”打开当前回答的首条证据。
- 面板显示文件名、位置、解析后的原文，以及可选展开的匹配信息；可在本回答所有命中片段间切换。
- Excel/CSV 使用行号；PDF/Word 使用页面或正文分区与内容块序号，内容块序号不表示原文件行号。
- 视口宽度大于 1100px 时使用右侧面板；1100px 及以下使用原生模态抽屉。
- 点击关闭、再次点击“收起来源”或在面板内按 Escape 可关闭；抽屉支持点击遮罩关闭。关闭后将焦点恢复至来源入口。
- 每次只展示一条回答的来源；切换会话后清除打开状态。没有来源的回答不显示来源入口。

## 兼容性

沿用现有 `ChatMessage.content`、`sources` 和 SSE 接口。来源到达后即可打开面板，正文继续流式生成；`done.answer` 仍替换草稿。引用清理保留 Markdown 换行，复制内容与界面正文一致。

面板展示后端返回的解析片段，不是原文件的版式预览，也不提供逐句引用映射。没有新增依赖、接口或数据迁移。

## 实现位置

- `frontend/src/components/AnswerCard.tsx`：Markdown 正文与文件标签。
- `frontend/src/components/MessageList.tsx`：消息头、复制/来源操作与滚动跟随。
- `frontend/src/components/ChatWindow.tsx`：按消息和片段标识维护面板选中状态。
- `frontend/src/components/SourceEvidencePanel.tsx`：桌面面板、抽屉和片段切换。
- `frontend/src/utils/answerPresentation.ts`：正文清理、文件归并与位置格式。
- `frontend/src/styles/answer.css`：回答与来源面板样式。

## 验证

前端生产构建、4 项现有上传测试及 10 组模拟 API Edge/Playwright 检查均通过，差异空白检查通过。覆盖 Markdown/表格、来源归并和切换、PDF/Word 位置、复制、键盘/遮罩关闭和焦点恢复、无来源回答、流式增量和最终答案替换、中断后保留正文与证据、会话切换。响应式检查覆盖 1440、1280、1100、960、768、600、390 和 320px，无页面横向溢出、运行时或控制台错误。

未调用真实模型或更改真实知识库、会话。Browser plugin not available，因此复用工作区提供的 Playwright；临时脚本和截图位于 `/tmp/distributor-answer-qa*`。
