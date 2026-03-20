# ================= 0. 环境配置区 =================
# 因为使用了 uv 进行版本管理所以基本不用担心

import time
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from curl_cffi import requests
from bs4 import BeautifulSoup
from ebooklib import epub

# ================= 1. 全局配置区 =================

# 请在此处填入你的 Cookie 和 User-Agent
# 如果不知道如何找出 Cookie 和 User-Agent 请参考 Readme

YOUR_COOKIE_STRING = ""
YOUR_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

# 书籍元数据配置(更方便你使用阅读器进行书籍分类)

BOOK_TITLE = "示例小说名称"
BOOK_AUTHOR = "示例作者"
OUTPUT_DIR = Path("./output")  # 输出文件夹（可以自定义）

# 延迟防封设置 (单位：秒)
CRAWL_DELAY = 3

# ================= 2. 目录数据 (RAW_HTML_CATALOG) =================
# 🌟【小白必读：如何获取并粘贴正确的 HTML 代码？】🌟
# 
# 步骤 1：在浏览器中打开你想爬取的小说目录页（通常是楼主发布的第一层楼）。
# 步骤 2：在网页的空白处【点击右键】，选择【查看网页源代码】（或者直接按快捷键 Ctrl+U）。
# 步骤 3：这时会弹出一个全是密密麻麻代码的新标签页。不要慌！按下 【Ctrl+F】 打开搜索框。
# 步骤 4：在搜索框里输入 【table】 ，基本上就能定位到目录开始的地方（或者你可以看一下哪里有很多的链接，那基本上就是目录了）。
# 步骤 5：用鼠标从第一章的 <a> 标签开始，一直往下拖动高亮，直到最后一章结束，复制。
# 步骤 6：把这段代码原封不动地粘贴到下方三个引号 """ 之间，完全覆盖掉现在的示例代码。
#
# 💡【匹配原理说明】：
# 我的代码里写了一个“正则表达式”，它并不关心代码里有多少个换行 <br>、加粗 <b>，或者是不是被放进了复杂的折叠框 <div> 里。
# 它只会寻找一个特定的格式：
# <a href="https://bbs.yamibo.com/xxxxx">章节标题</a>
#
# 只要包含上面这种 `<a>` 标签，爬虫就能把里面的【链接】和【章节标题】完美抠出来。

RAW_HTML_CATALOG = """
<a href="https://bbs.yamibo.com/forum.php?mod=redirect&amp;goto=findpost&amp;ptid=000000&amp;pid=11111111" target="_blank">第 1 章 示例章节</a><br />
<a href="https://bbs.yamibo.com/forum.php?mod=redirect&amp;goto=findpost&amp;ptid=000000&amp;pid=22222222" target="_blank">第 2 章 示例章节</a><br />
<div class="showcollapse_box"><div class="showcollapse_title">展开</div><div class="showcollapse_content">
<a href="https://bbs.yamibo.com/forum.php?mod=redirect&amp;goto=findpost&amp;ptid=000000&amp;pid=33333333" target="_blank">第 3 章 示例章节</a><br />
</div></div>
"""

# ================= 3. 核心功能类 =================

