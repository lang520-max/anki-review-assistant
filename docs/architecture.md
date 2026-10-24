# 架构与接口

Android（Compose）→ 只读来源适配器 → Room 本地来源快照 → Kotlin 统计 → JSON 导出／显式启用的同步 → 私人服务 → 只读 MCP。

`android/core` 是不依赖 Android 的模型与统计。应用层负责权限、SQLite 只读导入、存储、界面、Keystore、OAuth 和 WorkManager。Room 保存数据集索引，版本化 JSON 保存于应用私有不可变文件，避免大型 TEXT 超出 SQLite CursorWindow。先写新文件再事务切换索引，失败保留旧副本。统计仍会加载整个所选集合，百万事件可能占用大量内存。导入不会与 Provider 数据自动合并，也不会假装实时取得历史。

Android 当前状态读取通过官方 `ContentResolver.query`，隔离在 `AnkiReader`；所有其他功能不接触 Anki Provider。数据源失败或用户取消时不提交半份数据。导入在私有临时目录中处理，关闭后清理。

## JSON v1

顶层字段：`schemaVersion`、`collectionId`、`source`、`capturedAt`（毫秒）、`zoneId`、`rolloverHour`、`creationSeconds`（秒）、`historyAvailable`、`historyComplete`、`decks`、`notes`、`cards`、`reviews`、`warnings`。ID 为整数，跨语言消费者不得经 JavaScript 浮点数舍入。

Review 保留 `id`（原始毫秒事件时间／ID）、`cardId`、`ease`、`interval`、`lastInterval`、`timeMs`、`type`。负间隔按原始秒单位保存，不强转为天。卡片 `due` 保留调度器原始值，必须结合队列解释。

## 同步 REST API

所有 `/v1` 路由要求 OIDC 令牌并从已验证的 subject 推导用户，客户端不能指定 owner。

- `GET /v1/collections`：读取当前用户集合状态（`study:read`）。
- `POST /v1/collections/{id}/sync`：`baseRevision`、幂等 `batchId`，以及首传 `snapshot`，或后续 `metadata`、各表 `upserts`、`deletes`（`study:sync`）。
- `DELETE /v1/collections/{id}`：移除远端内容并保留无正文的版本墓碑，阻止在途旧上传恢复数据（`study:delete`）。

后续传输只发送改变的行和删除 ID。事务与版本租约防止覆盖其他设备更新；重复批次不重复记账。HTTP 409 不自动覆盖远端，需核对来源后重新登录以取得版本并明确重传。首次登录后需手动选牌组、开启上传；默认仅发送结构和学习事件，不发送笔记正文。

Android 保存成功上传快照作为私有增量检查点。网络失败由 WorkManager 退避重试，最多六次尝试；关闭开关取消任务。需要再次手动同步，不承诺定时自动获得 Anki 历史。重新导入／读取后选择同步，才上传新状态。

## 服务端

FastAPI + 官方 MCP Python SDK；SQLite 用于轻量测试，PostgreSQL 用于部署。版本化快照按用户和集合分隔；数据库事务保护版本变化。SDK 处理 Streamable HTTP 协议和 OAuth 资源元数据。当前锁定 SDK 1.29.0，以实际握手测试覆盖其支持的协议版本，不声称实现尚未支持的所有最新规范特性。

八个 MCP 工具均标注只读，统一要求集合 ID、起止学习日；支持适用的牌组筛选，明细分页上限 500。`get_sync_status` 和牌组当前统计与日期无关；未来负担只返回支持的未来 30 天中落在请求日期内的部分。

SQL 查询均参数化；Anki 笔记 HTML 仅转为纯文本显示，不执行脚本。MCP 提示模型将笔记内容视为数据，不作为指令。
