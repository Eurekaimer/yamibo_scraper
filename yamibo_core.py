import random
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from opencc import OpenCC

OUTPUT_DIR = Path("./output")
BASE_URL = "https://bbs.yamibo.com/"

RETRY_JITTER_MAX = 0.8
MIN_CATALOG_CHAPTERS = 3
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

_cc = OpenCC("t2s")
_CHAPTER_HINT_RE = re.compile(r"(episode|ep\.?\s*\d+|chapter|ch\.?\s*\d+)", re.I)
_CN_CHAPTER_HINT_RE = re.compile(r"(第\s*\d+\s*[话章节卷]|序章|终章|后记|番外|目录)")
_NUMERIC_TITLE_RE = re.compile(r"\d{1,4}([#.]|\s*话)?", re.I)
_SUSPICIOUS_TITLE_RE = re.compile(r"[#\[\]【】复制链接只看举报楼主沙发板凳]")
_POSTMESSAGE_RE = re.compile(r"^postmessage_\d+$")
_CATALOG_LINK_RE = re.compile(r'https?://bbs\.yamibo\.com/[^\s"<>]+viewthread[^\s"<>]*')
_THREAD_ID_RE = re.compile(r"(?:[?&]tid=|thread-)(\d+)")
_THREAD_PAGE_RE = re.compile(r"thread-\d+-(\d+)-\d+\.html")
_QUERY_PAGE_RE = re.compile(r"(?:[?&]|&amp;)page=(\d+)")
_POST_CONTAINER_RE = re.compile(r"^(post_|pid)\d+")
_EDIT_NOTICE_RE = re.compile(r"^\u672c\u5e16\u6700\u540e\u7531\s+.+?\s+\u4e8e\s+.+?\s+\u7f16\u8f91\s*$")
_CHAPTER_HEADING_RE = re.compile(
    r"^(?:"
    r"\u7b2c?\s*[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u3007\u96f6\u4e24\d]+(?:\u53c8[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u3007\u96f6\u4e24\d]+\u5206\u4e4b[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u3007\u96f6\u4e24\d]+)?"
    r"|\u756a\u5916(?:[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u3007\u96f6\u4e24\d]+)?"
    r"|\u5c3e\u58f0(?:[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u3007\u96f6\u4e24\d]+)?"
    r"|\u540e\u8bb0|\u5e8f\u7ae0|\u7ec8\u7ae0"
    r")\s*[\u3001.\uff0e\s].{0,80}$"
)


_NOISE_KEYWORDS = (
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
)

_CATALOG_FALLBACK_SELECTORS = (
    "table",
    "tbody",
    "div#postlist",
    "div[id^='postmessage_']",
    "td[id^='postmessage_']",
    "div.pcb",
)

_POST_AUTHOR_SELECTORS = (
    ".authi a[href*='space']",
    ".pls .xw1 a",
    ".pls a[href*='space']",
    "a[href*='uid=']",
    "a[href*='space-uid']",
)

_CONTENT_NOISE_SELECTORS = (
    "script",
    "style",
    "i.pstatus",
    ".pstatus",
    ".quote",
    ".blockquote",
    ".attach_nopermission",
    ".locked",
    ".ignore_js_op",
    ".aimg_tip",
    ".tip",
)


