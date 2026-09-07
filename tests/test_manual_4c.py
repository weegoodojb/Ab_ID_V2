from app.main import _parse_4c_values


def test_parses_optional_4c_values_for_eleven_cells():
    values = ["0", "0.5", "1", "2", "3", "4", "", "", "", "", ""]

    assert _parse_4c_values(values) == {
        "1": "0", "2": "5", "3": "10", "4": "20", "5": "30", "6": "40"
    }