from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

from auth import create_session, login_with_password
from config_store import load_config
from search import search_threads_by_keyword
from yamibo_core import FAILED_MARKER_PREFIX, OUTPUT_DIR, SPEED_PROFILES, YamiboScraper
from yamibo_output import _sanitize_filename, dump_failed_chapters, save_to_epub, save_to_txt


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _build_session(auth_required: bool = True):
    config = load_config()
    if config.cookie.strip():
        return create_session(config.user_agent, config.cookie.strip()), config
    if config.username.strip() and config.password:
        session = create_session(config.user_agent)
        if login_with_password(session, config.username.strip(), config.password):
            return session, config
        if auth_required:
            raise RuntimeError("account login failed; check yamibo_config.json")
    if auth_required:
        raise RuntimeError("missing cookie or account credentials; configure yamibo_config.json first")
    return create_session(config.user_agent), config


def _parse_forums(raw: str) -> list[int]:
    values = []
    for part in (raw or "49,55").split(","):
        part = part.strip()
        if part:
            values.append(int(part))
    return values or [49, 55]


def cmd_search(args: argparse.Namespace) -> int:
    session, _ = _build_session(auth_required=True)
    results = search_threads_by_keyword(session, args.keyword, forum_ids=_parse_forums(args.forums), limit=args.limit)
    for idx, item in enumerate(results, start=1):
        print(f"{idx}. [{item.get('forum_name', item.get('forum_id', '?'))}] {item['title']}")
        print(f"   replies={item.get('replies', 0)} views={item.get('views', 0)}")
        print(f"   {item['url']}")
    if not results:
        print("No results. Try a shorter keyword.")
    return 0


def _resolve_thread_url(args: argparse.Namespace, session) -> str:
    if args.url:
        return args.url
    if not args.keyword:
        raise RuntimeError("author-crawl requires --url or --keyword")
    results = search_threads_by_keyword(session, args.keyword, forum_ids=_parse_forums(args.forums), limit=max(1, args.pick))
    if len(results) < args.pick:
        raise RuntimeError(f"not enough search results to pick #{args.pick}")
    selected = results[args.pick - 1]
    print(f"Selected: {selected['title']}")
    print(selected["url"])
    return selected["url"]


def cmd_author_crawl(args: argparse.Namespace) -> int:
    session, config = _build_session(auth_required=True)
    scraper = YamiboScraper(session)
    thread_url = _resolve_thread_url(args, session)
    chapters = scraper.extract_author_chapters_from_thread(thread_url, author=args.author or None, max_pages=args.pages, min_chars=args.min_chars)
    if not chapters:
        raise RuntimeError("no author posts extracted")

    actual_author = chapters[0].get("author") or args.author or "UNKNOWN"
    title = args.title or config.book_title
    if not title or title.upper() == "TITLE":
        title = Path(_sanitize_filename(args.keyword or "yamibo_author_posts")).stem
    author = args.book_author or config.book_author
    if not author or author.upper() == "AUTHOR":
        author = actual_author

    safe_name = _sanitize_filename(title)
    txt_path = OUTPUT_DIR / f"{safe_name}.txt"
    epub_path = OUTPUT_DIR / f"{safe_name}.epub"
    profile = SPEED_PROFILES.get(args.speed, SPEED_PROFILES["fast"])
    failed_records: list[dict] = []

    print(f"Author posts: author={actual_author}, chapters={len(chapters)}, pages={args.pages}")
    for index, chapter in enumerate(chapters):
        content = chapter.get("content") or scraper.fetch_chapter_content(chapter["url"])
        if content.startswith("\u3010\u6700\u7ec8\u5931\u8d25"):
            marker = f"{FAILED_MARKER_PREFIX}{index + 1}#"
            failed_records.append({"index": index, "title": chapter["title"], "url": chapter["url"], "marker": marker})
            content = marker
        chapter["content"] = content
        print(f"[{index + 1}/{len(chapters)}] {chapter['title']}")
        if index + 1 < len(chapters):
            time.sleep(random.uniform(profile["delay_min"], profile["delay_max"]))

    if args.save in {"txt", "both"}:
        save_to_txt(chapters, txt_path)
    if args.save in {"epub", "both"}:
        save_to_epub(chapters, epub_path, title, author)
    if failed_records:
        failed_file = OUTPUT_DIR / f"{safe_name}.failed_chapters.json"
        dump_failed_chapters(failed_records, failed_file)
        print(f"Failed chapter record: {failed_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yamibo Scraper command line")
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search", help="search threads")
    search.add_argument("--keyword", required=True)
    search.add_argument("--forums", default="49,55")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)
    crawl = sub.add_parser("author-crawl", help="crawl substantial posts by author, without a catalog")
    crawl.add_argument("--url", default="")
    crawl.add_argument("--keyword", default="")
    crawl.add_argument("--forums", default="49,55")
    crawl.add_argument("--pick", type=int, default=1)
    crawl.add_argument("--author", default="", help="forum author id; blank means infer from first content post")
    crawl.add_argument("--pages", type=int, default=5, help="max pages to scan")
    crawl.add_argument("--min-chars", type=int, default=80)
    crawl.add_argument("--title", default="")
    crawl.add_argument("--book-author", default="")
    crawl.add_argument("--save", choices=["txt", "epub", "both"], default="both")
    crawl.add_argument("--speed", choices=sorted(SPEED_PROFILES), default="fast")
    crawl.set_defaults(func=cmd_author_crawl)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
