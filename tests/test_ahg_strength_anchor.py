from app.services.identification import assess_stages


def _antigen_rows(antigen, positive_cells, total=11):
    return [
        {"cell_id": str(cell), "antigen": antigen, "antigen_value": "+" if cell in positive_cells else "-"}
        for cell in range(1, total + 1)
    ]


def test_ahg_strength_anchor_prioritizes_strongest_tier_antigen():
    # User's worked example: cell 3 negative, cells 1/2/5/11 react 4+ (strong
    # tier), the rest of the positives react 3+. Antigen X exactly matches
    # the strong tier and should be selected as the anchor; antigen Y covers
    # the residual weaker-positive cells.
    strong_cells = {1, 2, 5, 11}
    weak_cells = {4, 6, 7, 8, 9, 10}
    antigen_rows = _antigen_rows("X", strong_cells) + _antigen_rows("Y", weak_cells)
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Unt w/Auto",
            "result_code": (
                "40" if cell in strong_cells else "30" if cell in weak_cells else "0"
            ),
        }
        for cell in range(1, 12)
    ]

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "COMPOUND_CANDIDATE"
    assert "anti-X + anti-Y" in ahg.candidates
    assert "4+" in ahg.detail
    assert "anti-X" in ahg.detail
    assert "앵커" in ahg.detail


def test_ahg_falls_back_to_full_search_when_no_strength_tier_matches():
    # Strengths are mixed (cell 6 is weaker than the rest) but no single
    # antigen's profile matches that particular strong tier exactly, so the
    # anchor search should find nothing and fall back to the full pairwise
    # search from Phase B, which still finds D+E via raw positive/negative.
    antigen_rows = _antigen_rows("D", set(range(1, 7))) + _antigen_rows("E", set(range(6, 12)))
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Unt w/Auto",
            "result_code": "10" if cell == 6 else "20",
        }
        for cell in range(1, 12)
    ]

    ahg = assess_stages(antigen_rows, result_rows)[0]

    assert ahg.status == "COMPOUND_CANDIDATE"
    assert "anti-D + anti-E" in ahg.candidates
    assert "앵커" not in ahg.detail


def test_ahg_strength_anchor_not_applied_to_enzyme_or_4c():
    strong_cells = {1, 2, 5, 11}
    weak_cells = {4, 6, 7, 8, 9, 10}
    antigen_rows = _antigen_rows("X", strong_cells) + _antigen_rows("Y", weak_cells)
    result_rows = [
        {
            "test_name": f"Cell-{cell}",
            "order_name": "0.8% PanelC Enz",
            "result_code": (
                "40" if cell in strong_cells else "30" if cell in weak_cells else "0"
            ),
        }
        for cell in range(1, 12)
    ]

    enzyme = assess_stages(antigen_rows, result_rows)[1]

    assert enzyme.status == "COMPOUND_CANDIDATE"
    assert "anti-X + anti-Y" in enzyme.candidates
    assert "앵커" not in enzyme.detail
