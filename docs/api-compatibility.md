# AnkiDroid 官方 API 核查

核查日期：2026-10-24；官方 `FlashCardsContract.kt` 当时 main 分支 blob：`287f3218284182ff932385db9b28c0243d5d1038`。main 上存在不表示所有发布版本均支持；本应用以实际查询能力为准。

来源：[官方契约](https://github.com/ankidroid/Anki-Android/blob/main/api/src/main/java/com/ichi2/anki/FlashCardsContract.kt)、[Provider URI 实现](https://github.com/ankidroid/Anki-Android/blob/main/AnkiDroid/src/main/java/com/ichi2/anki/provider/CardContentProvider.kt)。

| 数据 | 官方 API | 本应用处理 |
|---|---|---|
| 牌组 ID／名称 | `/decks` 的 `deck_id`、`deck_name` | 查询 |
| 笔记 ID／字段 | `/notes` 的 `_id`、`flds` | 查询，字段用 U+001F 分隔 |
| 卡片 ID／笔记／牌组 | `/cards` | 查询，不支持时保留牌组与笔记并提示 |
| 队列、类型、due、间隔 | `/cards` 的可选投影 | 逐列探测，缺失值为 null |
| reps、lapses、SM-2 factor | 同上 | 原始计数，不当作逐次历史 |
| FSRS difficulty／stability | 最新契约的可选投影 | 有则读取，无则 null；导入适配器暂不解码 protobuf 内存状态 |
| 逐次 revlog／回答按钮／耗时 | **没有公开查询端点** | 用户导出文件只读导入 |
| 集合创建与学习日参数 | 当前 API 不完整 | Provider 来源不伪造精确到期时间；文件来源结合所选时区／日界线估算 |
| 新卡／学习中／复习队列 | 支持队列字段时可分类 | 是当前状态计数，不等于当天实际学习次数 |
| 历史学习时间 | 无 revlog 查询 | 依赖导入的 `revlog.time` |

`/schedule` 的 `ease`、`time_taken` 是提交回答使用的写入参数，不能用它们查询过去回答；本项目不调用该端点。卡片“最后复习时间”是单值元信息，也不能补齐完整 revlog。

官方权限是 `com.ichi2.anki.permission.READ_WRITE_DATABASE`；本应用无法自行制造底层只读权限，只能严格限制自己的调用边界。未授权、授权撤销、Provider 初始化失败等情况会停止读取并保留旧快照。

备用文件格式独立于 Provider，未知数据库版本或结构错误会拒绝。不是直接读取 Anki 私有目录，也不绕过 Android 权限。真正的 API 支持矩阵需要逐个发布版和手机实测；文档不会把源码核查或模拟测试当成所有版本兼容证明。
