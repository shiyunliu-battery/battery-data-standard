"""Batch intake audit and quality scoring."""

from __future__ import annotations

import html
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

import polars as pl

from .api import detect, detect_kind, read_eis, read_with_report
from .archive import is_supported_source_path
from .eis import validate_eis
from .io import write_json
from .reports import ColumnProvenance, ValidationIssue
from .schema import OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from .validation import validate


@dataclass
class AuditIssue:
    level: str
    code: str
    message: str
    column: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditRecord:
    input_path: str
    relative_path: str
    status: str
    data_kind: str
    quality_score: int
    quality_grade: str
    cycler: str | None = None
    schema: str | None = None
    rows: int | None = None
    columns: list[str] = field(default_factory=list)
    detection_confidence: float | None = None
    kind_confidence: float | None = None
    missing_required_columns: list[str] = field(default_factory=list)
    completeness: dict[str, Any] = field(default_factory=dict)
    unit_repairs: list[dict[str, Any]] = field(default_factory=list)
    repair_operations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    current_sign: str | None = None
    current_sign_evidence: str | None = None
    checks: dict[str, Any] = field(default_factory=dict)
    issues: list[AuditIssue] = field(default_factory=list)
    error_type: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["issues"] = [issue.to_dict() for issue in self.issues]
        return data


@dataclass
class AuditReport:
    input_path: str
    files: int
    converted: int
    eis: int
    unsupported: int
    errors: int
    average_score: float
    cycler_counts: dict[str, int]
    kind_counts: dict[str, int]
    status_counts: dict[str, int]
    top_issue_codes: dict[str, int]
    records: list[AuditRecord]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        return data

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def audit(
    path: str | Path,
    *,
    recursive: bool = False,
    cycler: str | None = "auto",
    profile: str | Path | dict[str, Any] | None = None,
    current_sign: str = "charge-positive",
    repair_policy: str = "warn",
    detection_threshold: float = 0.1,
    sheet: str | int | None = None,
    json_path: str | Path | None = None,
    html_path: str | Path | None = None,
) -> AuditReport:
    """Audit raw cycler files and optionally write JSON and HTML reports."""
    input_path = Path(path)
    sources = _audit_sources(input_path, recursive=recursive)
    records = [
        audit_file(
            source,
            root=input_path if input_path.is_dir() else input_path.parent,
            cycler=cycler,
            profile=profile,
            current_sign=current_sign,
            repair_policy=repair_policy,
            detection_threshold=detection_threshold,
            sheet=sheet,
        )
        for source in sources
    ]
    report = _build_report(input_path, records)
    if json_path is not None:
        write_json(json_path, report.to_dict())
    if html_path is not None:
        _write_html_report(report, html_path)
    return report


