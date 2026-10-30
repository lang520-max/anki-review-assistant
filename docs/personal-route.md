# 定制 AnkiDroid：手动询问路线

部署地址优先使用 `https://47-109-157-25.sslip.io/anki-analysis/`，并保留 `https://kailang.online/anki-analysis/` 后备地址。两者都通过有效 HTTPS 访问同一个私人服务。当前网络实测后者 TLS 连接可能中断，因此不能只验证服务器本机地址。

此路线复用原仓库的统计模块，在 `server/mcp/personal.py` 增加轻量个人服务。现有 OIDC/MCP 部署路线继续保留。首版通过本对话获授权的 ECS SSH 查询已上传快照，其他 ChatGPT/Codex 会话不自动获得访问；没有定时日报或云端模型调用。

手机上传严格 schemaVersion=2：单词文字、范围内牌组、卡片调度字段、真实复习记录、分流计数、新增分流阶段和中断标记。其他笔记字段及媒体不接受。模板字段需先在手机本地预览，未选择的字段留空。

服务只监听 `127.0.0.1:8766`，由既有 nginx HTTPS 的 `/anki-analysis/` 转发。一次性授权码通过服务器命令生成，7 天有效且使用后失效；手机凭据由 Android Keystore 加密，服务端仅存哈希，不能查询单词明细。模型查询通过 SSH 命令进行，root 密钥不进入手机或仓库。

完整快照在验证完成后用 SQLite 事务替换；单设备序号防止旧请求覆盖，重复请求不追加。下一份成功快照反映撤销和删除，失败时保留上次完整版本。上传上限为压缩 8 MiB、解压 32 MiB。服务端校验 ID 唯一、引用关系、授权范围以及中断事件与实时复习日志的吻合。

手机原同步入口会安排私人上传，在 AnkiWeb 成功后再次安排更新后的快照；未登录 AnkiWeb、其同步失败或取消，不阻止独立私人上传。两路状态分别显示。返回牌组首页后补传，6 小时网络可用时补查；Android 系统可延迟任务。允许流量与 Wi-Fi；暂停后保留云端快照，无系统失败通知。删除副本同时撤销本设备凭据。

新增事件保存在词库旁的 `study-analysis-events.jsonl`，以官方复习日志 ID 和完整评分/用时/间隔指纹过滤：撤销后不导出失效事件，重做后能重新匹配。不额外修改官方调度、撤销记录和 AnkiWeb 同步标志。损坏尾行忽略并明确标记统计不完整。已有历史不能补造阶段与中断；旧卡片当前所在组不能证明历史作答所在组。

前台停留超过 2 分钟后，下次翻面或评分确认是否中断；确认后评分与次数保留，只从筛选后时间统计排除。后台时长不充当前台等待。查看结果按 Anki 实际 rollover、原生 dayIndex 和 day cutoff；预计负担仅包含当前已排程卡片。

新版本内的更新安装入口先建立 Anki 原生一致 colpkg 备份，加上事件及本机设置；不重复复制媒体，失败停止安装。**旧 routing5 更新器不包含这段新备份代码，首次升级到新版本前仍需使用旧版原生备份/导出，不能声称新代码已保护首次安装。** 设置副本含私人凭据，只保存在 App 私有目录，不公开分享。colpkg 只恢复词库，独立事件与设置需要一起恢复；这一恢复步骤需单独验收。

运维（在 ECS release/server 目录运行，使用 release/venv/bin/python）：

```text
python -m mcp.personal --database /var/lib/anki-analysis/analysis.sqlite3 --pair
python -m mcp.personal --database /var/lib/anki-analysis/analysis.sqlite3 --query get_study_overview --start 2026-10-29 --end 2026-10-29
python -m mcp.personal --database /var/lib/anki-analysis/analysis.sqlite3 --query get_repair_progress
```

部署脚本会备份已有数据库与被修改配置，校验 nginx，切换独立 release 并检查本机健康；失败回退配置。还必须验证公开 HTTPS、原站点健康和手机端上传。后续发布 APK 保留原包名、签名和对应完整 GPL 源码；构建完成不等于真机验收。
