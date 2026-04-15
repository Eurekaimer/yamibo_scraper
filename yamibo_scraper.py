# ================= 0. 环境配置区 =================

import time
import re
import random
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urljoin
from bs4 import BeautifulSoup
from ebooklib import epub
from opencc import OpenCC

from auth import create_session, prompt_cookie, login_with_password
from search import search_threads_by_keyword
from config_store import load_config, save_config
from cli import (
    get_main_action,
    get_save_choice,
    get_crawl_speed_mode,
    get_catalog_mode,
    get_search_keyword,
    get_search_forum_scope,
    choose_thread,
    get_auth_mode,
    print_terminal_encoding_hint,
    edit_config_interactive,
    ask_use_existing_txt_for_epub,
    ask_retry_failed_chapters,
    ask_yes_no,
    ask_preview_confirm,
    ask_retry_search,
    choose_catalog_candidate,
    choose_book_metadata,
)

# ================= 1. 全局配置区 =================

OUTPUT_DIR = Path("./output")

BASE_URL = "https://bbs.yamibo.com/"

RETRY_JITTER_MAX = 0.8
MIN_CATALOG_CHAPTERS = 3
MAX_SEARCH_CANDIDATE_TRIES = 10
MAX_RETRIES = 5
ENABLE_SIMPLIFIED = True
FAILED_MARKER_PREFIX = "#FAILED_CHAPTER_"
SPEED_PROFILES = {
    "fast": {
        "label": "快速",
        "delay_min": 0.85,
        "delay_max": 1.25,
        "burst_every_min": 0,
        "burst_every_max": 0,
        "burst_pause_min": 0.0,
        "burst_pause_max": 0.0,
    },
    "balanced": {
        "label": "平衡",
        "delay_min": 1.6,
        "delay_max": 2.4,
        "burst_every_min": 16,
        "burst_every_max": 24,
        "burst_pause_min": 3.0,
        "burst_pause_max": 6.0,
    },
    "gentle": {
        "label": "稳妥",
        "delay_min": 2.8,
        "delay_max": 4.6,
        "burst_every_min": 8,
        "burst_every_max": 12,
        "burst_pause_min": 6.0,
        "burst_pause_max": 12.0,
    },
}

cc = OpenCC('t2s')  # 繁体转简体

# ================= 3. 核心类 =================


