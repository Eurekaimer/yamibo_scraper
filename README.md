# Yamibo Scraper

用于整理百合会帖子内容的个人阅读工具，支持导出 `TXT / EPUB`。

当前包含两端：
- 桌面端：Python GUI + CLI
- Android 端：`android_app/`

## 版权与使用说明

- 本项目仅供学习研究与个人阅读整理使用。
- 抓取内容的版权归原作者及百合会论坛所有。
- 请勿将抓取结果用于二次传播、公开分发或任何商业用途。
- 使用者应自行判断并承担相应使用风险。

## 使用建议

- 建议在网络稳定、权限正常的前提下使用。
- 如访问速度较慢或请求不稳定，建议先配置可用代理再进行抓取，通常能明显提升成功率与速度。
- 建议先预览章节，再执行完整抓取。
- 为降低论坛压力，建议优先使用“平衡”或“稳妥”速度。

## 桌面端

普通用户建议直接使用 Windows `exe` 版本。

- 打开 Releases，下载 `YamiboScraperGUI-win64.zip` 或 `YamiboScraperGUI.exe`
- 如果是压缩包，解压后直接双击 `YamiboScraperGUI.exe`
- 填写账号密码或 Cookie，然后依次执行搜索、选择目录、预览与抓取

开发使用建议直接跑源码：

```bash
uv sync
uv run python gui_app.py
```

如果想用命令行：

```bash
uv run python yamibo_scraper.py
```

桌面端输出：
- 配置文件：`yamibo_config.json`
- 输出目录：`output/`

## Android 端

Android 子项目位于 `android_app/`，整体流程尽量与桌面端保持一致：登录、搜索、提取目录、预览、抓取、导出、失败回填。

- 可直接安装 CI / Release 提供的 APK
- 也可以用 Android Studio 打开 `android_app` 自行构建
- `debug` 适合本地测试，`release` 更接近发布包
- 如果安装提示签名冲突，请先卸载旧版本

Android 端输出：
- 默认优先保存到 `Download/`
- 如果系统限制，会回退到 `Android/data/com.yamibo.mobile/files/output/`
- App 内支持一键导出到 `Download`
- 打开文件时会调用系统选择器；如果默认打开不稳定，建议手动选浏览器、文本阅读器或 EPUB 阅读器
- Android 端支持已抓取 TXT 转 EPUB，并会在抓取与转换时自动执行繁体转简体

界面预览：

![20260416151939](https://cdn.jsdelivr.net/gh/Eurekaimer/MyIMGs@main/img/20260416151939.png)

## 项目结构

- `gui_app.py`：桌面 GUI
- `yamibo_scraper.py`：CLI 和主抓取逻辑
- `search.py`：搜索与排序
- `auth.py`：登录
- `config_store.py`：本地配置
- `android_app/`：Android 子项目

## 已完成功能

- [x] 账号密码登录
- [x] Cookie 登录
- [x] Windows `exe` 直接运行支持
- [x] 按关键词搜索帖子
- [x] 分区筛选（49 / 55 / 双区）
- [x] 搜索结果热度排序
- [x] 自动提取多个目录候选
- [x] 手动选择目录候选
- [x] 章节预览后再抓取
- [x] 抓取结果导出为 TXT
- [x] 桌面端 TXT 转 EPUB
- [x] Android 端 TXT 转 EPUB
- [x] 自动繁体转简体
- [x] 失败章节记录与重试回填
- [x] 标题与作者自动推荐
- [x] Android 端支持按当前帖子重新推荐标题与作者
- [x] Android 端抓取开始时的前台服务闪退修复
- [x] Android 端文件打开改为系统选择器优先，降低默认打开失败概率
- [x] Android 端抓取流程顺序优化，与桌面端心智模型尽量保持一致
- [x] Android 端页面分区与文案顺序优化
- [x] Android 端后台通知与悬浮进度兼容降级处理
- [x] Android 端输出失败时自动回退应用目录
- [x] Android 端支持一键导出到 Download
- [x] Android 端历史文件列表与文件直接打开
- [x] 桌面端 GUI
- [x] 桌面端 CLI
- [x] Android 端基础抓取流程
- [x] 顶层 README 与 Android 端说明整理完成
