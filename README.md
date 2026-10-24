# Anki Review Assistant

安卓 AnkiDroid 只读学习分析助手。Kotlin / Compose，本地优先，支持官方 ContentProvider、Anki 历史导入、统计与 JSON 导出。

开发进行中。APK 由 GitHub Actions 的 Android APK 工作流构建，请从成功运行的 Artifacts 下载 debug APK。详细历史来自用户选择的含学习记录导出文件，官方 API 不提供 revlog。默认不上传个人数据。

## Build

JDK 17 + Android SDK 35: `cd android && bash gradlew :core:test :app:lintDebug :app:assembleDebug`

Debug APK 仅用于测试，正式签名尚未配置。许可证：Apache-2.0。
