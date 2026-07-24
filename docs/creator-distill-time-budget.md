# Creator Distill Time Budget

## 目标

创作者蒸馏使用同一个单调时钟 deadline 贯穿业务层、执行层和 LLM Provider。任何兼容请求或精简重试只能消费剩余预算，不能重新获得完整 timeout。

## 请求上限

- 成功路径：1 个逻辑请求，通常 1 个 HTTP 请求。
- `response_format` 明确不兼容：同一逻辑请求最多 2 个 HTTP 请求。
- 精简重试路径：最多 2 个逻辑请求；两次逻辑请求及其 HTTP 请求共享同一 deadline。
- 429、401/403、明确额度不足：1 个逻辑请求，立即停止。

旧路径可能形成“外层重试 × 执行层 schema 重试 × Provider 兼容回退”的请求放大。当前网页蒸馏将执行层固定为一次尝试，外层只对白名单错误执行一次精简重试。

## 默认总预算

| 模式 | 总墙钟预算 |
| --- | ---: |
| 单次请求 | 180 秒 |
| quick | 360 秒 |
| deep | 600 秒 |
| Batch Job | 600 秒 |
| Final Reduce 最低预留 | 120 秒 |
| 精简重试最低剩余 | 60 秒 |

单请求 timeout 仍可设置得更低。默认 quick 路径允许一次最多 180 秒的主请求，并在可恢复错误发生且剩余预算充足时，用共享总预算执行一次精简重试。Prompt 长度、样本数和已知视频时长用于诊断和批次规划，不自动提高总预算。

## 错误语义

- `LLM_RATE_LIMITED`：429，不重试。
- `LLM_AUTH_FAILED`：401/403，不重试。
- `LLM_QUOTA_EXCEEDED`：明确余额或配额不足，不重试。
- `LLM_GATEWAY_TIMEOUT`：408、504、客户端 timeout 或 deadline 耗尽。
- `LLM_UPSTREAM_UNAVAILABLE`：502、503 或传输错误。
- `LLM_RESPONSE_INVALID`：响应不是合法 JSON。

公开诊断只包含状态码、Provider、阶段、逻辑/HTTP 尝试次数、是否允许重试和是否使用 `response_format` 回退。不得包含 Key、Authorization、Prompt、网关正文或本机路径。

## Batch 行为

每批开始前重新计算：

```text
可供批次使用的预算 = 剩余总预算 - Final Reduce 预留
本批预算 = min(单批上限, 可用预算 / 剩余批次数)
```

预算不足时停止创建新的外部请求，保留已成功批次并生成本地汇总。Manifest 使用 `completed`、`partial`、`budget_exhausted`、`rate_limited` 或 `auth_failed` 表达最终状态。

## 验证边界

测试使用 fake Provider 和 fake monotonic clock，不执行真实等待。未获得用户对真实网关 smoke test 的单独授权：

```text
LIVE_LLM_SMOKE_NOT_RUN
```
