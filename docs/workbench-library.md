# Workbench Asset Library v1

Stage C 为 short-video-agent 增加一个只读的本地资产库，用来浏览已经生成的单作品 Case、创作者蒸馏报告和 Creator Strategy Plan。资产库不是任务执行器，也不是新的报告真源。

## 页面与接口

- 页面：`GET /library`
- 只读索引：`GET /api/library/assets`
- 首页入口：Workbench 任务控制台的“打开资产库”
- Case 打开入口：`/cases/{case_id}`
- Creator 报告打开入口：既有 `creator_clone.html` 或 `creator_clone.md` 安全文件路由
- Creator 上下文入口：返回 `/#profile`，再交给 Stage B 的精确恢复逻辑打开既有 `export` 阶段

资产库的“返回 Creator”只在资产库确认对应目录存在、且 `samples.json` 可安全读取时提供，并在当前浏览器会话中暂存经过白名单校验的恢复目标。报告文件存在但 Creator 上下文不可恢复时，只提供直接报告入口。该入口不会创建 Job、重新扫描、富化、蒸馏或修改 Runtime 状态。

## 统一资产 DTO

列表接口的每项固定为：

```json
{
  "asset_id": "",
  "asset_type": "case | creator_report | strategy_plan",
  "title": "",
  "creator_name": "",
  "platform": "",
  "status": "ready | incomplete | missing | stale",
  "created_at": "",
  "updated_at": "",
  "quality_score": null,
  "confidence": "",
  "sample_count": 0,
  "selected_count": 0,
  "open_url": "",
  "resume_target": {},
  "available_files": []
}
```

列表 DTO 不包含报告正文、Prompt、ASR/OCR 全文、Cookie、API Key、Token、请求头、签名 URL或本机绝对路径。`open_url` 只允许既有 Case 和 Creator 报告内部路由。

## 真源与派生关系

| 资产类型 | 真源 | 索引读取内容 | 不读取或不执行 |
| --- | --- | --- | --- |
| Case | SQLite `case_artifacts`、`local_video_items`、`douyin_video_items` 与 `outputs/cases/{case_id}` | 标识、标题、作者、时间、状态、已知产物存在性和安全质量摘要 | 不读取视频/图片正文，不调用 ffmpeg，不重新分析 |
| Creator Report | Creator Runtime `sessions.json` 与 `outputs/creator_clones/{set_id}` | set 标识、样本计数、报告文件存在性、更新时间和安全质量摘要 | 不复制报告正文，不调用 LLM，不重新蒸馏 |
| Strategy Plan | `creator_strategy_plan.json` 与对应 Creator Report | 文件存在性、更新时间和数值型质量摘要 | 不生成新方案，不建立独立详情真源 |

索引在请求时从现有真源重建，不新增数据库表，也不保存不可重建的数据副本。
为避免连续筛选和翻页重复扫描相同元数据，进程内保留最长约 30 秒的可重建快照；“刷新索引”会显式清除此快照。缓存不是唯一数据来源，进程重启或删除缓存不会丢失资产。

## API 合同

`GET /api/library/assets` 支持：

- `type=case|creator_report|strategy_plan`
- `status=ready|incomplete|missing|stale`
- `query`：仅匹配标题、创作者名和 `asset_id`
- `date_from`、`date_to`：按资产更新时间筛选
- `page`：从 1 开始
- `page_size`：默认 20，最大 100

响应包含分页、全局类型/状态 facets、来源级错误和截断元信息。单一来源失败时仍返回其他来源；所有正常和显式错误响应使用 `Cache-Control: no-store`。

## 状态语义

- `ready`：核心资产存在且可从既有安全路由打开。
- `incomplete`：核心对象存在，但部分派生产物或元数据缺失/无效。
- `missing`：数据库或 Runtime 仍有索引，但核心文件已经缺失。
- `stale`：Strategy Plan 的文件更新时间早于对应 Creator Report，只提示可能陈旧。

`stale` 不会触发重建、创建 Job 或回写任何状态。

## 安全边界

- `case_id`、`set_id` 和 `asset_id` 使用固定格式白名单。
- 文件读取限定在配置的 Case / Creator 根目录内；越界路径和符号链接被拒绝。
- JSON 读取有单文件大小和单请求总预算。
- 公开文本统一清除 Cookie、Authorization、Bearer Token、API Key、OpenAI 风格 Key、外部 URL 和本机路径。
- 列表不返回临时媒体 URL、签名 URL、完整请求头或原始 Job JSON。
- 页面使用 `textContent` 渲染可变元数据，不把后端文本作为 HTML 注入。
- 资产库不调用 Provider、LLM、ffmpeg 或任何外部服务。

## 性能上限

- Case：最近 2,000 条数据库记录。
- Creator Runtime：最近 2,000 条会话记录。
- Creator 目录：最多检查 10,000 个目录项，并索引最近 2,000 个安全目录。
- API：每页默认 20，最大 100。
- Runtime 索引：最大 4 MiB。
- `samples.json`：最大 1 MiB。
- Creator / Case 结果 JSON：最大 2 MiB。
- Strategy Plan：最大 1 MiB。
- HTML / Markdown 报告存在性检查：最大 8 MiB。

达到上限时响应会设置 `meta.partial=true` 并列出 `truncated_sources`。资产库只 stat 媒体文件，不读取视频或图片正文。

## 已知限制

- v1 不提供资产删除、重命名、移动、标签或全文检索。
- 关键词不搜索报告、Prompt、ASR、OCR 或评论全文。
- Strategy Plan 的 stale 判断只比较文件更新时间，不能证明语义版本完全一致。
- 早于单源上限的历史记录可能不展示；页面会显示非阻断式部分结果提示。
- v1 不为 Strategy Plan 新建独立详情页，只恢复到 Creator 的 `export` 阶段。
- Creator 报告只在已有 HTML 或 Markdown 文件时提供直接打开入口。
- Runtime 记录或报告文件本身不能证明 Creator 上下文可恢复；缺失、损坏、超大或不可读取的 `samples.json` 会关闭“返回 Creator”，但不会隐藏仍可安全打开的报告。

## Stage D 入口条件

只有在 Stage C Draft PR 完成人工审查、合并到 `main`，且完整 Python/JavaScript/HTTP/响应式回归通过后，才允许从最新 `main` 新建 Stage D 分支。Stage D 只负责前端模块拆分，不改变本页资产真源和只读合同。
