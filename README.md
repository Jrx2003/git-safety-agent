# Git Safety Agent (GSA)

GSA 是一个面向本地开发者与 Codex 使用者的 **GitHub 协作安全代理**。

它不尝试替代 Codex 写代码，也不做完整 coding agent。它解决的是另一段真实工作流：

> 代码已经由人或 Codex 改好了，但提交、推送、开 PR、关联 issue、检查协作状态这些 GitHub 操作仍然容易出错。GSA 负责把这些动作变成可解释、可确认、可审计的安全流程。

## 为什么需要 GSA

最初使用 Codex 时，常见协作方式是：

1. Codex 修改代码或给出一串 Git 命令。
2. 开发者手动执行 `git add`、`git commit`、`git push`、`gh pr create`。
3. 开发者需要自己判断命令是否安全、分支是否正确、是否会误提交敏感文件、是否会污染保护分支或覆盖别人提交。

这个过程对个人项目还可以接受，但放到 GitHub 协作里风险很高：

- 不确定当前分支是否应该推送。
- 不确定本地分支和远端是否分叉。
- 不确定 Codex 改动里是否混入临时文件、密钥或无关文件。
- 不确定 commit message、PR title、PR body 是否能准确关联 issue。
- 不确定 PR 是否已经 ready for review。

GSA 的目标是补齐 Codex 在 GitHub 协作中的“最后一公里”：**不写业务代码，只接管协作动作的安全执行层**。

## 产品边界

GSA 做：

- 提交前检查本地状态、diff、暂存区、敏感文件和风险操作。
- 根据 issue/PR 上下文生成分支名、commit message、PR title/body。
- 安全创建分支、提交、推送、创建 draft PR。
- 检查 PR 的 CI、review、unresolved comments、本地未推送提交等协作状态。
- 记录每一步计划、确认、命令、结果和 trace，方便审计与回放。

GSA 不做：

- 不自动实现 issue。
- 不自动修复 CI。
- 不自动解决 review comments。
- 不直接 merge PR。
- 不让 LLM 自由执行 shell。
- 不把 GitHub MCP 当作产品本身。GitHub MCP 或 `gh` 是上下文与执行工具，GSA 的价值是任务级 workflow、安全策略和审计轨迹。

## 核心场景

### 1. Safe Commit Workflow

用户输入：

```text
帮我提交这次 Codex 改动
```

GSA 应该执行：

1. 读取当前分支、工作区状态、暂存区和未暂存 diff。
2. 检查是否包含 `.env`、token、密钥、构建产物、临时文件。
3. 判断是否存在“多主题改动”，提示是否需要拆分 commit。
4. 生成 commit message 候选。
5. dry-run 展示将暂存和提交的文件。
6. 用户确认后执行 `git add` 和 `git commit`。

### 2. Issue Branch Workflow

用户输入：

```text
基于 issue #123 开一个修复分支
```

GSA 应该执行：

1. 通过 `gh issue view 123` 或 GitHub MCP 读取 issue 标题、描述、标签和关联信息。
2. 从 issue 生成安全分支名，例如 `fix/123-login-timeout`。
3. 检查当前工作区是否干净。
4. 确认 base branch，例如 `main` 或仓库默认分支。
5. 创建并切换分支。
6. 将 issue 摘要写入本次 session trace，供后续 commit/PR 使用。

### 3. Safe Push And Draft PR Workflow

用户输入：

```text
帮我推上去并开 draft PR
```

GSA 应该执行：

1. 拒绝直接推送 `main`、`master`、`develop` 等保护分支。
2. 检查本地分支是否落后或分叉于远端。
3. 检查是否存在未提交改动。
4. push 当前分支到远端。
5. 创建 draft PR，并自动生成 PR body：
   - What changed
   - Why
   - Validation
   - Risk
   - Related issue
6. 输出 PR 链接和下一步建议。

### 4. PR Readiness Workflow

用户输入：

```text
这个 PR 现在能交给 reviewer 吗？
```

GSA 应该执行：

