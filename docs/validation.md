# 验证记录

本文件区分已执行检查和仍需外部环境的验收。最终 CI 状态以对应提交的 Actions 记录为准。

## 已在云端工作区执行

- Python 3.12：12 项服务端测试通过；PostgreSQL 用例在没有连接变量时明确跳过。
- 覆盖每日统计、Hard 计入成功、学习／手动事件排除、笔记聚合、夏令时、空分母、未知时区、重复事件、增量删除、幂等性、用户隔离、scope 校验、MCP 握手与八个工具发现、真实 MCP 工具调用、JWT 签名／issuer／audience／过期／撤销校验。
- Python 编译检查和 Anki 查询边界静态检查通过。

## GitHub Actions

- 已实际触发 Android 构建，并修复 SDK 已移除的 tools 包、Kotlin Retention 名称冲突及 OAuth URI Lint 错误。
- 服务端单元／ASGI 测试与 PostgreSQL 事务／删除保护测试已在 Actions 成功执行。
- Android 实现提交 `9fd01a9358640736daf868cfdbd4e6dd7efbf184` 的构建、Lint、Kotlin 测试及 APK 上传均成功；Android 15 模拟器 6 项测试全部通过。

成功运行记录：

- [Android APK（含下载产物）](https://github.com/lang520-max/anki-review-assistant/actions/runs/40088591786)
- [Android 15 模拟器 6 项测试](https://github.com/lang520-max/anki-review-assistant/actions/runs/40088591794)
- [服务端与 PostgreSQL 测试](https://github.com/lang520-max/anki-review-assistant/actions/runs/40088591801)

随后服务端增补了同步状态的服务器时间／版本返回值和历史覆盖时间范围，本地 12 项测试通过；Android 文件没有变化。

## 尚未执行

- 物理安卓手机上的 AnkiDroid 权限与真实牌组端到端验收。
- 私人域名上的 HTTPS、Keycloak 登录撤销、Android 联网同步和 ChatGPT 账号接入。
- 生产签名密钥配置、正式版本发布、付费资源创建。

所有自动测试仅用合成数据；没有上传用户的真实学习数据。
