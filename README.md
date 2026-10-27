# Scholar Gallery · 学者论文画廊

25 位学者的固定 ORCID 论文画廊。点击姓名即可浏览配图、摘要和原文。

## 启动

浏览本地快照需要 Python 3.10+；补充官网数据需要安装 requirements.txt 中的依赖：

```sh
python server.py
```

打开 http://127.0.0.1:8765 。本地版和 GitHub Pages 均展示已同步的数据快照。

## 匹配规则

- 所有学者的 ORCID 固定在 scholars.json。
- 采集器只按固定 ORCID 查询，遍历所有分页；不使用姓名检索或可编辑查询。
- 采集器和网页均检查论文 authorDetails 中是否含有完全一致的 ORCID。不匹配或缺少作者 ORCID 的记录不展示。
- 已移除手动检索、ORCID 输入框、检索设置和外部检索入口；旧 localStorage 查询设置不再读取。
- 搜索框仅筛选已匹配的论文标题、摘要、期刊，不改变学者身份或查询数据源。
- 未关联 ORCID 的文章不收录，即使确实属于该学者。索引命中数可能高于通过作者元数据复核后显示的条数。
- Xiaozhou Luo 已完成 ORCID 索引全量同步：索引返回 55 条，通过作者 ORCID 严格核对后展示 55 条。

## 更新数据

```sh
python -m pip install -r requirements.txt
python collect.py --figures 4
python enrich.py --all-oa
python publisher.py
python -m unittest discover -s tests
```

更新默认遍历全部 ORCID 查询分页。保留 --all 和 --resolved-all 作为旧命令兼容参数。GitHub Actions 的 Refresh catalog 工作流每天自动运行一次，也可以在 Actions 页面手动运行；数据有变化时会提交到 main，并由 Deploy Pages 自动发布新快照。

采集失败保留原有符合固定 ORCID 的记录。更新会保留已核对的配图。图片及论文的许可不属于本仓库代码的 MIT 许可范围。

## 发表日期

- 卡片和论文详情显示来源实际提供的日期；“最新发表”和“最早发表”按年、月、日排序，同年论文也按日期排列。
- 优先显示 Europe PMC 的 electronicPublicationDate（在线发表）；详情同时保留期刊原始出版日期 dateOfPublication。
- 缺少具体日时显示 YYYY-MM 并注明“未提供具体日”；仅有年份时显示 YYYY 并注明“仅提供年份”。
- 不将可能补齐了月、日的 firstPublicationDate 或 printPublicationDate 当作精确日期，也不使用收录、创建或修订日期代替发表日期。排序时缺失月、日采用对应区间起点；页面仍保留真实精度。
- Refresh catalog 成功完成后通过 workflow_run 触发 Pages 发布，保证定时更新会出现在网站上。修改 collect.py 时先进行一次不抓取新图片的元数据刷新。

## 官网核对与配图

- lab_sources.json 保存 25 位学者的课题组网页或官方机构资料页。部分网页仅列代表性论文；无法访问、动态内容和没有 DOI 的条目会限制覆盖。
- enrich.py 只用精确 DOI 对照已有目录，绝不凭官网姓名新增文章。未匹配 DOI 写入 data/source-report.json，网页“官方来源”按钮可查看核对结果。
- 配图只取与单篇 DOI 对应的网页区块，并检查图片地址；开放获取全文则通过 PMCID 匹配图片。详情页提供来源链接。官网配图、正文插图和摘要图分别标注，不能混称为摘要图。
- 每篇文章都有视觉封面。无可用原图时显示期刊、年份和标题组成的“文献封面 · 非原文图片”；外部图片加载失败也自动回退，不伪造科学示意图。
- 图片源自出版社、课题组及开放仓储；通过自动校验的图片会缓存到本站，其他外链仍可能受来源变更或防外链限制。“只看真实配图”按已核对的图片记录筛选，不保证外部图片一直可访问。
- data/enrichment.json 缓存配图及全文检查结果。常规更新跳过已检查的无图文章；需要重新检查时运行 `python enrich.py --all-oa --retry`。仅更新官网可用 `python enrich.py --labs-only`。

## 出版社 Visual / Graphical Abstract

`python publisher.py` 根据已有论文的 DOI 访问出版社公开原文，核对页面 DOI 后，仅选取明确标注为 Graphical Abstract、Visual Abstract、TOC Graphic，或位于原文摘要区的图片。普通正文第一图、社交预览图和期刊标志不视作摘要图。找到的出版社摘要图优先展示，并保留原有配图记录和来源。

