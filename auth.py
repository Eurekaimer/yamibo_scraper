"""认证与会话初始化模块。"""

from getpass import getpass
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests

BASE_URL = "https://bbs.yamibo.com/"



def create_session(user_agent: str, cookie: Optional[str] = None) -> requests.Session:
    """初始化会话。"""

    session = requests.Session(impersonate="chrome110")
    headers = {
        "User-Agent": user_agent,
        "Referer": urljoin(BASE_URL, "forum.php"),
    }
    if cookie:
        headers["Cookie"] = cookie
    session.headers.update(headers)
    return session


def prompt_account_credentials() -> tuple[str, str]:
    """交互式输入账号密码。"""

    username = input("请输入百合会账号: ").strip()
    password = getpass("请输入百合会密码(输入不回显): ").strip()
    return username, password


def prompt_cookie() -> str:
    """交互式输入 Cookie（兜底模式）。"""

    return input("请输入浏览器抓取到的 Cookie: ").strip()


def _extract_login_form(session: requests.Session) -> tuple[str, str]:
    """获取登录提交地址和 formhash。"""

    login_page_url = urljoin(BASE_URL, "member.php?mod=logging&action=login")
    response = session.get(login_page_url, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    login_form = soup.find("form", id="loginform_Lz0") or soup.find("form", id="loginform")
    if not login_form:
        raise RuntimeError("未找到登录表单，请检查论坛页面结构是否变化")

    action = login_form.get("action", "")
    action_url = urljoin(BASE_URL, action)

    formhash_el = login_form.find("input", attrs={"name": "formhash"})
    if formhash_el and formhash_el.get("value"):
        return action_url, formhash_el["value"]

    formhash_match = re.search(r'formhash"\s+value="([a-zA-Z0-9]+)"', response.text)
    if formhash_match:
        return action_url, formhash_match.group(1)

    raise RuntimeError("未找到 formhash，无法提交登录")


def login_with_password(session: requests.Session, username: str, password: str) -> bool:
    """使用账号密码登录。返回是否登录成功。"""

    action_url, formhash = _extract_login_form(session)

    payload = {
        "formhash": formhash,
        "referer": urljoin(BASE_URL, "forum.php"),
        "loginfield": "username",
        "username": username,
        "password": password,
        "questionid": "0",
        "answer": "",
        "loginsubmit": "true",
    }

    response = session.post(action_url, data=payload, timeout=20)
    response.raise_for_status()

    profile_check = session.get(urljoin(BASE_URL, "home.php?mod=space"), timeout=20)
    if profile_check.status_code == 200 and username in profile_check.text:
        return True

    # 兜底：Discuz 常见登录 Cookie 命名
    cookie_names = {c.name.lower() for c in session.cookies}
    return any("auth" in c or "saltkey" in c for c in cookie_names)
