# Anki Review Assistant

新增一体化路线：定制 AnkiDroid 在同一个 App 中完成背词、分流、学习分析和私人上传，手机作为唯一答题来源。手机实现见 [ankidroid-integration](ankidroid-integration/README.md)，轻量 ECS 服务与手动查询见 [手动询问路线](docs/personal-route.md)。此路线使用严格的单词字段上传和完整快照替换；每天 08:00 自动分析暂不实现。下面保留原独立分析 App 的说明，其构建产物不等同于定制背词 App。

AnkiDroid 英语复习分析助手：**只读、本地优先、默认不上传数据**。已有牌组无需重建，不添加或修改任何 Anki 卡片。Android 8.0 及以上，Kotlin / Jetpack Compose。

[English](README_EN.md) · [手机安装](docs/installation.md) · [字段兼容性](docs/api-compatibility.md) · [指标定义](docs/metrics.md) · [隐私](docs/privacy.md)

## 获取测试 APK

打开仓库 **Actions → Android APK → 最近成功运行 → Artifacts**，下载 `anki-review-assistant-debug-…` 并解压安装 `app-debug.apk`。必须登录有仓库权限的 GitHub 账号。ZIP 内包含校验和与提交标识；不要从失败运行中寻找安装包。

首版采用 CI 临时 Debug 签名，不保证不同构建之间覆盖安装；卸载前导出本地副本。生产签名私钥未创建，也不会提交仓库。正式签名通过 GitHub Secrets 和手动草稿 Release 工作流管理。

## 已实现能力

- AnkiDroid 检测、官方权限授权及撤销提示，读取牌组、笔记及设备实际支持的卡片调度字段。
- 中文首页、统计、遗忘排行、同步、设置页面；Room 索引与私有数据文件支持离线查看。
- 通过系统文件选择器只读导入含学习记录的 `.apkg` / `.colpkg`，支持旧 SQLite 和新版 Zstandard 容器。
- 7 / 30 / 90 天和自定义学习日范围、牌组筛选、每日趋势、年轻／成熟观测成功率、按笔记聚合遗忘排行。
- JSON 导出，笔记正文默认排除；显式启用的私人云同步、牌组范围选择、增量传输、离线重试。
- 独立 Python 私人服务与八个只读 MCP 工具，OIDC / PKCE、Keystore、用户隔离、版本冲突及远程删除保护。
- GitHub Actions APK 构建、Kotlin 测试、Lint、合成文件模拟器测试、服务端与 PostgreSQL 集成测试。

**重要的数据边界：**当前 AnkiDroid 官方 API 不提供 revlog 查询。每日回答次数、按钮和耗时来自用户选择导入的真实历史文件，不会持续自动从手机取得。没有历史时显示不可用；卡片当前计数不能替代逐次历史。不同数据来源单独保存，更新时间始终可见。

本版不运行 FSRS 训练，不声称观测成功率等于预测保持率，不给出没有证据的精确新词配额。真实手机上的 AnkiDroid 兼容性、正式签名和公网 OAuth / ChatGPT 连接需要分别验收；服务端代码存在不代表已经部署。

## 开发与测试

在 Linux 或云端使用 JDK 17、Android SDK 35：

```sh
cd android
bash gradlew :core:test :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

在项目根目录，Python 3.12：

```sh
python -m pip install -r server/requirements.txt
python -m unittest discover -s server/tests -v
python scripts/check_read_only.py
```

PostgreSQL 测试在 Actions 服务容器中执行，本地没有 `TEST_DATABASE_URL` 时明确跳过。设备测试在 Android 模拟器运行 `:app:connectedDebugAndroidTest`。测试数据均为合成内容，不需要你的真实牌组。

## 私人 MCP 与部署

`get_study_overview`、`get_daily_reviews`、`get_retention_stats`、`get_difficult_words`、`get_review_history`、`get_future_workload`、`get_deck_statistics`、`get_sync_status`。

工具只读取已同步的数据，返回来源、统计口径和局限。上传与删除属于另行授权的 REST API，MCP 不暴露写入工具。云服务默认关闭，没有购买或部署任何资源。

参见 [架构](docs/architecture.md)、[部署与费用预算](docs/deployment.md)、[验收记录](docs/validation.md)。ChatGPT 自定义 MCP 的可用性由账号、客户端及工作区权限决定；始终支持 JSON 文件备用方案。

## 开源与贡献

原创实现采用 [Apache-2.0](LICENSE)，提供明确的复用与专利授权。参考项目许可证见 [第三方声明](THIRD_PARTY_NOTICES.md)。没有复制 Anki-Connect 或现有 AGPL MCP 实现。参见 [贡献指南](CONTRIBUTING.md)、[安全报告](SECURITY.md) 与 [更新记录](CHANGELOG.md)。
