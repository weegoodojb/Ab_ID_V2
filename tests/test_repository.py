from app.db.repository import (
    get_ident_test_date,
    initialize_database,
    list_lot_numbers_valid_on,
    list_patient_antigen_results,
    open_database,
    replace_agpf_snapshot,
    replace_rst_snapshot,
    list_review_results,
    list_antigen_rules,
    list_dosage_pairs,
    replace_antigen_rules,
    replace_dosage_pairs,
    save_patient_antigen_result,
    save_review_result,
)


def test_lists_only_lots_valid_on_ident_test_date(tmp_path):
    connection = open_database(tmp_path / "ab-id.sqlite3")
    initialize_database(connection)
    replace_agpf_snapshot(
        connection,
        [
            {"kd": "ID", "lno": "CURRENT", "expdt": "2026-09-15", "sq": "1", "ag": "D", "vl": "+"},
            {"kd": "ID", "lno": "EXPIRED", "expdt": "2026-09-01", "sq": "1", "ag": "D", "vl": "+"},
        ],
    )
    replace_rst_snapshot(
        connection,
        [{"sid": "S1", "adt": "2026-09-02 20:11:14", "tn": "Ident", "odr": "Panel"}],
    )

    test_date = get_ident_test_date(connection, "S1")

    assert test_date == "2026-09-02"
    assert list_lot_numbers_valid_on(connection, test_date, "ID") == ["CURRENT"]


def test_saves_and_lists_review_result(tmp_path):
    connection = open_database(tmp_path / "ab-id.sqlite3")
    initialize_database(connection)

    review_id = save_review_result(
        connection,
        "S1",
        "ID-LOT",
        "SCREEN-LOT",
        {"1": "10"},
        "Anti-E",
        "단일항체 의심",
        "검토 완료",
        "2026-09-04T10:00:00+00:00",
    )

    results = list_review_results(connection, "S1")

    assert review_id == results[0]["review_id"]
    assert results[0]["final_antibody"] == "Anti-E"
    assert '"1": "10"' in results[0]["four_c_json"]


def test_saves_antigen_rule_lists(tmp_path):
    connection = open_database(tmp_path / "ab-id.sqlite3")
    initialize_database(connection)

    replace_antigen_rules(connection, ["Fya", "Dia"], ["Fya", "M"])

    rules = {row["antigen"]: row for row in list_antigen_rules(connection)}

    assert rules["Dia"]["dosage_enabled"] == 1
    assert rules["Dia"]["enzyme_lost"] == 0
    assert rules["M"]["dosage_enabled"] == 0
    assert rules["M"]["enzyme_lost"] == 1


def test_saves_dosage_antigen_pairs(tmp_path):
    connection = open_database(tmp_path / "ab-id.sqlite3")
    initialize_database(connection)

    replace_dosage_pairs(connection, [("Fyb", "Fya"), ("S", "s")])

    pairs = list_dosage_pairs(connection)

    assert [(pair["antigen_one"], pair["antigen_two"]) for pair in pairs] == [
        ("Fya", "Fyb"),
        ("S", "s"),
    ]


def test_saves_and_lists_patient_antigen_results(tmp_path):
    connection = open_database(tmp_path / "ab-id.sqlite3")
    initialize_database(connection)

    save_patient_antigen_result(connection, "S1", "E", "양성", "2026-09-04T10:00:00+00:00")
    save_patient_antigen_result(connection, "S1", "Fya", "음성", "2026-09-04T10:00:00+00:00")
    save_patient_antigen_result(connection, "S1", "E", "음성", "2026-09-05T10:00:00+00:00")

    results = list_patient_antigen_results(connection, "S1")

    assert results == {"E": "음성", "Fya": "음성"}
    assert list_patient_antigen_results(connection, "S2") == {}