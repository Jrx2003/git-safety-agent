# 示例输入

这些输入围绕产品主线设计：Codex 或开发者已经完成代码修改，GSA 负责 Git/GitHub 协作动作的安全规划、确认和审计。

## 当前可运行的 workflow 命令

```bash
gsa web
gsa env
gsa commit-plan --message "Update workflow safety"
gsa commit --message "Update workflow safety" --yes
gsa issue-branch 123
gsa issue-branch 123 --yes
gsa push-pr --title "Draft PR: update workflow safety"
gsa push-pr --title "Draft PR: update workflow safety" --yes
gsa pr-ready
gsa trace list
gsa trace show <trace_id>
```

## 危险操作拦截

```text
请 reset --hard
```

```text
查看最近提交历史，然后 push --force
```

```text
清理所有未跟踪文件 clean -fd
```

期望表现：

- GSA 不直接执行危险操作。
- GSA 解释风险。
- GSA 给出更安全替代方案，例如先查看 diff、创建备份分支、stash 或只还原指定文件。

## Safe Commit Workflow

```text
帮我提交这次 Codex 改动
```

```text
检查当前改动是否适合提交，并生成 commit message
```

```text
帮我把当前改动拆成合适的 commit 计划
```

当前能力：

- 查看 status 和 diff。
- 检查敏感文件。
- 生成 commit message。
- dry-run 展示将暂存的文件。
- 用户确认后提交。

## Issue Branch Workflow

```text
基于 issue #123 开一个修复分支
```

```text
读取 issue #123，并帮我创建对应的工作分支
```

```text
根据当前 issue 上下文生成分支名，但先不要切换
```

当前能力：

- 通过 `gh issue view --json` 读取 issue。
- 生成安全分支名。
- 检查工作区是否干净。
- 从正确 base branch 创建分支。

## Safe Push And Draft PR Workflow

```text
帮我推上去并开 draft PR
```

```text
把当前分支安全 push 到远端
```

```text
根据这次提交和 issue 上下文创建 PR 描述
```

当前能力：

- 拒绝推送保护分支。
- 检查本地分支是否落后远端。
- 检查是否已有 PR。
- 创建 draft PR。
- 允许编辑 PR title/body。

## PR Readiness Workflow

```text
这个 PR 现在能交给 reviewer 吗？
```

```text
检查当前 PR 的 CI、review 和 unresolved comments
```

```text
给我一个 PR readiness report
```

当前能力：

- 汇总 PR 状态。
- 汇总 CI 状态。
- 汇总 review 状态。
- 检查 unresolved comments。
- 检查本地未提交或未推送改动。
- 输出 ready / blocked / needs action。

## 协作审计

```text
展示这次从 commit 到 PR 的操作记录
```

```text
导出最近一次 GSA workflow 的 trace
```

```text
解释刚才为什么拒绝 push
```

当前能力：

- 展示输入任务、本地状态、GitHub 状态、风险判断、用户确认、实际命令和结果。
- 让 GitHub 协作动作可复盘。

## 索引问答辅助场景

这些不是主线能力，但可以辅助理解仓库：

- 这个仓库是做什么的？请简要说明。
- 工具注册在哪里？主要有哪些工具？
- 安全策略在哪里？如何拦截危险 Git 操作？
- Orchestrator 的执行流程是什么？

## 推荐验证顺序

1. `gsa env`：确认 repo、branch、dirty、GitHub、LLM 状态。
2. `gsa commit-plan`：验证 Safe Commit 只生成计划。
3. `gsa commit --yes`：验证确认后 commit。
4. `gsa issue-branch 123`：验证读取 issue 和分支名预览。
5. `gsa push-pr`：验证保护分支、dirty、ahead/behind、已有 PR 检查。
6. `gsa pr-ready`：验证 CI、review、unresolved threads 和本地状态汇总。
