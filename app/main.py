"""Local web interface for antibody identification review."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
import logging
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.db.repository import (
    get_sample_directory_entry,
    get_antigen_rows,
    closest_valid_lot_on,
    get_ident_test_date,
    get_latest_result_rows,
    list_antigen_rules,
    list_dosage_pairs,
    initialize_database,
    list_lot_numbers,
    list_lot_numbers_valid_on,
    list_lot_options_valid_on,
    list_review_results,
    list_sample_directory,
    list_sample_ids,
    open_database,
    save_review_result,
    save_sample_directory,
    replace_antigen_rules,
    replace_dosage_pairs,
)
from app.services.identification import assess_stages
from app.services.result_normalizer import classify_method, display_antigen, normalize_result
from app.services.sync import MySqlMiddlewareSource, mysql_connection_status, synchronize_sample


BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    connection = open_database(settings.sqlite_path)
    initialize_database(connection)
    connection.close()
    yield


app = FastAPI(title="Ab ID Review", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    end_date = date.today()
    return _render(request, start_date=(end_date - timedelta(days=6)).isoformat(), end_date=end_date.isoformat())


@app.post("/load-ids", response_class=HTMLResponse)
def load_ids(
    request: Request,
    start_date: str = Form(...),
    end_date: str = Form(...),
):
    logger.info("ID load requested: %s through %s", start_date, end_date)
    try:
        source = MySqlMiddlewareSource(get_settings())
        sample_ids = source.fetch_id_sample_ids(start_date, end_date)
        connection = open_database(get_settings().sqlite_path)
        try:
            save_sample_directory(connection, sample_ids)
        finally:
            connection.close()
    except Exception as error:
        logger.exception("ID load failed: %s", type(error).__name__)
        return _render(
            request,
            start_date=start_date,
            end_date=end_date,
            message="MySQL에서 ID 검체번호를 불러오지 못했습니다. 연결 설정과 검사기간을 확인하세요.",
        )
    return _render(
        request,
        available_sample_ids=sample_ids,
        start_date=start_date,
        end_date=end_date,
        message=f"ID 검체번호 {len(sample_ids)}건을 불러왔습니다.",
    )


@app.post("/load-results", response_class=HTMLResponse)
def load_results(
    request: Request,
    sample_id: str = Form(...),
    start_date: str = Form(""),
    end_date: str = Form(""),
):
    logger.info("Result load requested: sample_id=%s", sample_id)
    try:
        settings = get_settings()
        connection = open_database(settings.sqlite_path)
        try:
            synchronize_sample(connection, MySqlMiddlewareSource(settings), sample_id)
        finally:
            connection.close()
    except Exception as error:
        logger.exception("Result load failed for sample_id=%s: %s", sample_id, type(error).__name__)
        return _render(
            request,
            available_sample_ids=[
                {"sample_id": sample_id, "test_date": "", "patient_name": "", "patient_id": ""}
            ],
            start_date=start_date,
            end_date=end_date,
            message="MySQL에서 검사 결과를 불러오지 못했습니다. 연결 설정을 확인하세요.",
        )
    sample_options = MySqlMiddlewareSource(get_settings()).fetch_id_sample_ids(start_date, end_date)
    connection = open_database(get_settings().sqlite_path)
    try:
        save_sample_directory(connection, sample_options)
    finally:
        connection.close()
    return _render(
        request,
        available_sample_ids=sample_options,
        sample_id=sample_id,
        start_date=start_date,
        end_date=end_date,
        message="결과를 불러왔습니다. 유효한 Surgiscreen lot을 선택한 뒤 분석하세요.",
    )


@app.post("/analyze", response_class=HTMLResponse)
def analyze(
    request: Request,
    sample_id: str = Form(...),
    id_lot_number: str = Form(...),
    screening_lot_number: str = Form(...),
    four_c_values: list[str] = Form([]),
    start_date: str = Form(""),
    end_date: str = Form(""),
):
    manual_4c = _parse_4c_values(four_c_values)
    return _render(
        request,
        sample_id,
        id_lot_number,
        screening_lot_number,
        manual_4c,
        start_date=start_date,
        end_date=end_date,
    )


@app.post("/save-review", response_class=HTMLResponse)
def save_review(
    request: Request,
    sample_id: str = Form(...),
    id_lot_number: str = Form(...),
    screening_lot_number: str = Form(...),
    four_c_values: list[str] = Form([]),
    final_antibody: str = Form(""),
    final_interpretation: str = Form(""),
    reviewer_note: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
):
    manual_4c = _parse_4c_values(four_c_values)
    connection = open_database(get_settings().sqlite_path)
    try:
        review_id = save_review_result(
            connection,
            sample_id,
            id_lot_number,
            screening_lot_number,
            manual_4c,
            final_antibody,
            final_interpretation,
            reviewer_note,
            datetime.now(UTC).isoformat(timespec="seconds"),
        )
    finally:
        connection.close()
    return _render(
        request,
        sample_id,
        id_lot_number,
        screening_lot_number,
        manual_4c,
        start_date=start_date,
        end_date=end_date,
        message=f"확정 결과 #{review_id}를 SQLite에 저장했습니다.",
    )


@app.post("/save-antigen-rules", response_class=HTMLResponse)
def save_antigen_rules(
    request: Request,
    enzyme_lost_antigens: str = Form(""),
    dosage_pairs: list[str] = Form([]),
):
    pairs = []
    for pair in dosage_pairs:
        values = [value.strip() for value in pair.split(",")]
        if len(values) == 2:
            pairs.append((values[0], values[1]))
    dosage_antigens = {antigen for pair in pairs for antigen in pair}
    connection = open_database(get_settings().sqlite_path)
    try:
        replace_antigen_rules(
            connection,
            dosage_antigens,
            enzyme_lost_antigens.split(","),
        )
        replace_dosage_pairs(connection, pairs)
    finally:
        connection.close()
    return _render(request, message="항원 기준정보를 SQLite에 저장했습니다.")


def _render(
    request: Request,
    sample_id: str | None = None,
    id_lot_number: str | None = None,
    screening_lot_number: str | None = None,
    manual_4c: dict[str, str] | None = None,
    four_c_text: str = "",
    available_sample_ids: list[dict[str, object]] | None = None,
    start_date: str = "",
    end_date: str = "",
    message: str | None = None,
):
    settings = get_settings()
    mysql_connected = mysql_connection_status(settings)
    connection = open_database(settings.sqlite_path)
    try:
        stored_sample_ids = list_sample_ids(connection)
        directory_samples = list_sample_directory(connection)
        sample_ids = available_sample_ids if available_sample_ids is not None else (
            directory_samples
            or [
                {"sample_id": item, "test_date": "", "patient_name": "", "patient_id": ""}
                for item in stored_sample_ids
            ]
        )
        id_test_date = get_ident_test_date(connection, sample_id) if sample_id else None
        id_lot_numbers = (
            list_lot_numbers_valid_on(connection, id_test_date, "ID")
            if id_test_date
            else []
        )
        screening_lot_numbers = (
            list_lot_numbers_valid_on(connection, id_test_date, "ABScrS")
            if id_test_date
            else []
        )
        if id_test_date and not id_lot_number:
            id_lot_number = closest_valid_lot_on(connection, id_test_date, "ID")
        if id_test_date and not screening_lot_number:
            screening_lot_number = closest_valid_lot_on(connection, id_test_date, "ABScrS")
        id_lot_options = (
            list_lot_options_valid_on(connection, id_test_date, "ID")
            if id_test_date
            else []
        )
        screening_lot_options = (
            list_lot_options_valid_on(connection, id_test_date, "ABScrS")
            if id_test_date
            else []
        )
        id_antigen_rows = (
            get_antigen_rows(connection, id_lot_number, "ID") if id_lot_number else []
        )
        screening_antigen_rows = (
            get_antigen_rows(connection, screening_lot_number, "ABScrS")
            if screening_lot_number
            else []
        )
        result_rows = get_latest_result_rows(connection, sample_id) if sample_id else []
        review_results = list_review_results(connection, sample_id) if sample_id else []
        selected_patient = get_sample_directory_entry(connection, sample_id) if sample_id else None
        antigen_rules = list_antigen_rules(connection)
        dosage_pair_rows = list_dosage_pairs(connection)
    finally:
        connection.close()

    id_matrix = _matrix(id_antigen_rows, result_rows, manual_4c or {}, cell_count=11)
    screening_matrix = _matrix(screening_antigen_rows, result_rows, {}, cell_count=3)
    antigram_columns = _antigram_columns(id_matrix + screening_matrix)
    dosage_pairs = {
        (str(pair["antigen_one"]), str(pair["antigen_two"]))
        for pair in dosage_pair_rows
    }
    screening_matches = _matching_antigens(screening_matrix, dosage_pairs)
    auto_control = _auto_control(result_rows)
    enzyme_lost_antigens = {str(rule["antigen"]) for rule in antigen_rules if rule["enzyme_lost"]}
    id_stage_assessments = assess_stages(
        id_antigen_rows,
        result_rows,
        manual_4c,
        dosage_pairs=dosage_pairs,
        enzyme_lost_antigens=enzyme_lost_antigens,
    )
    id_stage_matches = {
        assessment.stage: {_display_antigen(antigen) for antigen in assessment.matching_antigens}
        for assessment in id_stage_assessments
    }
    return templates.TemplateResponse(
        request,
        "analysis.html",
        {
            "sample_ids": sample_ids,
            "id_lot_numbers": id_lot_numbers,
            "screening_lot_numbers": screening_lot_numbers,
            "id_lot_options": id_lot_options,
            "screening_lot_options": screening_lot_options,
            "selected_sample_id": sample_id,
            "selected_id_lot_number": id_lot_number,
            "selected_screening_lot_number": screening_lot_number,
            "id_matrix": id_matrix,
            "screening_matrix": screening_matrix,
            "antigram_columns": antigram_columns,
            "four_c_values": _four_c_display_values(manual_4c),
            "start_date": start_date,
            "end_date": end_date,
            "message": message,
            "id_test_date": id_test_date,
            "mysql_connected": mysql_connected,
            "show_empty_state": bool(
                sample_id and id_lot_number and screening_lot_number and not id_matrix
            ),
            "review_results": review_results,
            "selected_patient": selected_patient,
            "auto_control": auto_control,
            "screening_matches": screening_matches,
            "id_stage_assessments": id_stage_assessments,
            "id_stage_matches": id_stage_matches,
            "antigen_rules": antigen_rules,
            "dosage_pair_rows": dosage_pair_rows,
        },
    )


def _matrix(antigen_rows, result_rows, manual_4c, cell_count: int):
    by_cell: dict[str, dict[str, object]] = {
        str(cell): {"cell": str(cell), "antigens": {}, "reactions": {}, "special": ""}
        for cell in range(1, cell_count + 1)
    }
    fallback_positions: dict[str, int] = {}
    donor_numbers: dict[str, str] = {}
    for row in antigen_rows:
        antigen = _display_antigen(row["antigen"])
        cell = str(row.get("cell_id") or "")
        if not cell:
            fallback_positions[antigen] = fallback_positions.get(antigen, 0) + 1
            cell = str(fallback_positions[antigen])
            logger.warning(
                "Antigen row missing a resolvable cell id; assigning sequential fallback "
                "position: antigen=%s fallback_cell=%s",
                antigen,
                cell,
            )
        if cell not in by_cell:
            continue
        value = row["antigen_value"]
        if antigen == "DonorN":
            donor_numbers[cell] = str(value)
            continue
        by_cell[cell]["antigens"][antigen] = value
        if cell_count == 3 and antigen == "Sp Ag" and "Di(a+" in str(value).replace(" ", ""):
            by_cell[cell]["special"] = "Di(a+)"

    for cell, donor_number in donor_numbers.items():
        by_cell[cell]["donor_number"] = donor_number

    for row in result_rows:
        method = classify_method(row["test_name"], row["order_name"])
        if method == "AUTO_CONTROL":
            continue
        cell = str(row["test_name"]).removeprefix("Cell-")
        if cell_count == 3 and row["test_name"] in {"Surg 1", "Surg 2", "Surg 3"}:
            cell = row["test_name"].removeprefix("Surg ")
            method = "SCREENING"
        if method not in {"AHG", "ENZYME", "SCREENING"}:
            continue
        if cell in by_cell:
            by_cell[cell]["reactions"][method] = normalize_result(row["result_code"]).display
    for cell, raw_value in manual_4c.items():
        if cell in by_cell:
            by_cell[cell]["reactions"]["4C"] = normalize_result(raw_value).display

    return list(by_cell.values()) if antigen_rows else []


def _auto_control(result_rows: list[dict[str, object]]) -> str:
    for row in result_rows:
        if classify_method(row["test_name"], row["order_name"]) == "AUTO_CONTROL":
            return normalize_result(row["result_code"]).display
    return ""


def _matching_antigens(
    matrix: list[dict[str, object]], dosage_pairs: set[tuple[str, str]] | None = None
) -> set[str]:
    if len(matrix) != 3 or not all(row["reactions"].get("SCREENING") for row in matrix):
        return set()
    matches: set[str] = set()
    antigen_names = {antigen for row in matrix for antigen in row["antigens"]}
    for antigen in antigen_names:
        if antigen in {"Jsa", "V"}:
            continue
        aligned = True
        for row in matrix:
            antigen_positive = _is_antigen_positive(row["antigens"].get(antigen))
            result_positive = _is_result_positive(row["reactions"]["SCREENING"])
            if not result_positive and _dosage_pair_positive(row, antigen, dosage_pairs or set()):
                result_positive = True
            if antigen_positive != result_positive:
                aligned = False
                break
        if aligned:
            matches.add(antigen)
    return matches


def _dosage_pair_positive(
    row: dict[str, object], antigen: str, dosage_pairs: set[tuple[str, str]]
) -> bool:
    antigen_values = row["antigens"]
    return any(
        antigen in pair
        and all(_is_antigen_positive(antigen_values.get(member)) for member in pair)
        for pair in dosage_pairs
    )


def _is_antigen_positive(value: object) -> bool:
    normalized = str(value or "").replace(" ", "").lower()
    return normalized not in {"", "0", "-", "/", "negative", "n"}


def _is_result_positive(value: object) -> bool:
    return str(value or "").strip().lower() not in {"", "n", "negative"}


def _antigram_columns(matrix: list[dict[str, object]]) -> list[str]:
    column_order = [
        "D", "C", "E", "c", "e", "f", "Cw", "V", "K", "k", "Kpa", "Kpb",
        "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Xga", "Lea", "Leb", "S", "s",
        "M", "N", "P1", "Lua", "Lub",
    ]
    available = {antigen for row in matrix for antigen in row["antigens"]}
    ordered = [antigen for antigen in column_order if antigen in available]
    return ordered + sorted(available - set(ordered))


# Kept as a module-level alias so existing imports (and tests) of the
# antigen-display helper by its historical name keep working.
_display_antigen = display_antigen


def _parse_4c_values(values: list[str]) -> dict[str, str]:
    reaction_codes = {"0": "0", "0.5": "5", "1": "10", "2": "20", "3": "30", "4": "40"}
    return {
        str(cell): reaction_codes[value.strip()]
        for cell, value in enumerate(values[:11], start=1)
        if value.strip() in reaction_codes
    }


def _four_c_display_values(values: dict[str, str] | None) -> list[str]:
    display_codes = {"0": "0", "5": "0.5", "10": "1", "20": "2", "30": "3", "40": "4"}
    return [display_codes.get(values.get(str(cell), ""), "") if values else "" for cell in range(1, 12)]