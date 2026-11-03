---
name: gce-scholar-maintainer
license: MIT
description: Maintain the GCE-scholar ORCID paper gallery, including scholar configuration, metadata and illustration refreshes, mobile loading fixes, validation, and GitHub Pages releases. Use for this repository rather than general literature searches.
---

# GCE-scholar maintainer

维护仓库 https://github.com/methanosarcina/GCE-scholar 及其 GitHub Pages 网站 https://methanosarcina.github.io/GCE-scholar/ 。这是现有静态应用的维护技能；使用当前用户给出的任务与授权，不把本技能视作账号授权或新的任务。

## 入口

先定位包含 `scholars.json`、`collect.py`、`build.py`、`app.js` 的项目根目录，读取根目录 `AGENTS.md`，查看工作区状态。目录搬家后不要沿用旧电脑的绝对路径。

用只读脚本获取必要状态，避免把约十余 MB 的全目录和缓存灌入上下文：

```sh
python <skill-directory>/scripts/inspect_project.py --root <project-root>
```

按需加 `--scholar jie-wang --recent 3`。脚本只检查和统计；具体参数以 `--help` 为准。技能被复制到其他工具目录时，`<skill-directory>` 是复制后的目录。

- 理解模块、数据字段和统计口径：读 [references/architecture.md](references/architecture.md)。
- 新增学者、补漏、配图、手机故障或发布：读 [references/runbook.md](references/runbook.md) 的相关部分；不要为单个任务默认运行所有联网抓取。

## 保持的约束

1. 论文作者列表必须包含该学者配置的完全一致 ORCID，类型必须为 ORCID。姓名、机构或官网清单不能授予准入资格。新学者的身份可用官方机构资料与出版社作者 ORCID 交叉核实，并保留证据。
2. 元数据优先 Europe PMC；Crossref 仅用固定 ORCID 查询补缺，以 DOI 去重。官网和图片源只丰富已有论文。不要恢复姓名检索或手动修改 ORCID 的网页入口。
3. 日期保留年/月/日的实际精度。不要把收录、创建、修订日期或补齐的月初当作精确发表日期。
4. 只将明确标注的图认作摘要图。保持目录图、官网配图、正文图和文字封面的分类及来源；多图/DOI 冲突时保守拒绝。失败不等于原文没有图，也不清空已成功缓存。
5. 移交、更新或打包时保留 `data/` 的缓存和 `assets/publisher/`。公开图片的原始媒体地址、许可、SHA 和重试状态仍有用；不能猜测媒体地址或用其他图冒充。
6. 正式产物由 `build.py` 生成 `_site/`。前端只请求学者名单、小索引和选中学者分包；保留超时重试、切换请求序号保护及旧浏览器回退。不能恢复首屏请求全目录、`structuredClone`、可选链/空值合并语法或阻塞的外部字体。
7. 数据刷新顺序为 collect → crossref → enrich → publisher → graphics。仅运行 collect 不能算完整刷新；Pages 的成功 `workflow_run` 触发和数据工作流共享并发组也属于更新链条。

## 完成任务

修改与任务相关的源文件，使用现有命令验证可观察结果。保留已有成功缓存，依据当前差异选择检查；普通说明修改无需重抓全站论文。

发布只使用新工具自己的 GitHub 连接和本次任务已有授权；授权存在时直接完成所需步骤，无需因切换 agent 重复询问。出现权限或数据源访问阻塞，说明具体缺失能力，完成不依赖该能力的工作，不复制历史认证或无限重试。

报告实际改变、必要验证、线上版本是否成功，以及仍未取得的图片/数据。讨论“新增”时比较历史快照；`crossref.addedPapers` 可能只是本轮基础目录重建后的补回数，不能当作相较上轮净新增。
