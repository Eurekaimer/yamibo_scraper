# Yamibo Scraper

百合会小说抓取工具，支持导出 `TXT / EPUB`。

当前包含两端：
- 桌面端：Python GUI + CLI
- Android 端：`android_app/`

## 说明
- 仅用于学习和个人阅读
- 请勿二次传播或商用
- 建议先预览再全量抓取，默认使用“平衡”或“稳妥”速度

## 桌面端

普通用户可以直接下载 Release 包运行；开发使用建议直接跑源码。

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

Android 子项目位于 `android_app/`。

- 可直接安装 CI / Release 提供的 APK
- 也可以用 Android Studio 打开 `android_app` 自行构建
- `debug` 适合本地测试，`release` 更接近发布包
- 如果安装提示签名冲突，请先卸载旧版本

Android 端输出：
- 默认优先保存到 `Download/`
- 如果系统限制，会回退到 `Android/data/com.yamibo.mobile/files/output/`
- App 内支持一键导出到 `Download`
- 打开文件时会调用系统选择器；如果默认打开不稳定，建议手动选浏览器、文本阅读器或 EPUB 阅读器

## 主要功能

- 账号密码登录 / Cookie 登录
- 搜索帖子并按热度排序
- 自动提取多个目录候选
- 先预览再抓取
- 导出 TXT / EPUB
- 失败章节单独回填

## 项目结构

- `gui_app.py`：桌面 GUI
- `yamibo_scraper.py`：CLI 和主抓取逻辑
- `search.py`：搜索与排序
- `auth.py`：登录
- `config_store.py`：本地配置
- `android_app/`：Android 子项目
