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


class YamiboScraper:
    def __init__(self, session):
        self.session = session
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _extract_pid(url: str) -> str:
        return parse_qs(urlparse(url).query).get("pid", [""])[0]

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

                for pstatus in content_node.find_all("i", class_="pstatus"):
                    pstatus.decompose()
                for noise in content_node.select("script, style"):
                    noise.decompose()

                text = content_node.get_text(separator="\n", strip=True)
                if ENABLE_SIMPLIFIED:
                    text = _cc.convert(text)
                text = re.sub(r"\n{3,}", "\n\n", text)
                if len(re.sub(r"\s+", "", text)) < 20:
                    raise ValueError("正文内容过短，疑似未命中正文区域")
                return text
            except Exception as exc:
                print(f"    ⚠️ 第{attempt + 1}次失败: {exc}")
                if attempt == MAX_RETRIES - 1:
                    return f"【最终失败：{exc}】"
                time.sleep((2 ** attempt) + random.uniform(0, RETRY_JITTER_MAX))
