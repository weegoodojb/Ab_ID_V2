from app.services.identification import assess_candidates, assess_stages


def _antigen_rows():
    return [
        {"ID": "1", "ABScrS": "0", "ag": "D", "vl": "+"},
        {"ID": "2", "ABScrS": "0", "ag": "D", "vl": "+"},
        {"ID": "3", "ABScrS": "0", "ag": "D", "vl": "-"},
        {"ID": "4", "ABScrS": "0", "ag": "D", "vl": "-"},
        {"ID": "1", "ABScrS": "0", "ag": "C", "vl": "-"},
        {"ID": "2", "ABScrS": "0", "ag": "C", "vl": "+"},
        {"ID": "3", "ABScrS": "0", "ag": "C", "vl": "+"},
        {"ID": "4", "ABScrS": "0", "ag": "C", "vl": "-"},
        {"ID": "5", "ABScrS": "1", "ag": "D", "vl": "+"},
    ]


def _ahg_rows():
    return [
        {"tn": "Cell-1", "odr": "0.8% PanelC Unt w/Auto", "rst": "10"},
        {"tn": "Cell-2", "odr": "0.8% PanelC Unt w/Auto", "rst": "20"},
        {"tn": "Cell-3", "odr": "0.8% PanelC Unt w/Auto", "rst": "0"},
        {"tn": "Cell-4", "odr": "0.8% PanelC Unt w/Auto", "rst": "0"},
        {"tn": "Cell-5", "odr": "0.8% PanelC Unt w/Auto", "rst": "10"},
        {"tn": "Auto", "odr": "0.8% PanelC Unt w/Auto", "rst": "0"},
    ]


def test_candidate_requires_two_positive_and_two_negative_panel_matches():
    candidates = assess_candidates(_antigen_rows(), _ahg_rows())
    anti_d = next(candidate for candidate in candidates if candidate.antigen == "D")

    assert anti_d.status == "POSSIBLE"
    assert anti_d.positive_matches == 2
    assert anti_d.negative_matches == 2
    assert anti_d.screening_matches == 1
    assert anti_d.contradictions == ()


def test_contradictory_panel_cell_excludes_candidate():
    rows = _ahg_rows()
    rows[2]["rst"] = "10"

    candidates = assess_candidates(_antigen_rows(), rows)
    anti_d = next(candidate for candidate in candidates if candidate.antigen == "D")

    assert anti_d.status == "EXCLUDED"
    assert anti_d.contradictions == ("3",)


def test_manual_4c_reaction_is_included_in_evidence():
    candidates = assess_candidates(
        _antigen_rows(), _ahg_rows(), manual_4c={"Cell-3": "0"}
    )
    anti_d = next(candidate for candidate in candidates if candidate.antigen == "D")

    assert anti_d.negative_matches == 3


def test_stage_assessment_confirms_anti_e_when_ahg_pattern_matches_all_cells():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": "E", "antigen_value": "+" if cell in {3, 6} else "-"}
        for cell in range(1, 12)
    ]
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Unt w/Auto",
            "result_code": "10" if cell in {3, 6} else "0",
        }
        for cell in range(1, 12)
    ]

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.stage == "AHG"
    assert ahg.status == "CONFIRMED"
    assert ahg.candidates == ("anti-E",)
    assert ahg.matching_antigens == ("E",)


def test_stage_assessment_keeps_enzyme_independent_from_ahg():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": "E", "antigen_value": "+" if cell in {3, 6} else "-"}
        for cell in range(1, 12)
    ]
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Enz",
            "result_code": "10" if cell in {1, 3, 6, 11} else "0",
        }
        for cell in range(1, 12)
    ]

    enzyme = assess_stages(antigen_rows, result_rows)[1]

    assert enzyme.stage == "Enzyme"
    assert enzyme.status == "CANDIDATE"


def test_stage_assessment_does_not_confirm_from_all_negative_enzyme_results():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": "Lua", "antigen_value": "-"}
        for cell in range(1, 12)
    ]
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Enz",
            "result_code": "0",
        }
        for cell in range(1, 12)
    ]

    enzyme = assess_stages(antigen_rows, result_rows)[1]

    assert enzyme.status == "UNID"
    assert enzyme.candidates == ()


def test_dosage_does_not_create_candidate_without_any_raw_positive():
    antigen_rows = [
        {"cell_id": "1", "antigen": "Lua", "antigen_value": "+"},
        {"cell_id": "1", "antigen": "Lub", "antigen_value": "+"},
    ]
    result_rows = [
        {"test_name": "Cell-1", "order_name": "0.8% PanelC Enz", "result_code": "0"},
    ]

    enzyme = assess_stages(
        antigen_rows, result_rows, dosage_pairs={("Lua", "Lub")}
    )[1]

    assert enzyme.status == "UNID"


