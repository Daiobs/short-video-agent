# Douyin Login State Extractor

`Douyin Login State Extractor` 是 short-video-agent 的本机 Chrome Manifest V3 扩展。它解决的是登录状态同步，而不是页面采集：

```text
在 Chrome 登录抖音
→ 用户主动点击扩展获取 Douyin Cookie、User-Agent、Referer
→ 用户确认同步到 127.0.0.1:8765
→ short-video-agent 后续复用已保存登录状态扫描任意主页
```

扩展不读取作品 DOM，不读取 Network 或 localStorage，不绕验证码、不破解签名，也不会为每个主页重复授权。

## 安装

1. 启动 short-video-agent：

   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
   ```

2. 在 Chrome 打开 `chrome://extensions`。
3. 开启“开发者模式”。
4. 点击“加载已解压的扩展程序”。
5. 选择：

   ```text
   extensions/douyin-login-state-extractor/
   ```

6. 把扩展固定到浏览器工具栏。

扩展不使用 npm、Webpack、Vite 或远程脚本，仓库中的目录就是可加载版本。

## 一次配对

1. 打开 short-video-agent，点击右上角设置。
2. 在“Chrome 登录状态同步”中点击“生成配对码”。
3. 打开扩展，在十分钟内输入八位配对码。
4. 点击“完成配对”。

配对成功后，扩展只在 `chrome.storage.local` 中保存：

- HMAC 共享密钥；
- 服务地址；
- 配对状态；
- 最近同步时间。

扩展不在 storage 中保存 Cookie、User-Agent 或 Referer。除非重新安装扩展、清除扩展存储或主动重新配对，否则配对只需执行一次。

## 同步登录状态

1. 在 Chrome 中登录你自己的抖音账号。
2. 点击扩展。
3. 点击“1. 获取环境 + 登录状态”。
4. 检查安全预览：
   - Cookie 始终显示为 `********`；
   - 字段数量；
   - 登录态字段数量；
   - User-Agent；
   - 目标域名；
   - Referer。
5. 点击“2. 同步到 short-video-agent”。

同步成功后，设置页会显示：

- 来源：`Chrome 扩展同步`；
- Cookie：`********`；
- 字段数量和登录态字段数量；
- 最近同步时间；
- Cookie API 健康状态。

之后输入其他抖音主页 URL 时直接复用，不需要再次配对或逐主页确认。

## Cookie 保存位置

插件同步凭据保存到：

```text
~/.short-video-agent/credentials.json
```

安全约束：

- 文件位于仓库外；
- 目录权限为 `0700`；
- 文件和临时文件权限为 `0600`；
- 写入时执行 `fsync`；
- 使用 `os.replace` 原子替换；
- 拒绝符号链接；
- Cookie 不写入 `.local_settings.json`。

`.local_settings.json` 只记录凭据指纹、字段数量、扩展版本和最近同步时间，不包含 Cookie 或共享密钥。

设置页的手工 Cookie 兼容入口也使用同一个安全凭据文件。旧版本曾写入 `.local_settings.json` 的手工 Cookie 会在首次读取时迁移到 `credentials.json`，成功后原位置只保留状态、指纹和更新时间。

## 过期与切换账号

Cookie 过期时：

1. 在 Chrome 中重新登录抖音；
2. 点击扩展“获取环境 + 登录状态”；
3. 再次点击同步。

不需要重新配对。

切换账号时也使用相同步骤。新同步会原子替换旧登录状态。

## 重新配对

出现以下情况时使用“重新配对”：

- 扩展被重新安装；
- 扩展存储被清空；
- 共享密钥失效；
- 希望轮换共享密钥。

在设置页重新生成配对码，再在扩展中完成配对。完成前，旧共享密钥不会因为生成配对码而立即失效；新配对成功后才原子替换。

## 清除凭据

扩展中的“清除本机登录状态”会向本机服务发送经过 HMAC 验证的删除请求：

- 删除插件同步的 Douyin Cookie、User-Agent 和 Referer；
- 保留配对关系；
- 不删除手工 Cookie 或环境变量；
- 如果存在手工 Cookie，Provider 自动回退到手工配置。

若要删除全部配对信息，停止服务后删除：

```text
~/.short-video-agent/credentials.json
```

然后在设置页重新配对。

## 权限说明

Manifest 只申请：

```text
cookies
storage
activeTab
```

Host 权限只包含：

```text
https://www.douyin.com/*
https://*.douyin.com/*
http://127.0.0.1:8765/*
```

扩展不会申请：

```text
<all_urls>
history
debugger
webRequest
clipboardRead
```

Cookie 通过以下限定查询读取：

```javascript
chrome.cookies.getAll({
  url: "https://www.douyin.com/aweme/v1/web/aweme/post/"
})
```

随后再次过滤 `douyin.com` / `.douyin.com` 域、Cookie 名称、数量和总长度。

## 本机同步协议

配对接口：

```text
POST /api/local-login-state/pair/start
POST /api/local-login-state/pair/complete
```

状态与同步接口：

```text
GET    /api/local-login-state/status
POST   /api/local-login-state/douyin/sync
DELETE /api/local-login-state/douyin
```

同步和删除请求使用 HMAC-SHA256。签名输入固定为：

```text
timestamp + "\n" + nonce + "\n" + raw_request_body
```

服务端要求：

- timestamp 与当前时间偏差不超过 60 秒；
- nonce 符合安全格式且只能使用一次；
- 请求体不超过 64 KiB；
- Cookie Header 不超过 32 KiB；
- Cookie 不超过 256 条；
- schema version 和扩展版本受支持；
- 请求来自 loopback；
- Cookie、共享密钥和签名不进入响应或日志。

## 威胁模型

本功能防护：

- 远程客户端访问本机同步 API；
- 第三方网页直接发起写请求；
- 错误或过期配对码；
- 伪造 HMAC；
- 过期请求；
- nonce 重放；
- 超大请求；
- Cookie Header 注入；
- 非 Douyin Referer；
- 符号链接覆盖；
- 非原子凭据写入；
- Cookie 在页面、API 状态、Job、Case、Creator 产物或 Git 中泄漏。

本功能不承诺：

- 绕过抖音验证码、风控或账号权限；
- 保证平台私有 Web API 永久稳定；
- 替用户判断内容分析、下载或使用授权；
- 抵御已经控制本机用户账号和文件系统的恶意程序。

当 Cookie API 返回登录失效、限流或平台结构变化时，系统返回安全错误码并停止，不反复请求。

## 插件不做什么

- 不读取页面作品 DOM；
- 不扫描创作者主页；
- 不下载视频；
- 不读取浏览历史；
- 不读取其他域 Cookie；
- 不读取 localStorage；
- 不读取或监听 Network；
- 不修改浏览器 Cookie；
- 不复制 Cookie 到剪贴板；
- 不调用外部服务；
- 不执行远程代码。