def audit_file(
    path: str | Path,
    *,
    root: str | Path | None = None,
    cycler: str | None = "auto",
    profile: str | Path | dict[str, Any] | None = None,
    current_sign: str = "charge-positive",
    repair_policy: str = "warn",
    detection_threshold: float = 0.1,
    sheet: str | int | None = None,
) -> AuditRecord:
    """Audit one file without writing converted output."""
    input_path = Path(path)
    relative_path = _relative_path(input_path, Path(root) if root is not None else input_path.parent)
    issues: list[AuditIssue] = []
    try:
        kind = detect_kind(input_path, sheet=sheet)
    except Exception as exc:
        return _error_record(input_path, relative_path, "unknown", "DetectionError", str(exc))

    if kind.kind == "unsupported":
        issues.append(AuditIssue("info", "unsupported-file", kind.reason))
        return AuditRecord(
            input_path=str(input_path),
            relative_path=relative_path,
            status="unsupported",
            data_kind=kind.kind,
            kind_confidence=kind.confidence,
            quality_score=0,
            quality_grade=_grade(0),
            issues=issues,
        )

    if kind.kind == "eis":
        return _audit_eis_file(input_path, relative_path, kind.confidence, sheet=sheet)

    try:
        detection = detect(input_path)
        df, report = read_with_report(
            input_path,
            cycler=cycler,
            profile=profile,
            strict=False,
            keep_raw=False,
            current_sign=current_sign,
            repair_policy=repair_policy,
            detection_threshold=detection_threshold,
            sheet=sheet,
        )
        validation = validate(df, strict=False)
        checks = _quality_checks(df)
        validation_issues = _quality_scored_validation_issues(validation.issues)
        issues.extend(_validation_issues(validation_issues))
        issues.extend(_check_issues(checks))
        missing = [
            issue.column
            for issue in validation.issues
            if issue.code == "missing-required-column" and issue.column is not None
        ]
        completeness = _completeness(validation.issues)
        unit_repairs = _unit_repairs(report.provenance)
        current_evidence = _current_sign_evidence(report.provenance, report.warnings)
        score = _score_record(
            status="converted",
            detection_confidence=report.detection_confidence or detection.confidence,
            validation_issues=validation_issues,
            audit_issues=issues,
            warnings=report.warnings,
            repair_operations=report.repair_operations,
            unit_repairs=unit_repairs,
            current_sign_evidence=current_evidence,
        )
        return AuditRecord(
            input_path=str(input_path),
            relative_path=relative_path,
            status="converted" if validation.valid else "converted-with-issues",
            data_kind=kind.kind,
            kind_confidence=kind.confidence,
            quality_score=score,
            quality_grade=_grade(score),
            cycler=report.cycler,
            schema=report.schema_version,
            rows=report.rows,
            columns=report.columns,
            detection_confidence=report.detection_confidence or detection.confidence,
            missing_required_columns=missing,
            completeness=completeness,
            unit_repairs=unit_repairs,
            repair_operations=report.repair_operations,
            warnings=report.warnings,
            current_sign=report.current_sign,
            current_sign_evidence=current_evidence,
            checks=checks,
            issues=issues,
        )
    except Exception as exc:
        score = 0
        issues.append(AuditIssue("error", "conversion-error", str(exc)))
        return AuditRecord(
            input_path=str(input_path),
            relative_path=relative_path,
            status="error",
            data_kind=kind.kind,
            kind_confidence=kind.confidence,
            quality_score=score,
            quality_grade=_grade(score),
            issues=issues,
            error_type=type(exc).__name__,
            error=str(exc),
        )


def _audit_eis_file(
    input_path: Path, relative_path: str, kind_confidence: float, *, sheet: str | int | None
) -> AuditRecord:
    issues: list[AuditIssue] = []
    try:
        df = read_eis(input_path, sheet=sheet)
        validation = validate_eis(df)
        issues.extend(_validation_issues(validation.issues))
        score = _score_record(
            status="eis",
            detection_confidence=kind_confidence,
            validation_issues=validation.issues,
            audit_issues=issues,
            warnings=[],
            repair_operations=[],
            unit_repairs=[],
            current_sign_evidence=None,
        )
        return AuditRecord(
            input_path=str(input_path),
            relative_path=relative_path,
            status="eis",
            data_kind="eis",
            kind_confidence=kind_confidence,
            quality_score=score,
            quality_grade=_grade(score),
            schema="eis",
            rows=df.height,
            columns=list(df.columns),
            issues=issues,
        )
    except Exception as exc:
        issues.append(AuditIssue("error", "eis-conversion-error", str(exc)))
        return AuditRecord(
            input_path=str(input_path),
            relative_path=relative_path,
            status="error",
            data_kind="eis",
            kind_confidence=kind_confidence,
            quality_score=0,
            quality_grade=_grade(0),
            issues=issues,
            error_type=type(exc).__name__,
            error=str(exc),
        )


