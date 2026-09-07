"""Two-antibody compound pattern detection.

Layered on top of the single-antigen scoring in ``identification.py``. All
results from this module are surfaced at the same conservative
``CANDIDATE`` tier as the rest of the app (see ``StageAssessment`` in
``identification.py``) — a clean pairwise fit is never treated as a
confirmation, since exhaustively testing every antigen pair against a
small (e.g. 11-cell) panel carries a real chance of a coincidental
perfect fit.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations


def hard_excluded_antigens(
    profiles: Mapping[str, Mapping[str, bool]],
    effective_by_antigen: Mapping[str, Mapping[str, bool]],
) -> set[str]:
    """Antigens ruled out for any compound pair.

    An antigen is excluded if there is a cell where the antigen is present
    but the (dosage-adjusted) patient reaction is negative — the classical
    single-specificity rule-out. An antigen-negative cell with a positive
    reaction is NOT grounds for exclusion: a compound partner may explain
    that reaction instead.
    """
    excluded: set[str] = set()
    for antigen, profile in profiles.items():
        effective = effective_by_antigen.get(antigen, {})
        for cell, is_positive in profile.items():
            if is_positive and cell in effective and not effective[cell]:
                excluded.add(antigen)
                break
    return excluded


def _pair_is_valid(
    profile_a: Mapping[str, bool],
    profile_b: Mapping[str, bool],
    effective_a: Mapping[str, bool],
    effective_b: Mapping[str, bool],
    expected_cell_count: int,
) -> bool:
    """Whether the combined (OR) reaction of A and B perfectly explains the
    panel, with each contributing at least one distinguishing cell.

    Requires full-panel coverage and zero mismatches (the same rigor as a
    single-antigen ``CONFIRMED``), plus a "distinguishing cell" for each
    side — a cell where that antigen alone (not the other) is positive.
    Without that requirement, a bystander antigen whose positive cells are
    a subset of a stronger partner's would ride along on a pair the
    stronger antigen alone already explains just as well.
    """
    cells = set(profile_a) & set(profile_b) & set(effective_a) & set(effective_b)
    if len(cells) != expected_cell_count:
        return False
    distinguishes_a = distinguishes_b = False
    for cell in cells:
        a_positive = profile_a[cell]
        b_positive = profile_b[cell]
        predicted = a_positive or b_positive
        observed = effective_a[cell] or effective_b[cell]
        if predicted != observed:
            return False
        if a_positive and not b_positive:
            distinguishes_a = True
        elif b_positive and not a_positive:
            distinguishes_b = True
    return distinguishes_a and distinguishes_b


def compound_pairs(
    profiles: Mapping[str, Mapping[str, bool]],
    effective_by_antigen: Mapping[str, Mapping[str, bool]],
    excluded: set[str],
    expected_cell_count: int,
) -> list[tuple[str, str]]:
    """All antigen pairs whose combined reaction perfectly explains the panel.

    See ``_pair_is_valid`` for the exact acceptance criteria.
    """
    candidates = sorted(antigen for antigen in profiles if antigen not in excluded)
    return [
        (first, second)
        for first, second in combinations(candidates, 2)
        if _pair_is_valid(
            profiles[first],
            profiles[second],
            effective_by_antigen.get(first, {}),
            effective_by_antigen.get(second, {}),
            expected_cell_count,
        )
    ]


def strength_tier_anchor(
    profiles: Mapping[str, Mapping[str, bool]],
    positive_cells: set[str],
    strengths: Mapping[str, int],
) -> str | None:
    """Find a single antigen whose profile exactly matches the strongest-
    reacting tier of cells, when reaction strengths are not uniform.

    A cluster of stronger reactions (e.g. 4+ among otherwise 3+ positives)
    often points to one dominant antibody; isolating the antigen whose
    profile matches exactly that strong tier gives a more targeted anchor
    for the compound search than a symmetric brute-force pair search.
    Returns the antigen name only when exactly one such antigen exists —
    ambiguity here is treated the same as "no anchor found".
    """
    known_strengths = {cell: strengths[cell] for cell in positive_cells if cell in strengths}
    if not known_strengths:
        return None
    max_strength = max(known_strengths.values())
    strong_tier = {cell for cell, value in known_strengths.items() if value == max_strength}
    if strong_tier == positive_cells:
        return None
    anchors = [
        antigen
        for antigen, profile in profiles.items()
        if profile and all(profile[cell] == (cell in strong_tier) for cell in profile)
    ]
    return anchors[0] if len(anchors) == 1 else None


def anchored_pairs(
    profiles: Mapping[str, Mapping[str, bool]],
    effective_by_antigen: Mapping[str, Mapping[str, bool]],
    excluded: set[str],
    expected_cell_count: int,
    anchor: str,
) -> list[tuple[str, str]]:
    """Pairs containing ``anchor`` whose combined reaction perfectly explains
    the panel — a scoped version of ``compound_pairs`` that only searches
    for a partner to explain what the anchor leaves unexplained."""
    if anchor in excluded:
        return []
    return [
        tuple(sorted((anchor, other)))
        for other in sorted(profiles)
        if other != anchor
        and other not in excluded
        and _pair_is_valid(
            profiles[anchor],
            profiles[other],
            effective_by_antigen.get(anchor, {}),
            effective_by_antigen.get(other, {}),
            expected_cell_count,
        )
    ]
