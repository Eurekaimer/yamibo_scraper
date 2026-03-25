# ================= 0. 环境配置区 =================

import time
import re
import random
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from ebooklib import epub
from opencc import OpenCC

from auth import create_session, prompt_account_credentials, prompt_cookie, login_with_password
from search import search_threads_by_keyword
from config_store import load_config, save_config
from cli import (
    get_main_action,
    get_save_choice,
    get_catalog_mode,
    get_search_keyword,
    choose_thread,
    get_auth_mode,
    print_terminal_encoding_hint,
    edit_config_interactive,
    ask_use_existing_txt_for_epub,
    ask_retry_failed_chapters,
)

# ================= 1. 全局配置区 =================

OUTPUT_DIR = Path("./output")

CRAWL_DELAY = 3
MAX_RETRIES = 5
ENABLE_SIMPLIFIED = True
FAILED_MARKER_PREFIX = "#FAILED_CHAPTER_"

cc = OpenCC('t2s')  # 繁体转简体

# ================= 3. 核心类 =================


class YamiboScraper:
    def __init__(self, session):
        self.session = session
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def parse_catalog(self, html_text: str) -> list:
        chapters = []
        pattern = re.compile(r'<a href="(https://bbs\.yamibo\.com/[^"]+)"[^>]*>(.*?)</a>')

        for url, title in pattern.findall(html_text):
            title = re.sub('<.*?>', '', title).strip()  # 去掉 <strong>
            chapters.append({
                "title": title,
                "url": url.replace('&amp;', '&'),
                "content": ""
            })
        return chapters

    def fetch_chapter_content(self, url: str) -> str:
        pid = parse_qs(urlparse(url).query).get('pid', [None])[0]

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'html.parser')
                if pid:
                    target_id = f"postmessage_{pid}"
                    content_td = soup.find('td', id=target_id)
                else:
                    content_td = soup.find('td', id=re.compile(r"^postmessage_\d+$"))

                if not content_td:
                    raise ValueError("正文未找到")

                for pstatus in content_td.find_all('i', class_='pstatus'):
                    pstatus.decompose()

                text = content_td.get_text(separator='\n', strip=True)

                if ENABLE_SIMPLIFIED:
                    text = cc.convert(text)

                text = re.sub(r'\n{3,}', '\n\n', text)

                return text

            except Exception as e:
                print(f"    ⚠️ 第{attempt + 1}次失败: {e}")

                if attempt == MAX_RETRIES - 1:
                    return f"【最终失败：{e}】"

                sleep_time = 2 ** attempt
                time.sleep(sleep_time)


# ================= 4. 文件输出 =================

def save_to_txt(chapters, filename):
    with open(filename, "w", encoding="utf-8") as f:
        for c in chapters:
            f.write(f"==== {c['title']} ====\n\n{c['content']}\n\n\n")
    print(f"📄 TXT 文件已保存至: {filename}")


def save_to_epub(chapters, filename, title, author):
    book = epub.EpubBook()
    book.set_title(title)
    book.add_author(author)

    epub_chapters = []

    for i, c in enumerate(chapters):
        chapter = epub.EpubHtml(title=c['title'], file_name=f'chap_{i}.xhtml')

        html = f"<h1>{c['title']}</h1>"
        for line in c['content'].split('\n'):
            if line.strip():
                html += f"<p>{line}</p>"

        chapter.content = html
        book.add_item(chapter)
        epub_chapters.append(chapter)

    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + epub_chapters

    epub.write_epub(filename, book, {})
    print(f"📚 EPUB 文件已保存至: {filename}")


def parse_chapters_from_txt(filename: Path) -> list[dict]:
    if not filename.exists():
        return []

    content = filename.read_text(encoding="utf-8")
    pattern = re.compile(r"==== (.*?) ====\n\n(.*?)(?=\n\n\n==== |\Z)", re.S)
    chapters = []
    for title, body in pattern.findall(content):
        chapters.append({
            "title": title.strip(),
            "url": "",
            "content": body.strip(),
        })
    return chapters


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
    still_failed = []

    print("\n开始重试失败章节并回填 TXT ...")
    for item in records:
        marker = item["marker"]
        print(f"🔁 重试：{item['title']}")
        new_content = scraper.fetch_chapter_content(item["url"])
        if new_content.startswith("【最终失败"):
            still_failed.append(item)
            print("   ❌ 仍失败，保留标记。")
            continue

        txt_content = txt_content.replace(marker, new_content, 1)
        print("   ✅ 回填成功。")
        time.sleep(1)

    txt_file.write_text(txt_content, encoding="utf-8")
    if still_failed:
        dump_failed_chapters(still_failed, failed_file)
    else:
        failed_file.unlink(missing_ok=True)
        print("🎉 失败章节全部回填成功，失败记录文件已移除。")

    return still_failed


