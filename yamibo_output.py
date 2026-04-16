import json
import re
import time
from pathlib import Path

from ebooklib import epub

from yamibo_core import YamiboScraper

_FILENAME_SANITIZE_RE = re.compile(r'[<>:"/\\|?*]+')
_THREAD_AUTHOR_TAG_RE = re.compile(r"[\[【](.*?)[\]】]")
_THREAD_TITLE_PREFIX_RE = re.compile(r"^(?:[\[【].*?[\]】])+")
_THREAD_TITLE_UPDATE_YEAR_RE = re.compile(r"[（(]\d{4}.*?更新.*?[)）]\s*$")
_THREAD_TITLE_UPDATE_RE = re.compile(r"[（(].*?更新.*?[)）]\s*$")
_TXT_CHAPTER_RE = re.compile(r"==== (.*?) ====\n\n(.*?)(?=\n\n\n==== |\Z)", re.S)
_MULTISPACE_RE = re.compile(r"\s{2,}")

_AUTHOR_ROLE_WORDS = {
    "个人翻译",
    "长篇",
    "短篇",
    "自翻",
    "自购",
    "授权转载",
    "转载",
    "生肉",
    "小说",
    "漫画",
    "番外",
    "更新",
    "译文",
    "原创",
    "个人",
}


def _sanitize_filename(name: str) -> str:
    sanitized = _FILENAME_SANITIZE_RE.sub("_", (name or "").strip())
    sanitized = _MULTISPACE_RE.sub(" ", sanitized).strip(" .")
    return sanitized or "TITLE"


def _extract_suggested_meta_from_thread_title(raw_title: str) -> tuple[str, str]:
    title = (raw_title or "").strip()
    if not title:
        return "TITLE", "UNKNOWN"

    author = "UNKNOWN"
    for match in _THREAD_AUTHOR_TAG_RE.findall(title):
        tag = match.strip()
        if not tag or any(word in tag for word in _AUTHOR_ROLE_WORDS):
            continue
        if re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", tag):
            author = tag
            break

    cleaned = _THREAD_TITLE_PREFIX_RE.sub("", title).strip()
    cleaned = _THREAD_TITLE_UPDATE_YEAR_RE.sub("", cleaned).strip()
    cleaned = _THREAD_TITLE_UPDATE_RE.sub("", cleaned).strip()
    return cleaned or title, author


def _format_seconds(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours > 0 else f"{minutes:02d}:{secs:02d}"


def save_to_txt(chapters: list[dict], filename: Path) -> None:
    with open(filename, "w", encoding="utf-8") as handle:
        for chapter in chapters:
            handle.write(f"==== {chapter['title']} ====\n\n{chapter['content']}\n\n\n")
    print(f"📄 TXT 文件已保存至: {filename}")


def save_to_epub(chapters: list[dict], filename: Path, title: str, author: str) -> None:
    book = epub.EpubBook()
    book.set_title(title)
    book.add_author(author)

    epub_chapters = []
    for idx, chapter_data in enumerate(chapters):
        chapter = epub.EpubHtml(title=chapter_data["title"], file_name=f"chap_{idx}.xhtml")
        html = f"<h1>{chapter_data['title']}</h1>"
        for line in chapter_data["content"].split("\n"):
            if line.strip():
                html += f"<p>{line}</p>"
        chapter.content = html
        book.add_item(chapter)
        epub_chapters.append(chapter)

    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + epub_chapters
    epub.write_epub(filename, book, {})
    print(f"📚 EPUB 文件已保存至: {filename}")


def parse_chapters_from_txt(filename: Path) -> list[dict]:
    if not filename.exists():
        return []
    content = filename.read_text(encoding="utf-8")
    return [
        {"title": title.strip(), "url": "", "content": body.strip()}
        for title, body in _TXT_CHAPTER_RE.findall(content)
    ]


def dump_failed_chapters(failed_records: list[dict], output_file: Path) -> None:
    output_file.write_text(
        json.dumps(failed_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"🗂️ 失败章节记录已保存：{output_file}")


def retry_failed_chapters(scraper: YamiboScraper, failed_file: Path, txt_file: Path) -> list[dict]:
    if not failed_file.exists():
        print("未找到失败章节记录文件，跳过重试。")
        return []
    if not txt_file.exists():
        print("未找到 TXT 文件，无法执行回填。")
        return []

    records = json.loads(failed_file.read_text(encoding="utf-8"))
    txt_content = txt_file.read_text(encoding="utf-8")
    still_failed: list[dict] = []

    print("\n开始重试失败章节并回填 TXT ...")
    for item in records:
        print(f"🔁 重试：{item['title']}")
        refreshed = scraper.fetch_chapter_content(item["url"])
        if refreshed.startswith("【最终失败"):
            still_failed.append(item)
            print("   ❌ 仍失败，保留标记。")
            continue
        txt_content = txt_content.replace(item["marker"], refreshed, 1)
        print("   ✅ 回填成功。")
        time.sleep(1)

    txt_file.write_text(txt_content, encoding="utf-8")
    if still_failed:
        dump_failed_chapters(still_failed, failed_file)
    else:
        failed_file.unlink(missing_ok=True)
        print("🎉 失败章节全部回填成功，失败记录文件已移除。")
    return still_failed
