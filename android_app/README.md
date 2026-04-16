# Yamibo Scraper Mobile (Android)

这是 `yamibo_scraper` 的手机端适配子项目，目标是让你在手机上完成核心流程：

1. 账号密码或 Cookie 登录
2. 仅在 49/55 分区搜索帖子
3. 按热度（回复+浏览+排名）排序
4. 提取并手动选择目录候选
5. 先预览再确认抓取
6. 速度档位（极速/快速/平衡/稳妥）+ 预计剩余时间
7. 默认优先保存 TXT 到 Download 目录
8. 一键把回退文件导出到 Download
9. 失败章节单独重试并回填（无需整本重抓）

## 本地打包 APK（Android Studio）

1. 安装 Android Studio（建议最新稳定版）
2. `Open` 本目录 `android_app`
3. 首次同步完成后，点击 `Build > Build APK(s)`
4. 产物位置通常在：
   - `android_app/app/build/outputs/apk/debug/app-debug.apk`
   - `android_app/app/build/outputs/apk/release/*.apk`

## 命令行打包 APK（有 Android SDK 时）

在 `android_app` 目录执行：

```bash
gradle assembleDebug assembleRelease
```

如果你用的是 Gradle Wrapper，也可以改成：

```bash
./gradlew assembleDebug assembleRelease
```

GitHub Actions 会上传两个构建产物：
- `yamibo-mobile-debug-apk`
- `yamibo-mobile-release-apk`

说明：
- `debug`：开发调试包，便于本地快速安装测试，通常体积略大，默认带调试能力。
- `release`：发布配置构建出来的包，更接近最终分发版本。当前项目为了便于测试，`release` 也暂时使用 debug 签名，所以它仍然可以直接安装。
- 如果手机里已经装过旧签名版本，而这次安装提示冲突，请先卸载旧版本再装新的 APK。

## 手机端输出路径

- 默认：`Download/你的文件名.txt`
- 回退：`Android/data/com.yamibo.mobile/files/output/`

说明：
- Android 10 及以上通常可直接写入 Download（走系统 MediaStore）。
- Android 9 及以下如果没给存储权限，会自动回退到应用目录；授权后可直接写入 Download。
- 界面里有“一键导出到 Download”按钮，可把回退文件再导出到 Download。
- App 内打开文件时会优先走系统选择器；如果默认打开失败，建议在选择器里手动选浏览器、文本阅读器或 EPUB 阅读器。

## 注意

- 仍然建议先预览再全量抓取，避免误抓和重复请求。
- 极速/快速模式启用低并发加速；若出现频繁重试，建议切换到平衡模式。
- 仅用于个人阅读整理，请勿用于二次传播或商业用途。
