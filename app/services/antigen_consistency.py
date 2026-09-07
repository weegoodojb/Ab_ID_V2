"""Cross-check identified antibody candidates against the patient's own antigen typing.

An alloantibody specificity implies the patient should be negative for that
antigen — a patient does not make an alloantibody against an antigen they
carry themselves. This module only ever surfaces a warning, never a hard
block: the reviewer decides what a contradiction means (mistyping,
autoantibody, recent transfusion, etc.).
"""

from __future__ import annotations

from collections.abc import Mapping


POSITIVE_RESULT = "양성"


def check_antigen_consistency(
    candidate_antigens: set[str],
    patient_antigen_results: Mapping[str, str],
) -> list[str]:
    """Warn for any candidate antigen the patient is recorded as carrying."""
    return [
        f"환자가 {antigen} 항원 양성인데 anti-{antigen}이(가) 후보로 제시됨 "
        "— 자가항체 가능성 또는 재검토 필요"
        for antigen in sorted(candidate_antigens)
        if patient_antigen_results.get(antigen) == POSITIVE_RESULT
    ]
