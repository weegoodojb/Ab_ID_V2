from app.services.identification import assess_stages


def _ahg_rows(positive_cells, total=11):
    return [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Unt w/Auto",
            "result_code": "10" if cell in positive_cells else "0",
        }
        for cell in range(1, total + 1)
    ]


def _antigen_rows(antigen, positive_cells, total=11):
    return [
        {"cell_id": str(cell), "antigen": antigen, "antigen_value": "+" if cell in positive_cells else "-"}
        for cell in range(1, total + 1)
    ]


def test_compound_confirms_two_antibody_pattern_as_compound_candidate():
    # D positive on 1-6, E positive on 6-11 -> union covers all 11 cells,
    # each antigen has cells the other doesn't (distinguishing cells).
    antigen_rows = _antigen_rows("D", set(range(1, 7))) + _antigen_rows("E", set(range(6, 12)))
    result_rows = _ahg_rows(set(range(1, 12)))

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "COMPOUND_CANDIDATE"
    assert "anti-D + anti-E" in ahg.candidates
    assert set(ahg.matching_antigens) == {"D", "E"}


def test_compound_rejects_bystander_antigen_without_distinguishing_cell():
    # B's positive cells (1-3) are a strict subset of A's (1-6); pairing them
    # trivially reproduces A alone and must not be reported as compound.
    antigen_rows = _antigen_rows("D", set(range(1, 7))) + _antigen_rows("C", {1, 2, 3})
    result_rows = _ahg_rows(set(range(1, 7)))

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert not any("anti-C" in candidate for candidate in ahg.candidates)


def test_compound_search_skipped_when_single_antigen_confirmed():
    antigen_rows = _antigen_rows("E", {3, 6})
    result_rows = _ahg_rows({3, 6})

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "CONFIRMED"
    assert ahg.candidates == ("anti-E",)


def test_compound_excludes_hard_ruled_out_antigen():
    # Cell 1 has a negative reaction. D (2-6) and E (6-11) both correctly stay
    # negative there and pair up cleanly. C additionally claims cell 1 as
    # antigen-positive even though the reaction there is negative -> C must be
    # ruled out entirely, never appearing in any suggested pair.
    antigen_rows = (
        _antigen_rows("D", set(range(2, 7)))
        + _antigen_rows("E", set(range(6, 12)))
        + _antigen_rows("C", set(range(7, 12)) | {1})
    )
    result_rows = _ahg_rows(set(range(2, 12)))

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "COMPOUND_CANDIDATE"
    assert "anti-D + anti-E" in ahg.candidates
    assert not any("anti-C" in candidate for candidate in ahg.candidates)


def test_compound_respects_enzyme_lost_antigen_exclusion_in_enzyme_stage():
    antigen_rows = _antigen_rows("D", set(range(1, 7))) + _antigen_rows("Fya", set(range(6, 12)))
    result_rows = [
        {"test_name": f"Cell-{cell}", "order_name": "0.8% PanelC Enz", "result_code": "10"}
        for cell in range(1, 12)
    ]

    enzyme = assess_stages(antigen_rows, result_rows, enzyme_lost_antigens={"Fya"})[1]

    assert not any("Fya" in candidate for candidate in enzyme.candidates)


def test_compound_applies_dosage_pair_boost_like_single_antigen():
    # Cells 1-2 are homozygous Fya/Fyb (dosage cell) but the raw reaction is
    # negative there; the dosage boost is required for Fya to line up with
    # the observed reaction. Cell 4 is explained by E instead. Without the
    # boost, the Fya/E pair would show a mismatch on cells 1-2.
    antigen_rows = [
        {"cell_id": "1", "antigen": "Fya", "antigen_value": "+"},
        {"cell_id": "1", "antigen": "Fyb", "antigen_value": "+"},
        {"cell_id": "1", "antigen": "E", "antigen_value": "-"},
        {"cell_id": "2", "antigen": "Fya", "antigen_value": "+"},
        {"cell_id": "2", "antigen": "Fyb", "antigen_value": "+"},
        {"cell_id": "2", "antigen": "E", "antigen_value": "-"},
        {"cell_id": "3", "antigen": "Fya", "antigen_value": "-"},
        {"cell_id": "3", "antigen": "Fyb", "antigen_value": "-"},
        {"cell_id": "3", "antigen": "E", "antigen_value": "-"},
        {"cell_id": "4", "antigen": "Fya", "antigen_value": "-"},
        {"cell_id": "4", "antigen": "Fyb", "antigen_value": "-"},
        {"cell_id": "4", "antigen": "E", "antigen_value": "+"},
    ]
    result_rows = [
        {"test_name": "Cell-1", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "0"},
        {"test_name": "Cell-2", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "0"},
        {"test_name": "Cell-3", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "0"},
        {"test_name": "Cell-4", "order_name": "0.8% PanelC Unt w/Auto", "result_code": "10"},
    ]

    ahg = assess_stages(
        antigen_rows, result_rows, dosage_pairs={("Fya", "Fyb")}
    )[0]

    assert ahg.status == "COMPOUND_CANDIDATE"
    assert "anti-E + anti-Fya" in ahg.candidates


def test_compound_flags_enzyme_loss_pending_for_ahg_partner():
    antigen_rows = _antigen_rows("D", set(range(1, 7))) + _antigen_rows("Fya", set(range(6, 12)))
    result_rows = _ahg_rows(set(range(1, 12)))

    ahg = assess_stages(antigen_rows, result_rows, enzyme_lost_antigens={"Fya"})[0]

    assert ahg.status == "COMPOUND_CANDIDATE"
    assert "Enzyme 소실 확인 필요" in ahg.detail


def test_compound_not_attempted_when_no_positive_reactions():
    antigen_rows = _antigen_rows("D", set(range(1, 7))) + _antigen_rows("E", set(range(6, 12)))
    result_rows = _ahg_rows(set())

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "UNID"
    assert ahg.candidates == ()


def test_compound_lists_multiple_ambiguous_pairs_when_more_than_one_fits():
    # Two independent antigens (C, K) also each split the same 1-6/6-11 pattern,
    # so both (D,E) and (C,K) perfectly explain the full panel.
    antigen_rows = (
        _antigen_rows("D", set(range(1, 7)))
        + _antigen_rows("E", set(range(6, 12)))
        + _antigen_rows("C", set(range(1, 7)))
        + _antigen_rows("K", set(range(6, 12)))
    )
    result_rows = _ahg_rows(set(range(1, 12)))

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "COMPOUND_CANDIDATE"
    assert len(ahg.candidates) > 1
    assert "여러 조합 후보 있음" in ahg.detail


def test_compound_status_never_reports_stronger_than_candidate_tier():
    antigen_rows = _antigen_rows("D", set(range(1, 7))) + _antigen_rows("E", set(range(6, 12)))
    result_rows = _ahg_rows(set(range(1, 12)))

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status in {"CONFIRMED", "CANDIDATE", "COMPOUND_CANDIDATE", "UNID"}
    assert ahg.status != "COMPOUND_CONFIRMED"
