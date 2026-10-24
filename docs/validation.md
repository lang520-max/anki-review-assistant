# 验证记录

本文件区分已执行检查和仍需外部环境的验收。最终 CI 状态以对应提交的 Actions 记录为准。

## 已在云端工作区执行

- Python 3.12：12 项服务端测试通过；PostgreSQL 用例在没有连接变量时明确跳过。
- 覆盖每日统计、Hard 计入成功、学习／手动事件排除、笔记聚合、夏令时、空分母、未知时区、重复事件、增量删除、幂等性、用户隔离、scope 校验、MCP 握手与八个工具发现、真实 MCP 工具调用、JWT 签名／issuer／audience／过期／撤销校验。
- Python 编译检查和 Anki 查询边界静态检查通过。

## GitHub Actions

- 已实际触发 Android 构建，并修复 SDK 已移除的 tools 包、Kotlin Retention 名称冲突及 OAuth URI Lint 错误。
- 服务端单元／ASGI 测试与 PostgreSQL 事务／删除保护测试已在 Actions 成功执行。
- 最终 Android APK、设备测试与 PostgreSQL 完成结果将在构建结束后更新，不能把工作流文件存在等同于成功。

## 尚未执行

- 物理安卓手机上的 AnkiDroid 权限与真实牌组端到端验收。
- 私人域名上的 HTTPS、Keycloak 登录撤销、Android 联网同步和 ChatGPT 账号接入。
- 生产签名密钥配置、正式版本发布、付费资源创建。

所有自动测试仅用合成数据；没有上传用户的真实学习数据。
