# 把 GCE-scholar 交给另一个 agent

这个项目可以由支持终端、文件编辑和 Git 的 agent 接手。Skill 是维护手册，源码和 `data/` 是项目状态，GitHub 连接负责访问权限；仅发一个 SKILL.md 不会自动交接源码、账号或原聊天记忆。

仓库：https://github.com/methanosarcina/GCE-scholar
网站：https://methanosarcina.github.io/GCE-scholar/

## 在 Antigravity 中接手

1. 克隆上面的仓库，或解压完整交接包。
2. 在 Antigravity 中打开包含 `AGENTS.md`、`collect.py` 和 `scholars.json` 的项目根目录。
3. 项目内已有 `.agents/skills/gce-scholar-maintainer/SKILL.md`；支持 Agent Skills 的版本会发现它。若当前会话未发现新 Skill，重新打开项目/新建会话，或明确要求读取该文件。
4. 把下面的交接提示发给它，再附上你要做的具体任务。

```text
请接手维护 GCE-scholar。先阅读 AGENTS.md，并使用项目中的 gce-scholar-maintainer skill。
先执行只读检查，说明当前目录是否正常，再完成我接下来给出的具体任务。
保留严格 ORCID 收录、Crossref 自动补充、真实日期和图片来源，以及手机按学者加载。
如需发布，请依据本次任务的授权使用你自己的 GitHub 连接，不复制其他工具的认证文件。
```

## 其他 agent 工具

- 支持项目级 `.agents/skills/` 的工具可直接使用仓库内目录。
- Claude Code 可把整个 `gce-scholar-maintainer` 文件夹复制到项目的 `.claude/skills/`，不能只复制 SKILL.md 而漏掉 references/scripts。需要项目常驻规则时，在工具的项目指令中指向根目录 `AGENTS.md`。
- 采用其他 Skill 搜索目录的工具，把整个 Skill 文件夹放到它的受支持目录；不要假设所有工具都会自动扫描相同位置。
- 不支持 Skill 的工具也能接手：明确让它读取 `AGENTS.md`、Skill 入口及与任务有关的 references，然后在完整仓库中工作。
- 只拿到独立 Skill ZIP 时仍需取得项目源码；只拿到完整交接 ZIP 时，发布改动前仍需配置新的 GitHub 授权和 Git remote。推荐直接克隆仓库以保留版本历史。

这些步骤不要求安装 Antigravity 才能运行网站。根目录 `collaboration/` 是可选的历史协作辅助，不是网站依赖。

## 第一次检查

以下命令在项目根目录执行：

```sh
python .agents/skills/gce-scholar-maintainer/scripts/inspect_project.py --root . --scholar jie-wang --recent 3
python -m pip install -r requirements.txt
python -m unittest discover -s tests
node --test tests/test_dates.cjs tests/test_loading.cjs
python build.py --output _site
python server.py
```

本地地址是 http://127.0.0.1:8765 。单独执行检查和构建不抓取新论文，也不发布网站。数据抓取和发布步骤见 Skill 的 `references/runbook.md`。

## 权限与携带文件

读取公开仓库和公开学术数据通常不需要账号 token；推送仓库或触发私有权限的操作需要新工具自己的 GitHub 授权。当前仓库是公开的。

交接须保留隐藏的 `.github/`、`.agents/skills/`，以及全部 `data/` 缓存和 `assets/publisher/`。源码 ZIP 不包含 `.git/`，因此不带 Git remote 和本机认证；也无需携带 `_site/`、Python 缓存或 node_modules。

不要复制上一个工作区的 `work/`、GitHub CLI 配置、token、浏览器配置/cookies、设备登录记录或其他本机账号目录。代码的 MIT 许可不涵盖第三方论文与图片。

## 官方格式说明

- Antigravity 项目技能目录与格式：https://antigravity.google/docs/skills
- Claude Code 技能目录与格式：https://code.claude.com/docs/en/skills

本交接入口整理于 2026-11-03。学者数、论文数、任务状态和在线部署版本以实际检查结果为准。
