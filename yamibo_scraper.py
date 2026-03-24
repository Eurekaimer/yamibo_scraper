# ================= 0. 环境配置区 =================

import time
import re
import random
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from curl_cffi import requests
from bs4 import BeautifulSoup
from ebooklib import epub
from opencc import OpenCC

# ================= 1. 全局配置区 =================

YOUR_COOKIE_STRING = "Your Cookie"
YOUR_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36" 

BOOK_TITLE = "TITLE"
BOOK_AUTHOR = "AUTHOR"
OUTPUT_DIR = Path("./output")

CRAWL_DELAY = 3
MAX_RETRIES = 5
ENABLE_SIMPLIFIED = True

cc = OpenCC('t2s')  # 繁体转简体

# ================= 2. 目录 =================

RAW_HTML_CATALOG = """ HTML """

# ================= 3. 核心类 =================

class YamiboScraper:
    def __init__(self, cookie: str, user_agent: str):
        self.session = requests.Session(impersonate="chrome110")
        self.session.headers.update({
            'User-Agent': user_agent,
            'Cookie': cookie,
            'Referer': 'https://bbs.yamibo.com/forum.php'
        })
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def parse_catalog(self, html_text: str) -> list:
        chapters = []
        pattern = re.compile(r'<a href="(https://bbs\.yamibo\.com/[^"]+)"[^>]*>(.*?)</a>')
        
        for url, title in pattern.findall(html_text):
            title = re.sub('<.*?>', '', title).strip()  # 去掉 <strong>
            chapters.append({
                "title": title,
                "url": url.replace('&amp;', '&'),
                "content": ""
            })
        return chapters

    def fetch_chapter_content(self, url: str) -> str:
        pid = parse_qs(urlparse(url).query).get('pid', [None])[0]
        if not pid:
            return "【PID失败】"

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'html.parser')
                target_id = f"postmessage_{pid}"
                content_td = soup.find('td', id=target_id)

                if not content_td:
                    raise ValueError("正文未找到")

                for pstatus in content_td.find_all('i', class_='pstatus'):
                    pstatus.decompose()

                text = content_td.get_text(separator='\n', strip=True)

                if ENABLE_SIMPLIFIED:
                    text = cc.convert(text)

                text = re.sub(r'\n{3,}', '\n\n', text)

                return text

            except Exception as e:
                print(f"    ⚠️ 第{attempt+1}次失败: {e}")
                
                if attempt == MAX_RETRIES - 1:
                    return f"【最终失败：{e}】"
                
                sleep_time = 2 ** attempt
                time.sleep(sleep_time)

# ================= 4. 文件输出 =================

def save_to_txt(chapters, filename):
    with open(filename, "w", encoding="utf-8") as f:
        for c in chapters:
            f.write(f"==== {c['title']} ====\n\n{c['content']}\n\n\n")
    print(f"📄 TXT 文件已保存至: {filename}")

def save_to_epub(chapters, filename, title, author):
    book = epub.EpubBook()
    book.set_title(title)
    book.add_author(author)

    epub_chapters = []

    for i, c in enumerate(chapters):
        chapter = epub.EpubHtml(title=c['title'], file_name=f'chap_{i}.xhtml')
        
        html = f"<h1>{c['title']}</h1>"
        for line in c['content'].split('\n'):
            if line.strip():
                html += f"<p>{line}</p>"

        chapter.content = html
        book.add_item(chapter)
        epub_chapters.append(chapter)

    # 1. 设置内部的 TOC（目录）结构
    book.toc = tuple(epub_chapters)
    
    # 2. ⚠️ 关键修复：显式添加 NCX 和 Nav 导航项，阅读器才能解析出目录侧边栏
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # 3. 设置阅读顺序 (spine)，'nav' 表示把目录放在最前面
    book.spine = ['nav'] + epub_chapters

    # 生成 EPUB 文件
    epub.write_epub(filename, book, {} )
    print(f"📚 EPUB 文件已保存至: {filename}")

# ================= 5. 主程序 =================

def get_save_choice():
    print("="*30)
    print("请选择要保存的文件格式：")
    print("1. 只保存 TXT 格式")
    print("2. 只保存 EPUB 格式")
    print("3. 同时保存 TXT 和 EPUB")
    print("="*30)
    
    while True:
        choice = input("请输入对应数字 (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            return choice
        print("输入无效，请重新输入 1、2 或 3。")

def main():
    # 程序一开始先询问保存格式
    save_choice = get_save_choice()
    print("\n配置完成，开始抓取目录...")

    scraper = YamiboScraper(YOUR_COOKIE_STRING, YOUR_USER_AGENT)
    chapters = scraper.parse_catalog(RAW_HTML_CATALOG)

    if not chapters:
        print("未解析到任何章节，请检查 RAW_HTML_CATALOG 内容。")
        return

    failed = []

    for i, ch in enumerate(chapters):
        content = scraper.fetch_chapter_content(ch['url'])

        if content.startswith("【最终失败"):
            failed.append(ch['title'])

        ch['content'] = content

        # 生成 20 字预览用于控制台显示，去除所有空白字符以保证连贯
        clean_text = re.sub(r'\s+', '', content)
        preview = clean_text[:20] + "..." if len(clean_text) > 20 else clean_text

        print(f"[{i+1}/{len(chapters)}] {ch['title']} | 预览: {preview}")

        time.sleep(CRAWL_DELAY + random.uniform(0, 2))

    print("\n抓取结束，开始生成文件...")

    # 根据用户的输入执行对应的保存操作
    if save_choice in ['1', '3']:
        save_to_txt(chapters, OUTPUT_DIR / f"{BOOK_TITLE}.txt")
    
    if save_choice in ['2', '3']:
        save_to_epub(chapters, OUTPUT_DIR / f"{BOOK_TITLE}.epub", BOOK_TITLE, BOOK_AUTHOR)

    if failed:
        print(f"\n⚠️ 有 {len(failed)} 个章节抓取失败:")
        for f in failed:
            print(f" - {f}")
    else:
        print("\n🎉 全部操作完美完成！")

if __name__ == "__main__":
    main()