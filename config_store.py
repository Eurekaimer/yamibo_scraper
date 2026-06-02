"""配置读写模块。"""

from dataclasses import asdict, dataclass
import json
from pathlib import Path

CONFIG_PATH = Path("./yamibo_config.json")


@dataclass
class AppConfig:
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    cookie: str = ""
    username: str = ""
    password: str = ""
    book_title: str = "TITLE"
    book_author: str = "AUTHOR"
    raw_html_catalog: str = " HTML "


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        return AppConfig()

    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return AppConfig(**{**asdict(AppConfig()), **data})


def save_config(config: AppConfig) -> None:
    CONFIG_PATH.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
