# 私人服务部署方案

本项目没有代你购买、创建或部署服务器。安卓离线功能和 JSON 导出不需要服务器。以下方案用于之后自行托管，必须先完成验收。

## 资源与预算

建议 Linux VPS，2 vCPU、至少 4 GiB RAM、20 GiB 可用存储，以及两个指向同一机器的域名（学习 API 与授权服务）。费用预算暂按每月 **10—25 美元**计算，另预留域名、备份和流量费用；这是容量规划估算，不是任何商家的报价或收费承诺，购买前核实实际价格。

只有 Caddy 对外开放 80/443。API、两个 PostgreSQL 数据库及 Keycloak 通过 Compose 私有网络通信，没有数据库公网端口，不把手机 localhost 直接暴露到公网。配置模板不包含真实密码。

## 配置流程

1. 在服务器安装 Docker Engine 和 Compose，配置 DNS、防火墙和宿主机安全更新。
2. 复制 `deploy/.env.example` 为 `deploy/.env`。独立生成每个秘密，使用 URL-safe 值；不要将完成的文件提交 GitHub。
3. 在项目根目录执行 `docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build`。镜像为固定版本，部署前检查当前安全通告并更新、重新验证。
4. 登录 `https://你的授权域名/admin`，确认 `anki` realm 已导入，并创建个人用户；不要开放自助注册。
5. 创建 confidential OIDC 客户端 `anki-service`，关闭用户授权码和直接密码登录流程，仅供 introspection。把管理界面生成的客户端 secret 写入服务器 `.env` 的 `INTROSPECTION_CLIENT_SECRET`，重建 API 容器。
6. 核对 `anki-android` 是 public client，PKCE 为 S256，精确回调 `org.ankireview.assistant://oauth/callback`；确认 `offline_access`、`profile` 和三个 `study:*` scope 存在并正确分配。导入模板不存在的标准 scope 需在 Keycloak 中补齐。
7. 确保带 `study:read` 的访问令牌包含 `anki-review` audience；授权端 `/realms/anki/.well-known/openid-configuration` 能通过公网 HTTPS 正确发现。
8. 手机上填写服务地址、issuer `https://授权域名/realms/anki`、客户端 ID `anki-android`，浏览器登录后主动选择牌组、开启上传。

示例 Keycloak 配置是部署起点；本次没有在真实域名上完成 TLS、OIDC 和账户管理的端到端验收。首次上线必须完成下列检查，不能仅凭容器启动宣称连接成功。

## ChatGPT MCP

MCP 地址为 `https://学习域名/mcp`，OAuth 资源元数据位于 `/.well-known/oauth-protected-resource/mcp`。为 ChatGPT 单独注册 OAuth 客户端，精确使用当前 ChatGPT 设置页面给出的重定向地址，只允许 `study:read`。不要给此客户端上传或删除权限，不开放任意回调地址或匿名动态注册。

账号和工作区需要支持自定义远程 MCP；客户端可能要求预注册客户端凭据或管理员批准。若当前界面无法接入自己的授权服务器，保留服务并用 JSON 导出，不退化成无认证公网接口。

官方当前支持条件应以 [OpenAI 文档](https://help.openai.com/en/articles/12584461) 为准，不能承诺安卓 ChatGPT App 可以直接配置该连接。协议与传输以 [MCP 官方规范](https://modelcontextprotocol.io/specification/latest/basic/transports) 和锁定 SDK 的实际互操作测试为准。

## 上线验收与维护

- HTTPS 有效，HTTP 不接受学习数据；未授权访问和缺少 scope 均失败。
- 两个独立用户互不可见；撤销用户会话／离线授权后，introspection 拒绝旧凭据。
- 同步重试不重复；断网后恢复；远端删除后旧队列不能恢复数据；重新启用必须由用户主动操作。
- 模拟 PostgreSQL 重启、磁盘不足、版本冲突、授权服务故障；数据不出现部分提交。
- 单用户高负载先限制反向代理请求速率和连接数；本版不提供分布式配额或大规模多租户运行保证。
- 做加密备份和恢复演练。删除请求覆盖在线数据，备份按明确保留期限过期；只监控服务可用性、错误计数和存储容量，不采集学习正文或令牌。

正式 APK 通过手动 Signed release 工作流生成草稿 Release。先设置 GitHub `release` environment 和四个 `ANDROID_KEYSTORE_*`／`ANDROID_KEY_*` Secrets，并保留私钥的离线安全备份。本项目不创建公开生产签名密钥。
