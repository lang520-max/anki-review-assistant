# 一体化 AnkiDroid 手机端

本目录维护基于官方 AnkiDroid v2.22.3 的定制差异，与本仓库统计/个人服务一起评审。routing7 起用户日常使用的是包含背词、5 Again 分流、连续 5 Easy 修复、学习分析和私人上传的同一个 App。旧版 0–9 次主组计数继续可读；已有 5–9 次计数不会在启动时批量搬移，下次按 Again 时分流。

- 上游基线：`4f2ec681da36b8307a865f05192498b8425adf0f`
- 包名：`com.ichi2.anki.diversion`，沿用已有应用签名，不替换词库。
- `integrated.patch` 包含基线以来完整定制源代码差异，包括原分流和更新功能。源码许可按对应文件及上游 GPL-3.0 系列执行；本仓库其他 Apache-2.0 文件的许可不因此改变。
- `android/` 为原先独立分析 App，保留兼容用途。它不包含定制调度器，不能代替本目录一体化 App。

复现源代码：

```sh
git clone https://github.com/ankidroid/Anki-Android.git
cd Anki-Android
git checkout 4f2ec681da36b8307a865f05192498b8425adf0f
git apply --check /path/to/anki-review-assistant/ankidroid-integration/integrated.patch
git apply /path/to/anki-review-assistant/ankidroid-integration/integrated.patch
```

JDK 17、Android SDK 35，构建时设置原签名环境变量 `ANKI_UPDATE_KEYSTORE`。私钥不包含在仓库或源码下载中，维护者必须使用已保存的原文件；不能重新生成密钥替代。

```text
gradlew :libanki:testDebugUnitTest --tests com.ichi2.anki.libanki.sched.StudyDiversionTest --tests com.ichi2.anki.libanki.sched.StudyAnalysisTest :AnkiDroid:assembleFullDebug -PdiversionBuild=7 --max-workers=1
```

私人上传和查询的运行边界、部署与备份说明见 [手动询问路线](../docs/personal-route.md)。安装包与完整对应源码使用既有 HTTPS 更新渠道发布；GitHub 保存可复现差异。模拟器成功不代表用户真机已验收。
