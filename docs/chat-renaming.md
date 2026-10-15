# 历史聊天重命名

在左侧聊天列表点击某条聊天右侧的「⋯」，选择「重命名」，输入名称后保存。删除操作也收纳在这个菜单内，仍需确认。

## 行为

- 弹窗自动聚焦并选中原名称；支持回车保存、Escape 或取消关闭、Tab 循环和关闭后恢复焦点。
- 中文输入法选词时的回车不提交。首尾空白自动去除，名称须为 1–100 个 Unicode 码点，允许重名。
- 保存中禁用输入和重复操作；保存失败保留名称供重试。会话被删除时提示不存在，不重新创建。
- 更新成功后刷新列表；刷新浏览器和继续聊天均保留名称。
- 仅更新 `title`，保留会话 ID、历史消息、检索范围、范围版本和 `updated_at`，重命名本身不改变列表顺序。
- 旧会话无需迁移；旧的超长名称可以打开编辑，保存的新名称需符合长度要求。

## 接口与实现

`PATCH /api/conversations/{conversation_id}/title`

请求：`{"title":"月度销售分析"}`。成功返回更新后的会话；输入不合法返回 422，会话不存在返回 404。多个窗口同时修改同一标题时，后成功保存的名称生效。

请求校验位于 `backend/app/schemas/conversation.py`，路由位于 `backend/app/routers/conversations.py`，服务方法为 `ChatService.rename_conversation`。复用 JSON 存储的加锁字段合并，避免覆盖并发保存的检索范围或聊天时间。

前端由 `Sidebar.tsx` 管理菜单与当前编辑对象，`RenameConversationDialog.tsx` 管理输入和保存状态，`api/conversations.ts` 发送请求。菜单通过 portal 放入 body，避免被侧边栏滚动区域裁剪；过期的列表响应不会覆盖重命名后的状态。

后端进程需要重新启动以加载新增接口；前端开发服务支持热更新。

## 验证

- 后端：`cd backend && ../.venv/bin/python -m unittest discover -s tests -v`，70 项通过，包含 7 项新增重命名测试。测试使用临时目录。
- 前端：本次侧边栏及其依赖的严格 TypeScript 检查、全站 TypeScript/Vite 生产构建通过。期间工作区并行修改曾造成 `MessageList`/`AnswerCard` 属性不匹配，对应改动接齐后已重新构建通过。
- Edge/Playwright：隔离临时前后端上 10 组联调通过，1440×1000 和 390×844 验证菜单、弹窗、校验、保存、刷新、真实 SSE 续聊、404、500 重试及删除确认回归；额外验证键盘焦点循环和点击弹窗内边距不会关闭。
- Browser plugin not available，复用现有 Playwright 1.62.1，不安装依赖。测试数据、脚本和截图仅在 `/tmp/distributor-rename-qa*`，未修改真实知识库。无运行时异常或框架错误覆盖层；控制台只有故意注入的 500 和 404。
- 未验证 Safari、Firefox 和多个后端进程同时写入 JSON 的场景。
