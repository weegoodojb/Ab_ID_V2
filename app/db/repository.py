"""SQLite storage for immutable middleware snapshots."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path


logger = logging.getLogger(__name__)


def open_database(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS agpf_snapshot (
            snapshot_id INTEGER PRIMARY KEY,
            panel_kind TEXT NOT NULL,
            lot_number TEXT NOT NULL,
            expiration_date TEXT,
            cell_id TEXT NOT NULL,
            screening_cell TEXT,
            antigen TEXT NOT NULL,
            antigen_value TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rst_snapshot (
            sample_id TEXT NOT NULL,
            collected_at TEXT,
            test_name TEXT NOT NULL,
            order_name TEXT,
            result_code TEXT,
            patient_id TEXT,
            lot_identifier TEXT,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (sample_id, collected_at, test_name, order_name, lot_identifier)
        );

        CREATE TABLE IF NOT EXISTS sync_metadata (
            source_name TEXT PRIMARY KEY,
            synced_at TEXT NOT NULL,
            row_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS review_results (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT NOT NULL,
            id_lot_number TEXT NOT NULL,
            screening_lot_number TEXT NOT NULL,
            four_c_json TEXT NOT NULL,
            final_antibody TEXT NOT NULL,
            final_interpretation TEXT NOT NULL,
            reviewer_note TEXT NOT NULL,
            saved_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sample_directory (
            sample_id TEXT PRIMARY KEY,
            test_date TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            patient_id TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS antigen_rules (
            antigen TEXT PRIMARY KEY,
            dosage_enabled INTEGER NOT NULL DEFAULT 0,
            enzyme_lost INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS dosage_pairs (
            pair_id INTEGER PRIMARY KEY AUTOINCREMENT,
            antigen_one TEXT NOT NULL,
            antigen_two TEXT NOT NULL,
            UNIQUE (antigen_one, antigen_two)
        );
        """
    )
    connection.executemany(
        "INSERT OR IGNORE INTO antigen_rules (antigen, dosage_enabled, enzyme_lost) VALUES (?, ?, ?)",
        [(antigen, 1, 1) for antigen in ("Fya", "Fyb", "S", "s", "M", "N")],
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(agpf_snapshot)")}
    if "panel_kind" not in columns:
        connection.execute("DROP TABLE agpf_snapshot")
        connection.execute(
            """
            CREATE TABLE agpf_snapshot (
                snapshot_id INTEGER PRIMARY KEY,
                panel_kind TEXT NOT NULL,
                lot_number TEXT NOT NULL,
                expiration_date TEXT,
                cell_id TEXT NOT NULL,
                screening_cell TEXT,
                antigen TEXT NOT NULL,
                antigen_value TEXT,
                raw_json TEXT NOT NULL
            )
            """
        )
    connection.commit()


def replace_agpf_snapshot(
    connection: sqlite3.Connection, rows: Iterable[Mapping[str, object]]
) -> int:
    prepared_rows = []
    for row in rows:
        panel_kind = _value(row, "kd")
        cell_id = _cell_id(row)
        if not cell_id and panel_kind in {"ID", "ABScrS"}:
            logger.warning(
                "agpf row has no resolvable cell id and will not appear in any antigram "
                "row: panel_kind=%s lot_number=%s gr=%s antigen=%s",
                panel_kind,
                _value(row, "lno"),
                _value(row, "gr"),
                _value(row, "ag"),
            )
        prepared_rows.append(
            (
                panel_kind,
                _value(row, "lno"),
                _value(row, "expdt"),
                cell_id,
                "1" if panel_kind == "ABScrS" else "0",
                _value(row, "ag"),
                _value(row, "vl"),
                json.dumps(row, ensure_ascii=False, default=str),
            )
        )
    with connection:
        connection.execute("DELETE FROM agpf_snapshot")
        connection.executemany(
            """
            INSERT INTO agpf_snapshot (
                panel_kind, lot_number, expiration_date, cell_id, screening_cell, antigen, antigen_value, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            prepared_rows,
        )
    return len(prepared_rows)


def replace_rst_snapshot(
    connection: sqlite3.Connection, rows: Iterable[Mapping[str, object]]
) -> int:
    prepared_rows = [
        (
            _value(row, "sid"),
            _value(row, "adtc", "adt"),
            _value(row, "tn"),
            _value(row, "odr"),
            _value(row, "rst"),
            _value(row, "pid"),
            _value(row, "lid", "Iid"),
            json.dumps(row, ensure_ascii=False, default=str),
        )
        for row in rows
    ]
    with connection:
        connection.execute("DELETE FROM rst_snapshot")
        connection.executemany(
            """
            INSERT INTO rst_snapshot (
                sample_id, collected_at, test_name, order_name, result_code,
                patient_id, lot_identifier, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            prepared_rows,
        )
    return len(prepared_rows)


def upsert_rst_snapshot(
    connection: sqlite3.Connection, rows: Iterable[Mapping[str, object]]
) -> int:
    prepared_rows = [
        (
            _value(row, "sid"),
            _value(row, "adtc", "adt"),
            _value(row, "tn"),
            _value(row, "odr"),
            _value(row, "rst"),
            _value(row, "pid"),
            _value(row, "lid", "Iid"),
            json.dumps(row, ensure_ascii=False, default=str),
        )
        for row in rows
    ]
    with connection:
        connection.executemany(
            """
            INSERT INTO rst_snapshot (
                sample_id, collected_at, test_name, order_name, result_code,
                patient_id, lot_identifier, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sample_id, collected_at, test_name, order_name, lot_identifier)
            DO UPDATE SET result_code = excluded.result_code, raw_json = excluded.raw_json
            """,
            prepared_rows,
        )
    return len(prepared_rows)


def list_sample_ids(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT DISTINCT sample_id FROM rst_snapshot WHERE sample_id <> '' ORDER BY sample_id DESC"
    ).fetchall()
    return [row["sample_id"] for row in rows]


def save_sample_directory(
    connection: sqlite3.Connection, samples: Iterable[Mapping[str, object]]
) -> int:
    prepared_rows = [
        (
            _value(sample, "sample_id"),
            _value(sample, "test_date"),
            _value(sample, "patient_name"),
            _value(sample, "patient_id"),
        )
        for sample in samples
        if _value(sample, "sample_id")
    ]
    with connection:
        connection.executemany(
            """
            INSERT INTO sample_directory (sample_id, test_date, patient_name, patient_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(sample_id) DO UPDATE SET
                test_date = excluded.test_date,
                patient_name = excluded.patient_name,
                patient_id = excluded.patient_id
            """,
            prepared_rows,
        )
    return len(prepared_rows)


def list_sample_directory(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT sample_id, test_date, patient_name, patient_id
        FROM sample_directory
        ORDER BY test_date DESC, sample_id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_sample_directory_entry(
    connection: sqlite3.Connection, sample_id: str
) -> dict[str, object] | None:
    row = connection.execute(
        """
        SELECT sample_id, test_date, patient_name, patient_id
        FROM sample_directory
        WHERE sample_id = ?
        """,
        (sample_id,),
    ).fetchone()
    return dict(row) if row else None


def list_antigen_rules(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT antigen, dosage_enabled, enzyme_lost FROM antigen_rules ORDER BY antigen"
    ).fetchall()
    return [dict(row) for row in rows]


def replace_antigen_rules(
    connection: sqlite3.Connection,
    dosage_antigens: Iterable[str],
    enzyme_lost_antigens: Iterable[str],
) -> int:
    dosage = {antigen.strip() for antigen in dosage_antigens if antigen.strip()}
    enzyme_lost = {antigen.strip() for antigen in enzyme_lost_antigens if antigen.strip()}
    all_antigens = dosage | enzyme_lost
    with connection:
        connection.execute("DELETE FROM antigen_rules")
        connection.executemany(
            "INSERT INTO antigen_rules (antigen, dosage_enabled, enzyme_lost) VALUES (?, ?, ?)",
            [(antigen, int(antigen in dosage), int(antigen in enzyme_lost)) for antigen in sorted(all_antigens)],
        )
    return len(all_antigens)


def list_dosage_pairs(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT pair_id, antigen_one, antigen_two FROM dosage_pairs ORDER BY pair_id"
    ).fetchall()
    return [dict(row) for row in rows]


def replace_dosage_pairs(
    connection: sqlite3.Connection, pairs: Iterable[tuple[str, str]]
) -> int:
    prepared_pairs = sorted(
        {
            tuple(sorted((first.strip(), second.strip())))
            for first, second in pairs
            if first.strip() and second.strip() and first.strip() != second.strip()
        }
    )
    with connection:
        connection.execute("DELETE FROM dosage_pairs")
        connection.executemany(
            "INSERT INTO dosage_pairs (antigen_one, antigen_two) VALUES (?, ?)",
            prepared_pairs,
        )
    return len(prepared_pairs)


def list_lot_numbers(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT DISTINCT lot_number FROM agpf_snapshot WHERE lot_number <> '' ORDER BY lot_number DESC"
    ).fetchall()
    return [row["lot_number"] for row in rows]


def list_lot_numbers_valid_on(
    connection: sqlite3.Connection, test_date: str, panel_kind: str
) -> list[str]:
    rows = connection.execute(
        """
        SELECT lot_number
        FROM agpf_snapshot
        WHERE lot_number <> '' AND panel_kind = ?
        GROUP BY lot_number
        HAVING MAX(date(expiration_date)) >= date(?)
        ORDER BY lot_number DESC
        """,
        (panel_kind, test_date),
    ).fetchall()
    return [row["lot_number"] for row in rows]


def list_lot_options_valid_on(
    connection: sqlite3.Connection, test_date: str, panel_kind: str
) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT lot_number, MAX(expiration_date) AS expiration_date
        FROM agpf_snapshot
        WHERE lot_number <> '' AND panel_kind = ?
        GROUP BY lot_number
        HAVING MAX(date(expiration_date)) >= date(?)
        ORDER BY date(expiration_date), lot_number
        """,
        (panel_kind, test_date),
    ).fetchall()
    return [dict(row) for row in rows]


def closest_valid_lot_on(
    connection: sqlite3.Connection, test_date: str, panel_kind: str
) -> str | None:
    options = list_lot_options_valid_on(connection, test_date, panel_kind)
    return options[0]["lot_number"] if options else None


def get_ident_test_date(connection: sqlite3.Connection, sample_id: str) -> str | None:
    row = connection.execute(
        """
        SELECT substr(collected_at, 1, 10) AS test_date
        FROM rst_snapshot
        WHERE sample_id = ? AND test_name = 'Ident'
        ORDER BY collected_at DESC
        LIMIT 1
        """,
        (sample_id,),
    ).fetchone()
    return row["test_date"] if row else None


def get_antigen_rows(
    connection: sqlite3.Connection, lot_number: str, panel_kind: str
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT cell_id, screening_cell, antigen, antigen_value
        FROM agpf_snapshot
        WHERE lot_number = ? AND panel_kind = ?
        ORDER BY CAST(cell_id AS INTEGER), antigen
        """,
        (lot_number, panel_kind),
    ).fetchall()
    return [dict(row) for row in rows]


def get_latest_result_rows(
    connection: sqlite3.Connection, sample_id: str
) -> list[dict[str, object]]:
    """Return the most recent result per (test_name, order_name) for a sample.

    Ties on collected_at (e.g. re-tests logged under a different lot_identifier,
    which is part of the snapshot's primary key) are broken deterministically by
    lot_identifier so the displayed reaction never depends on SQLite's row order.
    """
    rows = connection.execute(
        """
        SELECT test_name, order_name, result_code, collected_at, lot_identifier
        FROM rst_snapshot
        WHERE sample_id = ?
        """,
        (sample_id,),
    ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        key = (row["test_name"], row["order_name"] or "")
        current = latest.get(key)
        if current is None or _result_sort_key(row) >= _result_sort_key(current):
            latest[key] = row
    ordered = sorted(latest.values(), key=lambda row: (row["order_name"] or "", row["test_name"]))
    return [
        {
            "test_name": row["test_name"],
            "order_name": row["order_name"],
            "result_code": row["result_code"],
        }
        for row in ordered
    ]


def _result_sort_key(row: sqlite3.Row) -> tuple[str, str]:
    return (row["collected_at"] or "", row["lot_identifier"] or "")


def save_review_result(
    connection: sqlite3.Connection,
    sample_id: str,
    id_lot_number: str,
    screening_lot_number: str,
    four_c_values: Mapping[str, str],
    final_antibody: str,
    final_interpretation: str,
    reviewer_note: str,
    saved_at: str,
) -> int:
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO review_results (
                sample_id, id_lot_number, screening_lot_number, four_c_json,
                final_antibody, final_interpretation, reviewer_note, saved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                id_lot_number,
                screening_lot_number,
                json.dumps(dict(four_c_values), ensure_ascii=False),
                final_antibody.strip(),
                final_interpretation.strip(),
                reviewer_note.strip(),
                saved_at,
            ),
        )
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite did not return a review result id")
    return int(cursor.lastrowid)


def list_review_results(
    connection: sqlite3.Connection, sample_id: str
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT review_id, sample_id, id_lot_number, screening_lot_number,
               four_c_json, final_antibody, final_interpretation, reviewer_note, saved_at
        FROM review_results
        WHERE sample_id = ?
        ORDER BY saved_at DESC, review_id DESC
        """,
        (sample_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _value(row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return str(value)
    return ""


def _cell_id(row: Mapping[str, object]) -> str:
    panel_kind = _value(row, "kd")
    group = _value(row, "gr")
    try:
        group_number = int(group)
    except ValueError:
        return ""
    if panel_kind == "ID" and 9 <= group_number <= 19:
        return str(group_number - 8)
    if panel_kind == "ABScrS" and 27 <= group_number <= 29:
        return str(group_number - 26)
    return ""