# ================= 5. 主程序 =================

def build_authenticated_session(config):
    auth_mode = get_auth_mode()

    if auth_mode == "1":
        if not config.username:
            config.username, config.password = prompt_account_credentials()
            save_config(config)

        session = create_session(user_agent=config.user_agent)
        try:
            ok = login_with_password(session, config.username, config.password)
        except Exception as exc:
            print(f"❌ 登录流程异常：{exc}")
            print("请尝试：1) 使用 Cookie 模式；2) 在“修改配置”里更新账号密码后重试。")
            return None

        if not ok:
            print("❌ 账号密码登录失败，请先在“修改配置”里更新账号信息，或改用 Cookie 模式。")
            return None

        print("✅ 登录成功，继续后续流程。")
        return session

    if not config.cookie:
        config.cookie = prompt_cookie()
        save_config(config)

    if not config.cookie:
        print("❌ Cookie 不能为空。")
        return None

    session = create_session(user_agent=config.user_agent, cookie=config.cookie)
    print("✅ 已加载 Cookie，继续后续流程。")
    return session


def resolve_chapters(scraper: YamiboScraper, config) -> list:
    mode = get_catalog_mode()

    if mode == "1":
        return scraper.parse_catalog(config.raw_html_catalog)

    keyword = get_search_keyword()
    results = search_threads_by_keyword(scraper.session, keyword)
    selected = choose_thread(results)

    if not selected:
        return []

    return [
        {
            "title": selected["title"],
            "url": selected["url"],
            "content": "",
        }
    ]


def run_scraper(config):
    save_choice = get_save_choice()
    txt_path = OUTPUT_DIR / f"{config.book_title}.txt"
    epub_path = OUTPUT_DIR / f"{config.book_title}.epub"

    if save_choice == "2" and txt_path.exists() and ask_use_existing_txt_for_epub(txt_path):
        chapters = parse_chapters_from_txt(txt_path)
        if not chapters:
            print("❌ TXT 解析失败，无法直接转换 EPUB，请改为重新抓取。")
            return
        save_to_epub(chapters, epub_path, config.book_title, config.book_author)
        return

    session = build_authenticated_session(config)
    if not session:
        return

    print("\n配置完成，开始抓取目录...")

    scraper = YamiboScraper(session)
    chapters = resolve_chapters(scraper, config)

    if not chapters:
        print("未解析到任何章节，请检查 raw_html_catalog 内容，或检查搜索结果。")
        return

    failed_records = []

    for i, ch in enumerate(chapters):
        content = scraper.fetch_chapter_content(ch['url'])

        if content.startswith("【最终失败"):
            marker = f"{FAILED_MARKER_PREFIX}{i + 1}#"
            failed_records.append({
                "index": i,
                "title": ch["title"],
                "url": ch["url"],
                "marker": marker,
            })
            content = marker

        ch['content'] = content

        clean_text = re.sub(r'\s+', '', content)
        preview = clean_text[:20] + "..." if len(clean_text) > 20 else clean_text

        print(f"[{i + 1}/{len(chapters)}] {ch['title']} | 预览: {preview}")

        time.sleep(CRAWL_DELAY + random.uniform(0, 2))

    print("\n抓取结束，开始生成文件...")

    if save_choice in ['1', '3']:
        save_to_txt(chapters, txt_path)

    if save_choice in ['2', '3']:
        save_to_epub(chapters, epub_path, config.book_title, config.book_author)

    if failed_records:
        failed_file = OUTPUT_DIR / f"{config.book_title}.failed_chapters.json"
        dump_failed_chapters(failed_records, failed_file)

        print(f"\n⚠️ 有 {len(failed_records)} 个章节抓取失败:")
        for item in failed_records:
            print(f" - {item['title']}")

        if save_choice in ["1", "3"] and ask_retry_failed_chapters():
            still_failed = retry_failed_chapters(scraper, failed_file, txt_path)
            if save_choice == "3":
                updated_chapters = parse_chapters_from_txt(txt_path)
                if updated_chapters:
                    save_to_epub(updated_chapters, epub_path, config.book_title, config.book_author)
                else:
                    print("⚠️ TXT 回填后解析失败，EPUB 未重新生成。")
            if still_failed:
                print(f"⚠️ 仍有 {len(still_failed)} 章失败，已保留失败记录文件便于后续继续执行。")
    else:
        print("\n🎉 全部操作完美完成！")


def main():
    print_terminal_encoding_hint()
    config = load_config()

    while True:
        action = get_main_action()

        if action == "1":
            run_scraper(config)
        elif action == "2":
            config = edit_config_interactive(config)
            save_config(config)
            print("✅ 配置已保存到 yamibo_config.json")
        else:
            print("已退出。")
            return


if __name__ == "__main__":
    main()
