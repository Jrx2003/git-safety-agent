# Design Rationale

这份文档记录 GSA 的需求演进、产品边界和架构取舍。

## 一句话定位

GSA 是一个 GitHub 协作安全代理。它不替代 Codex 写代码，而是在 Codex 生成本地改动之后，负责安全地完成提交、推送、创建 PR、关联 issue、检查 PR 状态，并留下可审计轨迹。

## 项目背景

使用 Codex 写代码时，风险不只来自代码本身，也来自代码改完之后的 Git/GitHub 操作。

常见情况是：

- Codex 给出一串 Git 命令。
- 开发者不确定 `git add .` 是否会把不该提交的文件带进去。
- 开发者不确定当前分支是否适合 push。
- 开发者不确定是否会直接推到保护分支。
- PR 可能缺少 issue 关联、验证说明或协作状态检查。

GSA 的目标是把“本地改动进入 GitHub 协作流程”的过程标准化，而不是再造一个 coding agent。

## 需求演进

### 第一阶段：Git 安全执行原型

最初目标是防止误执行危险 Git 操作，因此项目先实现了：

- 自然语言转结构化 plan。
- Git、文件、索引工具注册。
- 危险命令拦截。
- dry-run。
- 二次确认。
- JSONL trace。

这个阶段验证了安全执行闭环，但需求仍偏本地工具化。

### 第二阶段：GitHub 协作安全代理

后续需求重心从“能否安全执行 Git 命令”转向“这些命令在 GitHub 协作语境下是否正确”。

例如：

- 提交是否应该关联 issue。
- 分支是否应该从默认 base branch 创建。
- 当前分支是否已有 PR。
- push 是否会覆盖别人提交。
- PR 是否已经 ready for review。

因此项目主线调整为：Codex 改代码，GSA 管协作。

## 为什么不做完整 coding agent

完整 coding agent 需要处理需求理解、代码定位、实现、测试、修复和 review 反馈，这会让项目范围急剧扩大。

GSA 有意不做这些，因为目标问题不是“缺少另一个 coding agent”，而是：

- coding agent 产物如何安全进入 GitHub。
- 本地 Git 状态和 GitHub 协作状态如何统一判断。
- 高风险操作如何被确认和审计。

这个边界让项目更可控，也更容易形成明确的产品价值。

## 和 GitHub MCP 的关系

GitHub MCP 可以提供 GitHub API 工具，例如 issue、PR、repo、actions 等上下文。

GSA 不重复造 GitHub MCP，而是在它之上做任务级 workflow：

- issue branch workflow。
- safe push workflow。
- draft PR workflow。
- PR readiness workflow。

也就是说，GitHub MCP 是工具面，GSA 是安全流程层。

## 架构取舍

### 结构化 Plan

Git/GitHub 操作有副作用，不能让模型直接输出 shell 执行。因此 GSA 先让模型生成结构化 plan，再由本地 validator 和 risk policy 审查。

### 默认 dry-run

提交、推送、分支切换都可能影响协作状态。dry-run 能让用户先看到影响范围，再决定是否执行。

### trace 优先

协作动作需要可复盘。trace 可以回答：

- 当时用户要求什么？
- GSA 看到了什么状态？
- 为什么判断有风险？
- 用户确认了什么？
- 实际执行了什么？
- 结果是什么？

### 禁止自由 shell

自由 shell 很强，但安全边界很难控制。GSA 只允许注册工具执行，这样可以为每类工具设置 schema、风险等级和确认策略。

### React 工作台优先

Streamlit 适合早期验证，但后续 GitHub workflow 需要更明确的布局和状态门禁：

- 顶部环境状态。
- 左侧 workflow 导航。
- 主区表单和计划。
- 右侧风险、命令预览、执行结果。
- 长 diff 和 trace 展示。
- 键盘可达的确认流程。

因此当前默认界面改为 React/Vite，FastAPI 作为唯一 workflow API 后端。Streamlit 保留为 legacy。

### Secret redaction 作为横切层

`.env` 是本地 LLM 配置来源，但 key 不能穿过后端边界。GSA 在配置加载时注册真实 secret 值，并在 logger、trace、API response、CLI output 和报告写出前统一脱敏。

## 当前实现覆盖面

当前代码已经实现 GitHub 协作安全代理的 MVP 主链路：

- `web/`：React/Vite 工作台。
- `app/api.py`：FastAPI workflow API。
- `workflows/`：Safe Commit、Issue Branch、Push & Draft PR、PR Readiness。
- `github/gh.py`：基于 `gh` CLI 的 GitHub provider。
- `security/redaction.py`：secret 注册和统一脱敏。
- `Safety`：风险评估、危险命令拦截、写操作确认。
- `Tools`：legacy Git、文件、索引工具。
- `Observability`：JSONL 日志和运行摘要。
- `CLI`：workflow 命令和 legacy plan/run 命令。

它证明了“先 plan、再确认、执行前重校验、执行后审计”的闭环。

## 后续迭代重点

后续优先增强 GitHub 协作质量，而不是扩展 coding 能力：

1. 更完整的 PR body 生成和 PR 模板适配。
2. 更准确的多主题 diff 拆分建议。
3. GitHub MCP provider 替换 `gh` provider。
4. 团队级策略配置。

## 常见问题

### 这和 Claude Code 有什么区别？

Claude Code 是通用 coding agent。GSA 的边界更窄：它不写业务代码，只处理代码改完后的 GitHub 协作动作，重点是安全、确认和审计。

### 这和 GitHub MCP 有什么区别？

GitHub MCP 暴露 GitHub 工具。GSA 使用这些工具组织安全 workflow，例如 safe push、draft PR、readiness report。

### 为什么这是 agent 项目？

因为它不是固定脚本。它需要根据自然语言、当前 Git 状态、GitHub issue/PR 状态和安全策略动态规划下一步，并在风险不明确时追问或拒绝执行。

### 最大工程难点是什么？

难点不是调用 Git 命令，而是把副作用操作放进可控边界：

- 工具 schema。
- 风险分类。
- dry-run。
- 用户确认。
- 状态校验。
- 执行审计。

## 设计原则总结

agent 工程不只是让模型“能做事”，更重要的是让模型在正确边界内做事。GSA 的价值就是把 GitHub 协作中高风险、易出错、难审计的操作，变成可解释、可确认、可追踪的工程流程。