def test_stage_assessment_excludes_antigen_with_negative_reaction_on_positive_cell():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": "Fyb", "antigen_value": "+" if cell <= 6 else "-"}
        for cell in range(1, 12)
    ]
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Unt w/Auto",
            "result_code": "10" if cell in {3, 6} else "0",
        }
        for cell in range(1, 12)
    ]

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "CANDIDATE"
    assert ahg.candidates == ("anti-Fyb",)


def test_stage_assessment_displays_be_as_e():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": "BE", "antigen_value": "+" if cell in {3, 6} else "-"}
        for cell in range(1, 12)
    ]
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Unt w/Auto",
            "result_code": "10" if cell in {3, 6} else "0",
        }
        for cell in range(1, 12)
    ]

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.candidates == ("anti-E",)


def test_stage_assessment_ranks_near_match_as_candidate():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": "Fyb", "antigen_value": "+" if cell <= 10 else "-"}
        for cell in range(1, 12)
    ]
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Unt w/Auto",
            "result_code": "10" if cell <= 9 else "0",
        }
        for cell in range(1, 12)
    ]

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "CANDIDATE"
    assert ahg.candidates == ("anti-Fyb",)
    assert ahg.best_match_count == 10
    assert ahg.comparison_count == 11
    assert ahg.mismatch_count == 1


def test_dosage_pair_converts_negative_reaction_on_double_positive_cell():
    antigen_rows = [
        {"cell_id": cell, "antigen": antigen, "antigen_value": value}
        for cell, antigen, value in (
            ("1", "Fya", "+"), ("1", "Fyb", "+"),
            ("2", "Fya", "+"), ("2", "Fyb", "+"),
            ("3", "Fya", "-"), ("3", "Fyb", "-"),
        )
    ]
    result_rows = [
        {"test_name": "Cell-1", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "10"},
        {"test_name": "Cell-2", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "0"},
        {"test_name": "Cell-3", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "0"},
    ]

    ahg = assess_stages(antigen_rows, result_rows, dosage_pairs={("Fya", "Fyb")})[0]

    assert "anti-Fya" in ahg.candidates


def test_enzyme_lost_antigen_requires_enzyme_loss_evidence_for_ahg():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": "Fya", "antigen_value": "+" if cell <= 2 else "-"}
        for cell in range(1, 4)
    ]
    ahg_rows = [
        {"test_name": f"Cell-{cell}", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "10" if cell <= 2 else "0"}
        for cell in range(1, 4)
    ]

    ahg = assess_stages(antigen_rows, ahg_rows)[0]

    assert ahg.status == "CANDIDATE"
    assert ahg.candidates == ("anti-Fya",)
    assert "Enzyme 소실 확인 필요" in ahg.detail


def test_positive_auto_control_lowers_ahg_reaction_strength():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": "C", "antigen_value": "+"}
        for cell in range(1, 3)
    ]
    result_rows = [
        {"test_name": "Auto", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "10"},
        {"test_name": "Cell-1", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "20"},
        {"test_name": "Cell-2", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "20"},
    ]

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "CONFIRMED"
    assert ahg.candidates == ("anti-C",)
    assert "A/C 1+ 보정 적용" in ahg.detail


def test_incomplete_or_mismatched_panel_is_candidate_not_confirmed():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": "E", "antigen_value": "+" if cell <= 2 else "-"}
        for cell in range(1, 4)
    ]
    result_rows = [
        {"test_name": "Cell-1", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "10"},
        {"test_name": "Cell-2", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "10"},
    ]

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "CANDIDATE"
    assert ahg.candidates == ("anti-E",)


def test_dosage_pair_does_not_convert_unrelated_antigen():
    antigen_rows = [
        {"cell_id": "1", "antigen": "Fya", "antigen_value": "+"},
        {"cell_id": "1", "antigen": "Fyb", "antigen_value": "+"},
        {"cell_id": "1", "antigen": "E", "antigen_value": "+"},
        {"cell_id": "2", "antigen": "Fya", "antigen_value": "-"},
        {"cell_id": "2", "antigen": "Fyb", "antigen_value": "-"},
        {"cell_id": "2", "antigen": "E", "antigen_value": "-"},
    ]
    result_rows = [
        {"test_name": "Cell-1", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "0"},
        {"test_name": "Cell-2", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "0"},
    ]

    candidates = assess_stages(
        antigen_rows, result_rows, dosage_pairs={("Fya", "Fyb")}
    )[0]

    assert "anti-E" not in candidates.candidates


def test_excludes_js_a_and_v_from_stage_candidates():
    antigen_rows = [
        {"cell_id": str(cell), "antigen": antigen, "antigen_value": "+" if cell <= 10 else "-"}
        for antigen in ("Jsa", "V")
        for cell in range(1, 12)
    ]
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Unt w/Auto",
            "result_code": "10" if cell <= 10 else "0",
        }
        for cell in range(1, 12)
    ]

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert "anti-Jsa" not in ahg.candidates
    assert "anti-V" not in ahg.candidates