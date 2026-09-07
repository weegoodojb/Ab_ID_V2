"""Normalize analyzer result codes into display and analysis values."""

from __future__ import annotations

from dataclasses import dataclass


RESULT_CODES: dict[str, tuple[str, int]] = {
    "0": ("N", 0),
    "5": ("trace", 1),
    "10": ("1+", 2),
    "20": ("2+", 3),
    "30": ("3+", 4),
    "40": ("4+", 5),
}

AHG_ODR = "0.8% PanelC Unt w/Auto"
AHG_ODR_VARIANTS = {AHG_ODR, "0.8% PanelC Unt"}
ENZYME_ODR = "0.8% PanelC Enz"

ANTIGEN_DISPLAY_ALIASES: dict[str, str] = {
    "BC": "C",
    "BE": "E",
    "SC": "c",
    "SE": "e",
    "NK": "K",
    "SK": "k",
    "BS": "S",
    "SS": "s",
}


@dataclass(frozen=True)
class NormalizedResult:
    raw_value: str | None
    display: str
    strength: int | None
    is_positive: bool | None


def normalize_result(raw_value: object, positive_threshold: int = 1) -> NormalizedResult:
    """Convert middleware result codes to a comparable reaction result."""
    if raw_value is None:
        return NormalizedResult(None, "", None, None)

    value = str(raw_value).strip()
    if value == "":
        return NormalizedResult(value, "", None, None)

    code = RESULT_CODES.get(value)
    if code is None:
        return NormalizedResult(value, value, None, None)

    display, strength = code
    return NormalizedResult(value, display, strength, strength >= positive_threshold)


def classify_method(test_name: str | None, order_name: str | None) -> str | None:
    """Classify a middleware row by its configured analyzer method."""
    if test_name == "Auto":
        return "AUTO_CONTROL"
    if order_name in AHG_ODR_VARIANTS:
        return "AHG"
    if order_name == ENZYME_ODR:
        return "ENZYME"
    return None


def display_antigen(value: object) -> str:
    """Map middleware antigen abbreviations to their conventional display symbol."""
    antigen = str(value).strip()
    return ANTIGEN_DISPLAY_ALIASES.get(antigen.upper(), antigen)