class YamiboScraper:
    def __init__(self, session):
        self.session = session
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _extract_pid(url: str) -> str:
        parsed = urlparse(url or "")
        pid = parse_qs(parsed.query).get("pid", [""])[0]
        if pid:
            return pid
        fragment_match = re.search(r"pid(\d+)", parsed.fragment or "")
        return fragment_match.group(1) if fragment_match else ""

    @staticmethod
    def _is_probable_chapter_title(title: str) -> bool:
        normalized = (title or "").strip()
        lowered = normalized.lower()
        if not lowered:
            return False
        return bool(
            _CHAPTER_HINT_RE.search(lowered)
            or _CN_CHAPTER_HINT_RE.search(normalized)
            or _NUMERIC_TITLE_RE.fullmatch(lowered)
        )

    @staticmethod
    def _is_noise_title(title: str) -> bool:
        normalized = (title or "").strip()
        return not normalized or any(keyword in normalized for keyword in _NOISE_KEYWORDS)

    @staticmethod
    def _normalize_url(url: str) -> str:
        normalized = (url or "").strip().replace("&amp;", "&")
        if not normalized or normalized.startswith("javascript:"):
            return ""
        if normalized.startswith(("http://", "https://")):
            return normalized
        if normalized.startswith("forum.php"):
            return urljoin(BASE_URL, normalized)
        if normalized.startswith("./"):
            return urljoin(BASE_URL, normalized[2:])
        if normalized.startswith("/"):
            return f"https://bbs.yamibo.com{normalized}"
        return urljoin(BASE_URL, normalized)

    def _extract_chapters_from_soup(self, scope) -> list[dict]:
        chapters: list[dict] = []
        seen_keys: set[str] = set()
        anchors = scope.select(
            "a[href*='viewthread'], "
            "a[href*='mod=viewthread'], "
            "a[href*='goto=findpost'], "
            "a[href*='findpost'], "
            "a[href*='pid=']"
        )
        for idx, anchor in enumerate(anchors, start=1):
            url = self._normalize_url(anchor.get("href", ""))
            if not url or not any(part in url for part in ("viewthread", "findpost", "pid=")):
                continue

            pid = self._extract_pid(url)
            unique_key = f"pid:{pid}" if pid else f"url:{url}"
            if unique_key in seen_keys:
                continue

            title = anchor.get_text(strip=True)
            if self._is_noise_title(title):
                continue

            seen_keys.add(unique_key)
            chapters.append(
                {
                    "title": title or f"章节{idx}",
                    "url": url,
                    "pid": pid,
                    "order_hint": len(chapters),
                    "content": "",
                }
            )
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

        titles = [chapter.get("title", "") for chapter in chapters]
        probable_mask = [self._is_probable_chapter_title(title) for title in titles]
        pid_count = sum(1 for chapter in chapters if chapter.get("pid"))
        probable_title_count = sum(probable_mask)
        suspicious_title_count = sum(
            1
            for title, is_probable in zip(titles, probable_mask, strict=False)
            if not is_probable and _SUSPICIOUS_TITLE_RE.search(title)
        )

        base = float(len(chapters))
        pid_bonus = pid_count * 1.4
        title_bonus = probable_title_count * 1.8
        structure_bonus = 26.0 if selector == "showcollapse" else -24.0 if selector == "fallback-page" else 0.0
        size_bonus = 3.0 if len(chapters) >= MIN_CATALOG_CHAPTERS else 0.0
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
        parsed = self._extract_chapters_from_soup(soup)
        if parsed:
            return parsed

        chapters: list[dict] = []
        seen_urls: set[str] = set()
        for idx, raw_url in enumerate(_CATALOG_LINK_RE.findall(html_text), start=1):
            url = self._normalize_url(raw_url)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
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

        candidate_nodes: list[tuple[str, object]] = []
        for node in soup.select("div.showcollapse_content"):
            if node.select_one("a[href*='findpost'], a[href*='pid='], a[href*='viewthread']"):
                candidate_nodes.append(("showcollapse", node))

        for selector in _CATALOG_FALLBACK_SELECTORS:
            for node in soup.select(selector):
                if node.select_one("a[href*='viewthread'], a[href*='mod=viewthread']"):
                    candidate_nodes.append((selector, node))

        scored_candidates: list[dict] = []
        seen_signatures: set[tuple[str, ...]] = set()
        for idx, (selector, node) in enumerate(candidate_nodes, start=1):
            chapters = self._extract_chapters_from_soup(node)
            if not chapters:
                continue

            signature = tuple((chapter.get("pid") or chapter.get("url")) for chapter in chapters[:30])
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)

            detail = self._score_catalog_detail(chapters, selector=selector)
            scored_candidates.append(
                {
                    "selector": f"{selector}#{idx}",
                    "chapters": chapters,
                    "chapter_count": len(chapters),
                    "score": detail["score"],
                    "score_reason": detail,
                    "sample_titles": [chapter["title"] for chapter in chapters[:3]],
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
                    "sample_titles": [chapter["title"] for chapter in fallback[:3]],
                }
            )

        scored_candidates.sort(key=lambda item: item["score"], reverse=True)
        return scored_candidates[:8]

    def extract_catalog_from_thread(self, thread_url: str) -> list[dict]:
        candidates = self.extract_catalog_candidates_from_thread(thread_url)
        if not candidates:
            return []
        best = candidates[0]
        print(
            f"   auto selected candidate ({best['selector']}), "
            f"章节 {best['chapter_count']}，评分 {best['score']:.1f}。"
        )
        return best["chapters"]


    @staticmethod
    def _extract_tid(url: str) -> str:
        match = _THREAD_ID_RE.search(url or "")
        return match.group(1) if match else ""

    def _thread_page_url(self, thread_url: str, page: int) -> str:
        normalized = self._normalize_url(thread_url)
        tid = self._extract_tid(normalized)
        if not tid:
            return normalized
        if "thread-" in normalized:
            return urljoin(BASE_URL, f"thread-{tid}-{page}-1.html")
        return urljoin(BASE_URL, f"forum.php?mod=viewthread&tid={tid}&page={page}")

    @staticmethod
    def _page_number_from_href(href: str) -> int | None:
        match = _THREAD_PAGE_RE.search(href or "")
        if match:
            return int(match.group(1))
        match = _QUERY_PAGE_RE.search(href or "")
        if match:
            return int(match.group(1))
        return None

    def _thread_page_urls(self, thread_url: str, soup: BeautifulSoup, total_pages: int) -> list[str]:
        urls = {1: self._normalize_url(thread_url)}
        for anchor in soup.select(".pg a[href]"):
            page = self._page_number_from_href(anchor.get("href", ""))
            if page and page > 1:
                urls[page] = self._normalize_url(anchor.get("href", ""))
        return [urls.get(page) or self._thread_page_url(thread_url, page) for page in range(1, total_pages + 1)]

    @staticmethod
    def _max_thread_page(soup: BeautifulSoup) -> int:
        pages = [1]
        for anchor in soup.select(".pg a[href]"):
            href = anchor.get("href", "")
            page = YamiboScraper._page_number_from_href(href)
            if page:
                pages.append(page)
            text = anchor.get_text(strip=True)
            if text.isdigit():
                pages.append(int(text))
        for node in soup.select(".pg, .pgb"):
            for page_text in re.findall(r"\d+", node.get_text(" ", strip=True)):
                pages.append(int(page_text))
        return max(pages)

    @staticmethod
    def _extract_post_author(post_node) -> str:
        for selector in _POST_AUTHOR_SELECTORS:
            node = post_node.select_one(selector)
            if node:
                author = node.get_text(strip=True)
                if author and author not in {"[\u590d\u5236\u94fe\u63a5]", "\u590d\u5236\u94fe\u63a5"}:
                    return author
        return ""

    @staticmethod
    def _is_noise_content_line(line: str) -> bool:
        return any(line == keyword or (len(line) <= 12 and keyword in line) for keyword in _NOISE_KEYWORDS)

    def _infer_default_author_from_soup(self, soup: BeautifulSoup, min_chars: int) -> str:
        for content_node in soup.select("td[id^='postmessage_'], div[id^='postmessage_']"):
            post_node = content_node.find_parent(id=_POST_CONTAINER_RE) or content_node.find_parent("table") or content_node
            post_author = self._extract_post_author(post_node)
            if not post_author:
                continue
            try:
                post_text = self._clean_content_node(content_node)
            except Exception:
                return post_author
            if len(re.sub(r"\s+", "", post_text)) >= min_chars:
                return post_author
        return ""

    def _clean_content_node(self, content_node) -> str:
        node = BeautifulSoup(str(content_node), "html.parser")
        root = node.find(id=content_node.get("id")) or node
        for noise in root.select(", ".join(_CONTENT_NOISE_SELECTORS)):
            noise.decompose()

        lines: list[str] = []
        for raw_line in root.get_text(separator="\n", strip=True).splitlines():
            line = raw_line.replace("\xa0", " ").strip()
            if not line:
                continue
            if _EDIT_NOTICE_RE.match(line):
                continue
            if self._is_noise_content_line(line):
                continue
            lines.append(line)

        text = "\n".join(lines)
        if ENABLE_SIMPLIFIED:
            text = _cc.convert(text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(re.sub(r"\s+", "", text)) < 20:
            raise ValueError("content too short; probable non-content node")
        return text

    @staticmethod
    def _guess_post_title(text: str, fallback: str) -> str:
        for line in (text or "").splitlines()[:18]:
            candidate = line.strip()
            if not candidate:
                continue
            if _EDIT_NOTICE_RE.match(candidate):
                continue
            if _CHAPTER_HEADING_RE.match(candidate):
                return candidate[:80]
        return fallback

    def _extract_author_posts_from_soup(
        self,
        soup: BeautifulSoup,
        thread_url: str,
        author: str | None,
        min_chars: int,
        start_index: int,
    ) -> list[dict]:
        chapters: list[dict] = []
        expected_author = (author or "").strip()
        for content_node in soup.select("td[id^='postmessage_'], div[id^='postmessage_']"):
            pid = content_node.get("id", "").replace("postmessage_", "", 1)
            post_node = content_node.find_parent(id=_POST_CONTAINER_RE) or content_node.find_parent("table") or content_node
            post_author = self._extract_post_author(post_node)
            if expected_author and post_author != expected_author:
                continue

            try:
                post_text = self._clean_content_node(content_node)
            except Exception:
                continue
            if len(re.sub(r"\s+", "", post_text)) < min_chars:
                continue

            index = start_index + len(chapters) + 1
            fallback_title = f"\u4f5c\u8005\u697c\u5c42 {index}"
            title = self._guess_post_title(post_text, fallback_title)
            tid = self._extract_tid(thread_url)
            chapter_url = self._normalize_url(f"forum.php?mod=viewthread&tid={tid}&pid={pid}") if tid else thread_url
            chapters.append(
                {
                    "title": title,
                    "url": chapter_url,
                    "pid": pid,
                    "author": post_author,
                    "order_hint": index - 1,
                    "content": post_text,
                }
            )
        return chapters

    def extract_author_chapters_from_thread(
        self,
        thread_url: str,
        author: str | None = None,
        max_pages: int | None = None,
        min_chars: int = 20,
    ) -> list[dict]:
        """Build chapters from substantial posts by one author, without relying on a catalog/elevator."""

        first_response = self.session.get(thread_url, timeout=20)
        first_response.raise_for_status()
        first_soup = BeautifulSoup(first_response.content, "html.parser")
        total_pages = self._max_thread_page(first_soup)
        if max_pages is not None:
            total_pages = min(total_pages, max(1, max_pages))

        if not (author or "").strip():
            author = self._infer_default_author_from_soup(first_soup, min_chars)

        chapters = self._extract_author_posts_from_soup(
            first_soup,
            thread_url=thread_url,
            author=author,
            min_chars=min_chars,
            start_index=0,
        )
        seen_pids = {chapter.get("pid") for chapter in chapters if chapter.get("pid")}

        page_urls = self._thread_page_urls(thread_url, first_soup, total_pages)
        for page_url in page_urls[1:]:
            time.sleep(random.uniform(0.25, 0.65))
            response = self.session.get(page_url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            page_chapters = self._extract_author_posts_from_soup(
                soup,
                thread_url=thread_url,
                author=author,
                min_chars=min_chars,
                start_index=len(chapters),
            )
            for chapter in page_chapters:
                pid = chapter.get("pid")
                if pid and pid in seen_pids:
                    continue
                if pid:
                    seen_pids.add(pid)
                chapters.append(chapter)

        return chapters

    def fetch_chapter_content(self, url: str) -> str:
        pid = self._extract_pid(url) or None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                content_node = None
                if pid:
                    target_id = f"postmessage_{pid}"
                    content_node = soup.find("td", id=target_id) or soup.find("div", id=target_id)
                if not content_node:
                    content_node = soup.find("td", id=_POSTMESSAGE_RE)
                if not content_node:
                    content_node = soup.find("div", id=_POSTMESSAGE_RE)
                if not content_node:
                    content_node = soup.select_one("div.pcb, td.t_f, div.t_f")
                if not content_node:
                    raise ValueError("正文未找到")

                return self._clean_content_node(content_node)
            except Exception as exc:
                print(f"    attempt {attempt + 1} failed: {exc}")
                if attempt == MAX_RETRIES - 1:
                    return f"【最终失败：{exc}】"
                time.sleep((2 ** attempt) + random.uniform(0, RETRY_JITTER_MAX))
