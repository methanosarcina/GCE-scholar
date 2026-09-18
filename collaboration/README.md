# Antigravity 外部协作

安装并登录 Antigravity CLI 后，从项目目录运行：

```powershell
python collaboration/run_antigravity.py collaboration/publisher-review.md --include publisher.py
```

调用使用当前账号的默认模型；不自动切换模型、关闭审批或修改用户全局配置。
此入口用于有明确范围的代码审阅，采用 plan 模式和沙箱，不授权外部代理修改项目。
只有任务文件和 --include 明确指定的源码会放入提示，不传递完整聊天或整个论文目录。

完整输出、用量、会话编号和审阅报告保存在本地 `.collaboration/`，不会提交到 Git。
协调者只读取简短状态和 review.md，核实建议后自行修改与测试。
原始输出可能包含账号相关诊断，不应公开上传。

按出版社或完整适配器分配任务，避免逐篇启动代理。可确定的批量抓取交给 Python。
每次调用仍有 Antigravity 的启动上下文开销；减少 Codex 消耗不等于总 token 更少。
代码执行、网络采集等更广范围任务需另行明确任务和权限，不能借此审阅入口隐式扩大范围。
