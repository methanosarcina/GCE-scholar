# 按任务维护

所有命令均在项目根目录执行；如果环境命令名是 python3，用它替代 python。先查看当前源文件和 Git 差异，不要把旧文档里的样例计数当成当前状态。

## 接手与本地验证

```sh
python .agents/skills/gce-scholar-maintainer/scripts/inspect_project.py --root .
python -m pip install -r requirements.txt
python -m unittest discover -s tests
node --test tests/test_dates.cjs tests/test_loading.cjs
python build.py --output _site
python server.py
```

本地地址 http://127.0.0.1:8765 。这些检查、构建和本地预览不需要 GitHub 写权限。已有测试覆盖身份过滤、日期精度、图片解析、Crossref 缓存、构建分包、超时重试及切换竞态。只改文案时可缩小检查范围；新增解析或数据流程时跑相关回归和构建。

浏览器自动检查使用环境已有工具。不要复制上一台电脑的浏览器运行库绝对路径；若没有浏览器工具，准确说明已完成的静态/单元验证，不能声称实机手机已验证。

## 新增学者

1. 用官方机构页、本人课题组、论文作者块或公开 ORCID 资料交叉核对身份和唯一 ORCID。名字相同不够。保留 `identityEvidence`，不要求用户重复确认已经给出的机构。
2. 在 `scholars.json` 添加安全且唯一的 id、name、orcid、固定 query；可填中文 nativeName。需要时在 `lab_sources.json` 添加真实官方列表。
3. 运行元数据阶段并补图。新增配置后必须生成相应 catalog entry；空壳配置不能通过构建的成员一致性校验。
4. 用检查脚本限定该 id，验证作者 ORCID 和数据；在手机宽度检查姓名搜索、日期、图片来源。

不要把官网有名有姓但缺作者 ORCID 的条目直接塞入目录，也不伪造作者标识来满足构建。

## 元数据更新与漏收

轻量刷新：

```sh
python collect.py --resolved-all --figures 0
python crossref.py
python publisher.py --apply-only
python graphics.py --apply-only
```

collect 重建基础目录，随后 crossref 补回并更新近期期刊记录。Crossref 故障时可 `python crossref.py --apply-only` 恢复已验证缓存。不能在 collect 后就发布“刷新完成”。Crossref 本身支持 `--scholar jie-wang`、`--days 365`；选择一个学者只限制此次查询，其他安全缓存仍会应用。

对用户指出的某篇漏收论文，先核对 DOI、在线与卷期日期，再查各来源是否收录及作者 ORCID 是否存在。Europe PMC 查不到不等于没有论文；Crossref 中查到姓名也不等于通过严格 ORCID。

完整更新采用现有工作流或以下顺序，注意它可能执行较多联网请求：

```sh
python collect.py --resolved-all --figures 4
python crossref.py
python enrich.py --all-oa
python publisher.py --retry
python graphics.py --repository-limit 150 --max-seconds 600
```

保留成功缓存。源失败时标明真实状态，不用空结果覆盖现有成功图，也不把缓存补回条数当作净新增。

## 配图与课题组网站

- `python enrich.py --labs-only` 刷新官方清单；按精确 DOI 或已支持的出版社文章 URL 与既有目录匹配。引用后紧邻的单张纯图段落可识别，同 DOI 对应不同图会保守拒绝。
- `python publisher.py --limit 40` 限量尝试公开出版社摘要区；`--retry-network` 可限于网络/图片失败，`--apply-only` 不联网重查。
- `python graphics.py --rss-only` 看官方期刊 RSS；`--repository-only --repository-limit 150` 看 PMC Cloud；`--apply-only` 应用成功本地缓存。
- RSS 只保留近期窗口，刚发表几天的论文也可能已滚出；失败不证明原文无摘要图。新期刊用 `publisher-feeds.json` 的期刊级 feed 配置，不做每篇手工规则。
- PMC Cloud 必须核对元数据/JATS DOI，只用元数据公开列出的 media_urls。没有媒体时保留 no_repository_media 等真实状态，不猜 URL。
- 用实际 GET 验图；某些学校服务器 HEAD 返回 405 而 GET 可读。不要因 HEAD 拒绝就误判图片不存在。
- 明确的图形摘要才标“摘要图”；其他公开配图保持目录图/课题组图/正文图标签。保留来源、许可和原始字节校验。
- 普通获取遇到登录或验证限制时记录并使用已配置的公开来源，不加入浏览器登录状态或验证码绕过。历史 `--page-snapshot` 是可选维护入口，自动流程不依赖鼠标或逐篇快照。

