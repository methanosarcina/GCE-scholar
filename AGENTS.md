# GCE-scholar maintenance

Public repository: https://github.com/methanosarcina/GCE-scholar
Live website: https://methanosarcina.github.io/GCE-scholar/

This is a static paper gallery maintained by Python collectors and GitHub Actions. The checked-in source, configuration and caches are the project state; a prior chat or a particular desktop agent is not required.

For maintenance, read `.agents/skills/gce-scholar-maintainer/SKILL.md`; load its references only for the task at hand. `HANDOFF.md` explains how to open the project in another agent tool. No global skill installation is required for the project-local bundle.

## Product requirements

- Only a configured, exact author ORCID grants paper admission. Names, affiliations and lab publication lists are evidence for identifying a scholar, never substitutes for a paper's author ORCID.
- Preserve source date precision and image provenance. A text cover, body figure, lab image, RSS catalog image and explicit graphical abstract are different categories.
- Data refresh order is `collect.py` → `crossref.py` → `enrich.py` → `publisher.py` → `graphics.py`. Preserve successful caches and image assets when a source fails.
- Publish with `build.py`: mobile startup must use the small catalog index and the selected scholar's shard. `_site/` is generated output.
- Keep the successful `workflow_run` Pages trigger and the shared data-workflow concurrency group. A bot's data commit alone does not reliably trigger another push workflow.

## Working here

Use Python 3.10+ and Node for the existing tests. Start locally with `python server.py`; it builds the same static output as Pages. There is no npm application build or database server.

Do not read the full catalog or raw caches into the model context just to get counts. Use the skill's read-only inspection script, targeted JSON processing, or a small relevant extract. Read current files and workflow definitions instead of relying on historical counts in documentation.

Repository access and any publication must follow the current user's task and authorization. This file and the skill do not supply credentials. Use the new tool's own GitHub connection; never copy another tool's token or browser profile.

用户偏好：用中文清楚说明结果。用户发英语句子或中英混用表达时，先保留原意给出自然、口语化英文，再用简短中文解释关键修改；若同时有实质问题，简短纠错后回答。原句已自然时不强行改写。
