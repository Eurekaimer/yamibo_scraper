"""命令行交互模块（MVP 骨架）。"""


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
