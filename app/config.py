"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    sqlite_path: Path
    mysql_host: str | None
    mysql_port: int
    mysql_database: str | None
    mysql_user: str | None
    mysql_password: str | None

    @property
    def mysql_configured(self) -> bool:
        return all(
            [self.mysql_host, self.mysql_database, self.mysql_user, self.mysql_password]
        )


def get_settings() -> Settings:
    return Settings(
        sqlite_path=Path(os.getenv("ABID_SQLITE_PATH", "data/ab_id.sqlite3")),
        mysql_host=os.getenv("ABID_MYSQL_HOST"),
        mysql_port=int(os.getenv("ABID_MYSQL_PORT", "3306")),
        mysql_database=os.getenv("ABID_MYSQL_DATABASE"),
        mysql_user=os.getenv("ABID_MYSQL_USER"),
        mysql_password=os.getenv("ABID_MYSQL_PASSWORD"),
    )