## 手机加载故障

先看是否已显示真实学者名、统计数字、错误提示和论文卡片。默认 Scholar Gallery/数字为 —/始终“正在读取”说明启动或数据加载未完成，不应只归咎排版。

检查路径：名单 → 小索引 → 当前学者分包。Network 中启动不应下载总 `data/catalog.json`，也不应请求 Google Fonts。确认相对 URL 在 `/GCE-scholar/` 子路径下正确。

保护已修复行为：

- 不依赖 structuredClone、可选链/空值合并语法；无 AbortController 也能超时结束。
- 失败首屏可见，能重试；未载入前禁用筛选/导出，函数仍能安全处理空状态。
- A 慢、B 快的切换顺序中，A 不能覆盖 B；按请求序号核对。
- 320、360、390、430px 无横向溢出；论文最多的学者也可滚动、筛选和打开详情。
- 旧浏览器缺 dialog.showModal 时保留详情回退。
- `index.html` 当前为 CSS/JS 资源带版本查询。更新前端时核对版本与手机缓存；需要时更新版本，不恢复阻塞字体导入。

改源文件，重新 build；不要把 `_site/` 当作源文件直接修。

## 发布到现有 GitHub Pages

仓库为 `methanosarcina/GCE-scholar`，默认发布分支 main。先查看 origin、分支和当前未提交改动。当前用户已授权发布时按授权继续；仅审阅/咨询任务不自动授予额外发布权限。

如果共享 Windows 工作区的 Git 报 dubious ownership，先核实当前绝对目录确为可信项目，再给本次 Git 命令添加 `-c safe.directory=<absolute-project-root>`；不需要将全部磁盘设为全局信任。正常克隆且所有者一致时无需这一步。

新工具连接自己的 GitHub 账号/连接器或标准 GitHub CLI。可用 `gh auth status` 和仓库权限检查判断授权；不要读取或拷贝旧机器的 token、浏览器 profile 或 work 目录。写权限 403 时应取得正确账号/仓库授权，不能把反复换入口当作修复。

1. 运行与本次改动相关的检查和 `python build.py --output _site`。
2. 审阅代码/配置与数据差异，只提交任务相关文件；data 与 assets 需要一起保留。
3. 按当前授权提交并推送或走 PR，避免强推。两个目录写入工作流会排队；本地与服务器同时有更新时先核对合并，不能直接覆盖一方成功缓存。
4. 查看 Deploy Pages 是否实际成功。数据刷新提交由成功 workflow_run 继续部署，不删该触发条件。
5. 读取线上 catalog-index.json、目标学者 shard、关键图片，并在可用浏览器里确认页面和详情。手机修复需在发布后验证线上加载行为。

Git 成功、workflow 成功和线上已见新数据是不同证据，汇报时区分。没有发布授权或连接时交付可审阅源码/包并说明该项未发布，不谎报已上线。

## 随后交接

完整仓库/源码包应包括 `.github/`、本 Skill、AGENTS.md、HANDOFF.md、全部 data 缓存和 assets。`.git/` 只存在于正常克隆/checkout，不加入分发 ZIP；`_site/`、临时测试 profile、缓存依赖和本机账号配置无需携带。

仅传 Skill 不等于交接项目状态。把原聊天的关键规则沉淀到这些文件；日常结果和数量通过检查脚本现算，不再把长聊天历史当成运行依赖。
