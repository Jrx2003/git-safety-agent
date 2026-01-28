# Git Safety Agent

一个“可控、可观测、可评测”的工程化 Agent 系统，支持自然语言驱动的 Git 操作、有限本地文件读写、目录语义理解与文件整理建议，并提供本地 GUI/Web 界面。

目标对齐：
- 证明具备 Agent 核心能力研发（规划、校验、执行、总结）
- 强调工程化：可控（安全策略）、可观测（日志/trace）、可评测（测试与评测）
- 具备 GUI，可视化目录结构、Git 历史、执行计划与风险提示

## 架构图（ASCII）

```
用户输入
   │
   ▼
[Planner(LLM/规则)] -> Plan(JSON)
   │           │
   │           └─ 校验/风险/确认
   ▼
[Orchestrator] ──> MCP Client ──(stdio)──> MCP Server
                               │
                               ├─ Git Tools
                               ├─ File Tools
                               └─ Index Tools (LangChain)
   │
   ├─ 事件日志(JSONL)
   ├─ 变更报告(changes.md)
   └─ Memory(会话+持久化)
```

## 关键特性

- **可控**：禁止危险 git 操作（reset --hard/clean -fd/force push），写操作必须 YES 二次确认 + 试运行预览。
- **可观测**：每次运行生成 trace_id + JSONL 事件日志 + changes.md 摘要。
- **可评测**：提供 eval/test_cases.yaml 与 runner，可在无 key 下运行规则规划器。
- **MCP 支持**：实现 MCP Server/Client（stdio JSON-RPC 兼容层），工具统一注册与调用。
- **LangChain 索引**：本地目录切片、索引、搜索与摘要，支持目录整理建议。

## 安全策略与防误用设计（示例）

- **黑名单**：reset --hard / clean -fd / push --force 一律拒绝。
- **Sandbox**：文件操作仅限 workspace，realpath 校验阻止路径逃逸。
- **二次确认**：medium/high 风险步骤必须 YES。
- **试运行**：写操作默认试运行，展示 diff 或影响范围。
- **歧义追问**：信息不足时返回 questions，不允许猜测执行。
- **变更上限**：单次写步骤 >10 直接拒绝。

## GUI 使用说明

运行 `gsa ui` 后，可看到：
- 任务输入框：支持整段自然语言
- 计划面板：展示 JSON 计划（含 risk）
- 执行控制：YES 确认、执行按钮
- 建议与提示：questions/风险提示
- 目录结构：左侧树状目录（支持搜索）
- Git 历史：最近提交列表
- 日志：trace_id 与最近日志内容
- 默认使用 LLM，如未配置 API Key 将自动降级为规则规划
- 对话模式：计划执行 / 索引问答 / 仓库概览 / 整理建议
- 整理建议可一键转成可执行计划

## LangChain 索引/搜索/摘要

- 加载：DirectoryLoader + TextLoader（仅文本后缀）
- 切片：RecursiveCharacterTextSplitter
- 向量库：FAISS（本地）
- 检索：相似度搜索
- 总结/建议：有 Key 时使用 LLM，无 Key 时使用规则摘要

## GLM-4.7 API Key 配置

**必须模型：`glm-4.7`**，使用官方 `zai-sdk` 调用

可选配置方式（优先级：环境变量 > config.yaml）：
1) 环境变量
```
export BIGMODEL_API_KEY=""
```
或
```
export ZAI_API_KEY=""
```
2) config.yaml（留空占位）
```
# config.yaml
BIGMODEL_API_KEY: ""
```

未配置 key 时：系统使用规则规划器 + 规则摘要，保证 demo 可运行。

如需启用最新 SDK（推荐）：
```
pip install zai-sdk
```

注意：启动 UI 的 Python 环境必须与安装 zai-sdk 的环境一致。

高级配置（可选，写在 config.yaml 或环境变量）：
```
GLM_BASE_URL: "https://api.z.ai/api/paas/v4/"
GLM_MODEL: "glm-4.7"          # 可改为 glm-4.7-flash
GLM_TIMEOUT: 300
GLM_CONNECT_TIMEOUT: 8
GLM_MAX_RETRIES: 2
GLM_MAX_TOKENS: 65536
GLM_TEMPERATURE: 1.0
GLM_THINKING_ENABLED: true
```

说明：
- 中国大陆默认使用 `https://open.bigmodel.cn/api/paas/v4/`（ZhipuAiClient）
- 海外默认使用 `https://api.z.ai/api/paas/v4/`（ZaiClient）
- 可通过环境变量 `ZAI_BASE_URL` 覆盖

## 如何运行

### 1) 安装
```
cd git-safety-agent
pip install -e .[dev]
```

### 2) CLI
```
# 生成计划
python -m gsa.cli plan --input "看看当前仓库状态"

# 生成并执行（需要 --yes 才会真正写）
python -m gsa.cli run --input "暂存所有改动" --yes
```

### 3) GUI
```
python -m gsa.cli ui
```

### 4) API（可选）
```
python -m gsa.cli api --port 8000
```

## 如何运行测试与评测

```
pytest -q
python -m gsa.eval.runner
```

## 失败模式与防护（至少 5 条）

1) 未配置 API Key：自动降级为规则规划/摘要。
2) 规划结果无效 JSON：解析失败后回退规则规划器。
3) 写操作未确认：仅试运行，不会修改。
4) 路径越界：realpath 校验直接拒绝。
5) 索引不存在：提示先构建索引。

## AI 编程辅助说明

- 使用 AI 辅助生成结构与初版代码。
- 关键安全逻辑（策略、校验、风险）手写并编写测试。
- 任何写操作必须通过工具与确认流程，避免模型直接执行命令。

## MCP 兼容范围说明

本项目实现“最小 MCP 兼容层”（stdio JSON-RPC 风格），包含：
- tools/list, tools/call
- resources/list, resources/read

可与 MCP Client 进行基本工具调用与资源读取；未覆盖完整官方协议扩展。