def _audit_sources(path: Path, *, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {path}")
    pattern = "**/*" if recursive else "*"
    return sorted(item for item in path.glob(pattern) if item.is_file() and _is_audit_source(item))


_AUDIT_INPUT_SUFFIXES = {
    ".csv",
    ".txt",
    ".tsv",
    ".xlsx",
    ".xls",
    ".mpt",
    ".mpr",
    ".dta",
    ".mat",
    ".parquet",
}

_AUDIT_HELPER_SUFFIXES = (
    ".conversion-report.json",
    ".metadata.json",
    ".manifest.jsonl",
    ".manifest.json",
)

_AUDIT_HELPER_NAME_MARKERS = (
    "readme",
    "manifest",
    "metadata",
    "label",
    "labels",
    "summary",
    "datasheet",
    "specification",
    "manufacturer",
    "figure",
    "plot",
    "codebook",
    "schedule",
    "procedure",
)


def _is_audit_source(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(_AUDIT_HELPER_SUFFIXES):
        return False
    if any(marker in name for marker in _AUDIT_HELPER_NAME_MARKERS):
        return False
    return is_supported_source_path(path, _AUDIT_INPUT_SUFFIXES)


def _quality_checks(df: pl.DataFrame) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    if df.is_empty():
        return checks
    if "test_time_s" in df.columns:
        times = _float_values(df["test_time_s"])
        finite_times = [value for value in times if value is not None and math.isfinite(value)]
        duplicate_count = len(finite_times) - len(set(finite_times))
        non_monotonic = sum(1 for left, right in pairwise(finite_times) if right <= left)
        checks["duplicated_timestamps"] = duplicate_count
        checks["non_monotonic_time"] = non_monotonic
    if "voltage_v" in df.columns:
        checks["suspicious_flat_voltage"] = _flat_signal(df["voltage_v"])
    if "current_a" in df.columns:
        checks["suspicious_flat_current"] = _flat_signal(df["current_a"])
    if "cycle_index" in df.columns:
        checks["cycle_anomalies"] = _index_anomalies(df["cycle_index"])
    if "step_index" in df.columns:
        checks["step_anomalies"] = _index_anomalies(df["step_index"])
    return checks


def _flat_signal(series: pl.Series) -> dict[str, Any]:
    values = [value for value in _float_values(series) if value is not None and math.isfinite(value)]
    if len(values) < 10:
        return {"flag": False, "reason": "fewer than 10 numeric points"}
    span = max(values) - min(values)
    mean_abs = sum(abs(value) for value in values) / len(values)
    tolerance = max(1e-9, mean_abs * 1e-6)
    return {"flag": span <= tolerance, "span": span, "points": len(values)}


def _index_anomalies(series: pl.Series) -> dict[str, int]:
    values = [value for value in _float_values(series) if value is not None and math.isfinite(value)]
    decreases = sum(1 for left, right in pairwise(values) if right < left)
    negative = sum(1 for value in values if value < 0)
    return {"decreases": decreases, "negative_values": negative}


def _float_values(series: pl.Series) -> list[float | None]:
    values: list[float | None] = []
    for value in series.to_list():
        if value is None:
            values.append(None)
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            values.append(None)
            continue
        values.append(number)
    return values


def _validation_issues(issues: list[ValidationIssue]) -> list[AuditIssue]:
    return [AuditIssue(issue.level, issue.code, issue.message, issue.column) for issue in issues]


def _quality_scored_validation_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.code != "missing-optional-column"]


def _completeness(issues: list[ValidationIssue]) -> dict[str, Any]:
    required_missing = sorted(
        issue.column for issue in issues if issue.code == "missing-required-column" and issue.column
    )
    optional_missing = sorted(
        issue.column for issue in issues if issue.code == "missing-optional-column" and issue.column
    )
    required_total = len(REQUIRED_COLUMNS)
    optional_total = len(OPTIONAL_COLUMNS)
    required_present = required_total - len(required_missing)
    optional_present = optional_total - len(optional_missing)
    return {
        "required_present": required_present,
        "required_total": required_total,
        "required_missing": required_missing,
        "optional_present": optional_present,
        "optional_total": optional_total,
        "optional_missing": optional_missing,
        "optional_coverage": round(optional_present / optional_total, 3) if optional_total else 1.0,
    }


def _check_issues(checks: dict[str, Any]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if checks.get("duplicated_timestamps", 0):
        issues.append(
            AuditIssue(
                "warning",
                "duplicated-timestamps",
                f"{checks['duplicated_timestamps']} duplicated test_time_s values.",
                "test_time_s",
            )
        )
    if checks.get("non_monotonic_time", 0):
        issues.append(
            AuditIssue(
                "warning",
                "non-monotonic-time",
                f"{checks['non_monotonic_time']} non-monotonic test_time_s transitions.",
                "test_time_s",
            )
        )
    for key, column in (("suspicious_flat_voltage", "voltage_v"), ("suspicious_flat_current", "current_a")):
        value = checks.get(key)
        if isinstance(value, dict) and value.get("flag"):
            issues.append(AuditIssue("warning", key.replace("_", "-"), f"{column} appears flat.", column))
    for key, column in (("cycle_anomalies", "cycle_index"), ("step_anomalies", "step_index")):
        value = checks.get(key)
        if isinstance(value, dict) and (value.get("decreases", 0) or value.get("negative_values", 0)):
            issues.append(
                AuditIssue(
                    "warning",
                    key.replace("_", "-"),
                    f"{column} has decreases={value.get('decreases', 0)} and "
                    f"negative_values={value.get('negative_values', 0)}.",
                    column,
                )
            )
    return issues


def _unit_repairs(provenance: list[ColumnProvenance]) -> list[dict[str, Any]]:
    repairs = []
    for item in provenance:
        if item.transform and item.transform.startswith("unit conversion"):
            repairs.append(
                {
                    "column": item.column,
                    "source": item.source,
                    "source_unit": item.source_unit,
                    "transform": item.transform,
                }
            )
    return repairs


def _current_sign_evidence(provenance: list[ColumnProvenance], warnings: list[str]) -> str:
    for item in provenance:
        if item.column == "current_a" and item.transform and "current sign" in item.transform:
            return item.transform
    for warning in warnings:
        if "current sign" in warning.lower() or "status column" in warning.lower():
            return warning
    return "raw current mapped without explicit charge/discharge sign evidence"


def _score_record(
    *,
    status: str,
    detection_confidence: float | None,
    validation_issues: list[ValidationIssue],
    audit_issues: list[AuditIssue],
    warnings: list[str],
    repair_operations: list[str],
    unit_repairs: list[dict[str, Any]],
    current_sign_evidence: str | None,
) -> int:
    if status == "unsupported":
        return 0
    validation_issues = _quality_scored_validation_issues(validation_issues)
    score = 92 if status == "eis" else 100
    if detection_confidence is not None:
        if detection_confidence < 0.2:
            score -= 20
        elif detection_confidence < 0.5:
            score -= 10
    for issue in validation_issues:
        score -= 20 if issue.level == "error" else 3
    for issue in audit_issues:
        if issue.code in {"duplicated-timestamps", "non-monotonic-time"}:
            score -= 10
        elif issue.level == "warning":
            score -= 5
    score -= min(15, len(warnings) * 3)
    score -= min(20, len(repair_operations) * 5)
    if current_sign_evidence and current_sign_evidence.startswith("raw current mapped without explicit"):
        score -= 5
    return max(0, min(100, round(score)))


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _build_report(input_path: Path, records: list[AuditRecord]) -> AuditReport:
    status_counts = Counter(record.status for record in records)
    kind_counts = Counter(record.data_kind for record in records)
    cycler_counts = Counter(
        record.cycler or "unknown" for record in records if record.status.startswith("converted")
    )
    issue_counts = Counter(issue.code for record in records for issue in record.issues)
    scores = [record.quality_score for record in records]
    average = round(sum(scores) / len(scores), 1) if scores else 0.0
    return AuditReport(
        input_path=str(input_path),
        files=len(records),
        converted=status_counts.get("converted", 0) + status_counts.get("converted-with-issues", 0),
        eis=status_counts.get("eis", 0),
        unsupported=status_counts.get("unsupported", 0),
        errors=status_counts.get("error", 0),
        average_score=average,
        cycler_counts=dict(sorted(cycler_counts.items())),
        kind_counts=dict(sorted(kind_counts.items())),
        status_counts=dict(sorted(status_counts.items())),
        top_issue_codes=dict(issue_counts.most_common(10)),
        records=records,
    )


def _write_html_report(report: AuditReport, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(_html_record_row(record) for record in report.records)
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>BDS Audit Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #1f2933; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; }}
    .metric {{ border: 1px solid #d8dee4; border-radius: 6px; padding: 12px 16px; min-width: 120px; }}
    .metric strong {{ display: block; font-size: 24px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #d8dee4; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; }}
    .grade-A {{ color: #1d4ed8; font-weight: bold; }}
    .grade-B {{ color: #2563eb; font-weight: bold; }}
    .grade-C {{ color: #ca8a04; font-weight: bold; }}
    .grade-D, .grade-F {{ color: #b91c1c; font-weight: bold; }}
    code {{ white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>BDS Audit Report</h1>
  <p>Input: <code>{html.escape(report.input_path)}</code></p>
  <div class="summary">
    <div class="metric"><strong>{report.files}</strong>files</div>
    <div class="metric"><strong>{report.converted}</strong>converted</div>
    <div class="metric"><strong>{report.eis}</strong>EIS</div>
    <div class="metric"><strong>{report.unsupported}</strong>unsupported</div>
    <div class="metric"><strong>{report.errors}</strong>errors</div>
    <div class="metric"><strong>{report.average_score}</strong>avg score</div>
  </div>
  <h2>Breakdown</h2>
  <p>Status: <code>{html.escape(json.dumps(report.status_counts, sort_keys=True))}</code></p>
  <p>Kind: <code>{html.escape(json.dumps(report.kind_counts, sort_keys=True))}</code></p>
  <p>Cycler: <code>{html.escape(json.dumps(report.cycler_counts, sort_keys=True))}</code></p>
  <p>Top issues: <code>{html.escape(json.dumps(report.top_issue_codes, sort_keys=True))}</code></p>
  <h2>Files</h2>
  <table>
    <thead>
      <tr>
        <th>File</th>
        <th>Status</th>
        <th>Kind</th>
        <th>Cycler</th>
        <th>Score</th>
        <th>Rows</th>
        <th>Optional Coverage</th>
        <th>Issues</th>
        <th>Repairs / Sign Evidence</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def _html_record_row(record: AuditRecord) -> str:
    issues = "; ".join(f"{issue.code}: {issue.message}" for issue in record.issues[:5])
    repairs = "; ".join(record.repair_operations[:3])
    if record.current_sign_evidence:
        repairs = f"{repairs}; {record.current_sign_evidence}" if repairs else record.current_sign_evidence
    optional_coverage = record.completeness.get("optional_coverage")
    optional_text = "" if optional_coverage is None else f"{float(optional_coverage) * 100:.0f}%"
    score = f'<span class="grade-{html.escape(record.quality_grade)}">{record.quality_score} ({record.quality_grade})</span>'
    return f"""<tr>
  <td><code>{html.escape(record.relative_path)}</code></td>
  <td>{html.escape(record.status)}</td>
  <td>{html.escape(record.data_kind)}</td>
  <td>{html.escape(record.cycler or "")}</td>
  <td>{score}</td>
  <td>{"" if record.rows is None else record.rows}</td>
  <td>{html.escape(optional_text)}</td>
  <td>{html.escape(issues)}</td>
  <td>{html.escape(repairs)}</td>
</tr>"""


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _error_record(path: Path, relative_path: str, kind: str, error_type: str, error: str) -> AuditRecord:
    issue = AuditIssue("error", "audit-error", error)
    return AuditRecord(
        input_path=str(path),
        relative_path=relative_path,
        status="error",
        data_kind=kind,
        quality_score=0,
        quality_grade=_grade(0),
        issues=[issue],
        error_type=error_type,
        error=error,
    )
