"""帖子搜索模块（MVP 骨架）。"""

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup


def _normalize_thread_url(href: str) -> str:
    href = href.strip()
    if not href:
        return ""

    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("forum.php"):
        return "https://bbs.yamibo.com/" + href
    if href.startswith("/"):
        return "https://bbs.yamibo.com" + href
    return ""


def search_threads_by_keyword(session, keyword: str, limit: int = 10) -> list[dict]:
    """按关键字搜索百合会帖子，返回候选列表。"""

    query = quote_plus(keyword)
    urls = [
        f"https://bbs.yamibo.com/search.php?mod=forum&searchsubmit=yes&srchtxt={query}",
        f"https://bbs.yamibo.com/search.php?mod=forum&srchtxt={query}",
    ]

    for url in urls:
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            print(f"⚠️ 搜索请求失败：{exc}")
            continue

        soup = BeautifulSoup(response.content, "html.parser")
        results = []
        seen = set()

        # 优先常见主题链接样式
        for anchor in soup.select("a.xst, a.s.xst, h3.xs3 a"):
            href = _normalize_thread_url(anchor.get("href", ""))
            title = anchor.get_text(strip=True)
            if not href or not title:
                continue
            if "mod=viewthread" not in href and "thread-" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            results.append({"title": title, "url": href})
            if len(results) >= limit:
                return results

        # 兜底：全量扫描所有链接
        for anchor in soup.find_all("a", href=True):
            href = _normalize_thread_url(anchor["href"])
            if not href:
                continue
            if not re.search(r"(mod=viewthread|thread-\d+)", href):
                continue
            title = anchor.get_text(" ", strip=True)
            if not title or len(title) < 2:
                continue
            if href in seen:
                continue
            seen.add(href)
            results.append({"title": title, "url": href})
            if len(results) >= limit:
                return results

        if results:
            return results

    return []
