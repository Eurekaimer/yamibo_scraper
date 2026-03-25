"""命令行交互模块（MVP 骨架）。"""

from getpass import getpass


def get_main_action() -> str:
    print("\n请选择操作：")
    print("1. 开始抓取")
    print("2. 修改配置")
    print("3. 退出")

    while True:
        action = input("请输入对应数字 (1/2/3): ").strip()
        if action in ["1", "2", "3"]:
            return action
        print("输入无效，请重新输入 1、2 或 3。")


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


def choose_thread(results: list[dict]) -> dict | None:
    if not results:
        print("未搜索到可用帖子。")
        return None

    print("\n搜索结果：")
    for idx, item in enumerate(results, start=1):
        print(f"{idx}. {item['title']}\n   {item['url']}")

    while True:
        raw = input("请选择目标帖子序号（输入 q 取消）: ").strip().lower()
        if raw == "q":
            return None
        if raw.isdigit():
            i = int(raw)
            if 1 <= i <= len(results):
                return results[i - 1]
        print("输入无效，请重新输入。")


def print_terminal_encoding_hint() -> None:
    print("\n[提示] 若终端中文乱码，请切换到 UTF-8 编码终端后重试。")
    print("Windows PowerShell 可先执行: chcp 65001")


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
            print("请输入新的 raw_html_catalog，单独一行输入 END 结束：")
            lines = []
            while True:
                line = input()
                if line == "END":
                    break
                lines.append(line)
            if lines:
                config.raw_html_catalog = "\n".join(lines)
        elif choice == "8":
            return config
        else:
            print("输入无效，请重新输入。")
            continue

        print("✅ 已更新。可继续修改或输入 8 返回。")
