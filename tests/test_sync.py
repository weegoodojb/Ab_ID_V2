from app.db.repository import initialize_database, open_database
from app.services.sync import synchronize


class FakeMiddlewareSource:
    def fetch_agpf(self):
        return [
            {"lno": "8RC437", "ID": "1", "ABScrS": "0", "ag": "D", "vl": "+"},
            {"lno": "8RC437", "ID": "1", "ABScrS": "0", "ag": "C", "vl": "-"},
        ]

    def fetch_rst(self):
        return [
            {
                "sid": "I24D32780",
                "adt": "2026-09-02 20:00:25",
                "tn": "Cell-1",
                "odr": "0.8% PanelC Enz",
                "rst": "10",
                "pid": "001040087",
                "Iid": "J60007889",
            },
            {
                "sid": "I24D32780",
                "adt": "2026-09-02 20:11:14",
                "tn": "Auto",
                "odr": "0.8% PanelC Unt w/Auto",
                "rst": "0",
                "pid": "001040087",
                "Iid": "J60007889",
            },
        ]


def test_sync_preserves_analyzer_rows_and_raw_payload(tmp_path):
    connection = open_database(tmp_path / "ab-id.sqlite3")
    initialize_database(connection)

    summary = synchronize(connection, FakeMiddlewareSource())

    assert summary.agpf_rows == 2
    assert summary.rst_rows == 2
    result = connection.execute(
        "SELECT test_name, result_code, raw_json FROM rst_snapshot WHERE test_name = 'Auto'"
    ).fetchone()
    assert result["result_code"] == "0"
    assert '"tn": "Auto"' in result["raw_json"]