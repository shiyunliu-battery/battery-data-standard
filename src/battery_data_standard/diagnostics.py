"""Single-file diagnostics for user-facing conversion explainability."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .api import detect, detect_kind, read_eis, read_with_report
from .eis import validate_eis
from .exceptions import BatteryDataStandardError, FileIOError
from .export import to_export_frame
from .reports import ColumnProvenance


@dataclass
class ExplainReport:
    input_path: str
    status: str
    data_kind: dict[str, Any]
    detection: dict[str, Any] | None = None
    selected_adapter: str | None = None
    confidence: float | None = None
    sheet: str | int | None = None
    source_columns: list[str] = field(default_factory=list)
    canonical_columns: list[str] = field(default_factory=list)
    export_columns: list[str] = field(default_factory=list)
    column_mapping: list[dict[str, Any]] = field(default_factory=list)
    unit_transforms: list[dict[str, Any]] = field(default_factory=list)
    current_sign: str | None = None
    current_sign_evidence: str | None = None
    current_sign_confidence: str | None = None
    current_sign_sanity: dict[str, Any] | None = None
    semantic_sources: dict[str, Any] | None = None
    step_cycle_semantics: dict[str, Any] | None = None
    repair_policy: str = "warn"
    validation: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)
    time_sampling: dict[str, Any] | None = None
    recommended_next_action: str = ""
    error_type: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_text(self) -> str:
        lines = [
            "BDS explain",
            f"Input: {self.input_path}",
            f"Status: {self.status}",
            f"Data kind: {self.data_kind.get('kind')} ({self.data_kind.get('confidence')})",
        ]
        if self.selected_adapter:
            lines.append(f"Adapter: {self.selected_adapter} ({self.confidence})")
        if self.sheet:
            lines.append(f"Sheet: {self.sheet}")
        if self.current_sign:
            lines.append(f"Current sign: {self.current_sign}")
        if self.current_sign_evidence:
            lines.append(f"Current sign evidence: {self.current_sign_evidence}")
        if self.current_sign_confidence:
            lines.append(f"Current sign confidence: {self.current_sign_confidence}")
        if self.current_sign_sanity and self.current_sign_sanity.get("status") == "suspicious":
            lines.append(f"Current sign warning: {self.current_sign_sanity.get('reason')}")
        if self.validation:
            lines.append(f"Validation valid: {self.validation.get('valid')}")
        if self.time_sampling:
            lines.append(f"Time sampling: {self.time_sampling.get('status')}")
            missing = self.time_sampling.get("missing_points")
            if missing:
                lines.append(f"Missing sample points: {missing}")
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings[:8])
        validation_issues = (self.validation or {}).get("issues") or []
        if validation_issues:
            lines.append("Validation issues:")
            lines.extend(f"- {issue.get('code')}: {issue.get('message')}" for issue in validation_issues[:8])
        if self.column_mapping:
            lines.append("Column mapping:")
            for item in self.column_mapping[:12]:
                transform = f" [{item['transform']}]" if item.get("transform") else ""
                source_unit = f" ({item['source_unit']})" if item.get("source_unit") else ""
                lines.append(
                    f"- {item['source']}{source_unit} -> {item['canonical_column']} -> "
                    f"{item.get('export_column') or ''}{transform}"
                )
        if self.unmapped_columns:
            lines.append("Unmapped columns:")
            lines.append("- " + ", ".join(self.unmapped_columns[:20]))
        if self.error:
            lines.append(f"Error: {self.error_type}: {self.error}")
        if self.recommended_next_action:
            lines.append(f"Next: {self.recommended_next_action}")
        return "\n".join(lines)


def explain(
    path: str | Path,
    *,
    cycler: str | None = "auto",
    profile: str | Path | dict[str, Any] | None = None,
    current_sign: str = "charge-positive",
    current_sign_check: str = "none",
    repair_policy: str = "warn",
    detection_threshold: float = 0.1,
    sheet: str | int | None = None,
    target: str = "bds",
) -> ExplainReport:
    """Explain how BDS detects, maps, validates, and would export one file."""
    input_path = Path(path)
    if not input_path.exists():
        raise FileIOError(f"Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise FileIOError(f"Input path is not a file: {input_path}")

    kind = detect_kind(input_path, sheet=sheet)
    source_columns = [str(column) for column in kind.evidence.get("columns", [])]

    if kind.kind == "unsupported":
        return ExplainReport(
            input_path=str(input_path),
            status="unsupported",
            data_kind=kind.to_dict(),
            sheet=sheet,
            source_columns=source_columns,
            repair_policy=repair_policy,
            recommended_next_action=(
                "No conversion was attempted because the file looks like helper content or an unsupported "
                "data family."
            ),
        )

    if kind.kind == "eis":
        return _explain_eis(input_path, kind.to_dict(), source_columns=source_columns, sheet=sheet)

    detection = _safe_detect(input_path)
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
        export_df = to_export_frame(df, target=target)
        current_sign_evidence = _current_sign_evidence(report.provenance, report.warnings)
        validation = report.validation.to_dict()
        status = "ok" if report.validation.valid else "converted-with-issues"
        source_columns = _source_columns(report.metadata, source_columns)
        return ExplainReport(
            input_path=str(input_path),
            status=status,
            data_kind=kind.to_dict(),
            detection=detection,
            selected_adapter=report.cycler,
            confidence=report.detection_confidence,
            sheet=report.sheet_name or sheet,
            source_columns=source_columns,
            canonical_columns=report.columns,
            export_columns=list(export_df.columns),
            column_mapping=_column_mapping(report.provenance, target=target),
            unit_transforms=_unit_transforms(report.provenance),
            current_sign=report.current_sign,
            current_sign_evidence=current_sign_evidence,
            current_sign_confidence=report.metadata.get("current_sign_confidence"),
            current_sign_sanity=report.metadata.get("current_sign_sanity"),
            semantic_sources=report.metadata.get("semantic_sources"),
            step_cycle_semantics=report.metadata.get("step_cycle_semantics"),
            repair_policy=repair_policy,
            validation=validation,
            warnings=report.warnings,
            unmapped_columns=report.unmapped_columns,
            time_sampling=report.metadata.get("time_sampling"),
            recommended_next_action=_next_action(status, report.cycler),
        )
    except BatteryDataStandardError as exc:
        return ExplainReport(
            input_path=str(input_path),
            status="error",
            data_kind=kind.to_dict(),
            detection=detection,
            selected_adapter=(detection or {}).get("cycler"),
            confidence=(detection or {}).get("confidence"),
            sheet=sheet,
            source_columns=source_columns,
            repair_policy=repair_policy,
            recommended_next_action=(
                "Review the detected candidates, try an explicit --cycler value, or share a reduced "
                "fixture with the source headers and expected time/voltage/current columns."
            ),
            error_type=type(exc).__name__,
            error=str(exc),
        )


def _explain_eis(
    input_path: Path,
    kind: dict[str, Any],
    *,
    source_columns: list[str],
    sheet: str | int | None,
) -> ExplainReport:
    try:
        df = read_eis(input_path, sheet=sheet)
        validation = validate_eis(df)
        status = "eis" if validation.valid else "eis-with-issues"
        return ExplainReport(
            input_path=str(input_path),
            status=status,
            data_kind=kind,
            sheet=sheet,
            source_columns=source_columns or list(df.columns),
            canonical_columns=list(df.columns),
            export_columns=list(df.columns),
            validation=validation.to_dict(),
            recommended_next_action="Use bds convert-eis to write a standardized EIS table.",
        )
    except BatteryDataStandardError as exc:
        return ExplainReport(
            input_path=str(input_path),
            status="error",
            data_kind=kind,
            sheet=sheet,
            source_columns=source_columns,
            recommended_next_action="Review the EIS columns or specify the worksheet with --sheet.",
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


def _column_mapping(provenance: list[ColumnProvenance], *, target: str) -> list[dict[str, Any]]:
    return [
        {
            "source": item.source,
            "canonical_column": item.column,
            "export_column": _export_column(item.column, target=target),
            "source_unit": item.source_unit,
            "transform": item.transform,
        }
        for item in provenance
    ]


def _unit_transforms(provenance: list[ColumnProvenance]) -> list[dict[str, Any]]:
    return [
        {
            "column": item.column,
            "source": item.source,
            "source_unit": item.source_unit,
            "transform": item.transform,
        }
        for item in provenance
        if item.transform and item.transform.startswith("unit conversion")
    ]


def _current_sign_evidence(provenance: list[ColumnProvenance], warnings: list[str]) -> str:
    for item in provenance:
        if item.column == "current_a" and item.transform and "current sign" in item.transform:
            return item.transform
    for warning in warnings:
        if "current sign" in warning.lower() or "status column" in warning.lower():
            return warning
    return "raw current mapped without explicit charge/discharge sign evidence"


def _export_column(column: str, *, target: str) -> str | None:
    target = target.strip().lower().replace("_", "-")
    maps = {
        "bds": {
            "record_index": "Record Index",
            "date_time": "Date Time",
            "test_time_s": "Test Time (s)",
            "voltage_v": "Voltage (V)",
            "current_a": "Current (A)",
            "cycle_index": "Cycle Count",
            "step_index": "Step Index",
            "step_time_s": "Step Time (s)",
            "power_w": "Power (W)",
            "charge_capacity_ah": "Charging Capacity (Ah)",
            "discharge_capacity_ah": "Discharging Capacity (Ah)",
            "charge_energy_wh": "Charging Energy (Wh)",
            "discharge_energy_wh": "Discharging Energy (Wh)",
            "ambient_temperature_deg_c": "Ambient Temperature (degC)",
            "temperature_t1_deg_c": "Surface Temperature T1 (degC)",
            "internal_resistance_ohm": "Internal Resistance (ohm)",
        },
        "bdf": {
            "date_time": "Date Time ISO",
            "test_time_s": "Test Time / s",
            "voltage_v": "Voltage / V",
            "current_a": "Current / A",
            "unix_time_s": "Unix Time / s",
            "cycle_index": "Cycle Count / 1",
            "step_index": "Step Count / 1",
            "record_index": "Step Index / 1",
            "step_time_s": "Step Time / s",
            "power_w": "Power / W",
            "ambient_temperature_deg_c": "Ambient Temperature / degC",
            "temperature_t1_deg_c": "Surface Temperature T1 / degC",
            "charge_capacity_ah": "Charging Capacity / Ah",
            "discharge_capacity_ah": "Discharging Capacity / Ah",
            "charge_energy_wh": "Charging Energy / Wh",
            "discharge_energy_wh": "Discharging Energy / Wh",
            "internal_resistance_ohm": "Internal Resistance / ohm",
        },
        "pybamm": {"test_time_s": "time_s", "current_a": "current_a"},
        "pyprobe": {
            "test_time_s": "time_s",
            "voltage_v": "voltage_v",
            "current_a": "current_a",
            "cycle_index": "cycle_index",
            "step_index": "step_index",
            "step_time_s": "step_time_s",
            "charge_capacity_ah": "charge_capacity_ah",
            "discharge_capacity_ah": "discharge_capacity_ah",
        },
        "cellpy": {
            "record_index": "data_point",
            "test_time_s": "test_time",
            "current_a": "current",
            "voltage_v": "voltage",
            "date_time": "datetime",
            "step_time_s": "step_time",
            "cycle_index": "cycle_index",
            "step_index": "step_index",
            "charge_capacity_ah": "charge_capacity",
            "discharge_capacity_ah": "discharge_capacity",
            "charge_energy_wh": "charge_energy",
            "discharge_energy_wh": "discharge_energy",
        },
        "beep": {
            "test_time_s": "test_time",
            "current_a": "current",
            "voltage_v": "voltage",
            "cycle_index": "cycle_index",
            "step_index": "step_index",
            "step_time_s": "step_time",
            "charge_capacity_ah": "charge_capacity",
            "discharge_capacity_ah": "discharge_capacity",
            "charge_energy_wh": "charge_energy",
            "discharge_energy_wh": "discharge_energy",
        },
    }
    if target in {"duckdb", "polars", "battery-archive"}:
        target = "bds"
    return maps.get(target, {}).get(column)


def _next_action(status: str, cycler: str | None) -> str:
    if status == "ok":
        cycler_arg = cycler or "auto"
        return f"Convert with bds convert <input> <output> --cycler {cycler_arg} --report auto."
    return "Review validation issues and warnings before trusting downstream exports."


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
