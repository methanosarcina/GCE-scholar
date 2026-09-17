# Scholar Gallery · 学者论文画廊

面向个人科研阅读的学者论文网站。内置 25 位关注学者，以图片和摘要卡片浏览文献。原生 HTML/CSS/JavaScript，Python 标准库采集器，无需付费 API key。

## 本地启动

需要 Python 3.10 或更新版本。在项目目录执行：

```sh
python server.py
```

打开 http://127.0.0.1:8765 。请通过 HTTP 打开，而非双击 HTML。停止服务用 Ctrl+C。

## 功能

- 学者导航、论文详情、作者机构与 ORCID、出版社和 Europe PMC 原文链接。
- 优先展示公开摘要图，其次正文插图，最后摘要文字；正文插图不会标记成摘要图。
- 已载入论文的关键词、年份、配图筛选，引用数排序和 JSON 导出。
- 初始快照中，24 位学者按公开作者资料匹配到 ORCID，并读取全部 ORCID 关联结果；Xiaozhou Luo 暂保留最近 36 条姓名检索候选及分页游标。本地版可继续在线加载；GitHub Pages 静态版提供数据源检索链接。
- ORCID 与高级检索设置保存在浏览器 localStorage。
- GitHub Pages 可托管完整静态快照；本地服务器代理 API 请求。实测上游 CORS 和 JSONP 不能稳定使用，因此静态版不依赖它们，数据更新通过采集器进行。

## 作者身份与覆盖范围

**初始名单来自用户提供的截图；多数作者身份仍需用户确认。** ORCID 推定依据保存在 `scholars.json` 的 `identityEvidence`（论文原文链接和机构）。用户已确认 Chang Liu 的 UC Irvine、Haiyan Liu 的 USTC、Tao Liu 的北京大学、Xiao Xie 的清华大学身份，并结合公开来源定位 ORCID。Xiaozhou Luo 暂未收紧身份，其记录出现多个 ORCID。姓名检索命中数不是该学者经过核实的论文总数。

四位作者的核对来源：[Chang Liu](https://pubmed.ncbi.nlm.nih.gov/32198494/)、[Haiyan Liu](https://wires.onlinelibrary.wiley.com/doi/abs/10.1002/wcms.1646)、[Tao Liu](https://orcid.org/0000-0001-5347-5892)、[Xiao Xie](https://www.chem.tsinghua.edu.cn/info/1097/3748.htm)。谢肖在清华主页记载此前任职普林斯顿，因此不能只按清华机构筛选其历史论文。

在论文详情中查看作者机构和 ORCID，用设置面板更改查询。持久配置写入 `scholars.json` 的 `query`，例如 `AUTHORID:"0000-0002-6231-5302"`。ORCID 检索也会遗漏尚未关联该标识的记录，不应等同于完整发表清单。机构限制可能遗漏作者换单位前的论文。下一步应结合实验室官网、ORCID 和其他索引交叉核实。

数据库为 Europe PMC，覆盖生命科学及相关领域，不能保证收录每位学者所有文章。默认不造假论文、不用生成图冒充真实摘要图、不绕过付费墙。

## 更新数据

```sh
python collect.py                 # 每人最近一页；每人最多检查 4 篇 OA 论文配图
python collect.py --resolved-all  # 推荐：ORCID 学者全量，未定位姓名仅一页
python collect.py --figures 20    # 增加图片提取数量
python collect.py --all --figures 100  # 拉取每个查询的全部数据库结果
python -m unittest discover -s tests
```

**建议先核实作者身份，再执行 `--all`**，常见姓名可能匹配很多不同研究者。全量拉取可能耗时较长。同步失败保留该作者旧快照并记录错误；不会把失败记录冒充空的完整论文集。`complete` 仅代表该查询已分页到底。

后续在线加载的论文默认显示摘要；配图由采集器离线补充。快照中的图片是 NCBI 原始图片链接，未下载或再分发图片文件；每张图保留原文链接，许可字段取自数据源。图片可能因原站变更或网络条件不可用。转载使用前应查看具体文章的许可说明。仓库的 MIT 许可仅适用于原创程序代码，不适用于论文、摘要或图像。

## 发布到 GitHub

目标公开仓库建议为 `methanosarcina/scholar-gallery`。本项目目前是可上传源码，是否已经发布以实际远程仓库为准。

1. 在 GitHub 创建空的公开仓库 `scholar-gallery`。
2. 上传本目录全部文件，或使用下面的 Git 命令。
3. 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。
4. 运行 Deploy Pages 工作流，或推送到 main。默认网址为 `https://methanosarcina.github.io/scholar-gallery/`（部署完成前不可用）。

```sh
git init -b main
git add .
git commit -m "Build Scholar Gallery"
git remote add origin https://github.com/methanosarcina/scholar-gallery.git
git push -u origin main
```

部署工作流只发布网站文件。Refresh catalog 工作流可手动运行，更新后提交快照；随后手动运行 Deploy Pages 发布更新（默认 GITHUB_TOKEN 的提交不会触发其他工作流）。无后台定时任务，无分析跟踪。

## 文件

`index.html` / `style.css` / `app.js`：网站；`scholars.json`：名单及查询；`data/catalog.json`：数据快照；`collect.py`：采集及图片解析；`server.py`：本地服务。

API 参考：[Europe PMC REST API](https://europepmc.org/RestfulWebService)。图片出处：[PubMed Central](https://pmc.ncbi.nlm.nih.gov/)。
