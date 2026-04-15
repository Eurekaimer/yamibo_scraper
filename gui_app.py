"""简易图形界面（Tkinter）."""

from __future__ import annotations

import re
import time
import random
import sys
import os
import subprocess
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox
import platform
import ctypes

from auth import create_session, login_with_password
from config_store import load_config, save_config
from search import search_threads_by_keyword
from yamibo_scraper import (
    OUTPUT_DIR,
    SPEED_PROFILES,
    YamiboScraper,
    parse_chapters_from_txt,
    save_to_txt,
    save_to_epub,
    dump_failed_chapters,
    retry_failed_chapters,
    FAILED_MARKER_PREFIX,
    _sanitize_filename,
    _extract_suggested_meta_from_thread_title,
    _format_seconds,
)


class YamiboGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Yamibo Scraper GUI")
        self.root.geometry("1050x760")
        self.root.configure(bg="#fff5f5")

        self.config = load_config()
        self.session = None
        self.scraper = None

        self.search_results: list[dict] = []
        self.catalog_candidates: list[dict] = []
        self.current_chapters: list[dict] = []
        self.current_source_thread: dict | None = None
        self.preview_cache: dict[int, str] = {}
        self.latest_txt_path: Path | None = None
        self.latest_epub_path: Path | None = None
        self.latest_failed_file: Path | None = None

        self._build_vars()
        self._init_fonts()
        self._apply_theme()
        self._build_ui()
        self.refresh_txt_list()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _init_fonts(self):
        self._try_load_bundled_fonts()
        families = set(tkfont.families(self.root))
        preferred = [
            "LXGW WenKai",
            "霞鹜文楷",
            "LXGW WenKai Mono",
            "Microsoft YaHei UI",
            "Microsoft YaHei",
        ]
        self.font_family = next((f for f in preferred if f in families), "Microsoft YaHei UI")
        self.base_font = (self.font_family, 10)
        self.title_font = (self.font_family, 18, "bold")
        self.section_font = (self.font_family, 11, "bold")
        self.mono_font = (self.font_family, 10)
        self.root.option_add("*Font", self.base_font)

    def _try_load_bundled_fonts(self):
        """尝试加载项目内置字体，便于打包后即用。"""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base = Path(getattr(sys, "_MEIPASS"))
        else:
            base = Path(__file__).parent
        font_dir = base / "assets" / "fonts"
        if not font_dir.exists():
            return

        ttf_files = list(font_dir.glob("*.ttf")) + list(font_dir.glob("*.otf"))
        if not ttf_files:
            return

        # Windows: 进程私有加载，不污染系统字体安装
        if platform.system().lower().startswith("win"):
            FR_PRIVATE = 0x10
            for f in ttf_files:
                try:
                    ctypes.windll.gdi32.AddFontResourceExW(str(f), FR_PRIVATE, 0)
                except Exception:
                    pass

    def _apply_theme(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background="#fff5f5")
        style.configure("Card.TLabelframe", background="#fff5f5", foreground="#7f1d1d")
        style.configure("Card.TLabelframe.Label", background="#fff5f5", foreground="#7f1d1d", font=self.section_font)
        style.configure("TLabel", background="#fff5f5", foreground="#7f1d1d", font=self.base_font)
        style.configure(
            "Primary.TButton",
            background="#dc2626",
            foreground="#ffffff",
            font=self.base_font,
            padding=(10, 6),
            borderwidth=0,
        )
        style.map("Primary.TButton", background=[("active", "#ef4444")], foreground=[("active", "#ffffff")])
        style.configure(
            "Ghost.TButton",
            background="#fee2e2",
            foreground="#7f1d1d",
            font=self.base_font,
            padding=(10, 6),
            borderwidth=0,
        )
        style.map("Ghost.TButton", background=[("active", "#fecaca")])
        style.configure("TEntry", fieldbackground="#fff1f2", foreground="#7f1d1d")
        style.configure("TCombobox", fieldbackground="#fff1f2", foreground="#7f1d1d")
        style.configure("TNotebook", background="#fff5f5", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8), font=self.base_font)

    def _build_vars(self):
        self.user_agent_var = tk.StringVar(value=self.config.user_agent)
        self.username_var = tk.StringVar(value=self.config.username)
        self.password_var = tk.StringVar(value=self.config.password)
        self.cookie_var = tk.StringVar(value=self.config.cookie)
        self.remember_auth_var = tk.BooleanVar(value=bool(getattr(self.config, "remember_auth", True)))
        self.book_title_var = tk.StringVar(value=self.config.book_title if self.config.book_title != "TITLE" else "")
        self.book_author_var = tk.StringVar(value=self.config.book_author if self.config.book_author != "AUTHOR" else "")
        self.auth_mode_var = tk.StringVar(value="account")
        self.source_mode_var = tk.StringVar(value="search")
        self.keyword_var = tk.StringVar()
        self.forum_scope_var = tk.StringVar(value="49,55")
        self.save_choice_var = tk.StringVar(value="3")
        self.speed_mode_var = tk.StringVar(value="fast")
        self.preview_count_var = tk.StringVar(value="2")
        self.convert_title_var = tk.StringVar()
        self.convert_author_var = tk.StringVar(value="UNKNOWN")

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)

        self.scrape_tab = ttk.Frame(notebook)
        self.convert_tab = ttk.Frame(notebook)
        notebook.add(self.scrape_tab, text="抓取")
        notebook.add(self.convert_tab, text="TXT 转 EPUB")

        self._build_scrape_tab()
        self._build_convert_tab()

    def _build_scrape_tab(self):
        title = ttk.Label(self.scrape_tab, text="Yamibo 小说抓取", font=self.title_font)
        title.pack(anchor="w", padx=10, pady=(8, 0))

        top = ttk.LabelFrame(self.scrape_tab, text="基础配置", style="Card.TLabelframe")
        top.pack(fill="x", padx=10, pady=8)

        row1 = ttk.Frame(top)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="User-Agent").pack(side="left")
        ttk.Entry(row1, textvariable=self.user_agent_var).pack(side="left", fill="x", expand=True, padx=6)

        row2 = ttk.Frame(top)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="账号").pack(side="left")
        ttk.Entry(row2, textvariable=self.username_var, width=20).pack(side="left", padx=6)
        ttk.Label(row2, text="密码").pack(side="left")
        ttk.Entry(row2, textvariable=self.password_var, width=20, show="*").pack(side="left", padx=6)
        ttk.Label(row2, text="Cookie").pack(side="left")
        ttk.Entry(row2, textvariable=self.cookie_var).pack(side="left", fill="x", expand=True, padx=6)

        row3 = ttk.Frame(top)
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="标题").pack(side="left")
        ttk.Entry(row3, textvariable=self.book_title_var, width=36).pack(side="left", padx=6)
        ttk.Label(row3, text="作者").pack(side="left")
        ttk.Entry(row3, textvariable=self.book_author_var, width=22).pack(side="left", padx=6)
        ttk.Button(row3, text="保存配置", command=self.save_config_from_ui, style="Primary.TButton").pack(side="left", padx=6)
        ttk.Button(row3, text="重建会话", command=self.rebuild_session, style="Ghost.TButton").pack(side="left", padx=2)

        option_row = ttk.Frame(top)
        option_row.pack(fill="x", pady=6)
        ttk.Label(option_row, text="登录").pack(side="left")
        ttk.Radiobutton(
            option_row,
            text="账号密码（推荐）",
            variable=self.auth_mode_var,
            value="account",
            command=self._on_auth_mode_changed,
        ).pack(side="left")
        ttk.Radiobutton(
            option_row,
            text="Cookie（兼容）",
            variable=self.auth_mode_var,
            value="cookie",
            command=self._on_auth_mode_changed,
        ).pack(side="left")
        ttk.Checkbutton(
            option_row,
            text="记住账号/密码",
            variable=self.remember_auth_var,
            onvalue=True,
            offvalue=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(option_row, text="来源").pack(side="left", padx=(16, 0))
        ttk.Radiobutton(option_row, text="搜索", variable=self.source_mode_var, value="search").pack(side="left")
        ttk.Radiobutton(option_row, text="raw_html", variable=self.source_mode_var, value="raw").pack(side="left")
        ttk.Label(option_row, text="输出").pack(side="left", padx=(16, 0))
        ttk.Combobox(
            option_row,
            textvariable=self.save_choice_var,
            state="readonly",
            values=["1", "2", "3"],
            width=4,
        ).pack(side="left", padx=4)
        ttk.Label(option_row, text="速度").pack(side="left", padx=(12, 0))
        ttk.Combobox(
            option_row,
            textvariable=self.speed_mode_var,
            state="readonly",
            values=["fast", "balanced", "gentle"],
            width=10,
        ).pack(side="left", padx=4)
        ttk.Label(option_row, text="预览章数").pack(side="left", padx=(12, 0))
        ttk.Entry(option_row, textvariable=self.preview_count_var, width=5).pack(side="left", padx=4)

        middle = ttk.Panedwindow(self.scrape_tab, orient=tk.HORIZONTAL)
        middle.pack(fill="both", expand=True, padx=10, pady=8)

        left = ttk.LabelFrame(middle, text="搜索与目录", style="Card.TLabelframe")
        right = ttk.LabelFrame(middle, text="HTML 与日志", style="Card.TLabelframe")
        middle.add(left, weight=1)
        middle.add(right, weight=1)

        search_bar = ttk.Frame(left)
        search_bar.pack(fill="x", pady=2)
        ttk.Label(search_bar, text="关键词").pack(side="left")
        ttk.Entry(search_bar, textvariable=self.keyword_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(search_bar, text="分区").pack(side="left")
        ttk.Combobox(
            search_bar,
            textvariable=self.forum_scope_var,
            state="readonly",
            values=["55", "49", "49,55"],
            width=8,
        ).pack(side="left", padx=4)
        ttk.Button(search_bar, text="搜索帖子", command=self.search_threads, style="Primary.TButton").pack(side="left", padx=4)

        ttk.Label(left, text="搜索结果").pack(anchor="w")
        self.result_list = tk.Listbox(
            left,
            height=12,
            bg="#fff7f7",
            fg="#7f1d1d",
            selectbackground="#fecaca",
            font=self.base_font,
            relief="flat",
        )
        self.result_list.pack(fill="both", expand=True, pady=4)

        candidate_bar = ttk.Frame(left)
        candidate_bar.pack(fill="x", pady=2)
        ttk.Button(candidate_bar, text="提取目录候选", command=self.load_candidates, style="Primary.TButton").pack(side="left")
        ttk.Button(candidate_bar, text="加载 raw_html 章节", command=self.load_raw_catalog, style="Ghost.TButton").pack(side="left", padx=6)
        ttk.Button(candidate_bar, text="预览章节", command=self.preview_chapters, style="Ghost.TButton").pack(side="left")

        ttk.Label(left, text="目录候选").pack(anchor="w")
        self.candidate_list = tk.Listbox(
            left,
            height=10,
            bg="#fff7f7",
            fg="#7f1d1d",
            selectbackground="#fecaca",
            font=self.base_font,
            relief="flat",
        )
        self.candidate_list.pack(fill="both", expand=True, pady=4)

        ttk.Label(right, text="raw_html_catalog（仅 raw 模式使用）").pack(anchor="w")
        self.raw_text = tk.Text(
            right,
            height=15,
            wrap="word",
            bg="#fff7f7",
            fg="#7f1d1d",
            insertbackground="#7f1d1d",
            font=self.base_font,
            relief="flat",
        )
        self.raw_text.pack(fill="x", pady=4)
        if self.config.raw_html_catalog and self.config.raw_html_catalog != " HTML ":
            self.raw_text.insert("1.0", self.config.raw_html_catalog)

        ttk.Label(right, text="日志/预览").pack(anchor="w")
        self.log_text = tk.Text(
            right,
            wrap="word",
            bg="#fff7f7",
            fg="#7f1d1d",
            insertbackground="#7f1d1d",
            font=self.mono_font,
            relief="flat",
        )
        self.log_text.pack(fill="both", expand=True, pady=4)

        run_bar = ttk.Frame(self.scrape_tab)
        run_bar.pack(fill="x", padx=10, pady=6)
        ttk.Button(run_bar, text="开始抓取", command=self.start_crawl, style="Primary.TButton").pack(side="left")
        ttk.Button(run_bar, text="仅回填失败章节", command=self.retry_failed_for_latest, style="Ghost.TButton").pack(side="left", padx=6)
        ttk.Button(run_bar, text="打开最新文件", command=self.open_latest_output_file, style="Ghost.TButton").pack(side="left", padx=6)
        ttk.Button(run_bar, text="清空日志", command=lambda: self.log_text.delete("1.0", "end"), style="Ghost.TButton").pack(side="left", padx=6)

        self.status_var = tk.StringVar(value="状态：待命（建议先输入账号密码并保存配置）")
        ttk.Label(self.scrape_tab, textvariable=self.status_var).pack(anchor="w", padx=12, pady=(0, 8))
        self._on_auth_mode_changed()

    def _build_convert_tab(self):
        top = ttk.Frame(self.convert_tab)
        top.pack(fill="both", expand=True, padx=10, pady=10)

        bar = ttk.Frame(top)
        bar.pack(fill="x")
        ttk.Button(bar, text="刷新 output 列表", command=self.refresh_txt_list, style="Ghost.TButton").pack(side="left")
        ttk.Label(bar, text="标题").pack(side="left", padx=(12, 2))
        ttk.Entry(bar, textvariable=self.convert_title_var, width=30).pack(side="left")
        ttk.Label(bar, text="作者").pack(side="left", padx=(12, 2))
        ttk.Entry(bar, textvariable=self.convert_author_var, width=20).pack(side="left")
        ttk.Button(bar, text="转换选中 TXT -> EPUB", command=self.convert_selected_txt, style="Primary.TButton").pack(side="left", padx=8)

        self.txt_list = tk.Listbox(top, bg="#fff7f7", fg="#7f1d1d", selectbackground="#fecaca")
        self.txt_list.pack(fill="both", expand=True, pady=8)

    def _on_auth_mode_changed(self):
        mode = self.auth_mode_var.get()
        if mode == "account":
            self.status_var.set("状态：账号密码登录模式（推荐）")
        else:
            self.status_var.set("状态：Cookie 登录模式（兼容）")

    def log(self, text: str):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.status_var.set(f"状态：{text[:50]}")
        self.root.update_idletasks()

    def rebuild_session(self):
        self.session = None
        self.scraper = None
        self.log("ℹ️ 会话已重置。")

    def _apply_config_from_ui(self):
        self.config.user_agent = self.user_agent_var.get().strip() or self.config.user_agent
        self.config.book_title = self.book_title_var.get().strip() or "TITLE"
        self.config.book_author = self.book_author_var.get().strip() or "AUTHOR"
        self.config.remember_auth = bool(self.remember_auth_var.get())

        raw = self.raw_text.get("1.0", "end").strip()
        self.config.raw_html_catalog = raw if raw else " HTML "

        if self.config.remember_auth:
            self.config.username = self.username_var.get().strip()
            self.config.password = self.password_var.get().strip()
            self.config.cookie = self.cookie_var.get().strip()
        else:
            self.config.username = ""
            self.config.password = ""
            self.config.cookie = ""

    def _auto_save_config(self):
        self._apply_config_from_ui()
        save_config(self.config)

    def save_config_from_ui(self):
        self._auto_save_config()
        self.rebuild_session()
        messagebox.showinfo("提示", "配置已保存。")

    def on_close(self):
        try:
            self._auto_save_config()
        except Exception:
            pass
        self.root.destroy()

    def _build_session(self, auth_required: bool):
        mode = self.auth_mode_var.get()
        ua = self.user_agent_var.get().strip() or self.config.user_agent

        if mode == "account":
            username = self.username_var.get().strip()
            password = self.password_var.get().strip()
            if not username or not password:
                if auth_required:
                    raise ValueError("账号模式需要填写用户名和密码。")
                return create_session(user_agent=ua)
            session = create_session(user_agent=ua)
            ok = login_with_password(session, username, password)
            if not ok:
                if auth_required:
                    raise RuntimeError("账号密码登录失败。")
                return create_session(user_agent=ua)
            return session

        cookie = self.cookie_var.get().strip()
        if not cookie:
            if auth_required:
                raise ValueError("Cookie 模式需要填写 Cookie。")
            return create_session(user_agent=ua)
        return create_session(user_agent=ua, cookie=cookie)

    def _ensure_scraper(self, auth_required: bool, force_reset: bool = False):
        if force_reset:
            self.session = None
            self.scraper = None
        if self.session is None:
            self.session = self._build_session(auth_required=auth_required)
            self.scraper = YamiboScraper(self.session)
            self._auto_save_config()
            self.log("✅ 会话已建立。")

    def _parse_forum_scope(self) -> list[int]:
        raw = self.forum_scope_var.get().strip()
        if raw == "55":
            return [55]
        if raw == "49":
            return [49]
        return [49, 55]

    def search_threads(self):
        try:
            self._ensure_scraper(auth_required=True)
            keyword = self.keyword_var.get().strip()
            if not keyword:
                raise ValueError("请输入关键词。")
            results = search_threads_by_keyword(
                self.session,
                keyword,
                forum_ids=self._parse_forum_scope(),
                limit=25,
            )
            self.search_results = results
            self.result_list.delete(0, "end")
            for item in results:
                self.result_list.insert(
                    "end",
                    f"[{item.get('forum_name','未知')}] {item['title']} | 回复:{item.get('replies',0)} 查看:{item.get('views',0)} 热度:{int(item.get('popularity_score',0))}",
                )
            self.log(f"🔎 搜索完成：{len(results)} 条。")
        except Exception as exc:
            messagebox.showerror("错误", str(exc))

    def load_candidates(self):
        try:
            self._ensure_scraper(auth_required=True)
            idx = self.result_list.curselection()
            if not idx:
                raise ValueError("请先在搜索结果里选择一个帖子。")
            item = self.search_results[idx[0]]
            self.current_source_thread = item
            candidates = self.scraper.extract_catalog_candidates_from_thread(item["url"])
            if not candidates:
                raise RuntimeError("未提取到目录候选。")
            self.catalog_candidates = candidates
            self.candidate_list.delete(0, "end")
            for c in candidates:
                self.candidate_list.insert(
                    "end",
                    f"{c['selector']} | 章节:{c['chapter_count']} | 评分:{c['score']:.1f}",
                )
            if candidates:
                self.candidate_list.selection_clear(0, "end")
                self.candidate_list.selection_set(0)
                self.candidate_list.activate(0)
            self.log(f"📚 已提取目录候选：{len(candidates)} 个。")
        except Exception as exc:
            messagebox.showerror("错误", str(exc))

    def load_raw_catalog(self):
        try:
            self._ensure_scraper(auth_required=False)
            raw_html = self.raw_text.get("1.0", "end").strip()
            if not raw_html:
                raise ValueError("raw_html_catalog 为空。")
            self.current_chapters = self.scraper.parse_catalog(raw_html)
            self.current_source_thread = None
            if not self.current_chapters:
                raise RuntimeError("raw_html 未解析到章节。")
            self.log(f"✅ raw_html 解析成功：{len(self.current_chapters)} 章。")
        except Exception as exc:
            messagebox.showerror("错误", str(exc))

    def _resolve_chapters_from_ui(self) -> list[dict]:
        if self.source_mode_var.get() == "raw":
            if not self.current_chapters:
                self.load_raw_catalog()
            return self.current_chapters

        if not self.catalog_candidates:
            self.load_candidates()
        idx = self.candidate_list.curselection()
        chosen = self.catalog_candidates[idx[0]] if idx else self.catalog_candidates[0]
        self.current_chapters = chosen["chapters"]
        self.log(
            f"✅ 使用候选：{chosen['selector']}（{chosen['chapter_count']} 章，评分 {chosen['score']:.1f}）"
        )
        return self.current_chapters

    def preview_chapters(self):
        try:
            self._ensure_scraper(auth_required=True)
            chapters = self._resolve_chapters_from_ui()
            self.preview_cache = {}
            try:
                requested = max(1, int(self.preview_count_var.get().strip()))
            except Exception:
                requested = 2
            count = min(requested, len(chapters))
            self.log(f"👀 开始预览前 {count} 章...")
            for i in range(count):
                c = chapters[i]
                content = self.scraper.fetch_chapter_content(c["url"])
                self.preview_cache[i] = content
                snippet = re.sub(r"\s+", " ", content).strip()[:120]
                self.log(f"[预览 {i + 1}] {c['title']}: {snippet}...")
            self.log("✅ 预览完成。")
        except Exception as exc:
            messagebox.showerror("错误", str(exc))

    def _resolve_output_meta(self):
        title = self.book_title_var.get().strip()
        author = self.book_author_var.get().strip()
        if not title and self.current_source_thread:
            s_title, s_author = _extract_suggested_meta_from_thread_title(self.current_source_thread["title"])
            title = s_title
            if not author:
                author = s_author
        title = title or "TITLE"
        author = author or "UNKNOWN"
        return title, author

    def _open_path_in_system(self, path: Path):
        if not path or not path.exists():
            messagebox.showwarning("提示", "目标文件不存在，无法打开。")
            return
        try:
            if platform.system().lower().startswith("win"):
                os.startfile(str(path))
            elif platform.system().lower() == "darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as exc:
            messagebox.showerror("错误", f"打开文件失败：{exc}")

    def open_latest_output_file(self):
        target = None
        if self.latest_txt_path and self.latest_txt_path.exists():
            target = self.latest_txt_path
        elif self.latest_epub_path and self.latest_epub_path.exists():
            target = self.latest_epub_path

        if not target:
            messagebox.showwarning("提示", "当前没有可打开的抓取结果文件。")
            return
        self._open_path_in_system(target)

    def _retry_failed_and_refill(
        self,
        txt_path: Path,
        failed_file: Path,
        epub_path: Path | None,
        title: str,
        author: str,
    ) -> list[dict]:
        if not txt_path.exists():
            raise RuntimeError("未找到 TXT 文件，无法执行失败回填。")
        if not failed_file.exists():
            raise RuntimeError("未找到失败记录文件，无法执行失败回填。")

        self.log("🔁 开始仅重试失败章节并回填...")
        still_failed = retry_failed_chapters(self.scraper, failed_file, txt_path)
        if still_failed:
            self.latest_failed_file = failed_file
            self.log(f"⚠️ 回填后仍有 {len(still_failed)} 章失败，已保留失败记录。")
            for item in still_failed:
                self.log(f"   - {item.get('title', '未知章节')}")
        else:
            self.latest_failed_file = None
            self.log("✅ 失败章节已全部回填完成。")

        if epub_path and epub_path.exists():
            updated_chapters = parse_chapters_from_txt(txt_path)
            if updated_chapters:
                save_to_epub(updated_chapters, epub_path, title, author)
                self.log("📘 EPUB 已按回填结果重新生成。")
            else:
                self.log("⚠️ TXT 回填后解析失败，EPUB 未重建。")

        self.refresh_txt_list()
        return still_failed

    def retry_failed_for_latest(self):
        try:
            self._ensure_scraper(auth_required=True)
            failed_file = self.latest_failed_file
            txt_path = self.latest_txt_path
            if not failed_file or not failed_file.exists():
                raise RuntimeError("当前没有可回填的失败章节记录。")
            if not txt_path or not txt_path.exists():
                raise RuntimeError("当前没有可回填的 TXT 文件。")

            title, author = self._resolve_output_meta()
            epub_path = self.latest_epub_path if (self.latest_epub_path and self.latest_epub_path.exists()) else None
            still_failed = self._retry_failed_and_refill(
                txt_path=txt_path,
                failed_file=failed_file,
                epub_path=epub_path,
                title=title,
                author=author,
            )
            if still_failed:
                messagebox.showwarning("回填完成", f"仍有 {len(still_failed)} 章失败，已保留失败记录。")
            else:
                messagebox.showinfo("回填完成", "失败章节已全部回填。")
        except Exception as exc:
            messagebox.showerror("错误", str(exc))

    def start_crawl(self):
        try:
            self._auto_save_config()
            self._ensure_scraper(auth_required=True, force_reset=True)
            chapters = self._resolve_chapters_from_ui()
            if not chapters:
                raise RuntimeError("没有可抓取章节。")

            title, author = self._resolve_output_meta()
            safe_name = _sanitize_filename(title)
            txt_path = OUTPUT_DIR / f"{safe_name}.txt"
            epub_path = OUTPUT_DIR / f"{safe_name}.epub"
            self.latest_txt_path = txt_path if self.save_choice_var.get().strip() in {"1", "3"} else None
            self.latest_epub_path = epub_path if self.save_choice_var.get().strip() in {"2", "3"} else None
            self.latest_failed_file = None

            speed_mode = self.speed_mode_var.get().strip() or "fast"
            profile = SPEED_PROFILES.get(speed_mode, SPEED_PROFILES["fast"])
            save_choice = self.save_choice_var.get().strip() or "3"

            self.log(f"🚀 开始抓取，共 {len(chapters)} 章，速度档：{profile['label']}")
            failed_records = []
            start_at = time.time()

            for i, ch in enumerate(chapters):
                if i in self.preview_cache:
                    content = self.preview_cache[i]
                else:
                    content = self.scraper.fetch_chapter_content(ch["url"])

                if content.startswith("【最终失败"):
                    marker = f"{FAILED_MARKER_PREFIX}{i + 1}#"
                    failed_records.append(
                        {"index": i, "title": ch["title"], "url": ch["url"], "marker": marker}
                    )
                    content = marker

                ch["content"] = content
                done = i + 1
                elapsed = time.time() - start_at
                eta = (elapsed / done) * (len(chapters) - done)
                self.log(f"[{done}/{len(chapters)}] {ch['title']} | 预计剩余时间: {_format_seconds(eta)}")

                if done < len(chapters):
                    time.sleep(random.uniform(profile["delay_min"], profile["delay_max"]))

            if save_choice in {"1", "3"}:
                save_to_txt(chapters, txt_path)
                self.latest_txt_path = txt_path
            if save_choice in {"2", "3"}:
                save_to_epub(chapters, epub_path, title, author)
                self.latest_epub_path = epub_path

            if failed_records:
                failed_file = OUTPUT_DIR / f"{safe_name}.failed_chapters.json"
                dump_failed_chapters(failed_records, failed_file)
                self.latest_failed_file = failed_file
                self.log(f"⚠️ 完成，但有 {len(failed_records)} 章失败。")
                for item in failed_records:
                    self.log(f"   - {item['title']}")

                # 只导出 EPUB 时，也额外保留 TXT 以便失败回填。
                if save_choice == "2" and (not txt_path.exists()):
                    save_to_txt(chapters, txt_path)
                    self.latest_txt_path = txt_path
                    self.log("📝 已额外生成 TXT，用于失败章节回填。")

                if self.latest_txt_path and messagebox.askyesno(
                    "失败章节回填",
                    f"检测到 {len(failed_records)} 章失败，是否立即仅重试失败章节并回填？",
                ):
                    still_failed = self._retry_failed_and_refill(
                        txt_path=self.latest_txt_path,
                        failed_file=failed_file,
                        epub_path=self.latest_epub_path if save_choice in {"2", "3"} else None,
                        title=title,
                        author=author,
                    )
                    if still_failed:
                        self.log(f"⚠️ 回填后仍有 {len(still_failed)} 章失败。")
                    else:
                        self.log("✅ 失败章节已全部回填。")
            else:
                self.log("✅ 文件生成完成，全部章节抓取成功。")

            self.refresh_txt_list()
            preferred = None
            if self.latest_txt_path and self.latest_txt_path.exists():
                preferred = self.latest_txt_path
            elif self.latest_epub_path and self.latest_epub_path.exists():
                preferred = self.latest_epub_path

            if preferred and messagebox.askyesno(
                "抓取完成",
                f"任务已完成，是否立即打开文件？\n{preferred.name}",
            ):
                self._open_path_in_system(preferred)
            else:
                messagebox.showinfo("完成", "抓取任务已完成。")
        except Exception as exc:
            messagebox.showerror("错误", str(exc))

    def refresh_txt_list(self):
        self.txt_list.delete(0, "end")
        for p in sorted(OUTPUT_DIR.glob("*.txt")):
            self.txt_list.insert("end", p.name)

    def convert_selected_txt(self):
        idx = self.txt_list.curselection()
        if not idx:
            messagebox.showwarning("提示", "请先选择一个 TXT 文件。")
            return

        txt_name = self.txt_list.get(idx[0])
        txt_path = OUTPUT_DIR / txt_name
        chapters = parse_chapters_from_txt(txt_path)
        if not chapters:
            messagebox.showerror("错误", "TXT 解析失败，无法转换。")
            return

        title = self.convert_title_var.get().strip() or txt_path.stem
        author = self.convert_author_var.get().strip() or "UNKNOWN"
        epub_path = txt_path.with_suffix(".epub")
        save_to_epub(chapters, epub_path, title, author)
        messagebox.showinfo("完成", f"已转换为 {epub_path.name}")


def launch_gui():
    if platform.system().lower().startswith("win"):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    root = tk.Tk()
    YamiboGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
