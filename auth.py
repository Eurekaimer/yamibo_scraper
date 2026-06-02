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


def _is_logged_in(session: requests.Session, username: str) -> bool:
    """检测当前 session 是否已经登录。"""

    try:
        profile_check = session.get(urljoin(BASE_URL, "home.php?mod=space"), timeout=20)
        if profile_check.status_code == 200 and username and username in profile_check.text:
            return True
    except Exception:
        pass

    cookie_names = {c.name.lower() for c in session.cookies}
    return any("auth" in c or "saltkey" in c for c in cookie_names)


def _extract_login_form(session: requests.Session) -> tuple[str, Optional[str]]:
    """获取登录提交地址和 formhash（可能为空）。"""

    login_urls = [
        urljoin(BASE_URL, "member.php?mod=logging&action=login"),
        urljoin(BASE_URL, "forum.php"),
    ]

    for login_page_url in login_urls:
        response = session.get(login_page_url, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        forms = soup.find_all("form")

        for form in forms:
            action = form.get("action", "")
            action_lower = action.lower()
            if "logging" not in action_lower and "login" not in action_lower:
                continue

            action_url = urljoin(BASE_URL, action)
            formhash_el = form.find("input", attrs={"name": "formhash"})
            formhash = formhash_el.get("value") if formhash_el else None
            return action_url, formhash

        # 页面级 formhash 兜底
        action_url = urljoin(BASE_URL, "member.php?mod=logging&action=login&loginsubmit=yes")
        formhash_match = re.search(r'name="formhash"\s+value="([a-zA-Z0-9]+)"', response.text)
        if formhash_match:
            return action_url, formhash_match.group(1)

    # 最终兜底：直接提交通用登录地址
    return urljoin(BASE_URL, "member.php?mod=logging&action=login&loginsubmit=yes"), None


def login_with_password(session: requests.Session, username: str, password: str) -> bool:
    """使用账号密码登录。返回是否登录成功。"""

    if _is_logged_in(session, username):
        return True

    action_url, formhash = _extract_login_form(session)

    payload = {
        "referer": urljoin(BASE_URL, "forum.php"),
        "loginfield": "username",
        "username": username,
        "password": password,
        "questionid": "0",
        "answer": "",
        "loginsubmit": "true",
    }
    if formhash:
        payload["formhash"] = formhash

    # 依次尝试常见 Discuz 登录提交地址
    submit_urls = [
        action_url,
        urljoin(BASE_URL, "member.php?mod=logging&action=login&loginsubmit=yes"),
        urljoin(BASE_URL, "member.php?mod=logging&action=login&loginsubmit=yes&inajax=1"),
    ]

    for url in submit_urls:
        try:
            response = session.post(url, data=payload, timeout=20)
            response.raise_for_status()
        except Exception:
            continue

        if _is_logged_in(session, username):
            return True

        if "欢迎您回来" in response.text or "欢迎您" in response.text:
            return True

    return False
