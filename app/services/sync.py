"""Read-only synchronization from the middleware MySQL database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Protocol

import pymysql

from app.config import Settings
from app.db.repository import replace_agpf_snapshot, replace_rst_snapshot, upsert_rst_snapshot
from app.services.result_normalizer import AHG_ODR, ENZYME_ODR


logger = logging.getLogger(__name__)


class MiddlewareSource(Protocol):
    def fetch_agpf(self) -> list[dict[str, object]]: ...

    def fetch_rst(self) -> list[dict[str, object]]: ...

    def fetch_id_sample_ids(self, start_date: str, end_date: str) -> list[dict[str, object]]: ...

    def fetch_rst_for_sample(self, sample_id: str) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class SyncSummary:
    agpf_rows: int
    rst_rows: int


class MySqlMiddlewareSource:
    def __init__(self, settings: Settings) -> None:
        if not settings.mysql_configured:
            raise ValueError("MySQL connection settings are incomplete.")
        self._settings = settings

    def fetch_agpf(self) -> list[dict[str, object]]:
        return self._fetch_all("SELECT * FROM agpf")

    def fetch_rst(self) -> list[dict[str, object]]:
        return self._fetch_all("SELECT * FROM rst")

    def fetch_id_sample_ids(self, start_date: str, end_date: str) -> list[dict[str, object]]:
        logger.info("MySQL ID lookup started: %s through %s", start_date, end_date)
        rows = self._fetch_all(
            """
                        SELECT
                                result.sid AS sample_id,
                                DATE_FORMAT(MAX(result.adt), '%%Y-%%m-%%d') AS test_date,
                                MAX(patient.pnm) AS patient_name,
                                MAX(result.pid) AS patient_id
                        FROM rst AS result
                        LEFT JOIN pinfo AS patient ON patient.pid = result.pid
                        WHERE result.adt >= %s
                            AND result.adt < DATE_ADD(%s, INTERVAL 1 DAY)
                            AND result.tn = 'Ident'
                            AND result.sid IS NOT NULL
                            AND result.sid <> ''
                        GROUP BY result.sid
                        ORDER BY MAX(result.adt) DESC, result.sid DESC
            """,
            (start_date, end_date),
        )
        for row in rows:
            row["patient_name"] = normalize_patient_name(row.get("patient_name"))
        logger.info("MySQL ID lookup completed: %d samples found", len(rows))
        return rows

    def fetch_rst_for_sample(self, sample_id: str) -> list[dict[str, object]]:
        logger.info("MySQL result load started: sample_id=%s", sample_id)
        rows = self._fetch_all("SELECT * FROM rst WHERE sid = %s", (sample_id,))
        logger.info("MySQL result load completed: sample_id=%s rows=%d", sample_id, len(rows))
        return rows

    def _fetch_all(self, query: str, parameters: tuple[object, ...] = ()) -> list[dict[str, object]]:
        logger.info("Opening MySQL read-only connection: host=%s database=%s", self._settings.mysql_host, self._settings.mysql_database)
        connection = pymysql.connect(
            host=self._settings.mysql_host,
            port=self._settings.mysql_port,
            user=self._settings.mysql_user,
            password=self._settings.mysql_password,
            database=self._settings.mysql_database,
            cursorclass=pymysql.cursors.DictCursor,
            charset="utf8",
            read_timeout=30,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, parameters)
                return list(cursor.fetchall())
        finally:
            connection.close()
            logger.info("MySQL read-only connection closed")


def mysql_connection_status(settings: Settings) -> bool:
    """Return whether the configured MySQL server accepts a read-only connection."""
    if not settings.mysql_configured:
        logger.warning("MySQL connection status: settings are incomplete")
        return False

    try:
        connection = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8",
            connect_timeout=5,
            read_timeout=5,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        finally:
            connection.close()
    except Exception as error:
        logger.warning("MySQL connection status: unavailable (%s)", type(error).__name__)
        return False

    logger.info("MySQL connection status: connected")
    return True


def normalize_patient_name(value: object) -> str:
    """Recover CP949 Korean text that was stored in a latin1 name column."""
    name = "" if value is None else str(value).strip()
    if not name or _contains_hangul(name):
        return name
    try:
        decoded = name.encode("latin1").decode("cp949")
    except UnicodeError:
        return name
    return decoded if _contains_hangul(decoded) else name


def _contains_hangul(value: str) -> bool:
    return any("\uac00" <= character <= "\ud7a3" for character in value)


def synchronize(connection, source: MiddlewareSource) -> SyncSummary:
    agpf_rows = replace_agpf_snapshot(connection, source.fetch_agpf())
    rst_rows = replace_rst_snapshot(connection, source.fetch_rst())
    timestamp = datetime.now(UTC).isoformat()
    with connection:
        connection.executemany(
            """
            INSERT INTO sync_metadata (source_name, synced_at, row_count)
            VALUES (?, ?, ?)
            ON CONFLICT(source_name) DO UPDATE SET
                synced_at = excluded.synced_at,
                row_count = excluded.row_count
            """,
            [("agpf", timestamp, agpf_rows), ("rst", timestamp, rst_rows)],
        )
    return SyncSummary(agpf_rows=agpf_rows, rst_rows=rst_rows)


def synchronize_sample(connection, source: MiddlewareSource, sample_id: str) -> SyncSummary:
    agpf_rows = replace_agpf_snapshot(connection, source.fetch_agpf())
    rst_rows = upsert_rst_snapshot(connection, source.fetch_rst_for_sample(sample_id))
    return SyncSummary(agpf_rows=agpf_rows, rst_rows=rst_rows)
