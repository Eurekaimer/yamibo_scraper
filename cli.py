"""命令行交互模块（MVP 骨架）。"""

from getpass import getpass
from pathlib import Path
import re


def get_main_action() -> str:
    print("\n请选择操作：")
    print("1. 开始抓取")
    print("2. output 目录 TXT 转 EPUB")
    print("3. 修改配置")
    print("4. 启动图形界面 GUI")
    print("5. 退出")

    while True:
        action = input("请输入对应数字 (1/2/3/4/5): ").strip()
        if action in ["1", "2", "3", "4", "5"]:
            return action
        print("输入无效，请重新输入 1、2、3、4 或 5。")


def get_save_choice() -> str:
    print("=" * 30)
    print("请选择要保存的文件格式：")
    print("1. 只保存 TXT 格式")
    print("2. 只保存 EPUB 格式")
    print("3. 同时保存 TXT 和 EPUB")
    print("=" * 30)

    while True:
        choice = input("请输入对应数字 (1/2/3): ").strip()
        if choice in ["1", "2", "3"]:
            return choice
        print("输入无效，请重新输入 1、2 或 3。")


def get_crawl_speed_mode() -> str:
    print("\n请选择抓取速度：")
    print("1. 快速（约 1s/章，轻微随机）")
    print("2. 平衡（约 2s/章）")
    print("3. 稳妥（约 3~4s/章，默认）")

    while True:
        choice = input("请输入对应数字 (1/2/3): ").strip()
        if choice == "1":
            return "fast"
        if choice == "2":
            return "balanced"
        if choice == "3":
            return "gentle"
        print("输入无效，请重新输入 1、2 或 3。")


def get_auth_mode() -> str:
    print("\n请选择登录方式：")
    print("1. 账号+密码登录（推荐）")
    print("2. 使用 Cookie（兼容模式）")

    while True:
        mode = input("请输入对应数字 (1/2): ").strip()
        if mode in ["1", "2"]:
            return mode
        print("输入无效，请重新输入 1 或 2。")


def get_catalog_mode() -> str:
    print("\n请选择抓取来源：")
    print("1. 使用 RAW_HTML_CATALOG（旧模式）")
    print("2. 根据小说名自动搜索（新骨架）")

    while True:
        mode = input("请输入对应数字 (1/2): ").strip()
        if mode in ["1", "2"]:
            return mode
        print("输入无效，请重新输入 1 或 2。")


def get_search_keyword() -> str:
    while True:
        keyword = input("请输入要搜索的小说名关键词: ").strip()
        if keyword:
            return keyword
        print("关键词不能为空，请重新输入。")


def get_search_forum_scope() -> list[int]:
    print("\n请选择搜索分区：")
    print("1. 译文区（forum-55）")
    print("2. 文学区（forum-49）")
    print("3. 两区都搜（49 + 55）")

    while True:
        choice = input("请输入对应数字 (1/2/3): ").strip()
        if choice == "1":
            return [55]
        if choice == "2":
            return [49]
        if choice == "3":
            return [49, 55]
        print("输入无效，请重新输入 1、2 或 3。")


def choose_thread(results: list[dict]) -> dict | None:
    if not results:
        print("未搜索到可用帖子。")
        return None

    print("\n搜索结果：")
    for idx, item in enumerate(results, start=1):
        forum_name = item.get("forum_name", "未知分区")
        replies = item.get("replies", 0)
        views = item.get("views", 0)
        score = item.get("popularity_score", 0)
        reply_rank = item.get("reply_rank", 0)
        view_rank = item.get("view_rank", 0)
        rank_text = (
            f"回复排序位次: {reply_rank or '-'} | 浏览排序位次: {view_rank or '-'}"
        )
        print(
            f"{idx}. [{forum_name}] {item['title']}\n"
            f"   回复: {replies} | 查看: {views} | 热度分: {score}\n"
            f"   {rank_text}\n"
            f"   {item['url']}"
        )

    while True:
        raw = input("请选择目标帖子序号（输入 q 取消）: ").strip().lower()
        if raw == "q":
            return None
        if raw.isdigit():
            i = int(raw)
            if 1 <= i <= len(results):
                return results[i - 1]
        print("输入无效，请重新输入。")


