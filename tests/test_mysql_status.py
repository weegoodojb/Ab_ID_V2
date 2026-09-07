from pathlib import Path

from app.config import Settings
from app.services.sync import mysql_connection_status


def test_reports_disconnected_when_mysql_settings_are_missing():
    settings = Settings(
        sqlite_path=Path("data/test.sqlite3"),
        mysql_host=None,
        mysql_port=3306,
        mysql_database=None,
        mysql_user=None,
        mysql_password=None,
    )

    assert mysql_connection_status(settings) is False