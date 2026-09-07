import pytest

from app.services.result_normalizer import classify_method, normalize_result


@pytest.mark.parametrize(
    ("raw_value", "display", "strength", "is_positive"),
    [
        ("0", "N", 0, False),
        ("5", "trace", 1, True),
        ("10", "1+", 2, True),
        ("20", "2+", 3, True),
        ("30", "3+", 4, True),
        ("40", "4+", 5, True),
    ],
)
def test_normalizes_middleware_result_codes(raw_value, display, strength, is_positive):
    result = normalize_result(raw_value)

    assert result.display == display
    assert result.strength == strength
    assert result.is_positive is is_positive


def test_trace_can_be_configured_as_negative():
    assert normalize_result("5", positive_threshold=2).is_positive is False


def test_keeps_missing_and_unknown_results_distinct():
    assert normalize_result(None).is_positive is None
    assert normalize_result("Done").is_positive is None


def test_classifies_auto_control_from_test_name():
    assert classify_method("Auto", "0.8% PanelC Unt w/Auto") == "AUTO_CONTROL"


def test_classifies_ahg_and_enzyme_rows():
    assert classify_method("Cell-1", "0.8% PanelC Unt w/Auto") == "AHG"
    assert classify_method("Cell-1", "0.8% PanelC Unt") == "AHG"
    assert classify_method("Cell-1", "0.8% PanelC Enz") == "ENZYME"