def ask_yes_no(question: str, default: bool | None = None) -> bool:
    suffix = " (y/n): "
    if default is True:
        suffix = " (Y/n): "
    elif default is False:
        suffix = " (y/N): "

    while True:
        raw = input(question + suffix).strip().lower()
        if not raw and default is not None:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("输入无效，请输入 y 或 n。")


def ask_preview_confirm() -> bool:
    return ask_yes_no("预览是否正确，并继续完整抓取？", default=True)


def ask_retry_search() -> bool:
    return ask_yes_no("是否返回搜索并重新选择帖子？", default=True)


def choose_book_metadata(
    current_title: str,
    current_author: str,
    suggested_title: str,
    suggested_author: str,
) -> tuple[str, str]:
    print("\n请确认输出书籍信息：")
    print(f"当前配置标题: {current_title or '(未设置)'}")
    print(f"推荐标题: {suggested_title or '(未识别)'}")
    print(f"当前配置作者: {current_author or '(未设置)'}")
    print(f"推荐作者: {suggested_author or '(未识别)'}")

    print("\n标题选项：")
    print("1. 使用推荐标题")
    print("2. 使用当前配置标题")
    print("3. 手动输入标题")

    while True:
        t_choice = input("请选择标题来源 (1/2/3): ").strip()
        if t_choice in {"1", "2", "3"}:
            break
        print("输入无效，请重新输入 1、2 或 3。")

    if t_choice == "1":
        title = suggested_title or current_title
    elif t_choice == "2":
        title = current_title
    else:
        title = input("请输入标题: ").strip()

    print("\n作者选项：")
    print("1. 使用推荐作者")
    print("2. 使用当前配置作者")
    print("3. 手动输入作者")

    while True:
        a_choice = input("请选择作者来源 (1/2/3): ").strip()
        if a_choice in {"1", "2", "3"}:
            break
        print("输入无效，请重新输入 1、2 或 3。")

    if a_choice == "1":
        author = suggested_author or current_author
    elif a_choice == "2":
        author = current_author
    else:
        author = input("请输入作者: ").strip()

    title = (title or "TITLE").strip()
    author = (author or "UNKNOWN").strip()
    return title, author


def choose_catalog_candidate(candidates: list[dict]) -> int | None:
    if not candidates:
        return None

    print("\n目录候选列表（按评分降序）：")
    for idx, item in enumerate(candidates, start=1):
        reason = item.get("score_reason", {})
        sample_titles = item.get("sample_titles", [])
        sample_text = " / ".join(sample_titles) if sample_titles else "(无)"
        print(
            f"{idx}. {item.get('selector', 'unknown')} | 章节 {item.get('chapter_count', 0)} | "
            f"总分 {item.get('score', 0):.1f} | "
            f"链接+{reason.get('base', 0):.1f} PID+{reason.get('pid_bonus', 0):.1f} "
            f"标题+{reason.get('title_bonus', 0):.1f} 结构+{reason.get('structure_bonus', 0):.1f} "
            f"数量+{reason.get('size_bonus', 0):.1f} 质量惩罚-{reason.get('quality_penalty', 0):.1f}"
        )
        print(f"   示例标题: {sample_text}")

    while True:
        raw = input("请选择目录候选序号（回车=自动最高分，q=放弃该帖子）: ").strip().lower()
        if raw == "":
            return 0
        if raw == "q":
            return None
        if raw.isdigit():
            i = int(raw)
            if 1 <= i <= len(candidates):
                return i - 1
        print("输入无效，请重新输入。")


