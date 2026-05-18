# User Scenarios

这些场景用于指导需求、实现和验证。核心假设是：代码修改已经由人或 Codex 完成，GSA 负责 GitHub 协作动作。

## 场景 1：提交 Codex 生成的改动

用户输入：

```text
帮我提交这次 Codex 改动
```

GSA 行为：

1. 读取当前分支。
2. 读取 `git status --short`。
3. 读取 staged / unstaged diff。
4. 检测敏感文件、临时文件、无关文件。
5. 总结这次改动的主题。
6. 生成 commit message 候选。
7. 展示 dry-run。
8. 用户确认后执行 `git add` 和 `git commit`。

用户价值：

- 不需要盲目执行 Codex 给出的 Git 命令。
- 能避免误提交密钥、缓存、截图、构建产物。

## 场景 2：当前改动不适合一个 commit

用户输入：

```text
帮我提交当前改动
```

GSA 发现：

- 同时修改了业务逻辑、README、格式化配置。
- diff 呈现多个主题。

GSA 行为：

1. 提示“这次改动可能应该拆成多个 commit”。
2. 按文件分组给出建议。
3. 用户选择继续单 commit 或按建议拆分。

用户价值：

- 提升提交质量。
- 让 PR review 更容易。

## 场景 3：基于 issue 创建分支

用户输入：

```text
基于 issue #123 开一个分支
```

GSA 行为：

1. 调用 `gh issue view 123` 或 GitHub MCP 读取 issue。
2. 摘要 issue 目标。
3. 生成分支名，例如 `fix/123-login-timeout`。
4. 检查当前工作区是否干净。
5. 从默认 base branch 创建分支。

用户价值：

- 分支命名统一。
- 分支和 issue 可追溯。
- 避免脏工作区切分支带来的混乱。

## 场景 4：脏工作区切分支

用户输入：

```text
切到 develop
```

GSA 发现：

- 当前有未提交改动。

GSA 行为：

1. 拒绝直接切分支。
2. 给出选项：
   - 先提交。
   - 先 stash。
   - 创建备份分支。
   - 放弃切分支。

用户价值：

- 避免改动被带到错误分支。
- 避免隐藏的合并冲突。

## 场景 5：安全推送当前分支

用户输入：

```text
帮我 push 当前分支
```

GSA 行为：

1. 检查当前分支名。
2. 拒绝 push 到 `main`、`master`、`develop`。
3. 检查 upstream。
4. 检查本地分支是否落后远端。
5. 展示将执行的 push 命令。
6. 用户确认后执行。

用户价值：

- 避免推错分支。
- 避免覆盖团队成员提交。

## 场景 6：创建 draft PR

用户输入：

```text
帮我开一个 draft PR
```

GSA 行为：

1. 检查当前分支是否已 push。
2. 检查当前分支是否已有 PR。
3. 从 commit 和 issue 上下文生成 PR title。
4. 生成 PR body：
   - What changed
   - Why
   - Validation
   - Risk
   - Related issue
5. 调用 `gh pr create --draft`。

用户价值：

- PR 信息更完整。
- 避免重复开 PR。
- reviewer 能快速理解背景。

## 场景 7：检查 PR 是否 ready

用户输入：

```text
这个 PR 能交给 reviewer 吗？
```

GSA 行为：

1. 读取 PR 状态。
2. 读取 CI 状态。
3. 读取 review 状态。
4. 读取 unresolved comments。
5. 检查本地是否有未提交或未推送改动。
6. 输出 readiness report。

输出示例：

```text
Ready: no
Blocked by:
- CI check test-suite failed
- 2 unresolved review threads
- local branch has 1 unpushed commit
Next actions:
- push local commit
- inspect failed CI
- resolve review threads before requesting re-review
```

用户价值：

- 不需要在 GitHub 页面和本地终端之间来回确认。
- 减少“以为 ready 实际不 ready”的沟通成本。

## 场景 8：PR 描述缺少验证信息

用户输入：

```text
检查这个 PR 的协作质量
```

GSA 发现：

- PR body 没有 validation section。
- 本地没有测试执行记录。

GSA 行为：

1. 提示 PR 还不适合请求 review。
2. 建议运行测试或补充验证说明。
3. 可在确认后更新 PR body。

用户价值：

- PR 更符合团队 review 标准。

## 场景 9：危险命令拦截

用户输入：

```text
reset --hard 然后重新提交
```

GSA 行为：

1. 拦截 `reset --hard`。
2. 解释风险：会丢弃未提交改动。
3. 建议替代方案：
   - 查看 diff。
   - 创建备份分支。
   - 只还原指定文件。
   - stash 当前改动。

用户价值：

- 防止不可逆数据丢失。

## 场景 10：协作审计

用户输入：

```text
展示这次从 commit 到 PR 的操作记录
```

GSA 行为：

1. 读取 `.gsa/logs` 和 `last_run_summary.json`。
2. 读取 `.gsa/workflows/<trace_id>.json`。
3. 汇总本次 workflow：
   - 输入任务。
   - 本地状态。
   - GitHub 状态。
   - 风险判断。
   - 用户确认。
   - 执行命令。
   - 结果链接。

用户价值：

- 出问题时可以复盘。
- 团队评审时能展示 agent 可审计性。

## 场景 11：本地 `.env` 已配置 LLM

用户打开工作台。

GSA 行为：

1. 后端读取 workspace `.env`。
2. 顶部状态只显示 “LLM 已配置”。
3. API 只返回 `configured`、`model`、`base_url`、`provider_label`。
4. Trace、日志、错误消息和报告中出现 key 形态时统一替换为 `[REDACTED]`。

用户价值：

- 可以使用本地 LLM 文案辅助。
- 不会把 API key 暴露给浏览器、公开文档或审计记录。
