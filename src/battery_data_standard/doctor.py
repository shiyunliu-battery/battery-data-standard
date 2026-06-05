"""Problem-oriented diagnostics for import failures and uncertain files."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .api import detect, detect_kind, read_eis, read_with_report
from .eis import validate_eis
from .exceptions import BatteryDataStandardError, FileIOError
from .reports import ValidationIssue
from .schema import REQUIRED_COLUMNS, aliases_for


@dataclass
class DoctorReport:
    input_path: str
    status: str
    data_kind: dict[str, Any]
    detection: dict[str, Any] | None = None
    selected_adapter: str | None = None
    confidence: float | None = None
    sheet: str | int | None = None
    source_columns: list[str] = field(default_factory=list)
    canonical_columns: list[str] = field(default_factory=list)
    missing_required_columns: list[str] = field(default_factory=list)
    validation_issues: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)
    suspicious_headers: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    fixture_checklist: list[str] = field(default_factory=list)
    error_type: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_text(self) -> str:
        lines = [
            "BDS doctor",
            f"Input: {self.input_path}",
            f"Status: {self.status}",
            f"Data kind: {self.data_kind.get('kind')} ({self.data_kind.get('confidence')})",
        ]
        if self.selected_adapter:
            lines.append(f"Adapter: {self.selected_adapter} ({self.confidence})")
        if self.sheet:
            lines.append(f"Sheet: {self.sheet}")
        if self.missing_required_columns:
            lines.append("Missing required columns:")
            lines.extend(f"- {column}" for column in self.missing_required_columns)
        if self.validation_issues:
            lines.append("Validation issues:")
            lines.extend(
                f"- {issue.get('code')}: {issue.get('message')}" for issue in self.validation_issues[:10]
            )
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings[:10])
        if self.suspicious_headers:
            lines.append("Suspicious headers:")
            lines.extend(
                f"- {item.get('source')} may be {item.get('target')} (score {item.get('score')})"
                for item in self.suspicious_headers[:10]
            )
        if self.unmapped_columns:
            lines.append("Unmapped columns:")
            lines.append("- " + ", ".join(self.unmapped_columns[:20]))
        if self.detection and self.detection.get("candidates"):
            lines.append("Adapter candidates:")
            for candidate in self.detection["candidates"][:5]:
                lines.append(
                    f"- {candidate.get('cycler')}: {candidate.get('confidence')} ({candidate.get('reason')})"
                )
        if self.error:
            lines.append(f"Error: {self.error_type}: {self.error}")
        if self.suggestions:
            lines.append("Suggested next steps:")
            lines.extend(f"- {suggestion}" for suggestion in self.suggestions)
        if self.fixture_checklist:
            lines.append("Minimum fixture checklist:")
            lines.extend(f"- {item}" for item in self.fixture_checklist)
        return "\n".join(lines)


def doctor(
    path: str | Path,
    *,
    cycler: str | None = "auto",
    profile: str | Path | dict[str, Any] | None = None,
    current_sign: str = "charge-positive",
    current_sign_check: str = "none",
    repair_policy: str = "warn",
    detection_threshold: float = 0.1,
    sheet: str | int | None = None,
) -> DoctorReport:
    """Diagnose why one source file may not convert cleanly."""
    input_path = Path(path)
    if not input_path.exists():
        raise FileIOError(f"Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise FileIOError(f"Input path is not a file: {input_path}")

    kind = detect_kind(input_path, sheet=sheet)
    source_columns = [str(column) for column in kind.evidence.get("columns", [])]
    detection = _safe_detect(input_path)
    fixture_checklist = _fixture_checklist()

    if kind.kind == "unsupported":
        return DoctorReport(
            input_path=str(input_path),
            status="unsupported",
            data_kind=kind.to_dict(),
            detection=detection,
            selected_adapter=(detection or {}).get("cycler"),
            confidence=(detection or {}).get("confidence"),
            sheet=sheet,
            source_columns=source_columns,
            suggestions=[
                "Use a raw time-series or EIS export rather than helper, procedure, label, or summary files.",
                "If this is a real cycler export, share a reduced fixture with original headers and 10-20 rows.",
            ],
            fixture_checklist=fixture_checklist,
        )

    if kind.kind == "eis":
        return _doctor_eis(
            input_path,
            kind.to_dict(),
            detection=detection,
            source_columns=source_columns,
            sheet=sheet,
            fixture_checklist=fixture_checklist,
        )

    try:
        df, report = read_with_report(
            input_path,
            cycler=cycler,
            profile=profile,
            strict=False,
            keep_raw=False,
            current_sign=current_sign,
            current_sign_check=current_sign_check,
            repair_policy=repair_policy,
            detection_threshold=detection_threshold,
            sheet=sheet,
        )
        source_columns = _source_columns(report.metadata, source_columns)
        issues = report.validation.issues
        missing = _missing_required_columns(issues)
        status = "ok" if report.validation.valid else "converted-with-issues"
        return DoctorReport(
            input_path=str(input_path),
            status=status,
            data_kind=kind.to_dict(),
            detection=detection,
            selected_adapter=report.cycler,
            confidence=report.detection_confidence,
            sheet=report.sheet_name or sheet,
            source_columns=source_columns,
            canonical_columns=list(df.columns),
            missing_required_columns=missing,
            validation_issues=[issue.to_dict() for issue in issues if issue.level == "error"][:20],
            warnings=report.warnings,
            unmapped_columns=report.unmapped_columns,
            suspicious_headers=_suspicious_headers(source_columns, missing),
            suggestions=_suggestions(
                status=status,
                input_path=input_path,
                missing_required=missing,
                detection=detection,
                selected_adapter=report.cycler,
                sheet=sheet,
            ),
            fixture_checklist=fixture_checklist,
        )
    except BatteryDataStandardError as exc:
        return DoctorReport(
            input_path=str(input_path),
            status="error",
            data_kind=kind.to_dict(),
            detection=detection,
            selected_adapter=(detection or {}).get("cycler"),
            confidence=(detection or {}).get("confidence"),
            sheet=sheet,
            source_columns=source_columns,
            suspicious_headers=_suspicious_headers(source_columns, list(REQUIRED_COLUMNS)),
            suggestions=_suggestions(
                status="error",
                input_path=input_path,
                missing_required=list(REQUIRED_COLUMNS),
                detection=detection,
                selected_adapter=(detection or {}).get("cycler"),
                sheet=sheet,
            ),
            fixture_checklist=fixture_checklist,
            error_type=type(exc).__name__,
            error=str(exc),
        )


def _doctor_eis(
    input_path: Path,
    kind: dict[str, Any],
    *,
    detection: dict[str, Any] | None,
    source_columns: list[str],
    sheet: str | int | None,
    fixture_checklist: list[str],
) -> DoctorReport:
    try:
        df = read_eis(input_path, sheet=sheet)
        validation = validate_eis(df)
        status = "ok" if validation.valid else "eis-with-issues"
        return DoctorReport(
            input_path=str(input_path),
            status=status,
            data_kind=kind,
            detection=detection,
            selected_adapter="eis",
            sheet=sheet,
            source_columns=source_columns or list(df.columns),
            canonical_columns=list(df.columns),
            validation_issues=[issue.to_dict() for issue in validation.issues],
            suggestions=["Use bds convert-eis to write a standardized EIS table."],
            fixture_checklist=fixture_checklist,
        )
    except BatteryDataStandardError as exc:
        return DoctorReport(
            input_path=str(input_path),
            status="error",
            data_kind=kind,
            detection=detection,
            sheet=sheet,
            source_columns=source_columns,
            suggestions=["Specify --sheet for the EIS worksheet or share a reduced EIS fixture."],
            fixture_checklist=fixture_checklist,
            error_type=type(exc).__name__,
            error=str(exc),
        )


def _safe_detect(path: Path) -> dict[str, Any] | None:
    try:
        return detect(path).to_dict()
    except BatteryDataStandardError:
        return None


def _source_columns(metadata: dict[str, Any], fallback: list[str]) -> list[str]:
    columns = metadata.get("raw_columns")
    if isinstance(columns, list):
        return [str(column) for column in columns]
    return fallback


def _missing_required_columns(issues: list[ValidationIssue]) -> list[str]:
    return [str(issue.column) for issue in issues if issue.code == "missing-required-column" and issue.column]


def _suspicious_headers(source_columns: list[str], missing_required: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for required in missing_required:
        aliases = (required, *aliases_for(required))
        best_source = None
        best_score = 0.0
        for source in source_columns:
            score = max(_similarity(source, alias) for alias in aliases)
            if score > best_score:
                best_source = source
                best_score = score
        if best_source and best_score >= 0.62:
            results.append(
                {
                    "source": best_source,
                    "target": required,
                    "score": round(best_score, 3),
                    "reason": "header is similar to a required canonical column but was not mapped",
                }
            )
    return results


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _slug(left), _slug(right)).ratio()


def _slug(value: str) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _suggestions(
    *,
    status: str,
    input_path: Path,
    missing_required: list[str],
    detection: dict[str, Any] | None,
    selected_adapter: str | None,
    sheet: str | int | None,
) -> list[str]:
    suggestions: list[str] = []
    if missing_required:
        suggestions.append(
            "Rename headers or pass --profile so these required columns map correctly: "
            + ", ".join(missing_required)
            + "."
        )
    if input_path.suffix.lower() in {".xlsx", ".xls"} and sheet is None:
        suggestions.append("If the workbook has multiple sheets, retry with --sheet <sheet-name>.")
    if detection:
        confidence = float(detection.get("confidence") or 0.0)
        if confidence < 0.35:
            suggestions.append("Detection confidence is low; retry with an explicit --cycler value.")
        candidates = detection.get("candidates") or []
        non_generic = [
            item
            for item in candidates
            if item.get("cycler") != "generic" and float(item.get("confidence") or 0.0) > 0
        ]
        if selected_adapter == "generic" and non_generic:
            suggestions.append(
                f"Generic was selected; try --cycler {non_generic[0].get('cycler')} if that matches the file."
            )
    if status == "ok":
        cycler_arg = selected_adapter or "auto"
        suggestions.append(f"Convert with bds convert {input_path} <output.csv> --cycler {cycler_arg}.")
    else:
        suggestions.append(
            "If conversion still fails, attach a reduced anonymized fixture that preserves headers and units."
        )
    return suggestions


def _fixture_checklist() -> list[str]:
    return [
        "Keep the original header rows, column names, units, and sheet name.",
        "Keep 10-20 representative data rows around the failing region.",
        "Preserve time, voltage, current, status/step type, cycle, step, capacity, energy, and temperature columns when present.",
        "Remove cell IDs, customer names, procedure names, comments, paths, and other commercial identifiers.",
        "State the cycler vendor/software/export settings and whether the reduced fixture may become a public regression test.",
    ]


def _clean(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, tuple):
        return [_clean(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    return value
