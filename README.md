# 花东鹏的 AI 应用工程作品集

我有十年以上企业软件和全栈交付经历，长期使用 Java、C#，也使用 Python、JavaScript 开发个人工具。近期主要在维护与架构升级中使用 AI 辅助编码，由我负责方向、问题拆解、方案判断和验收。

这里介绍三个业余项目，重点是如何把模型 API、现有产品和业务流程接成可以检查、恢复和人工把控的应用。它们体现 AI 应用工程实践，不代表我训练了基础模型。

| 项目 | 解决的问题 | 资料 |
| --- | --- | --- |
| 个人知识与内容工作流 | 检索来源可回查，多平台交付可分别恢复 | [案例](case-studies/knowledge-workflow.md) |
| 多作品创作与审稿台 | 长任务上下文容易漂移，读稿与反馈缺少统一入口 | [案例](case-studies/novel-review-workbench.md) |
| Easton Radar | 公开信息需要清洗、分类和保留证据入口 | [案例](case-studies/public-radar.md) · [已有公开代码](https://github.com/huadongpeng/easton-radar) |

仓库包含三个项目的脱敏案例，以及一个[可运行的本地审批与恢复样例](examples/README.md)。该样例于 2026-11-10 为展示工程方法新写，使用标准库和合成数据；不包含前两个项目的原始源码、生产配置或原始内容。三个完整项目的合成演示仍处于设计阶段，证据范围见[核验说明](docs/EVIDENCE.md)。

我关注企业业务系统集成、知识检索、工作流和可靠交付，希望把长期业务工程经验与 AI 应用结合。

## 运行本地样例

Python 3.9 或更新版本，无第三方依赖、模型密钥或网络请求：

```powershell
python .\examples\editorial_workflow.py --self-check
```

自测覆盖审批失效、幂等冲突、响应丢失及跨进程恢复等六项行为。详细输出与限制见[样例说明](examples/README.md)；这不是分布式 exactly-once 或完整知识问答系统。

- [我怎样与 AI 协作](docs/AI_COLLABORATION.md)
- [合成演示设计](examples/synthetic-demo-plan.md)
- [公开范围](docs/PUBLIC_SCOPE.md)

本文档未包含雇主或客户源码、业务数据、精确住址、账号和凭据。
