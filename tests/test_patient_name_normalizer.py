from app.services.sync import normalize_patient_name


def test_recovers_cp949_name_stored_as_latin1_text():
    stored_as_latin1 = "\u00b1\u00e8\u00b0\u00e6\u00bc\u00f6"

    assert normalize_patient_name(stored_as_latin1) == "\uae40\uacbd\uc218"


def test_keeps_already_decoded_korean_name():
    assert normalize_patient_name("\uae40\uacbd\uc218") == "\uae40\uacbd\uc218"


def test_keeps_non_korean_name_when_no_safe_conversion_exists():
    assert normalize_patient_name("Patient") == "Patient"