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

## 官网核对与配图

- lab_sources.json 保存 25 位学者的课题组网页或官方机构资料页。部分网页仅列代表性论文；无法访问、动态内容和没有 DOI 的条目会限制覆盖。
- enrich.py 只用精确 DOI 对照已有目录，绝不凭官网姓名新增文章。未匹配 DOI 写入 data/source-report.json，网页“官方来源”按钮可查看核对结果。
- 配图只取与单篇 DOI 对应的网页区块，并检查图片地址；开放获取全文则通过 PMCID 匹配图片。详情页提供来源链接。官网配图、正文插图和摘要图分别标注，不能混称为摘要图。
- 每篇文章都有视觉封面。无可用原图时显示期刊、年份和标题组成的“文献封面 · 非原文图片”；外部图片加载失败也自动回退，不伪造科学示意图。
- 图片由原网站提供，可能受网络、来源变更或防外链限制。“只看真实配图”按已核对的图片记录筛选，不保证外部图片一直可访问。
- data/enrichment.json 缓存配图及全文检查结果。常规更新跳过已检查的无图文章；需要重新检查时运行 `python enrich.py --all-oa --retry`。仅更新官网可用 `python enrich.py --labs-only`。

## 出版社 Visual / Graphical Abstract

`python publisher.py` 根据已有论文的 DOI 访问出版社公开原文，核对页面 DOI 后，仅选取明确标注为 Graphical Abstract、Visual Abstract、TOC Graphic，或位于原文摘要区的图片。普通正文第一图、社交预览图和期刊标志不视作摘要图。找到的出版社摘要图优先展示，并保留原有配图记录和来源。

结果保存在 data/publisher-graphics.json，覆盖情况和逐篇状态也可在网页查看。`--limit 80` 可限制本次检查数量；`--retry-network` 只重试网络或图片请求失败；`--retry` 可重查所有尚未配图的条目；`--apply-only` 只应用缓存。首次默认检查所有未尝试 DOI，后续只补充新条目。有些期刊没有摘要图；“未检测到”仅表示本次解析未找到。遇到登录、403 或验证页面不会绕过；同一站点持续拒绝访问时，剩余论文标记为暂缓，不能算作已逐篇检查。

GitHub 的手动 Refresh catalog 工作流会重新核对尚未配图的出版社条目，使当前环境的访问失败不会永久阻止后续补图。已找到的摘要图继续使用缓存。

## GitHub Pages

将源码上传到公开仓库。在 Settings → Pages 中选择 GitHub Actions，然后运行 Deploy Pages。工作流发布网页、学者配置、论文快照和来源核对报告。

目标公开仓库：methanosarcina/GCE-scholar。GitHub Pages 发布地址为 https://methanosarcina.github.io/GCE-scholar/ ，手机和电脑均可通过浏览器访问；以实际部署成功为准。

## 来源

[Europe PMC API](https://europepmc.org/RestfulWebService)；各学者身份匹配依据保存在 scholars.json 的 identityEvidence。

Xiaozhou Luo 的 ORCID 0000-0001-9808-6890 已由[出版社论文页面](https://academic.oup.com/bib/article/24/1/bbac476/6834141)核对。固定 ORCID 不等于数据库收录了其全部发表记录。
