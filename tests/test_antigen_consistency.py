from app.services.antigen_consistency import check_antigen_consistency


def test_warns_when_patient_carries_candidate_antigen():
    warnings = check_antigen_consistency({"E"}, {"E": "양성"})

    assert len(warnings) == 1
    assert "E" in warnings[0]
    assert "양성" in warnings[0]


def test_no_warning_for_negative_or_unrecorded_result():
    warnings = check_antigen_consistency({"E", "Fya"}, {"E": "음성"})

    assert warnings == []


def test_ignores_antigens_not_in_candidate_set():
    warnings = check_antigen_consistency({"E"}, {"Fya": "양성"})

    assert warnings == []
