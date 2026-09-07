"""Run a read-only MySQL-to-SQLite synchronization."""

from app.config import get_settings
from app.db.repository import initialize_database, open_database
from app.services.sync import MySqlMiddlewareSource, synchronize


def main() -> None:
    settings = get_settings()
    source = MySqlMiddlewareSource(settings)
    connection = open_database(settings.sqlite_path)
    try:
        initialize_database(connection)
        summary = synchronize(connection, source)
    finally:
        connection.close()
    print(f"Synced agpf={summary.agpf_rows}, rst={summary.rst_rows}")


if __name__ == "__main__":
    main()