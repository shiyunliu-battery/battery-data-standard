"""Data-kind detection for batch routing."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .eis import looks_like_eis_columns
from .exceptions import BatteryDataStandardError
from .io import read_table_with_metadata, sample_text, xlsx_sheet_names
from .schema import CANONICAL_COLUMNS, canonical_label_for


@dataclass
class DataKindResult:
    kind: str
    confidence: float
    reason: str
    path: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


UNSUPPORTED_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpg",
    ".jpeg",
    ".md",
    ".pdf",
    ".png",
    ".py",
    ".m",
    ".mp4",
    ".avi",
    ".tif",
    ".tiff",
}
UNSUPPORTED_NAME_MARKERS = (
    "readme",
    "requirements",
    "license",
    "label",
    "labels",
    "summary",
    "datasheet",
    "specification",
    "manufacturer",
    "figure",
    "plot",
    "codebook",
    "metadata",
    "schedule",
    "procedure",
    "[stats]",
)
UNSUPPORTED_COLUMN_MARKERS = (
    "rmse",
    "label",
    "feature",
    "trajectory_metrics",
    "capacity degradation",
    "model",
    "parameter",
)


def detect_kind(path: str | Path, *, sheet: str | int | None = None) -> DataKindResult:
    input_path = Path(path)
    suffix = input_path.suffix.lower()
    name = input_path.name.lower()
    if suffix in UNSUPPORTED_SUFFIXES:
        return DataKindResult(
            "unsupported",
            0.95,
            f"file suffix {suffix} is not a tabular battery data format",
            str(input_path),
        )
    if any(marker in name for marker in UNSUPPORTED_NAME_MARKERS):
        return DataKindResult(
            "unsupported",
            0.85,
            "file name looks like documentation, labels, metadata, or helper output",
            str(input_path),
        )
    sample = sample_text(input_path, limit=8192).lower()
    if "<maccortestprocedure" in sample or "maccor procedure file" in sample:
        return DataKindResult(
            "unsupported",
            0.95,
            "file looks like a Maccor procedure/schedule rather than measurement data",
            str(input_path),
        )
    if suffix in {".xls", ".xlsx"}:
        neware_excel_kind = _detect_neware_excel_kind(input_path, sheet=sheet)
        if neware_excel_kind is not None:
            return neware_excel_kind

    try:
        result = read_table_with_metadata(input_path, options={"sheet": sheet})
    except BatteryDataStandardError as exc:
        return DataKindResult("unknown", 0.0, str(exc), str(input_path))
    except OSError as exc:
        return DataKindResult("unknown", 0.0, str(exc), str(input_path))

    columns = [str(column) for column in result.data.columns]
    if looks_like_eis_columns(columns):
        return DataKindResult(
            "eis",
            0.95,
            "frequency and complex impedance columns detected",
            str(input_path),
            {"columns": columns},
        )
    if _looks_like_unsupported_table(columns):
        return DataKindResult(
            "unsupported",
            0.75,
            "table columns look like metadata, labels, figures, model outputs, or capacity-only summaries",
            str(input_path),
            {"columns": columns},
        )
    if _looks_like_timeseries(columns):
        if suffix in {".xls", ".xlsx"} and result.data.height <= 1:
            eis_excel_kind = _detect_eis_excel_kind(input_path, sheet=sheet)
            if eis_excel_kind is not None:
                return eis_excel_kind
        return DataKindResult(
            "timeseries",
            0.8,
            "time, voltage, and current-like columns detected",
            str(input_path),
            {"columns": columns},
        )

    if suffix in {".xls", ".xlsx"}:
        eis_excel_kind = _detect_eis_excel_kind(input_path, sheet=sheet)
        if eis_excel_kind is not None:
            return eis_excel_kind

    if "frequency" in sample and ("impedance" in sample or "re(z)" in sample or "zim" in sample):
        return DataKindResult("eis", 0.6, "EIS tokens detected in file sample", str(input_path))
    return DataKindResult(
        "unknown", 0.2, "no known data-kind signature detected", str(input_path), {"columns": columns}
    )


def _looks_like_timeseries(columns: list[str]) -> bool:
    labels = _canonical_labels(columns)
    slugs = {_slug(column) for column in columns}
    has_time = bool({"test_time_s", "date_time", "unix_time_s"} & labels) or any(
        token in slug
        for slug in slugs
        for token in ("time", "timestamp", "datetime", "testtim", "testtime", "runtime")
    )
    has_voltage = "voltage_v" in labels or any(
        token in slug
        for slug in slugs
        for token in ("voltage", "volt", "potential", "ewe", "ecell", "ubattery", "v5", "uv")
    )
    has_current = "current_a" in labels or any(
        token in slug for slug in slugs for token in ("current", "curr", "ampere", "ibattery", "ia", "cur")
    )
    return has_time and has_voltage and has_current


def _canonical_labels(columns: list[str]) -> set[str]:
    labels: set[str] = set()
    for column in columns:
        label = canonical_label_for(column) or _canonical_label_from_slug(column)
        if label is not None:
            labels.add(label)
    return labels


def _canonical_label_from_slug(column: str) -> str | None:
    column_slug = _slug(column)
    for spec in CANONICAL_COLUMNS:
        for alias in (spec.label, spec.machine_name, *spec.aliases):
            if column_slug == _slug(alias):
                return spec.label
    return None


def _looks_like_unsupported_table(columns: list[str]) -> bool:
    if not columns:
        return True
    slug_text = " ".join(_slug(column) for column in columns)
    if any(marker.replace(" ", "") in slug_text for marker in UNSUPPORTED_COLUMN_MARKERS):
        return True
    has_capacity = "capacity" in slug_text or "cap" in slug_text
    has_voltage = "voltage" in slug_text or "volt" in slug_text
    has_current = "current" in slug_text or "amp" in slug_text
    has_time = "time" in slug_text or "date" in slug_text
    return has_capacity and not (has_voltage and has_current and has_time)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _detect_neware_excel_kind(path: Path, *, sheet: str | int | None) -> DataKindResult | None:
    try:
        if path.suffix.lower() == ".xlsx":
            sheet_names = xlsx_sheet_names(path)
        else:
            import pandas as pd

            sheet_names = [str(name) for name in pd.ExcelFile(path).sheet_names]
    except Exception:
        return None

    if sheet is not None:
        selected = str(sheet)
        if _is_neware_detail_sheet(selected):
            return DataKindResult(
                "timeseries",
                0.9,
                "NEWARE Detail sheet detected",
                str(path),
                {"selected_sheets": [selected]},
            )
        if _is_neware_record_sheet(selected):
            return DataKindResult(
                "timeseries",
                0.9,
                "NEWARE record sheet detected",
                str(path),
                {"selected_sheets": [selected]},
            )
        if _is_neware_auxiliary_sheet(selected):
            return DataKindResult(
                "unsupported",
                0.9,
                "NEWARE auxiliary DetailTemp/DetailVol sheet requires the primary Detail sheet",
                str(path),
                {"selected_sheets": [selected]},
            )
        return None

    detail_sheets = [name for name in sheet_names if _is_neware_detail_sheet(name)]
    if detail_sheets:
        return DataKindResult(
            "timeseries",
            0.9,
            "NEWARE Detail sheet(s) detected",
            str(path),
            {"selected_sheets": detail_sheets},
        )
    record_sheets = [name for name in sheet_names if _is_neware_record_sheet(name)]
    if record_sheets:
        return DataKindResult(
            "timeseries",
            0.9,
            "NEWARE record sheet(s) detected",
            str(path),
            {"selected_sheets": record_sheets},
        )
    auxiliary_sheets = [name for name in sheet_names if _is_neware_auxiliary_sheet(name)]
    if auxiliary_sheets:
        return DataKindResult(
            "unsupported",
            0.9,
            "NEWARE auxiliary-only workbook requires the primary workbook with Detail sheets",
            str(path),
            {"auxiliary_sheets": auxiliary_sheets},
        )
    return None


def _detect_eis_excel_kind(path: Path, *, sheet: str | int | None) -> DataKindResult | None:
    try:
        if path.suffix.lower() == ".xlsx":
            sheet_names = xlsx_sheet_names(path)
        else:
            import pandas as pd

            sheet_names = [str(name) for name in pd.ExcelFile(path).sheet_names]
    except Exception:
        return None

    if sheet is not None:
        selected = str(sheet)
        if _is_eis_sheet(selected):
            return DataKindResult(
                "eis",
                0.9,
                "EIS worksheet detected",
                str(path),
                {"selected_sheets": [selected]},
            )
        return None

    eis_sheets = [name for name in sheet_names if _is_eis_sheet(name)]
    if not eis_sheets:
        return None
    return DataKindResult(
        "eis",
        0.9,
        "EIS worksheet detected",
        str(path),
        {"selected_sheets": eis_sheets},
    )


def _is_eis_sheet(name: str) -> bool:
    clean = str(name).strip().lower()
    return clean.startswith("acim") or "impedance" in clean or clean in {"eis", "eis data"}


def _is_neware_detail_sheet(name: str) -> bool:
    clean = str(name).strip().lower()
    return (
        (clean == "detail" or clean.startswith("detail_") or clean.startswith("detail "))
        and not clean.startswith("detailvol")
        and not clean.startswith("detailtemp")
    )


def _is_neware_record_sheet(name: str) -> bool:
    clean = str(name).strip().lower()
    return clean == "record" or clean.startswith("record_") or clean.startswith("record ")


def _is_neware_auxiliary_sheet(name: str) -> bool:
    clean = str(name).strip().lower()
    return clean.startswith("detailvol") or clean.startswith("detailtemp")