class YamiboScraper:
    def __init__(self, session):
        self.session = session
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _extract_pid(url: str) -> str:
        return parse_qs(urlparse(url).query).get("pid", [""])[0]

    @staticmethod
    def _is_probable_chapter_title(title: str) -> bool:
        t = (title or "").strip().lower()
        if not t:
            return False

        if re.search(r"(episode|ep\.?\s*\d+|chapter|ch\.?\s*\d+)", t):
            return True
        if re.search(r"(第\s*\d+\s*[话章节卷]|序章|终章|后记|番外|目录)", title):
            return True
        if re.fullmatch(r"\d{1,4}([#.]|\s*话)?", t):
            return True
        return False

    @staticmethod
    def _is_noise_title(title: str) -> bool:
        t = (title or "").strip()
        if not t:
            return True
        noise_keywords = [
            "只看该作者",
            "只看大图",
            "评分",
            "收藏",
            "回复",
            "举报",
            "电梯直达",
            "使用道具",
            "道具",
            "发消息",
            "楼主",
            "沙发",
            "板凳",
            "复制链接",
            "复制代码",
            "查看原图",
            "倒序浏览",
        ]
        return any(word in t for word in noise_keywords)

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = (url or "").strip().replace("&amp;", "&")
        if not url:
            return ""
        if url.startswith("javascript:"):
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("forum.php"):
            return urljoin(BASE_URL, url)
        if url.startswith("./"):
            return urljoin(BASE_URL, url[2:])
        if url.startswith("/"):
            return f"https://bbs.yamibo.com{url}"
        return urljoin(BASE_URL, url)

    def _extract_chapters_from_soup(self, scope) -> list[dict]:
        chapters = []
        seen = set()

        anchors = scope.select(
            "a[href*='viewthread'], "
            "a[href*='mod=viewthread'], "
            "a[href*='goto=findpost'], "
            "a[href*='findpost'], "
            "a[href*='pid=']"
        )
        for idx, anchor in enumerate(anchors, start=1):
            raw_href = anchor.get("href", "")
            url = self._normalize_url(raw_href)
            if not url:
                continue
            if not any(k in url for k in ("viewthread", "findpost", "pid=")):
                continue

            pid = self._extract_pid(url)
            unique_key = f"pid:{pid}" if pid else f"url:{url}"
            if unique_key in seen:
                continue

            title = anchor.get_text(strip=True)
            if self._is_noise_title(title):
                continue
            if not title:
                title = f"章节{idx}"

            seen.add(unique_key)
            chapters.append({
                "title": title,
                "url": url,
                "pid": pid,
                "order_hint": len(chapters),
                "content": "",
            })

        return chapters

    def _score_catalog_detail(self, chapters: list[dict], selector: str) -> dict:
        if not chapters:
            return {
                "score": -1.0,
                "base": 0.0,
                "pid_bonus": 0.0,
                "title_bonus": 0.0,
                "structure_bonus": 0.0,
                "size_bonus": 0.0,
                "quality_penalty": 0.0,
                "pid_count": 0,
                "probable_title_count": 0,
                "suspicious_title_count": 0,
            }

        base = float(len(chapters))
        pid_count = sum(1 for c in chapters if c.get("pid"))
        probable_title_count = sum(1 for c in chapters if self._is_probable_chapter_title(c.get("title", "")))
        suspicious_title_count = sum(
            1
            for c in chapters
            if (not self._is_probable_chapter_title(c.get("title", "")))
            and re.search(r"[#\[\]【】复制链接只看举报楼主沙发板凳]", c.get("title", ""))
        )

        pid_bonus = pid_count * 1.4
        title_bonus = probable_title_count * 1.8

        structure_bonus = 0.0
        if selector == "showcollapse":
            structure_bonus += 26.0
        elif selector == "fallback-page":
            structure_bonus -= 24.0

        size_bonus = 0.0
        if len(chapters) >= MIN_CATALOG_CHAPTERS:
            size_bonus += 3.0

        quality_penalty = suspicious_title_count * 4.0

        score = base + pid_bonus + title_bonus + structure_bonus + size_bonus - quality_penalty
        return {
            "score": score,
            "base": base,
            "pid_bonus": pid_bonus,
            "title_bonus": title_bonus,
            "structure_bonus": structure_bonus,
            "size_bonus": size_bonus,
            "quality_penalty": quality_penalty,
            "pid_count": pid_count,
            "probable_title_count": probable_title_count,
            "suspicious_title_count": suspicious_title_count,
        }

    def parse_catalog(self, html_text: str) -> list[dict]:
        soup = BeautifulSoup(html_text, "html.parser")
        chapters = self._extract_chapters_from_soup(soup)
        if chapters:
            return chapters

        # 兼容旧输入：纯文本中包含绝对链接
        chapters = []
        pattern = re.compile(r'https?://bbs\.yamibo\.com/[^\s"<>]+viewthread[^\s"<>]*')
        seen = set()
        for idx, raw_url in enumerate(pattern.findall(html_text), start=1):
            url = self._normalize_url(raw_url)
            if not url or url in seen:
                continue
            seen.add(url)
            chapters.append(
                {
                    "title": f"章节{idx}",
                    "url": url,
                    "pid": self._extract_pid(url),
                    "order_hint": idx - 1,
                    "content": "",
                }
            )
        return chapters

    def extract_catalog_candidates_from_thread(self, thread_url: str) -> list[dict]:
        response = self.session.get(thread_url, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        candidates = []
        # 优先处理论坛折叠目录块（showcollapse）
        for node in soup.select("div.showcollapse_content"):
            if node.select_one("a[href*='findpost'], a[href*='pid='], a[href*='viewthread']"):
                candidates.append(("showcollapse", node))

        # 回退处理其他正文容器
        for selector in [
            "table",
            "tbody",
            "div#postlist",
            "div[id^='postmessage_']",
            "td[id^='postmessage_']",
            "div.pcb",
        ]:
            for node in soup.select(selector):
                if node.select_one("a[href*='viewthread'], a[href*='mod=viewthread']"):
                    candidates.append((selector, node))

        scored_candidates = []
        signature_seen = set()
        for idx, (selector, node) in enumerate(candidates, start=1):
            chapters = self._extract_chapters_from_soup(node)
            if not chapters:
                continue

            detail = self._score_catalog_detail(chapters, selector=selector)
            signature = tuple((c.get("pid") or c.get("url")) for c in chapters[:30])
            if signature in signature_seen:
                continue
            signature_seen.add(signature)

            scored_candidates.append(
                {
                    "selector": f"{selector}#{idx}",
                    "chapters": chapters,
                    "chapter_count": len(chapters),
                    "score": detail["score"],
                    "score_reason": detail,
                    "sample_titles": [c["title"] for c in chapters[:3]],
                }
            )

        fallback = self._extract_chapters_from_soup(soup.select_one("div#postlist") or soup)
        if fallback:
            detail = self._score_catalog_detail(fallback, selector="fallback-page")
            scored_candidates.append(
                {
                    "selector": "fallback-page",
                    "chapters": fallback,
                    "chapter_count": len(fallback),
                    "score": detail["score"],
                    "score_reason": detail,
                    "sample_titles": [c["title"] for c in fallback[:3]],
                }
            )

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        return scored_candidates[:8]

    def extract_catalog_from_thread(self, thread_url: str) -> list[dict]:
        candidates = self.extract_catalog_candidates_from_thread(thread_url)
        if not candidates:
            return []
        best = candidates[0]
        print(
            f"   ✅ 自动选择最佳候选（{best['selector']}），"
            f"章节 {best['chapter_count']}，评分 {best['score']:.1f}。"
        )
        return best["chapters"]

    def fetch_chapter_content(self, url: str) -> str:
        pid = self._extract_pid(url) or None

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'html.parser')
                content_td = None
                if pid:
                    target_id = f"postmessage_{pid}"
                    content_td = soup.find('td', id=target_id) or soup.find('div', id=target_id)
                if not content_td:
                    content_td = soup.find('td', id=re.compile(r"^postmessage_\d+$"))
                if not content_td:
                    content_td = soup.find('div', id=re.compile(r"^postmessage_\d+$"))
                if not content_td:
                    content_td = soup.select_one("div.pcb, td.t_f, div.t_f")

                if not content_td:
                    raise ValueError("正文未找到")

                for pstatus in content_td.find_all('i', class_='pstatus'):
                    pstatus.decompose()
                for noise in content_td.select("script, style"):
                    noise.decompose()

                text = content_td.get_text(separator='\n', strip=True)

                if ENABLE_SIMPLIFIED:
                    text = cc.convert(text)

                text = re.sub(r'\n{3,}', '\n\n', text)
                if len(re.sub(r"\s+", "", text)) < 20:
                    raise ValueError("正文内容过短，疑似未命中正文区域")

                return text

            except Exception as e:
                print(f"    ⚠️ 第{attempt + 1}次失败: {e}")

                if attempt == MAX_RETRIES - 1:
                    return f"【最终失败：{e}】"

                sleep_time = (2 ** attempt) + random.uniform(0, RETRY_JITTER_MAX)
                time.sleep(sleep_time)


