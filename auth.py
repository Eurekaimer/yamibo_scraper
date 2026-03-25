"""认证与会话初始化模块（MVP 骨架）。"""

from dataclasses import dataclass
from getpass import getpass
from typing import Optional

from curl_cffi import requests


@dataclass
class AuthConfig:
    """运行时认证配置。"""

    cookie: str
    user_agent: str
    username: Optional[str] = None
    password: Optional[str] = None


def create_session(auth: AuthConfig) -> requests.Session:
    """根据认证信息初始化会话。当前 MVP 仍以 Cookie 为主。"""

    session = requests.Session(impersonate="chrome110")
    session.headers.update(
        {
            "User-Agent": auth.user_agent,
            "Cookie": auth.cookie,
            "Referer": "https://bbs.yamibo.com/forum.php",
        }
    )
    return session


def prompt_account_credentials() -> tuple[str, str]:
    """为后续账号密码登录预留入口。"""

    username = input("请输入百合会账号: ").strip()
    password = getpass("请输入百合会密码(输入不回显): ").strip()
    return username, password
