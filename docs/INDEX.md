# GSA Docs

这些文档围绕产品主线组织：**Codex 改代码，GSA 管 GitHub 协作落地**。

当前默认产品形态是 React 工作台 + FastAPI workflow API。Streamlit 保留为 legacy 入口。

## 文档列表

- [Product Requirements](PRODUCT_REQUIREMENTS.md)：产品定位、目标用户、真实痛点、核心需求和非目标。
- [User Scenarios](USER_SCENARIOS.md)：可用于实现和验证的 GitHub 协作场景。
- [Design Rationale](DESIGN_RATIONALE.md)：项目背景、需求演进、产品边界和架构取舍。
- [Roadmap](ROADMAP.md)：从当前本地安全原型到 GitHub 协作安全代理的迭代计划。

## 当前可用入口

```bash
gsa web
gsa env
gsa commit-plan
gsa issue-branch <issue>
gsa push-pr
gsa pr-ready [pr]
gsa trace show <trace_id>
```

`.env` 仅作为本地后端配置来源；文档、API、UI、trace 和测试快照都不应出现真实 key。

## 阅读顺序

1. 先读 `PRODUCT_REQUIREMENTS.md`，明确项目为什么存在。
2. 再读 `USER_SCENARIOS.md`，理解每个功能要服务的真实任务。
3. 再读 `DESIGN_RATIONALE.md`，理解为什么采用当前边界和架构。
4. 开发前读 `ROADMAP.md`，确定下一阶段做什么和不做什么。