# ================= 4. 文件输出 =================

def _sanitize_filename(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]+', "_", (name or "").strip())
    safe = re.sub(r"\s{2,}", " ", safe).strip(" .")
    return safe or "TITLE"


def _extract_suggested_meta_from_thread_title(raw_title: str) -> tuple[str, str]:
    title = (raw_title or "").strip()
    if not title:
        return "TITLE", "UNKNOWN"

    bracket_tags = re.findall(r"[\[【](.*?)[\]】]", title)
    author = "UNKNOWN"
    role_words = {
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
    for tag in bracket_tags:
        tag = tag.strip()
        if not tag:
            continue
        if any(word in tag for word in role_words):
            continue
        if re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", tag):
            author = tag
            break

    cleaned = re.sub(r"^(?:[\[【].*?[\]】])+", "", title).strip()
    cleaned = re.sub(r"[（(]\d{4}.*?更新.*?[)）]\s*$", "", cleaned).strip()
    cleaned = re.sub(r"[（(].*?更新.*?[)）]\s*$", "", cleaned).strip()
    cleaned = cleaned or title
    return cleaned, author


def _format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


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
    while True:
        auth_mode = get_auth_mode()

        if auth_mode == "1":
            if not config.username or not config.password:
                print("⚠️ 检测到账号或密码未配置，先进入配置编辑。")
                config = edit_config_interactive(config)
                save_config(config)
                if not config.username or not config.password:
                    print("❌ 账号或密码仍未配置，无法继续。")
                    if ask_yes_no("是否改用 Cookie 模式重试？", default=True):
                        continue
                    return None

            session = create_session(user_agent=config.user_agent)
            try:
                ok = login_with_password(session, config.username, config.password)
            except Exception as exc:
                print(f"❌ 登录流程异常：{exc}")
                if ask_yes_no("是否进入配置编辑后重试登录？", default=True):
                    config = edit_config_interactive(config)
                    save_config(config)
                    continue
                return None

            if not ok:
                print("❌ 账号密码登录失败。")
                if ask_yes_no("是否进入配置编辑后重试登录？", default=True):
                    config = edit_config_interactive(config)
                    save_config(config)
                    continue
                return None

            print("✅ 登录成功，继续后续流程。")
            return session

        if not config.cookie:
            print("⚠️ 检测到 Cookie 未配置，先进入配置编辑。")
            config = edit_config_interactive(config)
            save_config(config)
            if not config.cookie:
                config.cookie = prompt_cookie()
                save_config(config)

        if not config.cookie:
            print("❌ Cookie 不能为空。")
            if ask_yes_no("是否进入配置编辑后重试？", default=True):
                config = edit_config_interactive(config)
                save_config(config)
                continue
            return None

        session = create_session(user_agent=config.user_agent, cookie=config.cookie)
        print("✅ 已加载 Cookie，继续后续流程。")
        return session


def resolve_chapters_from_search(scraper: YamiboScraper) -> tuple[list[dict], dict | None]:
    keyword = get_search_keyword()
    forum_ids = get_search_forum_scope()
    results = search_threads_by_keyword(scraper.session, keyword, forum_ids=forum_ids, limit=20)
    selected = choose_thread(results)

    if not selected:
        return [], None

    try:
        selected_index = next(i for i, item in enumerate(results) if item["url"] == selected["url"])
    except StopIteration:
        selected_index = 0

    max_index = min(len(results), selected_index + MAX_SEARCH_CANDIDATE_TRIES)
    best_chapters = []
    best_thread = None

    for i in range(selected_index, max_index):
        item = results[i]
        print(f"\n🔎 尝试从帖子提取目录 [{i + 1}/{len(results)}]：{item['title']}")
        try:
            candidates = scraper.extract_catalog_candidates_from_thread(item["url"])
        except Exception as exc:
            print(f"   ⚠️ 提取失败：{exc}")
            continue

        if not candidates:
            print("   ⚠️ 未提取到任何目录候选。")
            continue

        choice = choose_catalog_candidate(candidates)
        if choice is None:
            print("   ⏭️ 放弃该帖子，继续下一条搜索结果。")
            continue

        chosen = candidates[choice]
        chapters = chosen["chapters"]
        reason = chosen["score_reason"]
        print(
            f"   ✅ 已选候选：{chosen['selector']} | 章节 {chosen['chapter_count']} | 分数 {chosen['score']:.1f} "
            f"(链接+{reason['base']:.1f}, PID+{reason['pid_bonus']:.1f}, 标题+{reason['title_bonus']:.1f}, "
            f"结构+{reason['structure_bonus']:.1f}, 数量+{reason['size_bonus']:.1f}, "
            f"质量惩罚-{reason.get('quality_penalty', 0):.1f})"
        )

        if len(chapters) >= MIN_CATALOG_CHAPTERS:
            print(f"✅ 使用该帖子作为目录来源：{item['title']}")
            return chapters, item

        if len(chapters) > len(best_chapters):
            best_chapters = chapters
            best_thread = item
        print("   ⏭️ 目录不足，继续尝试下一条搜索结果。")

    if best_chapters:
        print(
            f"⚠️ 未找到完整目录，回退使用候选最多的帖子：{best_thread['title']}（{len(best_chapters)} 条）"
        )
        return best_chapters, best_thread
    return [], selected


def prepare_chapters(scraper: YamiboScraper, config) -> tuple[list[dict], dict | None, str]:
    mode = get_catalog_mode()

    if mode == "1":
        if not config.raw_html_catalog.strip():
            print("⚠️ 当前 raw_html_catalog 为空，先进入配置编辑。")
            config = edit_config_interactive(config)
            save_config(config)
            if not config.raw_html_catalog.strip():
                return [], None, mode
        chapters = scraper.parse_catalog(config.raw_html_catalog)
        print(f"✅ 从 raw_html_catalog 解析出 {len(chapters)} 个章节链接。")
        return chapters, None, mode

    chapters, source_thread = resolve_chapters_from_search(scraper)
    return chapters, source_thread, mode


def preview_chapters(scraper: YamiboScraper, chapters: list[dict]) -> tuple[bool, dict[int, str]]:
    preview_count = min(2, len(chapters))
    if preview_count == 0:
        return False, {}

    print(f"\n开始抓取预览章节（共 {preview_count} 章）...")
    preview_cache: dict[int, str] = {}

    for i in range(preview_count):
        chapter = chapters[i]
        content = scraper.fetch_chapter_content(chapter["url"])
        preview_cache[i] = content

        clean_text = re.sub(r"\s+", " ", content).strip()
        snippet = clean_text[:100]
        if len(clean_text) > 100:
            snippet += "..."

        print(f"\n--- 预览章节 {i + 1}/{preview_count} ---")
        print(f"标题: {chapter['title']}")
        print(f"片段: {snippet or '(空)'}")

        if i + 1 < preview_count:
            time.sleep(random.uniform(1.2, 2.2))

    return ask_preview_confirm(), preview_cache


def ensure_book_meta(config, source_thread: dict | None) -> None:
    suggested_title = config.book_title
    suggested_author = config.book_author
    if source_thread:
        suggested_title, suggested_author = _extract_suggested_meta_from_thread_title(source_thread["title"])

    if not suggested_title:
        suggested_title = "TITLE"
    if not suggested_author or suggested_author.upper() == "AUTHOR":
        suggested_author = "UNKNOWN"

    current_title = config.book_title
    if current_title.upper() == "TITLE":
        current_title = ""
    current_author = config.book_author
    if current_author.upper() == "AUTHOR":
        current_author = ""

    selected_title, selected_author = choose_book_metadata(
        current_title=current_title,
        current_author=current_author,
        suggested_title=suggested_title,
        suggested_author=suggested_author,
    )

    config.book_title = selected_title
    config.book_author = selected_author

    save_config(config)


def run_scraper(config):
    session = build_authenticated_session(config)
    if not session:
        return

    print("\n配置完成，开始抓取目录...")

    scraper = YamiboScraper(session)
    preview_cache = {}
    source_thread = None
    source_mode = ""

    while True:
        chapters, source_thread, source_mode = prepare_chapters(scraper, config)
        if not chapters:
            print("未解析到任何章节，请检查目录来源后重试。")
            return

        confirmed, preview_cache = preview_chapters(scraper, chapters)
        if confirmed:
            break

        if source_mode == "2":
            if ask_retry_search():
                continue
            print("已取消本次抓取。")
            return

        if ask_yes_no("是否进入配置编辑，更新 raw_html_catalog 后重试？", default=True):
            config = edit_config_interactive(config)
            save_config(config)
            continue
        print("已取消本次抓取。")
        return

    ensure_book_meta(config, source_thread)
    save_choice = get_save_choice()
    speed_mode = get_crawl_speed_mode()
    speed_profile = SPEED_PROFILES[speed_mode]
    safe_base_name = _sanitize_filename(config.book_title)
    txt_path = OUTPUT_DIR / f"{safe_base_name}.txt"
    epub_path = OUTPUT_DIR / f"{safe_base_name}.epub"

    if save_choice == "2" and txt_path.exists() and ask_use_existing_txt_for_epub(txt_path):
        chapters_from_txt = parse_chapters_from_txt(txt_path)
        if not chapters_from_txt:
            print("❌ TXT 解析失败，无法直接转换 EPUB，请改为重新抓取。")
            return
        save_to_epub(chapters_from_txt, epub_path, config.book_title, config.book_author)
        return

    print("\n预览确认通过，开始完整抓取...")
    print(
        f"⚙️ 当前速度档：{speed_profile['label']} "
        f"（间隔 {speed_profile['delay_min']:.2f}~{speed_profile['delay_max']:.2f}s）"
    )

    failed_records = []
    total = len(chapters)
    full_start_time = time.time()

    next_burst_pause_at = None
    if speed_profile["burst_every_min"] > 0:
        next_burst_pause_at = random.randint(
            speed_profile["burst_every_min"],
            speed_profile["burst_every_max"],
        )

    for i, ch in enumerate(chapters):
        if i in preview_cache:
            content = preview_cache[i]
            print(f"[{i + 1}/{len(chapters)}] {ch['title']} | 使用预览缓存")
        else:
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
        done = i + 1
        elapsed = time.time() - full_start_time
        avg = elapsed / done if done else 0
        eta_seconds = avg * (total - done)

        print(
            f"[{done}/{total}] {ch['title']} | 预览: {preview} | "
            f"预计剩余时间: {_format_seconds(eta_seconds)}"
        )
        if done < total:
            delay = random.uniform(speed_profile["delay_min"], speed_profile["delay_max"])
            print(f"   ⏳ 休眠 {delay:.2f}s 后继续...")
            time.sleep(delay)

        if next_burst_pause_at and done == next_burst_pause_at and done < total:
            long_break = random.uniform(speed_profile["burst_pause_min"], speed_profile["burst_pause_max"])
            print(f"   💤 降压长休眠 {long_break:.2f}s（保护服务器）...")
            time.sleep(long_break)
            next_burst_pause_at += random.randint(
                speed_profile["burst_every_min"],
                speed_profile["burst_every_max"],
            )

    total_elapsed = time.time() - full_start_time
    print(f"\n抓取结束（总耗时 {_format_seconds(total_elapsed)}），开始生成文件...")

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
        print("\n✅ 文件生成完成。")
    else:
        print("\n✅ 文件生成完成，全部章节抓取成功。")


def run_txt_to_epub_from_output(config) -> None:
    txt_files = sorted(OUTPUT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"❌ 在 {OUTPUT_DIR} 中未找到 TXT 文件。")
        return

    print("\n可转换的 TXT 文件：")
    for i, p in enumerate(txt_files, start=1):
        print(f"{i}. {p.name}")

    while True:
        raw = input("请选择要转换的 TXT 序号（q 取消）: ").strip().lower()
        if raw == "q":
            return
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(txt_files):
                txt_path = txt_files[idx - 1]
                break
        print("输入无效，请重新输入。")

    chapters = parse_chapters_from_txt(txt_path)
    if not chapters:
        print("❌ TXT 解析失败，无法转换 EPUB。")
        return

    default_title = txt_path.stem
    default_author = config.book_author if config.book_author and config.book_author != "AUTHOR" else "UNKNOWN"

    if ask_yes_no(f"是否使用默认标题「{default_title}」？", default=True):
        title = default_title
    else:
        title = input("请输入 EPUB 标题: ").strip() or default_title

    author = input(f"请输入 EPUB 作者（默认 {default_author}）: ").strip() or default_author
    epub_path = txt_path.with_suffix(".epub")
    save_to_epub(chapters, epub_path, title, author)
    print("✅ TXT -> EPUB 转换完成。")


def main():
    print_terminal_encoding_hint()
    config = load_config()

    while True:
        action = get_main_action()

        if action == "1":
            run_scraper(config)
        elif action == "2":
            run_txt_to_epub_from_output(config)
        elif action == "3":
            config = edit_config_interactive(config)
            save_config(config)
            print("✅ 配置已保存到 yamibo_config.json")
        elif action == "4":
            try:
                from gui_app import launch_gui
            except Exception as exc:
                print(f"❌ GUI 启动失败：{exc}")
                continue
            launch_gui()
        else:
            print("已退出。")
            return


if __name__ == "__main__":
    main()
