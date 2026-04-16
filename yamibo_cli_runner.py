import random
import re
import time

from auth import create_session, login_with_password, prompt_cookie
from cli import (
    ask_preview_confirm,
    ask_retry_failed_chapters,
    ask_retry_search,
    ask_use_existing_txt_for_epub,
    ask_yes_no,
    choose_book_metadata,
    choose_catalog_candidate,
    choose_thread,
    edit_config_interactive,
    get_auth_mode,
    get_catalog_mode,
    get_crawl_speed_mode,
    get_main_action,
    get_save_choice,
    get_search_forum_scope,
    get_search_keyword,
    print_terminal_encoding_hint,
)
from config_store import load_config, save_config
from search import search_threads_by_keyword
from yamibo_core import (
    FAILED_MARKER_PREFIX,
    MIN_CATALOG_CHAPTERS,
    OUTPUT_DIR,
    SPEED_PROFILES,
    YamiboScraper,
)
from yamibo_output import (
    _extract_suggested_meta_from_thread_title,
    _format_seconds,
    _sanitize_filename,
    dump_failed_chapters,
    parse_chapters_from_txt,
    retry_failed_chapters,
    save_to_epub,
    save_to_txt,
)

MAX_SEARCH_CANDIDATE_TRIES = 10


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
        selected_index = next(index for index, item in enumerate(results) if item["url"] == selected["url"])
    except StopIteration:
        selected_index = 0

    best_chapters: list[dict] = []
    best_thread = None
    max_index = min(len(results), selected_index + MAX_SEARCH_CANDIDATE_TRIES)

    for index in range(selected_index, max_index):
        item = results[index]
        print(f"\n🔎 尝试从帖子提取目录 [{index + 1}/{len(results)}]：{item['title']}")
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
        print(f"⚠️ 未找到完整目录，回退使用候选最多的帖子：{best_thread['title']}（{len(best_chapters)} 条）")
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

    preview_cache: dict[int, str] = {}
    print(f"\n开始抓取预览章节（共 {preview_count} 章）...")
    for index in range(preview_count):
        chapter = chapters[index]
        content = scraper.fetch_chapter_content(chapter["url"])
        preview_cache[index] = content
        snippet = re.sub(r"\s+", " ", content).strip()
        snippet = f"{snippet[:100]}..." if len(snippet) > 100 else snippet
        print(f"\n--- 预览章节 {index + 1}/{preview_count} ---")
        print(f"标题: {chapter['title']}")
        print(f"片段: {snippet or '(空)'}")
        if index + 1 < preview_count:
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

    current_title = "" if config.book_title.upper() == "TITLE" else config.book_title
    current_author = "" if config.book_author.upper() == "AUTHOR" else config.book_author
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

    failed_records: list[dict] = []
    total = len(chapters)
    full_start_time = time.time()
    next_burst_pause_at = None
    if speed_profile["burst_every_min"] > 0:
        next_burst_pause_at = random.randint(
            speed_profile["burst_every_min"],
            speed_profile["burst_every_max"],
        )

    for index, chapter in enumerate(chapters):
        content = preview_cache[index] if index in preview_cache else scraper.fetch_chapter_content(chapter["url"])
        if index in preview_cache:
            print(f"[{index + 1}/{len(chapters)}] {chapter['title']} | 使用预览缓存")

        if content.startswith("【最终失败"):
            marker = f"{FAILED_MARKER_PREFIX}{index + 1}#"
            failed_records.append(
                {"index": index, "title": chapter["title"], "url": chapter["url"], "marker": marker}
            )
            content = marker

        chapter["content"] = content
        clean_text = re.sub(r"\s+", "", content)
        preview = f"{clean_text[:20]}..." if len(clean_text) > 20 else clean_text
        done = index + 1
        elapsed = time.time() - full_start_time
        eta_seconds = (elapsed / done) * (total - done) if done else 0
        print(f"[{done}/{total}] {chapter['title']} | 预览: {preview} | 预计剩余时间: {_format_seconds(eta_seconds)}")

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

    print(f"\n抓取结束（总耗时 {_format_seconds(time.time() - full_start_time)}），开始生成文件...")
    if save_choice in ["1", "3"]:
        save_to_txt(chapters, txt_path)
    if save_choice in ["2", "3"]:
        save_to_epub(chapters, epub_path, config.book_title, config.book_author)

    if not failed_records:
        print("\n✅ 文件生成完成，全部章节抓取成功。")
        return

    failed_file = OUTPUT_DIR / f"{safe_base_name}.failed_chapters.json"
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


def run_txt_to_epub_from_output(config) -> None:
    txt_files = sorted(OUTPUT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"❌ 在 {OUTPUT_DIR} 中未找到 TXT 文件。")
        return

    print("\n可转换的 TXT 文件：")
    for index, path in enumerate(txt_files, start=1):
        print(f"{index}. {path.name}")

    while True:
        raw = input("请选择要转换的 TXT 序号（q 取消）: ").strip().lower()
        if raw == "q":
            return
        if raw.isdigit():
            chosen = int(raw)
            if 1 <= chosen <= len(txt_files):
                txt_path = txt_files[chosen - 1]
                break
        print("输入无效，请重新输入。")

    chapters = parse_chapters_from_txt(txt_path)
    if not chapters:
        print("❌ TXT 解析失败，无法转换 EPUB。")
        return

    default_title = txt_path.stem
    default_author = config.book_author if config.book_author and config.book_author != "AUTHOR" else "UNKNOWN"
    title = default_title if ask_yes_no(f"是否使用默认标题「{default_title}」？", default=True) else input("请输入 EPUB 标题: ").strip() or default_title
    author = input(f"请输入 EPUB 作者（默认 {default_author}）: ").strip() or default_author
    save_to_epub(chapters, txt_path.with_suffix(".epub"), title, author)
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