def ask_use_existing_txt_for_epub(txt_path: Path) -> bool:
    print(f"\n检测到同名 TXT 文件：{txt_path}")
    while True:
        choice = input("是否直接使用该 TXT 转换为 EPUB（跳过重新抓取）？(y/n): ").strip().lower()
        if choice in {"y", "yes"}:
            return True
        if choice in {"n", "no"}:
            return False
        print("输入无效，请输入 y 或 n。")


def ask_retry_failed_chapters() -> bool:
    while True:
        choice = input("检测到失败章节，是否立即重试并回填 TXT？(y/n): ").strip().lower()
        if choice in {"y", "yes"}:
            return True
        if choice in {"n", "no"}:
            return False
        print("输入无效，请输入 y 或 n。")


def print_terminal_encoding_hint() -> None:
    print("\n[提示] 若终端中文乱码，请切换到 UTF-8 编码终端后重试。")
    print("Windows PowerShell 可先执行: chcp 65001")


def _catalog_stats(catalog_html: str) -> str:
    links = len(re.findall(r"<a\s+href=", catalog_html, flags=re.IGNORECASE))
    chars = len(catalog_html)
    return f"长度 {chars} 字符，检测到约 {links} 个章节链接"


def input_raw_html_catalog(current_value: str) -> str:
    print("\n请选择 raw_html_catalog 的录入方式：")
    print("1. 单行粘贴")
    print("2. 多行粘贴（单独一行输入 END 结束）")
    print("3. 从本地文件读取")
    print("4. 保持不变")

    while True:
        mode = input("请输入对应数字 (1/2/3/4): ").strip()

        if mode == "1":
            value = input("请粘贴 HTML（单行）: ").strip()
            print(f"✅ 已读取：{_catalog_stats(value)}")
            return value or current_value

        if mode == "2":
            print("开始粘贴，多行输入，最后单独输入 END 回车结束：")
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            value = "\n".join(lines).strip()
            if not value:
                print("⚠️ 未输入内容，保持不变。")
                return current_value
            print(f"✅ 已读取：{_catalog_stats(value)}")
            return value

        if mode == "3":
            file_path = input("请输入文件路径: ").strip()
            try:
                value = Path(file_path).read_text(encoding="utf-8")
            except Exception as exc:
                print(f"❌ 读取失败：{exc}")
                continue
            print(f"✅ 已读取文件：{_catalog_stats(value)}")
            return value

        if mode == "4":
            return current_value

        print("输入无效，请重新输入 1/2/3/4。")


def edit_config_interactive(config):
    print("\n=== 当前配置 ===")
    print(f"1. user_agent: {config.user_agent}")
    print(f"2. username: {config.username or '(未设置)'}")
    print(f"3. password: {'******' if config.password else '(未设置)'}")
    print(f"4. cookie: {'已设置' if config.cookie else '(未设置)'}")
    print(f"5. book_title: {config.book_title}")
    print(f"6. book_author: {config.book_author}")
    print(f"7. raw_html_catalog: {'已设置' if config.raw_html_catalog.strip() else '(未设置)'}")
    print("8. 返回")

    while True:
        choice = input("选择要修改的项 (1-8): ").strip()

        if choice == "1":
            config.user_agent = input("新的 user_agent: ").strip()
        elif choice == "2":
            config.username = input("新的 username: ").strip()
        elif choice == "3":
            config.password = getpass("新的 password(输入不回显): ").strip()
        elif choice == "4":
            config.cookie = input("新的 cookie: ").strip()
        elif choice == "5":
            config.book_title = input("新的 book_title: ").strip() or config.book_title
        elif choice == "6":
            config.book_author = input("新的 book_author: ").strip() or config.book_author
        elif choice == "7":
            config.raw_html_catalog = input_raw_html_catalog(config.raw_html_catalog)
        elif choice == "8":
            return config
        else:
            print("输入无效，请重新输入。")
            continue

        print("✅ 已更新。可继续修改或输入 8 返回。")