结果保存在 data/publisher-graphics.json，覆盖情况和逐篇状态也可在网页查看。`--limit 80` 可限制本次检查数量；`--retry-network` 只重试网络或图片请求失败；`--retry` 可重查所有尚未配图的条目；`--apply-only` 只应用缓存。首次默认检查所有未尝试 DOI，后续只补充新条目。有些期刊没有摘要图；“未检测到”仅表示本次解析未找到。遇到登录、403 或验证页面不会绕过；同一站点持续拒绝访问时，剩余论文标记为暂缓，不能算作已逐篇检查。

GitHub 的手动 Refresh catalog 工作流会重新核对尚未配图的出版社条目，使当前环境的访问失败不会永久阻止后续补图。已找到的摘要图继续使用缓存。

对于已能在普通浏览器打开、但自动请求被 403 拒绝的公开摘要页，维护者可导出只含页面 DOI、Visual Abstract 区块的 JSON 快照（字段 `doi`、`source`、`html`），运行 `python publisher.py --page-snapshot snapshot.json`。仅接受已在固定 ORCID 目录中的 DOI，并重新验证图片的实际 GET 响应；不会新增论文或导入浏览器登录信息。带签名有效期的公开图片保存在 `assets/publisher/`，详情保留出版社出处；这些图片不适用代码的 MIT 许可。自动更新与 Pages 发布均会保留这些文件。

## 无需人工操作的批量配图

运行 python graphics.py 即可按目录中固定 ORCID 已确认的 DOI 批量补图，不需要浏览器、鼠标、登录状态或逐篇页面快照。

- 出版社 RSS：publisher-feeds.json 保存 ACS 官方期刊 RSS 目录，也支持为其他出版社配置期刊级 feeds 链接；不需要为每篇文章编写规则。程序读取所需期刊的 ASAP 和当前期 RSS，仅匹配已有 DOI，验证图片实际内容后缓存到本站。普通 RSS 配图标为“期刊目录图”；只有来源明确标为 Graphical/Visual Abstract 时才标为“摘要图”。
- 开放仓储：通过 NCBI 于 2026 年更新的 PMC Cloud API 发现文章版本，核对元数据和 JATS 中的 DOI；只采用明确标注为图形摘要、且官方元数据提供了媒体下载地址的图片。未提供媒体文件时不拼接或猜测地址。
- 更新与重试：data/automatic-graphics.json 缓存成功结果、各来源状态和重试时间；每轮默认检查 150 篇尚未核实的仓储记录。失败不清除已有图片；期刊目录图不会覆盖已核实的摘要图。带签名或普通图片均校验后保存为本地资产。
- GitHub 的每日 Refresh catalog 会运行批量配图。也可单独运行 Actions → Refresh illustrations；修改采集模块或 RSS 配置后会自动运行。刷新成功后自动发布 Pages，两个写数据的工作流会排队执行，避免提交冲突。

常用命令：

    python graphics.py --rss-only
    python graphics.py --repository-only --repository-limit 150
    python graphics.py --retry --max-seconds 600
    python graphics.py --apply-only

RSS 通常只含近期文章；历史论文需由开放仓储或可访问的出版社页面补充。受限页面、仓储没有发布的媒体文件、没有图形摘要的文章，无法保证全部自动取得。它们会保留真实状态，后续按重试计划继续检查，不用正文第一图假冒摘要图。

官方数据接口：[ACS RSS](https://pubs.acs.org/pages/rss)、[PMC Cloud](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/)。之前的 page-snapshot 导入仅作为可选维护工具，自动工作流不调用它。

## GitHub Pages

将源码上传到公开仓库。在 Settings → Pages 中选择 GitHub Actions，然后运行 Deploy Pages。工作流发布网页、学者配置、论文快照和来源核对报告。

目标公开仓库：methanosarcina/GCE-scholar。GitHub Pages 发布地址为 https://methanosarcina.github.io/GCE-scholar/ ，手机和电脑均可通过浏览器访问；以实际部署成功为准。

## 来源

[Europe PMC API](https://europepmc.org/RestfulWebService)；各学者身份匹配依据保存在 scholars.json 的 identityEvidence。

Xiaozhou Luo 的 ORCID 0000-0001-9808-6890 已由[出版社论文页面](https://academic.oup.com/bib/article/24/1/bbac476/6834141)核对。固定 ORCID 不等于数据库收录了其全部发表记录。
