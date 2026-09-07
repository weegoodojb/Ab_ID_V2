"""Explainable rule-based candidate ranking for antibody identification."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.services.result_normalizer import classify_method, display_antigen, normalize_result


SCREENING_MARKERS = {"1", "Y", "S", "SCREEN", "SCREENING"}
ENZYME_LOST_ANTIGENS = {"Fya", "Fyb", "S", "s", "M", "N"}
NON_ANTIBODY_ANTIGENS = {"DonorN", "Sp Ag"}
EXCLUDED_ANTIGENS = {"Jsa", "V"}


@dataclass(frozen=True)
class CandidateAssessment:
    antibody: str
    antigen: str
    status: str
    score: float
    positive_matches: int
    negative_matches: int
    contradictions: tuple[str, ...]
    screening_matches: int
    screening_contradictions: int


@dataclass(frozen=True)
class StageAssessment:
    stage: str
    status: str
    candidates: tuple[str, ...]
    matching_antigens: tuple[str, ...]
    detail: str
    best_match_count: int = 0
    comparison_count: int = 0
    mismatch_count: int = 0


def assess_candidates(
    antigen_rows: Iterable[Mapping[str, object]],
    result_rows: Iterable[Mapping[str, object]],
    manual_4c: Mapping[str, object] | None = None,
    positive_threshold: int = 1,
) -> list[CandidateAssessment]:
    """Rank single-antibody candidates from panel and screening reactions.

    A candidate predicts positivity when its antigen is present in a reagent cell.
    The returned score is a review priority, not a clinical probability.
    """
    antigen_by_cell: dict[str, dict[str, bool]] = defaultdict(dict)
    screening_cells: set[str] = set()
    for row in antigen_rows:
        cell_id = _cell_id(row.get("cell_id", row.get("ID")))
        antigen = str(row.get("antigen", row.get("ag", ""))).strip()
        if not cell_id or not antigen:
            continue
        antigen_by_cell[cell_id][antigen] = _is_antigen_positive(
            row.get("antigen_value", row.get("vl"))
        )
        marker = str(row.get("screening_cell", row.get("ABScrS", ""))).upper()
        if marker in SCREENING_MARKERS:
            screening_cells.add(cell_id)

    reactions = _collect_reactions(result_rows, manual_4c, positive_threshold)
    assessments = [
        _assess_antigen(antigen, antigen_by_cell, screening_cells, reactions)
        for antigen in sorted({item for values in antigen_by_cell.values() for item in values})
    ]
    return sorted(assessments, key=lambda item: (-item.score, item.antibody))


def assess_stages(
    antigen_rows: Iterable[Mapping[str, object]],
    result_rows: Iterable[Mapping[str, object]],
    manual_4c: Mapping[str, object] | None = None,
    dosage_pairs: set[tuple[str, str]] | None = None,
    enzyme_lost_antigens: set[str] | None = None,
) -> list[StageAssessment]:
    """Evaluate AHG, enzyme, and manual 4C independently for review display."""
    antigen_rows = list(antigen_rows)
    result_rows = list(result_rows)
    dosage_pairs = dosage_pairs or set()
    enzyme_lost_antigens = enzyme_lost_antigens if enzyme_lost_antigens is not None else ENZYME_LOST_ANTIGENS
    auto_control_strength = _auto_control_strength(result_rows)
    auto_control_display = _auto_control_display(result_rows)
    stages = [
        ("AHG", _stage_reactions(result_rows, "AHG", auto_control_strength)),
        ("Enzyme", _stage_reactions(result_rows, "ENZYME")),
        ("4도", _manual_reactions(manual_4c)),
    ]
    enzyme_reactions = stages[1][1]
    assessments: list[StageAssessment] = []
    for stage, reactions in stages:
        assessment = _assess_stage(
                stage,
                antigen_rows,
                reactions,
                dosage_pairs,
                enzyme_lost_antigens,
                enzyme_reactions,
            )
        if stage == "AHG" and auto_control_strength > 0 and assessment.candidates:
            assessment = StageAssessment(
                assessment.stage,
                assessment.status,
                assessment.candidates,
                assessment.matching_antigens,
                f"{assessment.detail}; A/C {auto_control_display} 보정 적용",
                assessment.best_match_count,
                assessment.comparison_count,
                assessment.mismatch_count,
            )
        assessments.append(assessment)
    return assessments


def _assess_stage(
    stage: str,
    antigen_rows: list[Mapping[str, object]],
    reactions: Mapping[str, bool],
    dosage_pairs: set[tuple[str, str]],
    enzyme_lost_antigens: set[str],
    enzyme_reactions: Mapping[str, bool],
) -> StageAssessment:
    profiles: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in antigen_rows:
        cell = _cell_id(row.get("cell_id", row.get("gr")))
        antigen = str(row.get("antigen", row.get("ag", ""))).strip()
        if (
            cell
            and antigen
            and antigen not in NON_ANTIBODY_ANTIGENS
            and antigen not in EXCLUDED_ANTIGENS
        ):
            profiles[antigen][cell] = _is_antigen_positive(
                row.get("antigen_value", row.get("vl"))
            )
    profile_by_cell: dict[str, dict[str, bool]] = defaultdict(dict)
    for antigen, cells in profiles.items():
        for cell, is_positive in cells.items():
            profile_by_cell[cell][antigen] = is_positive

    scores: list[tuple[str, int, int, bool]] = []
    for antigen, profile in profiles.items():
        if stage == "Enzyme" and antigen in enzyme_lost_antigens:
            continue
        enzyme_loss_pending = (
            stage == "AHG"
            and antigen in enzyme_lost_antigens
            and not _enzyme_loss_confirmed(profile, enzyme_reactions)
        )
        effective_reactions = {
            cell: value
            or (
                antigen in _dosage_antigens_for_cell(
                    profile_by_cell, cell, dosage_pairs
                )
            )
            for cell, value in reactions.items()
        }
        if sum(effective_reactions.values()) < 2:
            continue
        compared = [
            profile[cell] == value
            for cell, value in effective_reactions.items()
            if cell in profile
        ]
        if compared:
            scores.append((antigen, sum(compared), len(compared), enzyme_loss_pending))

    if not reactions:
        return StageAssessment(stage, "UNID", (), (), "반응 결과 없음")
    if not any(reactions.values()):
        return StageAssessment(
            stage,
            "UNID",
            (),
            (),
            "실제 양성 반응 없음",
            0,
            len(reactions),
            len(reactions),
        )
    if not scores:
        return StageAssessment(stage, "UNID", (), (), "비교 가능한 항원 없음")
    best_match_count = max(score[1] for score in scores)
    best_scores = [score for score in scores if score[1] == best_match_count]
    best_total = max(score[2] for score in best_scores)
    best_scores = [score for score in best_scores if score[2] == best_total]
    matches = [score[0] for score in best_scores]
    pending_loss = any(score[3] for score in best_scores)
    display_matches = tuple(sorted({display_antigen(antigen) for antigen in matches}))
    mismatch_count = best_total - best_match_count
    expected_cell_count = max(len(profile) for profile in profiles.values())
    if (
        len(matches) == 1
        and mismatch_count == 0
        and best_total == expected_cell_count
        and not pending_loss
    ):
        confirmed_antigen = display_matches[0]
        return StageAssessment(stage, "CONFIRMED", (f"anti-{confirmed_antigen}",), display_matches, "단일 항체 패턴 확정", best_match_count, best_total, mismatch_count)
    if matches:
        candidates = tuple(f"anti-{antigen}" for antigen in display_matches)
        detail = f"최고 일치 {best_match_count}/{best_total}개"
        if pending_loss:
            detail += "; Enzyme 소실 확인 필요"
        if len(matches) > 1:
            detail += "; 복수 후보 또는 복합항체 가능"
        return StageAssessment(stage, "CANDIDATE", candidates, display_matches, detail, best_match_count, best_total, mismatch_count)
    return StageAssessment(stage, "UNID", (), (), f"일치율 부족 ({best_match_count}/{best_total}개)", best_match_count, best_total, mismatch_count)


def _stage_reactions(
    rows: Iterable[Mapping[str, object]],
    target_method: str,
    auto_control_strength: int = 0,
) -> dict[str, bool]:
    reactions: dict[str, bool] = {}
    for row in rows:
        method = classify_method(
            _optional_text(row.get("test_name", row.get("tn"))),
            _optional_text(row.get("order_name", row.get("odr"))),
        )
        if method != target_method:
            continue
        cell = _cell_id(row.get("test_name", row.get("tn")))
        normalized = normalize_result(row.get("result_code", row.get("rst")))
        if cell and normalized.is_positive is not None:
            if target_method == "AHG" and normalized.strength is not None:
                adjusted_strength = max(0, normalized.strength - auto_control_strength)
                reactions[cell] = adjusted_strength >= 1
            else:
                reactions[cell] = normalized.is_positive
    return reactions


def _auto_control_strength(rows: Iterable[Mapping[str, object]]) -> int:
    for row in rows:
        if classify_method(
            _optional_text(row.get("test_name", row.get("tn"))),
            _optional_text(row.get("order_name", row.get("odr"))),
        ) == "AUTO_CONTROL":
            normalized = normalize_result(row.get("result_code", row.get("rst")))
            return normalized.strength or 0
    return 0


def _auto_control_display(rows: Iterable[Mapping[str, object]]) -> str:
    for row in rows:
        if classify_method(
            _optional_text(row.get("test_name", row.get("tn"))),
            _optional_text(row.get("order_name", row.get("odr"))),
        ) == "AUTO_CONTROL":
            return normalize_result(row.get("result_code", row.get("rst"))).display
    return ""


def _manual_reactions(values: Mapping[str, object] | None) -> dict[str, bool]:
    reactions: dict[str, bool] = {}
    for cell, value in (values or {}).items():
        normalized = normalize_result(value)
        if normalized.is_positive is not None:
            reactions[_cell_id(cell)] = normalized.is_positive
    return reactions


def _collect_reactions(
    rows: Iterable[Mapping[str, object]],
    manual_4c: Mapping[str, object] | None,
    positive_threshold: int,
) -> dict[str, list[bool]]:
    reactions: dict[str, list[bool]] = defaultdict(list)
    for row in rows:
        method = classify_method(
            _optional_text(row.get("test_name", row.get("tn"))),
            _optional_text(row.get("order_name", row.get("odr"))),
        )
        cell_id = _cell_id(row.get("test_name", row.get("tn")))
        normalized = normalize_result(row.get("result_code", row.get("rst")), positive_threshold)
        if method in {"AHG", "ENZYME"} and cell_id and normalized.is_positive is not None:
            reactions[cell_id].append(normalized.is_positive)

    for cell_id, raw_value in (manual_4c or {}).items():
        normalized = normalize_result(raw_value, positive_threshold)
        if normalized.is_positive is not None:
            reactions[_cell_id(cell_id)].append(normalized.is_positive)
    return reactions


def _assess_antigen(
    antigen: str,
    antigen_by_cell: Mapping[str, Mapping[str, bool]],
    screening_cells: set[str],
    reactions: Mapping[str, list[bool]],
) -> CandidateAssessment:
    positive_matches = negative_matches = 0
    screening_matches = screening_contradictions = 0
    contradictions: list[str] = []

    for cell_id, observed_reactions in reactions.items():
        present = antigen_by_cell.get(cell_id, {}).get(antigen)
        if present is None:
            continue
        for observed_positive in observed_reactions:
            matches = present == observed_positive
            if cell_id in screening_cells:
                if matches:
                    screening_matches += 1
                else:
                    screening_contradictions += 1
            elif matches and observed_positive:
                positive_matches += 1
            elif matches:
                negative_matches += 1
            else:
                contradictions.append(cell_id)

    panel_total = positive_matches + negative_matches + len(contradictions)
    score = 0.0 if panel_total == 0 else round(100 * (positive_matches + negative_matches) / panel_total, 1)
    if screening_matches + screening_contradictions:
        screening_ratio = (screening_matches - screening_contradictions) / (
            screening_matches + screening_contradictions
        )
        score = round(max(0, min(100, score + 10 * screening_ratio)), 1)

    if panel_total == 0:
        status = "INSUFFICIENT_DATA"
    elif positive_matches >= 2 and negative_matches >= 2 and not contradictions:
        status = "POSSIBLE"
    else:
        status = "EXCLUDED"

    return CandidateAssessment(
        antibody=f"anti-{antigen}",
        antigen=antigen,
        status=status,
        score=score,
        positive_matches=positive_matches,
        negative_matches=negative_matches,
        contradictions=tuple(sorted(set(contradictions))),
        screening_matches=screening_matches,
        screening_contradictions=screening_contradictions,
    )


def _cell_id(value: object) -> str:
    text = _optional_text(value) or ""
    return text.removeprefix("Cell-").strip()


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value).strip()


def _is_antigen_positive(value: object) -> bool:
    return str(value).strip().upper() in {"+", "POS", "POSITIVE", "1", "Y"}


def _dosage_cell_applies(
    profile_by_cell: Mapping[str, Mapping[str, bool]],
    cell: str,
    dosage_pairs: set[tuple[str, str]],
) -> bool:
    profile = profile_by_cell.get(cell, {})
    normalized_profile = {
        display_antigen(antigen): is_positive for antigen, is_positive in profile.items()
    }
    return any(
        normalized_profile.get(first, False) and normalized_profile.get(second, False)
        for first, second in dosage_pairs
    )


def _enzyme_loss_confirmed(
    profile: Mapping[str, bool], enzyme_reactions: Mapping[str, bool]
) -> bool:
    positive_cells = [cell for cell, is_positive in profile.items() if is_positive]
    observed = [enzyme_reactions[cell] for cell in positive_cells if cell in enzyme_reactions]
    return len(observed) >= 2 and all(not is_positive for is_positive in observed)


def _dosage_antigens_for_cell(
    profile_by_cell: Mapping[str, Mapping[str, bool]],
    cell: str,
    dosage_pairs: set[tuple[str, str]],
) -> set[str]:
    if not _dosage_cell_applies(profile_by_cell, cell, dosage_pairs):
        return set()
    profile = profile_by_cell.get(cell, {})
    normalized_profile = {
        display_antigen(antigen): is_positive for antigen, is_positive in profile.items()
    }
    return {
        antigen
        for pair in dosage_pairs
        if normalized_profile.get(pair[0], False) and normalized_profile.get(pair[1], False)
        for antigen in pair
    }