class YamiboScraper:
    def __init__(self, cookie: str, user_agent: str):
        self.session = requests.Session(impersonate="chrome110")
        self.session.headers.update({
            'User-Agent': user_agent,
            'Cookie': cookie,
            'Referer': 'https://bbs.yamibo.com/forum.php',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        })
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def parse_catalog(self, html_text: str) -> list:
        """解析目录 HTML，提取章节名和链接"""
        chapters = []
        pattern = re.compile(r'<a href="(https://bbs\.yamibo\.com/[^"]+)"[^>]*>(.*?)</a>')
        for url, title in pattern.findall(html_text):
            clean_title = title.strip()
            if clean_title == "目录": 
                continue
            chapters.append({
                "title": clean_title, 
                "url": url.replace('&amp;', '&'),
                "content": ""  # 预留存放正文的字段
            })
        return chapters

    def fetch_chapter_content(self, url: str) -> str:
        """抓取单章正文"""
        pid = parse_qs(urlparse(url).query).get('pid', [None])[0]
        if not pid: 
            return "【提取失败：无法找到 PID】"

        try:
            response = self.session.get(url, allow_redirects=True, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser', from_encoding='utf-8')
            page_title = soup.title.string if soup.title else ""
            
            if "提示信息" in page_title or "登录" in page_title:
                return "【权限失败：可能被识别为游客，请检查 Cookie】"

            target_id = f"postmessage_{pid}"
            content_td = soup.find('td', id=target_id)

            if content_td:
                # 移除最后编辑提示等无关标签
                for pstatus in content_td.find_all('i', class_='pstatus'):
                    pstatus.decompose()
                
                text = content_td.get_text(separator='\n', strip=True)
                # 清理多余空行
                text = re.sub(r'\n{3,}', '\n\n', text)
                return text
            else:
                return "【解析失败：成功进入帖子，但未找到楼主的正文，可能 pid 错误】"

        except Exception as e:
            return f"【请求出错：{e}】"

# ================= 4. 文件生成模块 =================

def save_to_txt(chapters: list, filename: Path):
    """将章节列表保存为 TXT"""
    print(f"\n开始生成 TXT 文件: {filename.name}...")
    with open(filename, "w", encoding="utf-8") as f:
        for chapter in chapters:
            f.write(f"==== {chapter['title']} ====\n\n")
            f.write(chapter['content'])
            f.write("\n\n\n")
    print(f"✅ TXT 文件生成完毕！")

def save_to_epub(chapters: list, filename: Path, title: str, author: str):
    """将章节列表打包为 EPUB"""
    print(f"\n开始制作 EPUB 电子书: {filename.name}...")
    
    book = epub.EpubBook()
    book.set_identifier(f'id_{int(time.time())}')
    book.set_title(title)
    book.set_language('zh-CN')
    book.add_author(author)

    epub_chapters = []
    
    for i, chapter_data in enumerate(chapters):
        chap_title = chapter_data['title']
        chap_content = chapter_data['content']
        
        chapter = epub.EpubHtml(title=chap_title, file_name=f'chap_{i}.xhtml', lang='zh-CN')
        
        # 转换为 HTML 段落
        html_content = f"<h1>{chap_title}</h1>\n"
        for line in chap_content.split('\n'):
            line = line.strip()
            if line:
                html_content += f"<p>{line}</p>\n"
                
        chapter.content = html_content
        book.add_item(chapter)
        epub_chapters.append(chapter)

    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + epub_chapters

    epub.write_epub(filename, book, {})
    print(f"✅ EPUB 电子书生成完毕！")

# ================= 5. 主程序与交互 =================

def main():
    print(f"=== 百合会小说抓取工具 (示例版) ===\n")
    print(f"当前目标: 《{BOOK_TITLE}》 作者: {BOOK_AUTHOR}")
    
    # 用户交互选项
    print("请选择需要生成的格式：")
    print("1. 仅生成 TXT 格式")
    print("2. 同时生成 TXT 和 EPUB 格式")
    choice = input("请输入选项数字 (1/2) [默认2]: ").strip()
    generate_epub = choice != '1'
    
    scraper = YamiboScraper(YOUR_COOKIE_STRING, YOUR_USER_AGENT)
    chapters = scraper.parse_catalog(RAW_HTML_CATALOG)
    
    if not chapters:
        print("未解析到任何章节链接，请检查 RAW_HTML_CATALOG 是否正确。")
        return

    print(f"\n成功解析到 {len(chapters)} 个章节链接！准备开始抓取...")
    
    # 测试部分
    # 实际运行时请移除切片以抓取全部
    # chapters = chapters[:2] 
    
    # 抓取流程
    for i, chapter in enumerate(chapters):
        print(f"[{i+1}/{len(chapters)}] 正在抓取: {chapter['title']} ...")
        content = scraper.fetch_chapter_content(chapter['url'])
        chapter['content'] = content  # 将内容存入字典
        
        print(f"    -> 抓取完成！预览: {content[:15]}...")
        time.sleep(CRAWL_DELAY)  # 严格遵守延时

    # 文件生成流程
    base_filename = f"{BOOK_TITLE}"
    txt_path = OUTPUT_DIR / f"{base_filename}.txt"
    epub_path = OUTPUT_DIR / f"{base_filename}.epub"

    save_to_txt(chapters, txt_path)
    
    if generate_epub:
        save_to_epub(chapters, epub_path, BOOK_TITLE, BOOK_AUTHOR)
        
    print(f"\n🎉 任务全部完成！文件已保存至 {OUTPUT_DIR.resolve()} 目录下。")

if __name__ == "__main__":
    main()