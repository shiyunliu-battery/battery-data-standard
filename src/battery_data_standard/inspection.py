"""Unified, non-mutating diagnostics for one battery data source."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .diagnostics import ExplainReport, explain
from .doctor import _fixture_checklist, _suggestions, _suspicious_headers
from .exceptions import ConversionError

INSPECTION_REPORT_VERSION = "bds-inspection-v1"
MAX_INSPECTION_FINDINGS = 500


@dataclass
class InspectionReport:
    """Serializable result of a read-only source inspection."""

    input_path: str
    inspection_status: str
    attention: str
    readable: bool
    data_kind: dict[str, Any]
    report_version: str = INSPECTION_REPORT_VERSION
    detection: dict[str, Any] | None = None
    selected_adapter: str | None = None
    confidence: float | None = None
    sheet: str | int | None = None
    target: dict[str, Any] = field(default_factory=dict)
    source_columns: list[str] = field(default_factory=list)
    canonical_columns: list[str] = field(default_factory=list)
    target_columns: list[str] = field(default_factory=list)
    column_mapping: list[dict[str, Any]] = field(default_factory=list)
    unit_transforms: list[dict[str, Any]] = field(default_factory=list)
    current_sign: str | None = None
    current_sign_evidence: str | None = None
    current_sign_confidence: str | None = None
    current_sign_sanity: dict[str, Any] | None = None
    time_sampling: dict[str, Any] | None = None
    repair_policy: str = "none"
    time_sampling_policy: str = "warn"
    source_file_modified: bool = False
    repairs_applied: bool = False
    validation: dict[str, Any] | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)
    finding_summary: dict[str, int] = field(default_factory=dict)
    findings_total: int = 0
    findings_truncated: bool = False
    missing_required_columns: list[str] = field(default_factory=list)
    suspicious_headers: list[dict[str, Any]] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    fixture_checklist: list[str] = field(default_factory=list)
    error_type: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_text(self) -> str:
        kind = self.data_kind.get("kind") or "unknown"
        lines = [
            "BDS inspect",
            f"File: {self.input_path}",
            f"Inspection: {self.inspection_status.upper()}",
            f"Attention: {self.attention.upper()}",
            "",
            "Detected data:",
            f"- Kind: {kind}",
        ]
        if self.selected_adapter:
            lines.append(f"- Adapter: {self.selected_adapter} ({self.confidence})")
        if self.sheet:
            lines.append(f"- Sheet: {self.sheet}")

        lines.extend(["", "Readability:", f"- Readable: {'yes' if self.readable else 'no'}"])
        if self.validation is not None:
            lines.append(f"- Normalized schema valid: {'yes' if self.validation.get('valid') else 'no'}")
            rows = self.validation.get("rows")
            if rows is not None:
                lines.append(f"- Rows inspected: {rows}")

        target_id = self.target.get("id")
        if target_id and self.target.get("assessment") == "mapping-preview":
            lines.extend(
                [
                    "",
                    "Target preview:",
                    f"- Target: {target_id}",
                    "- Assessment: mapping preview only; not a conformance result",
                ]
            )

        if self.findings:
            lines.extend(["", "Important findings:"])
            for finding in self.findings[:20]:
                severity = str(finding.get("severity") or "info").upper()
                lines.append(f"- [{severity}] {finding.get('code')}: {finding.get('message')}")
            if len(self.findings) > 20:
                lines.append(f"- ... {len(self.findings) - 20} additional finding(s) retained in JSON")
            if self.findings_truncated:
                lines.append(f"- Finding list truncated; {self.findings_total} total finding(s) were counted")

        if self.column_mapping:
            lines.extend(["", "Mapping:"])
            for item in self.column_mapping[:20]:
                transform = f" [{item.get('transform')}]" if item.get("transform") else ""
                lines.append(
                    f"- {item.get('source')} -> {item.get('canonical_column')} -> "
                    f"{item.get('export_column') or ''}{transform}"
                )
            if len(self.column_mapping) > 20:
                lines.append(f"- ... {len(self.column_mapping) - 20} additional mapping(s) in JSON")

        if self.unmapped_columns:
            lines.extend(["", "Unmapped columns:", "- " + ", ".join(self.unmapped_columns[:20])])
            if len(self.unmapped_columns) > 20:
                lines.append(f"- ... {len(self.unmapped_columns) - 20} additional column(s) in JSON")

        lines.extend(["", "Source file modified: no", "Repairs applied: no"])
        if self.error:
            lines.extend(["", f"Error: {self.error_type}: {self.error}"])
        if self.suggested_actions:
            lines.extend(["", "Suggested next steps:"])
            lines.extend(f"- {action}" for action in self.suggested_actions)
        return "\n".join(lines)


def inspect(
    path: str | Path,
    *,
    cycler: str | None = "auto",
    profile: str | Path | dict[str, Any] | None = None,
    current_sign: str = "preserve",
    current_sign_check: str = "none",
    repair_policy: str = "none",
    detection_threshold: float = 0.1,
    sheet: str | int | None = None,
    target: str = "bds",
    max_findings: int = MAX_INSPECTION_FINDINGS,
) -> InspectionReport:
    """Inspect one source without writing output or applying data repairs.

    Unit conversions and target mappings may be calculated in memory for the
    preview. The input file is never changed, time-sampling gaps are not filled,
    and the default current-sign policy preserves source values.
    """
    if max_findings < 1:
        raise ValueError("max_findings must be at least 1")
    normalized_repair_policy = str(repair_policy).strip().lower()
    if normalized_repair_policy not in {"none", "warn"}:
        raise ConversionError("inspect supports repair_policy='none' or 'warn'; it never applies repairs")

    explained = explain(
        path,
        cycler=cycler,
        profile=profile,
        current_sign=current_sign,
        current_sign_check=current_sign_check,
        repair_policy=normalized_repair_policy,
        time_sampling_policy="warn",
        detection_threshold=detection_threshold,
        sheet=sheet,
        target=target,
    )
    return _inspection_from_explain(
        explained,
        input_path=Path(path),
        target=target,
        repair_policy=normalized_repair_policy,
        max_findings=max_findings,
    )


def _inspection_from_explain(
    explained: ExplainReport,
    *,
    input_path: Path,
    target: str,
    repair_policy: str,
    max_findings: int,
) -> InspectionReport:
    validation_issues = (explained.validation or {}).get("issues") or []
    missing = _missing_required_columns_from_dicts(validation_issues)
    findings = _findings(validation_issues, explained.warnings)
    findings_total = len(findings)
    visible_findings = findings[:max_findings]
    summary = Counter(str(item.get("severity") or "info") for item in findings)
    inspection_status, readable = _inspection_state(explained.status)
    attention = _attention(findings, inspection_status=inspection_status)
    suspicious_headers = _suspicious_headers(explained.source_columns, missing)
    actions = _suggestions(
        status=explained.status,
        input_path=input_path,
        missing_required=missing,
        detection=explained.detection,
        selected_adapter=explained.selected_adapter,
        sheet=explained.sheet,
    )
    if explained.data_kind.get("kind") != "timeseries" and explained.recommended_next_action:
        actions.insert(0, explained.recommended_next_action)

    target_assessment = (
        "mapping-preview" if explained.data_kind.get("kind") == "timeseries" else "not-applicable"
    )

    return InspectionReport(
        input_path=str(input_path),
        inspection_status=inspection_status,
        attention=attention,
        readable=readable,
        data_kind=explained.data_kind,
        detection=explained.detection,
        selected_adapter=explained.selected_adapter,
        confidence=explained.confidence,
        sheet=explained.sheet,
        target={
            "id": target,
            "assessment": target_assessment,
            "conformant": None,
        },
        source_columns=explained.source_columns,
        canonical_columns=explained.canonical_columns,
        target_columns=explained.export_columns,
        column_mapping=explained.column_mapping,
        unit_transforms=explained.unit_transforms,
        current_sign=explained.current_sign,
        current_sign_evidence=explained.current_sign_evidence,
        current_sign_confidence=explained.current_sign_confidence,
        current_sign_sanity=explained.current_sign_sanity,
        time_sampling=explained.time_sampling,
        repair_policy=repair_policy,
        validation=explained.validation,
        findings=visible_findings,
        finding_summary=dict(summary),
        findings_total=findings_total,
        findings_truncated=findings_total > max_findings,
        missing_required_columns=missing,
        suspicious_headers=suspicious_headers,
        unmapped_columns=explained.unmapped_columns,
        suggested_actions=actions,
        fixture_checklist=_fixture_checklist() if attention == "blocking" else [],
        error_type=explained.error_type,
        error=explained.error,
    )


def _missing_required_columns_from_dicts(issues: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(issue["column"])
            for issue in issues
            if issue.get("code") == "missing-required-column" and issue.get("column")
        }
    )


def _findings(
    validation_issues: list[dict[str, Any]], warnings: list[str]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen_messages: set[str] = set()
    for issue in validation_issues:
        code = str(issue.get("code") or "validation-issue")
        level = str(issue.get("level") or "warning")
        severity = "blocking" if level == "error" else "review"
        if code == "missing-optional-column":
            severity = "info"
        message = str(issue.get("message") or code)
        seen_messages.add(message)
        findings.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "column": issue.get("column"),
                "source": "validation",
            }
        )
    for warning in warnings:
        message = str(warning)
        if message in seen_messages:
            continue
        findings.append(
            {
                "code": "conversion-warning",
                "severity": "review",
                "message": message,
                "column": None,
                "source": "conversion",
            }
        )
    return findings


def _inspection_state(status: str) -> tuple[str, bool]:
    if status == "unsupported":
        return "unsupported", False
    if status == "error":
        return "failed", False
    return "completed", True


def _attention(findings: list[dict[str, Any]], *, inspection_status: str) -> str:
    if inspection_status in {"failed", "unsupported"}:
        return "blocking"
    severities = {str(item.get("severity")) for item in findings}
    if "blocking" in severities:
        return "blocking"
    if "review" in severities:
        return "review"
    return "none"


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
