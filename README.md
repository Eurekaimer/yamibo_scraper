# Yamibo Scraper

Personal reading/export tool for Yamibo threads. It logs in, searches threads, extracts catalog links or substantial posts by author, cleans forum noise, converts Traditional Chinese text to Simplified Chinese, and exports TXT/EPUB.

## What is new

- Search now tries query variants: original keyword, simplified keyword, punctuation split terms, and compact terms. This fixes long-title searches such as `full or partial novel title`.
- New author-post fallback for threads without a catalog/elevator. Leave author blank to infer the first substantial post author, or pass a forum author ID explicitly.
- Author-post scans cache extracted post text, so preview/crawl does not re-fetch the same pid.
- Content cleanup removes edit notices, quote blocks, attachments/no-permission blocks, scripts/styles, and common forum UI noise.
- New non-interactive CLI: `yamibo_cmd.py`, suitable for Windows exe and Linux/NixOS shell usage.

## Install

```bash
uv sync
```

Config is stored in `yamibo_config.json`. It can contain plaintext username/password or Cookie. Do not commit or share this file.

## GUI

```bash
uv run python gui_app.py
```

Recommended flow:

1. Login with account/password or Cookie.
2. Search by keyword.
3. If the thread has a catalog, use `Extract catalog candidates`.
4. If there is no catalog, use author filtering: leave author blank to infer the first content author, set a page budget, then load author posts.
5. Preview before crawling.

Start with 3-5 pages for author-post scanning. Increase the page budget only after preview looks correct.

## Command line

Search:

```bash
uv run python yamibo_cmd.py search --keyword "novel title" --limit 5
```

Crawl author posts by keyword:

```bash
uv run python yamibo_cmd.py author-crawl --keyword "novel title" --pages 5 --save both
```

Crawl author posts by URL:

```bash
uv run python yamibo_cmd.py author-crawl --url "https://bbs.yamibo.com/forum.php?mod=viewthread&tid=503382" --author "author-id" --pages 5 --save txt
```

Output goes to `output/`.

## Windows exe

Build manually if needed:

```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --windowed --name YamiboScraperGUI --add-data "assets;assets" gui_app.py
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --console --name YamiboScraperCLI yamibo_cmd.py
```

CLI exe smoke test:

```powershell
.\dist\YamiboScraperCLI.exe search --keyword "novel title" --limit 1
```

## Linux / NixOS

Use source mode:

```bash
uv sync
uv run python yamibo_cmd.py search --keyword "keyword"
uv run python yamibo_cmd.py author-crawl --url "thread-url" --pages 5
```

Build native binaries on the target OS if required. Do not reuse Windows exe on Linux/NixOS.

## Security and robustness notes

- No DeepSeek or other external LLM/API is used by default. Thread content stays local except for requests to Yamibo.
- `yamibo_config.json` is sensitive. A leaked Cookie may be enough to reuse your session.
- Output filenames are sanitized and written under the project output directory.
- Page budgets and speed profiles exist to reduce server pressure and lower the chance of rate limiting.
- This project is for personal learning/reading organization. Do not redistribute scraped content.

## Android

Android is not the verified target for this PC-focused pass. Build and verify it separately in Android Studio or with a Gradle wrapper before publishing an APK.
