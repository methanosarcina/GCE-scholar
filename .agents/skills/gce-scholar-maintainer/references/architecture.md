# 项目结构与数据契约

## 可执行模块

| 文件 | 用途 |
| --- | --- |
| collect.py | 按配置的固定 ORCID 遍历 Europe PMC，规范化作者、摘要、日期，保留已有配图 |
| crossref.py | 补充近 365 天固定 ORCID 期刊论文；游标分页、DOI 去重、失败回用成功缓存 |
| enrich.py | 官网发表清单按 DOI 核对与配图；可补 OA 全文图，不能新增论文 |
| publisher.py | 读取公开原文的明确摘要图区块；实际 GET 校验，缓存带签名图片 |
| graphics.py | 官方期刊 RSS 和 PMC Cloud 的自动图片发现、DOI/媒体校验与缓存 |
| build.py | 校验配置/目录成员和作者 ORCID，发布小索引、学者分包、旧目录和全部图片 |
| server.py | 先构建，再在本机 8765 端口提供 `_site/` |
| app.js / index.html / style.css | 无框架前端；先名单后小索引，按需请求学者分包 |

Python 3.10+；联网富化使用 `requirements.txt` 的 BeautifulSoup。Node 只跑已有 CJS 测试。没有 npm 应用构建、数据库或必须的特定 IDE。

## 配置与原始状态

- `scholars.json`：`id` 是唯一的小写连字符 slug；固定 `orcid`；`query` 为 `AUTHORID:"<orcid>"`；可含 `nativeName`、`institution`、`identityEvidence` 和身份核对说明。
- `lab_sources.json`：学者 id 对应官方发表清单/机构页、标签及可选 `images:false`。
- `publisher-feeds.json`：期刊级官方 RSS 配置。不要维护成每篇文章一条的手工图片表。
- `data/catalog.json`：源目录，顶层 `updated`、各阶段时间及 `scholars`。
- `data/crossref.json`：按学者缓存的已通过严格 ORCID 检查的规范记录、最近成功时间和查询状态。
- `data/enrichment.json`：官网/OA 图缓存和检查结果。
- `data/publisher-graphics.json`：出版社图、逐 DOI 状态和汇总。
- `data/automatic-graphics.json`：RSS/PMC 图、各来源尝试、重试时间、期刊发现缓存。
- `data/source-report.json`：网页来源面板使用的汇总，含官网、Crossref、出版社和自动图片部分。
- `assets/publisher/`：原始媒体字节的本地缓存，命名为 SHA256 前 32 位加图片扩展名。第三方图片不是代码 MIT 许可的组成部分。

成功缓存和媒体文件属于可维护状态，不是随意清理的临时文件。

## 学者 entry 与 paper

每个 `catalog.scholars[id]` 包含 `orcid/query/papers/total/complete/updated`，可带 `labSource/imageCount/crossrefCount/crossrefUpdated`。

`total` 和 `complete` 描述 Europe PMC 查询；Crossref 补入不会把它们重写成所有数据源的合并命中数。不能仅由“已完整遍历”断言收齐学者所有论文。

常用 paper 字段：

- `id`：Europe PMC 的 `MED:…` 等，或 `DOI:<lowercase-doi>`。
- `doi/title/journal/abstract/authors/authorDetails/url/year/citations/pmcid/oa/license`。
- `authorDetails[].authorId = {type:"ORCID", value:"0000-…"}`：准入依据；缺失或错误时不能用作者姓名补造。
- `publicationDate/datePrecision/dateSource/onlinePublicationDate/printPublicationDate`：真实精度。Crossref 用 published-online、published-print、published 的 date-parts；不用 created/deposited。
- `metadataSource:"crossref"` 与 `metadataURL`：区分来源，详情不能错标 Europe PMC。
- `figure/fallbackFigure/labSources/publisherImageStatus`：图与出处。图可有 `kind/provider/source/url/doi/match/evidence/checkedAt/license/sha256/storage/publisherAsset`。

配图优先保留已核实摘要图，其次目录图、课题组图、正文图。类别以各模块的现行排序为准，不能仅由“这张图看起来像摘要”升级。

## 构建产物

`_site/` 不提交。构建复制旧 `data/catalog.json` 供兼容，但当前网页不在启动时请求它。

- `data/catalog-index.json`：各学者 entry 去掉 papers，增加 `paperCount` 和 `file`。
- `data/scholars/<id>.json`：该学者完整紧凑 entry。
- 页面、名单、来源报告和 `assets/` 与分包一并发布。

不能只上传 index.html，或只生成索引而漏上传分包与图片。`server.py` 也提供这套构建结果，直接双击源码 HTML 无法可靠读取数据。

## 统计口径

- 学者归属条数：同一合著论文可在两位学者下各一条。
- 不同文献：优先按规范 DOI 去重；无 DOI 记录单独按源 id 处理。
- Crossref 缓存条数包含与 Europe PMC 已有目录重叠的结果，不是新增文献数。
- `crossref.addedPapers` 是对本轮已有目录补入的归属数。工作流先重建 Europe PMC，再补回 Crossref-only，所以它可能每轮重复。
- 净新增需比较前后快照的 DOI 集合，并说明是否按学者归属统计；文献中可能包括更正、综述、不同语言版本，不要都称为新原创研究。

## 更新与发布

`refresh.yml` 每天 02:17 UTC 或手动运行；修改 collect.py、crossref.py、scholars.json 会触发轻量的元数据刷新。push 触发时不重抓图片。

`illustrations.yml` 可单独手动补图；修改 graphics.py 或期刊 RSS 配置也触发。两个写目录工作流共用 `scholar-catalog-data` 并发组，避免同时写数据。

`pages.yml` 在源码 push、手动请求或上述成功的 workflow_run 后执行测试、构建和部署。保留 workflow_run：机器人 token 创建的数据提交不会必然触发另一个 push 工作流。
