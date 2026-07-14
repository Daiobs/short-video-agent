# Workbench Shell v1

## 目标与范围

Workbench Shell v1 将现有首页重组为本地“短视频拆解工作台”。本轮只调整入口、导航、状态展示和页面信息架构，不改写单作品解析、下载、Case 素材包、Creator Clone Runtime、任务执行或安全中间件。

分支基线：`origin/main` 的 `6d6d906`。基线测试为 `338 passed, 1 warning`。

## 信息架构

页面采用固定工作台外壳：

```text
workbench-shell
├── workbench-sidebar
│   ├── 主要工作流
│   ├── 高级工具 / 备用采集（默认折叠）
│   └── 未来模块（默认折叠）
└── workbench-main-shell
    ├── workbench-topbar
    ├── workbench-content
    └── AI 拆解助手
```

真实可用入口：

- 工作台
- 单作品拆解
- 创作者拆解
- 质量校准

本机 Chrome 辅助属于默认折叠的高级备用采集能力，不与主页扫描主力数据源并列展示。
抖音数据源、AI 能力和系统诊断统一从右上角设置按钮进入，不在侧栏和首页重复设置入口。
右上角齿轮位于路由面板之外，因此 `#workbench`、`#single`、`#profile` 三个页面共用同一个设置弹窗入口；AI 助手不再提供设置或 preflight 快捷按钮。

默认折叠的占位入口：

- 案例报告库
- 独立素材池
- Case 库
- 创作者样本库
- platform_lab 测试中心
- 拆解 Prompt 库

占位入口由 `workbench.js` 在浏览器内拦截，只显示“尚未接入”说明，不调用后端 API。

## 路由映射

| Hash | 页面 | 说明 |
| --- | --- | --- |
| `#workbench` | 工作台首页 | `/` 首次加载会规范化为 `/#workbench`，展示 4 步宏观流程 |
| `#single` | 单作品解析 | 保留原单作品表单、结果和 Case 流程 |
| `#profile` | Creator Clone Lab | 保留原有 6 步内部状态和恢复逻辑 |
| 空值或未知 Hash | 工作台首页 | 安全回退到 `#workbench` |

`workbench.js` 提供纯路由映射，`app.js` 继续负责切换现有业务面板、恢复 Creator Clone 状态和更新助手上下文。

## 4 步宏观流程

1. 素材导入：单作品、创作者主页、Douyin Cookie / Web API、作品链接、JSON/CSV 与已有 Case。
2. 证据富化：视频、关键帧、contact sheet、ASR、OCR、评论和指标快照。
3. 爆款拆解：钩子、画面、镜头、文案、人设、标题话题、转化与复用公式。
4. 克隆规则 / 复用输出：Creator Clone 报告、Strategy Generator、JSON、HTML/Markdown 报告和下一批拍摄方案。

这 4 步只展示能力和引导入口，不控制 Creator Clone 内部 6 步 Workflow。

## 状态接口

工作台复用现有接口：

- `GET /api/settings/preflight`
- `GET /api/settings/llm`
- `GET /api/settings/data-sources`

根据最新界面约束，顶部只保留“本地安全模式”和“LLM”两个状态徽标，以及设置按钮。ffmpeg、ffprobe、yt-dlp、ASR、OCR、Chrome 和数据源详情仍在设置弹窗的“本地工作流预检”与“抖音数据源”中展示，避免顶部状态条变成工具清单。

## 数据源主次

- 用户配置 Douyin Cookie 后，Cookie / Web API 是主页作品扫描的主力数据源。
- Cookie 未配置、失效或请求失败时，回退到公开扫描或手动作品链接。
- 本机 Chrome 辅助位于“高级工具 / 备用采集”，只读取页面可见作品列表和元数据。
- 工作台首页只读展示抖音数据源的配置与结构校验状态，不渲染 Cookie 原文或脱敏片段；修改配置和 API 自检统一使用右上角设置按钮。
- 本轮只修正产品语义和入口位置，不修改 `DataSourceManager`、Provider、数据库或任务执行逻辑。

