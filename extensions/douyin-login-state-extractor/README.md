# Douyin Login State Extractor

这是 `short-video-agent` 的本地 Chrome Manifest V3 插件。它在用户主动点击后读取当前 Chrome 中适用于抖音 Web API 的 Cookie，并通过签名请求同步到本机服务。

插件不读取页面作品 DOM，不读取 `localStorage`，不观察 Network，不修改 Cookie，不绕过验证码或平台风控。

## 安装

1. 启动本机 `short-video-agent`，地址为 `http://127.0.0.1:8765`。
2. 打开 `chrome://extensions`。
3. 开启“开发者模式”。
4. 点击“加载已解压的扩展程序”。
5. 选择本目录：`extensions/douyin-login-state-extractor/`。
6. 在 Chrome 中正常登录抖音。

本插件没有 npm 依赖、构建步骤或远程脚本。

## 一次配对

1. 在 `short-video-agent` 设置页生成有效期不超过 10 分钟的配对码。
2. 打开插件，输入配对码并点击“配对”。
3. 配对成功后，共享密钥写入 `chrome.storage.local`。

除非用户主动重新配对、清除扩展数据或共享密钥失效，否则后续同步不需要再次输入配对码，也不需要为每个抖音主页重新授权。

插件调用：

```text
POST http://127.0.0.1:8765/api/local-login-state/pair/complete
```

请求：

```json
{
  "schema_version": 1,
  "pairing_code": "设置页生成的临时配对码",
  "extension_version": "1.0.0"
}
```

成功响应：

```json
{
  "ok": true,
  "pairing": {
    "paired": true,
    "shared_key": "32 字节随机值的无填充 base64url 编码",
    "schema_version": 1
  }
}
```

插件不会保存配对码。

## 获取与同步

“获取环境 + 登录状态”会调用：

```javascript
chrome.cookies.getAll({
  url: "https://www.douyin.com/aweme/v1/web/aweme/post/"
})
```

获取后执行以下约束：

- 只保留 Cookie `domain` 严格等于 `douyin.com` 或 `.douyin.com` 的记录；
- Cookie name 必须符合安全 token 格式；
- Cookie value 不得包含控制字符或分号；
- 保留 Chrome 返回顺序；
- 最多 256 条；
- 生成的 Cookie Header 最大 32 KiB；
- `HttpOnly` Cookie 不会被排除；
- Cookie 只短暂保存在 Popup 内存，关闭 Popup 即释放；
- Popup 只显示 `********`、字段数量和登录态字段数量，不显示原文。

同步端点：

```text
POST /api/local-login-state/douyin/sync
```

请求体：

```json
{
  "schema_version": 1,
  "cookie_header": "name=value; name2=value2",
  "user_agent": "Chrome User-Agent",
  "referer": "https://www.douyin.com/",
  "captured_at": "ISO-8601",
  "pair_count": 0,
  "login_key_count": 0,
  "extension_version": "1.0.0"
}
```

`pair_count` 是通过过滤且进入 Cookie Header 的字段数量。请求体不得超过 64 KiB。

## HMAC-SHA256 合同

同步和清除请求使用共享密钥签名。状态接口只返回脱敏状态，不需要签名。每次签名请求生成 16 字节随机 nonce，并使用 Unix 秒级时间戳。后端返回的 `shared_key` 先按无填充 base64url 解码成 32 字节 HMAC key。

Canonical message：

```text
timestamp
nonce
原始 JSON 请求体
```

DELETE 没有请求体时，最后一行为空。HMAC 结果使用小写十六进制。

请求头：

```text
X-SVA-Schema-Version: 1
X-SVA-Extension-Version: 1.0.0
X-SVA-Timestamp: 1780000000
X-SVA-Nonce: 32 位十六进制随机值
X-SVA-Signature: HMAC-SHA256 十六进制值
```

后端应拒绝：

- 时间偏差超过 60 秒；
- 重复 nonce；
- 错误 HMAC；
- schema 或扩展版本不兼容；
- 非 localhost 请求；
- 大于 64 KiB 的正文；
- 重定向请求。

插件对本机 API 使用 `redirect: "error"`、`credentials: "omit"` 和 `cache: "no-store"`。

## 状态与清除

状态：

```text
GET /api/local-login-state/status
```

清除本机保存的抖音登录状态：

```text
DELETE /api/local-login-state/douyin
```

“清除本机登录状态”只删除 `short-video-agent` 持久化的登录状态，不删除或修改 Chrome Cookie，也不会退出 Chrome 中的抖音账号。清除后配对仍然有效，可以再次获取和同步。

“重新配对”只清除插件本地的共享密钥和最近同步时间。之后需要在设置页重新生成配对码。

## Storage 合同

`chrome.storage.local` 只保存：

```text
pairing_shared_secret
last_synced_at
```

以下内容绝不进入插件 storage：

- Cookie Header；
- 单个 Cookie；
- User-Agent；
- Referer；
- 配对码；
- API 响应正文。

## 权限说明

插件权限严格为：

```text
cookies
storage
activeTab
```

Host permissions 严格为：

```text
https://www.douyin.com/*
https://*.douyin.com/*
http://127.0.0.1:8765/*
```

插件不申请 `<all_urls>`、`history`、`debugger`、`webRequest`、`clipboardRead` 或 `tabs` 权限。

## 威胁模型

- 插件仅连接固定的 `127.0.0.1:8765`，不把登录状态发送到远程服务器。
- 共享密钥用于 HMAC，不放进页面 DOM，也不返回给 Popup。
- timestamp 与 nonce 防止旧同步请求被重复播放。
- Cookie 原文不展示、不复制、不记录日志、不进入 Git。
- 本机后端负责将 Cookie 保存到仓库外安全凭据文件，并保证 `0600`、原子替换、拒绝符号链接。
- 如果本机电脑、Chrome Profile 或扩展上下文本身已被恶意软件控制，本插件无法提供额外隔离。

## 自测

无需安装依赖：

```bash
node --check service-worker.js
node --check popup.js
node --check lib/constants.mjs
node --check lib/cookie-security.mjs
node --check lib/signing.mjs
node self-test.mjs
```

真实同步需要先由后端实现本 README 中的本地 API 合同，再由用户手动加载扩展、完成配对并点击同步。
