# 手机 ChatGPT 私人 Anki 插件

数据路线：AnkiDroid → 既有私人上传服务 → 独立的只读 MCP 服务 → ChatGPT。查询服务运行在 ECS，不依赖用户电脑开机。手机 App 的上传授权与 ChatGPT 查询授权分开。

MCP 地址：`https://47-109-157-25.sslip.io/anki-plugin/mcp`。鉴权：OAuth；客户端注册：DCR；scope：`study:read`。ChatGPT 自动发现资源元数据和授权端点后，用户在私人连接页输入独立的 16 位一次性连接码。连接码通过服务器 CLI 生成，7 天有效，单次使用，不放进仓库或 APK。

在 ChatGPT 网页的“插件 → 添加 → 添加自定义 MCP 服务器”创建个人插件，然后安装/连接。同一账号的手机客户端可使用其可用插件，实际入口仍需真机确认。当前账号已经通过网页发现服务元数据。授权后可直接询问昨日耗时、Again 最多的词、未来负担和修复进度；模型应先核对上传时间。创建连接与授权成功是两件事，不能将插件卡片出现当作授权已完成。

## 服务边界

- 9 个工具：同步状态、学习总览、每日记录、难词、观测成功率、作答历史、未来负担、牌组规模、修复进度。全部只读；没有上传、删除或改卡工具。
- 使用 `mode=ro` 读取既有快照，systemd 同时把上传数据库目录设为只读；OAuth 状态使用 `/var/lib/anki-plugin/auth.sqlite3` 独立保存。
- 严格绑定资源、scope、用户、客户端、精确回调地址与 PKCE。授权码只用一次，访问令牌 15 分钟，刷新令牌最长 90 天并轮换，重放旧刷新令牌会撤销该连接。
- 授权页使用 Cookie + 隐藏表单值 + 服务端哈希校验，来源校验，十分钟会话有效期，连接码不可重复使用。浏览器使用 `Referrer-Policy: same-origin`，避免 Chromium 对同站表单发送 `Origin: null`，同时抑制跨站回调的来源信息。
- 手机上传令牌不能用于插件读取；插件令牌也不能向原上传服务写入。删除手机云端副本后，插件查询显示无数据，不凭历史回复编造分析。
- 插件输出只包含已经获手机上传授权的数据。多设备必须明确选择，不自动合并作答。日期范围按手机 Anki 学习日解释。

## 部署与运维

`deploy/install-plugin.py` 部署独立 `/opt/anki-plugin/releases/<release>`，绑定回环地址 8767，由既有 nginx HTTPS 转发。不会替换或重启原上传服务。部署前备份授权数据库和代理配置，运行协议测试，检查服务和 nginx；失败回退配置与 release 指针。

生产以 `/opt/anki-plugin/current` 为工作目录，使用 `venv/bin/python -m server.mcp.personal_plugin` 运行，不能在 `server/` 内运行，否则本仓库 `mcp` 包会遮蔽 SDK。CLI `--login-code` 创建连接码，`--revoke-all` 撤销所有插件读取授权及未使用连接码，保留手机上传授权和数据。日常断开某一个连接使用标准 OAuth 撤销端点。

授权元数据：`/.well-known/oauth-authorization-server/anki-plugin`；资源元数据：`/.well-known/oauth-protected-resource/anki-plugin/mcp`。只接受官方文档当前的精确稳定回调 `https://chatgpt.com/connector_platform_oauth_redirect`，并在成功和错误的授权回调中返回精确 issuer。若未来 ChatGPT 改用其他回调，需重新核对后更新精确允许列表，不能开放任意回调。

## 验证

本地/服务器测试覆盖元数据发现、匿名与上传令牌拒绝、回调与 scope 限制、表单保护、一次性码、PKCE、资源绑定、撤销、刷新轮换与重放、进程重启持久化、真实合成快照读取、空数据和多设备。公网另使用一次性测试连接完整执行初始化、9 个工具发现、同步状态查询与撤销；不打印令牌。

官方接入说明：[Authentication](https://developers.openai.com/plugins/build/auth)、[Connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt)。文档支持与账号实际可用性应分别验证。

2026-10-30 验收：当前用户 ChatGPT 账号已创建、安装并完成私人 OAuth 授权；9 个工具出现在真实插件工具目录中，已通过正式连接调用 `get_sync_status` 成功返回“手机还没有上传分析数据”。这证明账号连接和工具调用已经走通，不代表已取得真实学习数据或已在手机 App 实测。手机上传后，查询即可使用已授权快照。真实浏览器另验证了表单来源策略和跨域回调；CSP 仅额外允许 `https://chatgpt.com` 回跳，服务端仍精确校验回调 URL。
