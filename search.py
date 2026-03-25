"""帖子搜索模块（MVP 骨架）。"""

from urllib.parse import quote_plus

from bs4 import BeautifulSoup


def search_threads_by_keyword(session, keyword: str, limit: int = 10) -> list[dict]:
    """按关键字搜索百合会帖子，返回候选列表。"""

    query = quote_plus(keyword)
    url = f"https://bbs.yamibo.com/search.php?mod=forum&searchsubmit=yes&srchtxt={query}"

    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        print(f"⚠️ 搜索请求失败：{exc}")
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    results = []

    candidates = soup.select("a.xst, a.s.xst, a[href*='mod=viewthread'], a[href*='viewthread']")
    seen = set()

    for anchor in candidates:
        href = anchor.get("href", "").strip()
        title = anchor.get_text(strip=True)
        if not href or not title:
            continue

        if href.startswith("javascript:"):
            continue

        if href.startswith("forum.php"):
            href = "https://bbs.yamibo.com/" + href
        elif href.startswith("/"):
            href = "https://bbs.yamibo.com" + href
        elif href.startswith("./"):
            href = "https://bbs.yamibo.com/" + href[2:]

        if "viewthread" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)

        results.append({"title": title, "url": href})
        if len(results) >= limit:
            break

    return results
