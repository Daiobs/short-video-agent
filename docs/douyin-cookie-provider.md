# Douyin Personal-Cookie Provider

本文记录个人账号 Douyin Cookie 驱动主页扫描的正式合同、当前实现和安全边界。它是维护与审查文档，不是规避平台校验的操作指南。

## 定位

主页扫描正式主路径为：

```text
用户主动配置个人账号 Cookie
→ Douyin Cookie Web API Provider
→ 有界分页取得本人有权分析的公开作品元数据
```

安全兜底为作品链接、结构化 JSON/CSV 和已有 Case。既有公开页面扫描可以作为自动的非登录回退；既有 Chrome 辅助仍是用户显式触发的高级工具，不读取 Cookie，也不接入 Cookie Provider 主链路。

Stage E 已取消。本项目不开发浏览器 Cookie 自动读取、本地连接器扩展、签名破解、验证码处理、反爬规避或批量账号系统。

## 架构审计

### 保存位置

- 设置页面保存到项目根目录的 `.local_settings.json`，位于 `douyin` section；该文件已被 Git 忽略。
- `DOUYIN_COOKIE`、`DOUYIN_USER_AGENT`、`DOUYIN_REFERER` 可作为本机环境变量默认值。
- 页面保存值优先于环境变量；两者都只属于本机运行时配置。
- Cookie 指纹只用于同一份本机设置文件中的健康状态关联，不包含可还原值。

Cookie 不写入 SQLite、Job、Creator `samples.json`、Case、Prompt、报告、日志或浏览器存储。

### 数据流

```text
设置弹窗
→ PUT /api/settings/data-sources/douyin
→ 格式和登录态字段校验
→ .local_settings.json
→ effective_douyin_settings()
→ DataSourceManager
→ DouyinCookieProfileProvider
→ 仅允许的 Douyin HTTPS Web API
```

只读状态接口 `GET /api/settings/data-sources` 只返回是否配置、固定掩码和字段名级诊断。`POST /api/settings/data-sources/douyin/test` 最多读取 5 条，只做一次有界自检，不创建 Job。

### Provider 顺序

1. 请求显式包含多作品链接时，使用 `manual_links`，不读取 Cookie。
2. 请求显式包含 JSON/CSV 时，使用 `structured_items`，不读取 Cookie。
3. `PROFILE_SCAN_PROVIDER=external_api` 时只进入显式预留 Provider；当前不会调用未授权第三方服务。
4. 默认使用 `cookie_api`。
5. Cookie 主路径失败后，可尝试既有公开 HTML Provider；成功时结果明确标记 `fallback_used=true` 和安全错误码。
6. 公开回退也失败时，保留 Cookie 主路径的公开错误分类，并提示作品链接、JSON/CSV 或已有 Case。

已有 Case 导入不经过主页 Provider。Chrome 辅助不会被 Cookie 失败自动启动。

## Cookie 合同

设置和请求前会：

- 去除首尾空白，并兼容用户粘贴的 `Cookie:` 前缀；
- 按 `key=value` 解析，忽略空分隔项；
- 拒绝无等号、非法 key、空 value、重复 key；
- 拒绝明显占位值；
- 限制总长度为 32,768 字符、字段数为 256；
- 要求至少包含一个 session key，并至少识别两个登录态字段；
- 只公开字段名和计数，不公开任何 value。

格式或登录态字段不足时不会发起远端请求。Cookie 只允许发送到 `https://www.douyin.com` 的内置 Web API 路径。配置的 Referer 必须是 Douyin HTTPS 地址，并在请求前去除 query 和 fragment；否则使用 `https://www.douyin.com/`。

状态响应允许的 Cookie 信息为：

```json
{
  "has_cookie": true,
  "masked_cookie": "********",
  "pair_count": 5,
  "login_key_count": 5,
  "present_important_keys": ["sessionid", "sid_guard"],
  "missing_login_keys": []
}
```

固定掩码不包含原值前缀、后缀或长度信息。

## 请求、分页与截断

当前内置 API 候选最多两个；只有首个端点返回 404/405 时才尝试兼容端点。任何请求都使用 `follow_redirects=False` 和 `trust_env=False`。

分页限制：

| 项目 | 默认值 | 硬上限 |
| --- | ---: | ---: |
| 单页作品数 | `PROFILE_SCAN_COUNT_PER_PAGE=20` | 50 |
| 最大页数 | `PROFILE_SCAN_MAX_PAGES=10` | 20 |
| 单次目标作品数 | 调用方设置，页面通常最多 150 | 200 |
| 连续无新增页面 | 2 | 2 |

请求未显式提供 `max_pages` 时使用配置值。作品按稳定 `aweme_id` 去重；单条坏记录只增加 `invalid_item_count`，不丢弃整页。

以下情况立即停止分页：

- 已达到目标作品数或页数上限；
- 空页；
- `has_more` 或 cursor 缺失、非法；
- cursor 重复；
- 连续两页没有新增作品；
- 后续页发生安全分类后的上游错误。