1. 读取 PR 状态、CI 状态、review 状态和 unresolved comments。
2. 检查本地是否还有未提交或未推送改动。
3. 检查 PR 描述是否缺少验证说明或 issue 关联。
4. 输出 readiness report：
   - Ready
   - Blocked
   - Needs action

## 当前实现状态

当前主线已经从“自然语言工具原型”推进到 **React 工作台 + FastAPI workflow API**。

已具备：

- React/Vite 工作台：Overview、Safe Commit、Issue Branch、Push & Draft PR、PR Readiness、Trace。
- FastAPI 任务级 API：前端只调用 workflow endpoint，不直接拼 Git/GitHub 命令。
- `gh` CLI provider：MVP 通过结构化 `gh --json` 读取 issue、PR、checks 和已有 PR。
- Safe Commit：分组展示 staged/unstaged 文件、敏感文件阻断、diff summary、确认后 commit。
- Issue Branch：读取 issue 元数据、生成包含 issue 编号的分支名、脏工作区阻断、确认后创建分支。
- Push & Draft PR：保护分支阻断、dirty 阻断、ahead/behind 检查、已有 PR 检测、确认后 push 并创建 draft PR。
- PR Readiness：汇总 PR、CI/checks、review、本地未推送提交和本地 dirty 状态。
- Trace：记录 plan、风险、命令预览、执行结果和 GitHub URL，输出前统一脱敏。
- CLI 兼容入口：`gsa env`、`gsa commit-plan`、`gsa commit --yes`、`gsa issue-branch`、`gsa push-pr`、`gsa pr-ready`、`gsa trace show`。
- Streamlit 旧界面保留为 legacy：`gsa ui`。

仍不做：

- 不实现 GitHub issue。
- 不自动修 CI。
- 不自动处理 review comment。
- 不 merge。
- 不把 LLM 接到任意 shell。

## 架构主线

Legacy agent runtime：

```text
用户输入
  |
  v
Planner(LLM/规则) -> Plan(JSON)
  |
  v
Safety Validator -> Risk Policy -> Confirmation
  |
  v
Orchestrator -> MCP Client -> MCP Server
                         |
                         +-- Git Tools
                         +-- File Tools
                         +-- Index Tools
  |
  +-- JSONL Trace
  +-- changes.md
  +-- last_run_summary.json
```

当前 GitHub workflow runtime：

```text
用户 / Codex 完成代码改动
  |
  v
GSA Session
  |
  +-- Local Git Snapshot
  +-- GitHub Issue / PR Context
  +-- Safety Policy
  +-- Confirmation Gate
  |
  v
Workflow Runtime
  |
  +-- Safe Commit
  +-- Issue Branch
  +-- Safe Push + Draft PR
  +-- PR Readiness
  |
  v
Git / gh
  |
  v
Audit Trace + GitHub Collaboration Result
```

GitHub provider 当前使用 `gh` CLI。后续可以替换为 GitHub MCP，但 workflow API 不需要变化。

## 目录结构

```text
git-safety-agent/
  src/gsa/
    agent/           # Planner / Orchestrator / Schema / Memory
    mcp/             # 当前最小 MCP 兼容层
    tools/           # Git / File / Index 工具实现
    safety/          # 风险评估、策略校验、二次确认
    security/        # secret 注册与统一脱敏
    github/          # gh CLI provider
    workflows/       # Safe Commit / Issue Branch / Push PR / PR Readiness
    observability/   # trace_id、JSONL 日志、执行摘要
    llm/             # LLM Client 和 Prompt
    app/             # FastAPI 和 legacy Streamlit
    eval/            # 规则规划评测用例与 runner
  web/               # React/Vite 工作台
  docs/              # 产品需求、设计取舍、场景、路线图
  tests/             # safety 相关单元测试
  examples/          # 示例输入
  images/            # README 截图
```

## 文档导航

- [Product Requirements](docs/PRODUCT_REQUIREMENTS.md)：产品定位、目标用户、核心需求和非目标。
- [User Scenarios](docs/USER_SCENARIOS.md)：围绕 Codex + GitHub 协作的真实任务场景。
- [Design Rationale](docs/DESIGN_RATIONALE.md)：需求演进、产品边界和架构取舍。
- [Roadmap](docs/ROADMAP.md)：从当前原型到 GitHub 协作安全代理的迭代计划。

