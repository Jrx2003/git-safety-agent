# Product Requirements

## 产品定位

GSA 是一个 **GitHub 协作安全代理**。

它服务于这样一种开发流程：

1. 开发者使用 Codex 或其他 coding agent 修改代码。
2. 修改完成后，开发者需要提交、推送、关联 issue、创建 PR、检查 PR 状态。
3. 这些 Git/GitHub 动作虽然看起来简单，但在多人协作里风险很高。
4. GSA 负责把这些动作变成安全、可确认、可审计的 workflow。

一句话：

> Codex 负责改代码，GSA 负责把改动安全送进 GitHub 协作流程。

## 背景问题

使用 Codex 时，常见问题不是“模型不会写代码”，而是“模型给出的 Git 命令是否该执行”。

典型风险包括：

- 直接 `git add .`，把临时文件、调试文件、密钥文件一起提交。
- 在错误分支上 commit 或 push。
- 推送到保护分支。
- 本地分支落后远端，push 后产生协作冲突。
- commit message 和 PR 描述没有关联 issue，reviewer 难以理解背景。
- PR 还没有通过 CI 或仍有 unresolved comments，却被误认为 ready。
- 操作过程没有结构化记录，事后无法解释做过什么。

## 目标用户

### 主要用户

- 使用 Codex / Claude Code / Cursor 等 coding agent 的个人开发者。
- 在 GitHub 上协作的工程师。
- 对 Git 命令不够自信，但需要安全提交和开 PR 的开发者。

### 次要用户

- 想要审计 agent 产出代码进入仓库过程的团队。
- 想把 GitHub 协作流程标准化的小团队。
- 需要将 agent 产出的本地改动纳入标准 GitHub 协作流程的团队。

## 核心价值

### 1. 把命令变成 workflow

GSA 不只是包装 `git` 或 `gh` 命令，而是把命令放入有前置检查、有风险解释、有确认门禁、有结果记录的流程里。

### 2. 把 GitHub 上下文引入本地操作

提交和 PR 不应该只基于本地 diff。GSA 应该读取 issue、PR、CI、review 状态，让本地动作和 GitHub 协作状态保持一致。

### 3. 把 agent 行为变得可审计

每次高风险操作都应该留下：

- 输入任务。
- 本地状态。
- GitHub 状态。
- 计划。
- 风险判断。
- 用户确认。
- 实际命令。
- 执行结果。

## 非目标

GSA 不做完整 coding agent。

明确不做：

- 不自动实现 GitHub issue。
- 不自动修复 CI 失败。
- 不自动解决 review comments。
- 不自动 merge PR。
- 不让 LLM 自由执行任意 shell。
- 不取代 GitHub MCP 或 `gh`，而是在它们之上组织安全 workflow。

这些边界能降低实现复杂度，也能让项目定位更清晰。

## MVP 需求

当前 MVP 以 React 工作台和任务级 FastAPI API 实现。所有写操作遵循：

1. 先生成 `WorkflowPlan`。
2. 前端展示风险和命令预览。
3. 用户勾选确认。
4. 执行接口重新读取 Git/GitHub 状态。
5. 状态不一致时拒绝执行，要求重新生成 plan。

LLM 只用于 commit/PR 文案辅助；Git/GitHub 判断和执行必须在无 LLM 时仍可用。

### Safe Commit

目标：把 Codex 改完的本地变更安全提交。

必须能力：

- 查看当前分支。
- 查看 `git status`。
- 查看 staged / unstaged diff。
- 检测敏感文件和明显临时文件。
- 生成 commit message。
- 允许用户选择要暂存的文件。
- dry-run 展示将执行的操作。
- 用户确认后执行 commit。

验收标准：

- 不会默认提交 `.env`、私钥、token 文件。
- 不会在没有 diff 时创建空提交。
- 不会在未确认时执行写操作。
- 会提示多主题改动是否需要拆分。

### Issue Branch

目标：从 GitHub issue 安全创建工作分支。

必须能力：

- 读取 issue 标题、编号、标签和描述摘要。
- 生成合法分支名。
- 检查工作区是否干净。
- 检查默认 base branch。
- 创建并切换分支。
- 在 session 中保存 issue 上下文。

验收标准：

- 脏工作区时不会直接切分支。
- 分支名不包含非法字符。
- 分支名能追溯 issue 编号。

### Safe Push And Draft PR

目标：把本地分支安全推送并创建 draft PR。

必须能力：

- 检查当前分支是否为保护分支。
- 检查 upstream 和远端分叉状态。
- 检查是否存在未提交改动。
- push 当前分支。
- 创建 draft PR。
- 生成 PR title/body。
- 关联 issue。

验收标准：

- 不会直接 push 到 `main`、`master`、`develop`。
- 分支落后远端时先阻止并解释风险。
- PR body 包含改动摘要和验证说明。

### PR Readiness

目标：判断 PR 是否可以交给 reviewer。

必须能力：

- 读取 PR 基本信息。
- 读取 CI 状态。
- 读取 review 状态。
- 读取 unresolved comments。
- 检查本地未提交/未推送改动。
- 输出 readiness report。

验收标准：

- CI 未通过时显示 blocked。
- 存在 unresolved comments 时显示 needs action。
- 本地有未推送 commit 时提示先 push。

### Secret Safety

目标：让本地 LLM 配置可用，但绝不把 key 暴露给前端、日志、trace、报告或文档。

必须能力：

- 后端读取 workspace `.env` 和当前进程环境。
- `GET /api/environment` 只返回 LLM 是否配置、模型、base URL、provider label。
- `.env`、`.env.*`、私钥、token 文件不能被文件预览、索引和 Safe Commit 默认选择；`.env.example` 只允许空占位。
- logger、trace、API response、CLI output、`changes.md`、`last_run_summary.json` 写出前统一脱敏。

验收标准：

- 仓库 tracked 文件中不出现真实 API key。
- UI 只显示 LLM 已配置/未配置，不显示 key。
- 模拟异常、payload、命令输出含 key 时会被替换为 `[REDACTED]`。

### Frontend Accessibility

目标：让工作台不用读 README 也能判断当前仓库是否可操作。

必须能力：

- 顶部展示 workspace、branch、dirty、GitHub 登录、LLM 配置状态。
- 左侧按 workflow 导航，主区展示任务，右侧展示风险、命令预览和结果。
- 所有表单控件有可见 label。
- 状态不能只靠颜色表达。
- 写操作按钮在未生成 plan、未确认或 plan 过期时 disabled。
- 错误区域使用 `role="alert"`，加载区域使用 `aria-busy`。
- 长 diff 和 trace 默认折叠或滚动，不造成页面横向溢出。

## 设计原则

### 默认保守

协作动作宁可多问一句，也不要猜测执行。

### 明确解释风险

用户确认前必须知道：

- 会改什么。
- 为什么有风险。
- 如果失败会怎样。
- 如何恢复。

### 不隐藏命令

GSA 可以自动执行，但应展示将要执行的 Git/GitHub 命令和影响范围。

### 工具受限

LLM 只能调用注册工具，不能自由 shell。

### 可审计优先

每次 workflow 都应生成 trace，便于问题复盘和团队审计。

## 成功指标

- 用户可以放心把 Codex 生成的本地改动交给 GSA 处理提交和 PR。
- 高风险 Git 操作都能被拦截或显式确认。
- PR 描述和 commit message 能准确关联 issue。
- 每次协作动作都有可读的执行摘要。
- 项目可以用真实 workflow 证明需求、边界、架构和安全策略是闭环的。
