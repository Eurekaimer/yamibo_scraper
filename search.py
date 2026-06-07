"""帖子搜索模块（MVP 骨架）。"""

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from opencc import OpenCC

BASE_URL = "https://bbs.yamibo.com/"
_cc = OpenCC("t2s")
_QUERY_SPLIT_RE = re.compile(r"[\s,\uFF0C\u3001\u3002\uFF1B;\uFF1A:\u300A\u300B\u3008\u3009\u300E\u300F\u300C\u300D()\uFF08\uFF09\[\]\u3010\u3011]+")

FORUM_NAME_MAP = {
    49: "文学区",
    55: "译文区",
}


def _normalize_url(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("javascript:"):
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("forum.php"):
        return BASE_URL + href
    if href.startswith("./"):
        return BASE_URL + href[2:]
    if href.startswith("/"):
        return "https://bbs.yamibo.com" + href
    return BASE_URL + href


def _extract_tid(url: str) -> str:
    m = re.search(r"[?&]tid=(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"thread-(\d+)-", url)
    if m:
        return m.group(1)
    return ""


def _extract_forum_info(anchor, fallback_fid: int | None) -> tuple[int | None, str]:
    row = anchor.find_parent("tr")
    forum_anchor = None
    if row:
        forum_anchor = row.select_one("a[href*='forum-'], a[href*='fid=']")

    forum_id = fallback_fid
    forum_name = FORUM_NAME_MAP.get(fallback_fid, "未知分区")

    if forum_anchor:
        forum_name = forum_anchor.get_text(strip=True) or forum_name
        href = forum_anchor.get("href", "")
        m = re.search(r"forum-(\d+)-", href) or re.search(r"[?&]fid=(\d+)", href)
        if m:
            forum_id = int(m.group(1))
            forum_name = FORUM_NAME_MAP.get(forum_id, forum_name)

    return forum_id, forum_name


def _safe_int(text: str) -> int:
    cleaned = re.sub(r"[^\d]", "", text or "")
    return int(cleaned) if cleaned else 0


def _extract_thread_stats(anchor) -> tuple[int, int]:
    row = anchor.find_parent("tr")
    if not row:
        return 0, 0

    num_cell = row.select_one("td.num, td[class*='num']")
    if num_cell:
        nums = re.findall(r"\d[\d,]*", num_cell.get_text(" ", strip=True))
        if len(nums) >= 2:
            return _safe_int(nums[0]), _safe_int(nums[1])
        if len(nums) == 1:
            return _safe_int(nums[0]), 0

    candidates = row.select("td span.xi1, td span.xw1, td em, td cite")
    nums = []
    for node in candidates:
        val = _safe_int(node.get_text(strip=True))
        if val > 0:
            nums.append(val)
    if len(nums) >= 2:
        return nums[0], nums[1]
    return 0, 0


def _collect_results_from_soup(
    soup: BeautifulSoup,
    result_map: dict[str, dict],
    forum_ids: set[int] | None,
    fallback_fid: int | None,
    order_key: str,
) -> None:
    candidates = soup.select("a.xst, a.s.xst, a[href*='mod=viewthread'], a[href*='viewthread']")
    rank = 0

    for anchor in candidates:
        href = _normalize_url(anchor.get("href", ""))
        title = anchor.get_text(strip=True)
        if not href or not title:
            continue

        if "viewthread" not in href:
            continue

        forum_id, forum_name = _extract_forum_info(anchor, fallback_fid)
        if forum_ids and forum_id is not None and forum_id not in forum_ids:
            continue

        tid = _extract_tid(href)
        unique_key = f"tid:{tid}" if tid else f"url:{href}"
        rank += 1
        replies, views = _extract_thread_stats(anchor)
        if unique_key not in result_map:
            result_map[unique_key] = {
                "title": title,
                "url": href,
                "forum_id": forum_id,
                "forum_name": forum_name,
                "replies": 0,
                "views": 0,
                "reply_rank": 0,
                "view_rank": 0,
                "popularity_score": 0.0,
            }
        item = result_map[unique_key]
        item["title"] = title
        item["url"] = href
        item["forum_id"] = forum_id
        item["forum_name"] = forum_name

        if replies > item.get("replies", 0):
            item["replies"] = replies
        if views > item.get("views", 0):
            item["views"] = views

        # 记录该结果在排序页中的名次（越靠前越好）
        rank_field = "reply_rank" if order_key == "replies" else "view_rank"
        if item[rank_field] == 0 or rank < item[rank_field]:
            item[rank_field] = rank


def _query_variants(keyword: str) -> list[str]:
    raw = (keyword or "").strip()
    if not raw:
        return []

    candidates: list[str] = [raw]
    simplified = _cc.convert(raw)
    if simplified != raw:
        candidates.append(simplified)

    for base in list(candidates):
        parts = [
            p.strip()
            for p in re.split(_QUERY_SPLIT_RE, base)
            if p.strip()
        ]
        candidates.extend(part for part in parts if len(part) >= 4)

    compact = re.sub(_QUERY_SPLIT_RE, "", simplified)
    if compact and compact != simplified:
        candidates.append(compact)

    seen: set[str] = set()
    result: list[str] = []
    for item in candidates:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result[:6]


def search_threads_by_keyword(
    session,
    keyword: str,
    forum_ids: list[int] | None = None,
    limit: int = 10,
) -> list[dict]:
    """按关键字搜索百合会帖子，支持限制分区。"""

    query_variants = _query_variants(keyword)
    scoped_forums = forum_ids or [55, 49]
    forum_set = set(scoped_forums) if scoped_forums else None

    result_map: dict[str, dict] = {}

    for order_key in ("replies", "views"):
        for fid in scoped_forums:
            for query_text in query_variants:
                before_count = len(result_map)
                query = quote_plus(query_text)
                url_candidates = [
                    (
                        f"{BASE_URL}search.php?mod=forum&searchsubmit=yes"
                        f"&srchfid%5B%5D={fid}&orderby={order_key}&ascdesc=desc"
                        f"&srchtxt={query}&kw={query}"
                    ),
                    (
                        f"{BASE_URL}search.php?mod=forum&searchsubmit=yes"
                        f"&srchfid%5B%5D={fid}&orderby={order_key}&ascdesc=desc"
                        f"&srchtxt={query}"
                    ),
                ]

                for url in url_candidates:
                    try:
                        response = session.get(url, timeout=20)
                        response.raise_for_status()
                    except Exception as exc:
                        print(f"search request failed (fid={fid}, order={order_key}, query={query_text}): {exc}")
                        continue

                    soup = BeautifulSoup(response.content, "html.parser")
                    _collect_results_from_soup(
                        soup=soup,
                        result_map=result_map,
                        forum_ids=forum_set,
                        fallback_fid=fid,
                        order_key=order_key,
                    )
                    if len(result_map) > before_count:
                        break
                if len(result_map) > before_count:
                    break

    all_results = list(result_map.values())
    for item in all_results:
        reply_rank = item.get("reply_rank", 0)
        view_rank = item.get("view_rank", 0)
        reply_rank_score = max(0.0, 150.0 - reply_rank) if reply_rank else 0.0
        view_rank_score = max(0.0, 120.0 - view_rank) if view_rank else 0.0
        raw_score = item.get("replies", 0) * 3 + item.get("views", 0)
        item["popularity_score"] = raw_score + reply_rank_score * 100 + view_rank_score * 60

    all_results.sort(
        key=lambda x: (
            -x.get("popularity_score", 0),
            x.get("reply_rank", 10**9),
            x.get("view_rank", 10**9),
            -x.get("replies", 0),
            -x.get("views", 0),
        )
    )

    return all_results[:limit]