已经取得作品时返回 partial 结果，不因后续页失败丢弃前页。安全元信息包含：

```json
{
  "page_count": 1,
  "item_count": 20,
  "duplicate_count": 0,
  "invalid_item_count": 0,
  "retry_count": 0,
  "partial": true,
  "truncated_reason": "page_limit",
  "truncated_error_code": "DOUYIN_PAGE_LIMIT_REACHED"
}
```

## 有界重试

- 单次 HTTP timeout：8 秒。
- 每页最多 2 次请求，即最多 1 次重试。
- 退避：第一次重试前 150ms。
- 只重试网络错误、timeout、429 和 5xx。
- 不重试未配置/无效 Cookie、登录失效、403、HTML/非 JSON、JSON 合同错误和分页错误。
- 404/405 不做同端点重试，只允许尝试一个内置兼容端点。

没有后台无限重试，也不会自动修改 Cookie。

## 公开错误分类

| 错误码 | 含义 | 建议动作 |
| --- | --- | --- |
| `DOUYIN_COOKIE_NOT_CONFIGURED` | 未配置个人 Cookie | 本机设置中配置，或使用安全兜底 |
| `DOUYIN_COOKIE_INVALID` | 格式、重复字段、空值、占位值或长度不合法 | 人工重新复制完整 Cookie |
| `DOUYIN_LOGIN_REQUIRED` | 需要有效登录态或返回登录页 | 人工更新 Cookie |
| `DOUYIN_AUTH_EXPIRED` | 401 或明确登录态过期状态 | 人工更新 Cookie |
| `DOUYIN_UPSTREAM_REDIRECT` | 非登录的意外跳转 | 停止请求并检查输入/平台状态 |
| `DOUYIN_UPSTREAM_NON_JSON` | 200 但 content type 非 JSON | 稍后重试或使用兜底 |
| `DOUYIN_UPSTREAM_RATE_LIMITED` | 429 | 稍后人工重试 |
| `DOUYIN_UPSTREAM_FORBIDDEN` | 403 | 检查权限和 Cookie，不自动重试 |
| `DOUYIN_UPSTREAM_TIMEOUT` | 有界请求超时 | 稍后人工重试 |
| `DOUYIN_UPSTREAM_UNAVAILABLE` | 网络、5xx 或其他 HTTP 不可用 | 稍后重试或使用兜底 |
| `DOUYIN_RESPONSE_INVALID` | 空响应、损坏 JSON 或合同变化 | 检查平台接口变化 |
| `DOUYIN_PAGINATION_INVALID` | 分页字段或 cursor 无效 | 停止分页；有前页时返回 partial |
| `DOUYIN_PAGE_LIMIT_REACHED` | 达到页数或作品上限 | 当前结果为 partial |
| `DOUYIN_NO_PUBLIC_WORKS` | API 没有返回公开视频 | 检查账号可见性或使用其他导入方式 |

公开响应只允许安全错误码、固定说明、HTTP 状态、content type、跳转布尔值、页数、作品数、去重/坏记录数、重试数和截断原因。原始 HTML、响应正文、上游 message、完整 URL、请求头和内部异常不会返回。

## 日志和泄漏边界

Cookie Provider 结构化日志只允许：

```text
provider
provider_event
error_code
status_code
content_type
redirected
page_count
item_count
duplicate_count
invalid_item_count
partial
truncated_reason
retry_count
```

日志不记录 Cookie、请求头、响应正文、上游 URL query、异常原文或本机路径。Profile Job 失败只保存公开错误和经过 allowlist 过滤的 diagnostics；意外异常使用固定用户提示。

## 自检与人工更新

自检必须由用户点击触发，目标数硬限制为 5。它返回是否配置、字段计数、HTTP 状态、content type、错误码、是否跳转、重试数和作品数；不返回 Cookie 或上游正文，也不创建 Creator Job。

Cookie 过期时：

1. 用户在自己已登录且有权使用的抖音会话中人工取得新的 Cookie；
2. 在本机设置弹窗粘贴并保存；
3. 输入主页 URL 或 `sec_user_id`，执行一次小规模自检；
4. 自检失败后停止重复请求，改用作品链接、JSON/CSV 或已有 Case。

如果本机没有配置 Cookie，真实冒烟记录为：

```text
LIVE_SMOKE_NOT_RUN_NO_COOKIE
```

如果诊断为登录态过期，记录 `LIVE_SMOKE_AUTH_EXPIRED` 后停止，不循环测试。

## 已知限制

- Douyin Web API 是平台非稳定公开合同，字段和可见作品范围可能变化。
- API 返回数量可能少于主页展示数量；隐藏、权限受限、广告或接口不可见作品不会被伪造补齐。
- partial 结果只代表已安全取得的部分数据，不承诺主页完整镜像。
- 本项目不生成 Web API 签名，不绕验证码或风控；需要这些能力时应停止，而不是扩展当前 Provider。
- Cookie 必须由用户自行维护，系统不会从浏览器自动读取、刷新或同步。
