"""命令行交互模块（MVP 骨架）。"""

from getpass import getpass
from pathlib import Path
import re


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
