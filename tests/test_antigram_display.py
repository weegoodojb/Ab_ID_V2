from app.main import _display_antigen, _matching_antigens, _matrix


def test_normalizes_middleware_antigen_abbreviations_for_antigram_display():
    assert _display_antigen("BC") == "C"
    assert _display_antigen("BE") == "E"
    assert _display_antigen("SC") == "c"
    assert _display_antigen("SE") == "e"
    assert _display_antigen("NK") == "K"
    assert _display_antigen("SK") == "k"
    assert _display_antigen("BS") == "S"
    assert _display_antigen("SS") == "s"


def test_renders_fixed_id_and_screening_cell_counts():
    antigen_rows = [
        {"antigen": "BE", "antigen_value": "+"},
        {"antigen": "BE", "antigen_value": "-"},
        {"antigen": "BE", "antigen_value": "+"},
        {"antigen": "BC", "antigen_value": "-"},
    ]

    id_rows = _matrix(antigen_rows, [], {}, cell_count=11)
    screening_rows = _matrix(antigen_rows, [], {}, cell_count=3)

    assert len(id_rows) == 11
    assert len(screening_rows) == 3
    assert id_rows[0]["antigens"]["E"] == "+"
    assert id_rows[1]["antigens"]["E"] == "-"


def test_marks_screening_donor_number_and_dia_positive_cell():
    rows = [
        {"cell_id": "1", "antigen": "DonorN", "antigen_value": "337001"},
        {"cell_id": "1", "antigen": "Sp Ag", "antigen_value": "Di (a+)"},
    ]

    matrix = _matrix(rows, [], {}, cell_count=3)

    assert matrix[0]["donor_number"] == "337001"
    assert matrix[0]["special"] == "Di(a+)"


def test_highlights_antigens_matching_all_three_screening_results():
    rows = [
        {"cell_id": "1", "antigen": "C", "antigen_value": "+"},
        {"cell_id": "1", "antigen": "E", "antigen_value": "+"},
        {"cell_id": "2", "antigen": "C", "antigen_value": "0"},
        {"cell_id": "2", "antigen": "E", "antigen_value": "0"},
        {"cell_id": "3", "antigen": "C", "antigen_value": "+"},
        {"cell_id": "3", "antigen": "E", "antigen_value": "+"},
    ]
    results = [
        {"test_name": "Surg 1", "order_name": "Ab Screening", "result_code": "10"},
        {"test_name": "Surg 2", "order_name": "Ab Screening", "result_code": "0"},
        {"test_name": "Surg 3", "order_name": "Ab Screening", "result_code": "10"},
    ]

    assert _matching_antigens(_matrix(rows, results, {}, cell_count=3)) == {"C", "E"}


def test_screening_highlight_applies_registered_dosage_pair():
    rows = [
        {"cell_id": "1", "antigen": "Fya", "antigen_value": "+"},
        {"cell_id": "1", "antigen": "Fyb", "antigen_value": "+"},
        {"cell_id": "2", "antigen": "Fya", "antigen_value": "+"},
        {"cell_id": "2", "antigen": "Fyb", "antigen_value": "+"},
        {"cell_id": "3", "antigen": "Fya", "antigen_value": "+"},
        {"cell_id": "3", "antigen": "Fyb", "antigen_value": "+"},
    ]
    results = [
        {"test_name": "Surg 1", "order_name": "Ab Screening", "result_code": "0"},
        {"test_name": "Surg 2", "order_name": "Ab Screening", "result_code": "10"},
        {"test_name": "Surg 3", "order_name": "Ab Screening", "result_code": "10"},
    ]

    matrix = _matrix(rows, results, {}, cell_count=3)

    assert "Fya" in _matching_antigens(matrix, {("Fya", "Fyb")})


def test_unperformed_four_c_is_blank_but_recorded_negative_is_n():
    rows = [{"cell_id": "1", "antigen": "E", "antigen_value": "+"}]

    matrix = _matrix(rows, [], {}, cell_count=11)

    assert matrix[0]["reactions"].get("4C", "") == ""

    matrix = _matrix(rows, [], {"1": "0"}, cell_count=11)

    assert matrix[0]["reactions"]["4C"] == "N"