## 安全策略

GSA 的安全策略不是为了限制用户，而是为了让高风险协作动作显式化。

- 写操作默认 dry-run。
- medium/high 风险操作必须确认。
- 禁止危险 Git 命令，如 `reset --hard`、`clean -fd`、`push --force`。
- 文件操作限制在 workspace 内。
- 拒绝访问常见敏感文件，如 `.env`、私钥、token 文件。
- 单次写步骤设置上限，避免一次计划产生过大破坏面。
- 信息不足时追问，不猜测执行。

## 运行方式

前置：Python >= 3.10。

### 安装

```bash
cd git-safety-agent
pip install -e .[dev]
npm --prefix web install
```

### React 工作台

推荐入口：

```bash
gsa web
```

默认启动：

- API: `http://127.0.0.1:8000`
- Web: `http://127.0.0.1:5173`

也可以拆开启动：

```bash
gsa api --host 127.0.0.1 --port 8000
npm --prefix web run dev
```

### Workflow CLI

```bash
gsa env

gsa commit-plan --message "Update workflow safety"
gsa commit --message "Update workflow safety" --yes

gsa issue-branch 123
gsa issue-branch 123 --yes

gsa push-pr --title "Draft PR: update workflow safety"
gsa push-pr --title "Draft PR: update workflow safety" --yes

gsa pr-ready
gsa pr-ready 123

gsa trace list
gsa trace show <trace_id>
```

### Legacy CLI / UI

```bash
# 生成计划，不修改文件
gsa plan --input "查看当前仓库状态并给出风险提示"

# 试运行，仍不会修改
gsa run --input "查看最近 3 次提交"

# 写操作需要显式确认
gsa run --input "暂存所有改动" --yes

# Streamlit legacy UI
gsa ui
```

## LLM 配置

默认模型为 `glm-4.7`，使用 `zai-sdk` 调用。LLM 只用于文案辅助；Git/GitHub workflow 在没有 LLM 的情况下仍可生成只读计划和执行规则化操作。

后端启动时会读取当前进程环境和 workspace `.env`。`.env` 只在本地后端读取，永不进入前端 bundle，API 也不会返回 key 原文。

```dotenv
BIGMODEL_API_KEY=
ZAI_API_KEY=
GLM_MODEL=glm-4.7
ZAI_BASE_URL=https://api.z.ai/api/paas/v4/
```

`.env.example` 提供占位说明，不包含任何真实值。

`GET /api/environment` 只返回：

- `configured`
- `model`
- `base_url`
- `provider_label`

不会返回 `api_key`、token 或 Authorization header。

## Secret Safety

GSA 默认把 secret safety 当作 workflow 前置条件：

- `.env`、`.env.*`、`*.pem`、`*.key`、`id_rsa`、`id_ed25519`、`secrets.json`、`tokens.json` 被视为敏感文件；`.env.example` 是只含空占位的例外。
- 文件读取、索引构建和 Safe Commit 默认拒绝这些文件。
- logger、trace、API response、CLI output、`changes.md`、`last_run_summary.json` 写出前会调用统一脱敏。
- 脱敏覆盖已加载的真实 key 值、`api_key`/`token`/`secret`/`password`/`authorization` 字段、Bearer token、`sk-...`、GitHub token 和长 token 字符串。

## 测试与评测

```bash
pytest -q
npm --prefix web run build
npm --prefix web audit --audit-level=moderate
python -m gsa.eval.runner
```

评测的重点应从“关键词命中哪个工具”逐步升级为：

- 危险 Git 操作是否被拦截。
- 模糊协作请求是否触发追问。
- safe commit 是否正确识别敏感文件和暂存区状态。
- safe push 是否拒绝保护分支和远端分叉风险。
- PR readiness 是否正确汇总 CI、review、本地状态。

## 项目总结

GSA 不是 coding agent，而是 Codex 之后的 GitHub 协作安全代理。它把本地代码改动进入 GitHub 的过程，从一串不透明的手动命令，变成带上下文、带风险解释、带确认门禁、带审计轨迹的工程 workflow。
