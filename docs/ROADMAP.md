# Roadmap

路线图围绕一个原则：先把真实 GitHub 协作需求做扎实，再考虑通用 agent 能力。

## Phase 0：本地安全执行原型

已完成。本阶段验证了 safety policy、dry-run、确认和 trace。

已有能力：

- 自然语言生成结构化 plan。
- Git / File / Index 工具。
- 风险等级和确认机制。
- 危险 Git 操作拦截。
- workspace 文件 sandbox。
- CLI / UI / API。
- JSONL trace 和运行摘要。
- 规则规划评测。

## Phase 1：需求和文档重定位

已完成。目标是把项目从“Git 安全工具原型”重定位为“GitHub 协作安全代理”。

任务：

- 重写 README。
- 新增产品需求文档。
- 新增用户场景文档。
- 新增设计背景和架构取舍文档。
- 新增路线图。

完成标准：

- 能清楚讲出 GSA 做什么、不做什么。
- 能解释为什么不做完整 coding agent。
- 能解释 GSA 和 GitHub MCP 的关系。

## Phase 2：Safe Commit Workflow

已实现 MVP。目标：让用户可以放心提交 Codex 生成的本地改动。

新增能力：

- `gsa commit-plan`：生成提交计划。
- `gsa commit`：确认后执行提交。
- diff 摘要。
- 敏感文件扫描。
- 临时文件和构建产物提示。
- commit message 生成。
- 文件选择和分组建议。

当前实现：

- `src/gsa/workflows/safe_commit.py`
- React Safe Commit 页面。
- CLI `gsa commit-plan` 和 `gsa commit --yes`。
- 执行前重新校验 branch、HEAD 和 status signature。

验收场景：

- 空暂存区不能 commit。
- `.env` 不能被默认提交。
- `git add .` 需要显式确认。
- 多主题 diff 会给拆分建议。

## Phase 3：Issue Branch Workflow

已实现 MVP。目标：从 GitHub issue 安全创建工作分支。

新增能力：

- 通过 `gh issue view` 或 GitHub MCP 读取 issue。
- 生成合法分支名。
- 检查默认 base branch。
- 检查工作区是否干净。
- 创建并切换分支。
- 保存 issue brief 到 session memory。

当前实现：

- `src/gsa/github/gh.py` 使用 `gh issue view --json`。
- `src/gsa/workflows/issue_branch.py`。
- React Issue Branch 页面。
- CLI `gsa issue-branch <issue> --yes`。

验收场景：

- issue 不存在时清晰报错。
- 脏工作区时拒绝切分支。
- 分支名包含 issue 编号。
- 已存在同名分支时给出复用或改名选项。

## Phase 4：Safe Push And Draft PR

已实现 MVP。目标：安全推送当前分支并创建 draft PR。

新增能力：

- 检查保护分支。
- 检查 upstream。
- 检查 ahead/behind。
- 检查当前分支是否已有 PR。
- push 当前分支。
- 创建 draft PR。
- 自动生成 PR body。

当前实现：

- `src/gsa/workflows/push_pr.py`。
- 检查保护分支、dirty、ahead/behind、已有 PR。
- React Push & Draft PR 页面。
- CLI `gsa push-pr --draft --yes`。

验收场景：

- 拒绝 push 到 `main` / `master` / `develop`。
- 分支落后远端时阻止 push。
- 已有 PR 时不重复创建。
- PR body 包含 validation 和 related issue。

## Phase 5：PR Readiness Workflow

已实现 MVP。目标：判断 PR 是否可以请求 review。

新增能力：

- 获取 PR 状态。
- 获取 CI/checks 状态。
- 获取 review 状态。
- 获取 unresolved comments。
- 检查本地未提交/未推送改动。
- 输出 readiness report。

当前实现：

- `src/gsa/workflows/pr_readiness.py`。
- `gh pr view`、`gh pr checks` 和 GraphQL review thread 读取。
- React PR Readiness 页面。
- CLI `gsa pr-ready [pr]`。

验收场景：

- CI 失败时显示 blocked。
- unresolved comments 存在时显示 needs action。
- 本地未推送提交会提示 push。
- 全部通过时建议 request review。

## Phase 6：审计和回放

已实现基础版。目标：让每次协作 workflow 可复盘。

新增能力：

- session timeline。
- 每个 workflow 的输入、状态、计划、确认、命令、结果。
- GitHub 链接记录。
- `gsa trace show <trace_id>`。
- `gsa trace show <trace_id>`。

后续增强：

- trace export。
- timeline 可视化。
- 团队审计报告。

验收场景：

- 能解释一次 PR 是如何创建的。
- 能看到用户确认了哪些高风险动作。
- 能定位失败发生在哪一步。

## 暂不做

这些能力暂时不进入路线图：

- 自动实现 issue。
- 自动修 CI。
- 自动改 review comments。
- 自动 merge。
- 多 agent coding。
- 任意 shell 执行。

原因：这些会把 GSA 推向完整 coding agent，偏离“GitHub 协作安全代理”的核心定位。

## 里程碑建议

### 下一步优先级

优先完成：

1. 更完整的 React 可访问性和端到端验收。
2. PR body 模板和 validation 自动汇总。
3. 多主题 diff 拆分建议。
4. GitHub MCP provider 作为可替换实现。

### 团队版

后续再考虑：

1. 仓库级策略配置。
2. 团队分支命名规范。
3. PR 模板自动填充。
4. 审计报告导出。
5. GitHub MCP 作为可插拔 provider。