预检支持单独刷新并显示最后刷新时间。状态值统一映射为：

- `ready`：可用
- `partial`：待确认或读取失败后的安全回退
- `missing`：缺失
- `disabled`：未启用
- 未知值：降级为 `partial`

任何单个状态接口失败都不会阻断首页、单作品或 Creator Clone 页面。

## AI 拆解助手

右下角助手是轻量导航抽屉，不调用大模型、不模拟聊天，也不会自动推进 Workflow。它只展示：

- 当前模块
- 当前宏观步骤
- 推荐下一步
- 单作品拆解、创作者拆解、质量校准和工作台快捷入口
- 当前已有 Prompt 或 Strategy Plan 的快捷操作

## 关键 DOM 兼容清单

本轮保留以下原有关键 ID：

- `single-form`
- `single-button`
- `profile-form`
- `profile-quick-input`
- `creator-clone-next-button`
- `profile-results-body`
- `job-card`
- `creator-clone-result-card`
- `creator-strategy-plan-card`
- `settings-modal`
- `settings-toggle`
- `profile-browser-helper-button`
- `profile-chrome-confirm`

## 安全边界

本轮未修改 `app/main.py`、local-only middleware、Chrome 一次性 token、页面确认或 handoff 校验。继续保持：

- 仅允许 loopback 访问
- 非本机 Host 被拒绝
- 写操作校验本机 Origin / Referer
- Chrome 辅助扫描需要一次性 token 和用户确认
- Douyin Cookie 由用户主动配置，仅保存在本机。
- 已保存 Cookie 不回显原文。
- Cookie 不进入数据库、素材包、Prompt 或日志。
- 本机 Chrome 辅助不读取 Cookie。
- API Key、登录 token 和签名媒体 URL 不写入页面或日志。

## 静态资源与响应式

- `workbench.js` 和 `app.js` 都使用带版本号的静态 URL。
- `workbench.js` 只包含工作台纯映射、侧栏折叠和 coming-soon 行为。
- 桌面端使用固定侧栏；约 1120px 以下切换为顶部信息架构区；720px 以下卡片和导航改为单列。
- 表格继续由原有可滚动容器承载。
- 尊重 `prefers-reduced-motion`，关闭非必要过渡和滚动动画。

## 验证记录

- `origin/main` 基线：`338 passed, 1 warning`
- Workbench Shell 分支：`340 passed, 1 warning`
- JavaScript 语法：`workbench.js`、`app.js` 均通过 Node `--check`
- 页面回归：默认 `#workbench`、`#single`、`#profile`、设置定向、侧栏折叠和 coming-soon 行为均有静态或纯 JavaScript 测试覆盖
- 安全回归：保存测试 Cookie 后，首页和数据源状态 API 均不返回完整值或哨兵片段
- 兼容检查：原关键 DOM ID 全部存在，Creator Strategy 区域仍存在，本机 Chrome 确认框仍存在
- 响应式检查：1024px 与 390px 视口无页面级横向溢出，手机端设置按钮与单作品表单可操作
- 浏览器控制台：无 error / warning

## 本轮未做

- 不新增素材库、Case 库或创作者样本库后端
- 不实现 platform_lab
- 不新增 Provider
- 不新增数据库表
- 不接入聊天 Agent
- 不新增自动发布、账号矩阵或养号功能
- 不拆分 Creator Clone Runtime 或 `app.js` 的核心业务代码

## v2 建议

1. 当工作台模块继续增加时，再将状态加载和助手上下文从 `app.js` 迁移到独立控制器。
2. 为素材库、Case 库和报告库设计统一只读索引后，再启用对应导航入口。
3. 将状态刷新时间、错误摘要和运行诊断统一为不含敏感字段的前端 ViewModel。
4. 在不改动业务状态机的前提下，为移动端增加显式侧栏开关和键盘焦点管理。
