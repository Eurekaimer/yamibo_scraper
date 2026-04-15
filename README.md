# Yamibo Scraper（百合会小说抓取工具）

抓取百合会连载帖内容，导出 TXT / EPUB。  
支持 GUI 和 CLI 两种使用方式。

> 这个工具的初衷很简单：方便自己看小说，把帖子内容整理成更适合阅读和保存的格式。

## 免责声明
1. 本项目仅用于学习和个人阅读。
2. 抓取内容版权归原作者及百合会论坛所有。
3. 请勿二次传播，不用于商业用途。
4. 使用者自行承担使用风险与责任。

## 使用建议（请降低服务器压力）
1. 默认使用“平衡”或“稳妥”速度。
2. 先预览再全量抓取，避免重复下载错误帖子。
3. 不要短时间频繁重跑同一本内容。
4. 抓取失败优先用“失败回填”，而不是整本重抓。

## 快速开始（先下载，再使用）

### 1) 去哪里下载
- 方式 A（推荐给普通用户）：  
  打开 GitHub 仓库的 **Releases** 页面，下载 `YamiboScraperGUI-win64.zip`（或 `YamiboScraperGUI.exe`）。
- 方式 B（你自己本地开发/改代码）：  
  `git clone` 仓库到本地后运行。

### 2) 如何使用（Windows）

#### 路径 A：使用 Release 包
1. 下载 `YamiboScraperGUI-win64.zip`。
2. 解压到任意目录（例如桌面 `YamiboScraper`）。
3. 双击 `YamiboScraperGUI.exe`。
4. 在 GUI 中填写账号密码（推荐）或 Cookie（兼容）。
5. 搜索帖子 -> 选目录候选 -> 预览章节 -> 开始抓取。

#### 路径 B：使用仓库代码运行
1. `git clone` 后进入项目目录。
2. 安装依赖：
```bash
uv sync
```
3. 启动 GUI：
```bash
uv run python gui_app.py
```
4. 或启动 CLI：
```bash
uv run python yamibo_scraper.py
```

### 3) 文件保存位置
- 配置文件：`yamibo_config.json`（和 exe 同目录）
- 输出目录：`output/`（和 exe 同目录）
- 导出结果：`output/*.txt`、`output/*.epub`

---

## GUI 使用说明

1. 登录方式  
- 默认推荐：账号密码登录  
- 兼容方式：Cookie 登录

2. 抓取来源  
- 搜索：输入关键词，选择分区（译文区/文学区/双区）  
- raw_html：粘贴目录 HTML

3. 预览与抓取  
- 可先预览章节，确认内容正确后再全量抓取  
- 支持速度档位（快速 / 平衡 / 稳妥）  
- 支持 TXT、EPUB、或同时导出

4. 已有 TXT 转 EPUB
- 在 GUI 的 `TXT 转 EPUB` 页签里直接转换 `output` 目录中的 TXT。

---

## CLI 使用说明

如果你更习惯命令行，也可以运行 CLI：
```bash
python yamibo_scraper.py
```

CLI 主菜单支持：
- 开始抓取
- output 目录 TXT 转 EPUB
- 修改配置
- 启动 GUI

---

## 功能清单
- 登录方式：
  - 账号密码登录（优先）
  - Cookie 登录（兼容）
- 抓取来源：
  - 搜索帖子后抓取
  - 粘贴 `raw_html_catalog` 直接抓取
- 搜索能力：
  - 分区筛选（译文区 55 / 文学区 49 / 双区）
  - 搜索结果热度排序（回复+浏览综合）
- 目录提取：
  - 自动提取多个目录候选
  - 候选评分展示
  - 手动选择最准确候选
- 抓取体验：
  - 预览章节后再全量抓取（GUI 可设置预览章数）
  - 速度档位（快速 / 平衡 / 稳妥）
  - 进度与预计剩余时间显示
- 导出与补救：
  - 导出 TXT / EPUB / 同时导出
  - 抓取失败章节记录
  - 失败章节重试回填
  - `output` 目录 TXT 一键转 EPUB
- GUI 体验：
  - 登录方式切换
  - 字体内置加载（`assets/fonts`）
  - 红色系主题界面

---

## 原理与结构
- 网络请求：`curl_cffi`
- 页面解析：`BeautifulSoup`
- 繁简转换：`OpenCC`
- EPUB 生成：`ebooklib`
- GUI：`Tkinter`

主要文件：
- `gui_app.py`：GUI
- `yamibo_scraper.py`：CLI + 抓取主逻辑
- `search.py`：搜索与排序
- `auth.py`：登录
- `config_store.py`：本地配置
