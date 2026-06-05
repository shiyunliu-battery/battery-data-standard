"""Serializable report objects for detection, validation, and conversion."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _clean(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, tuple):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    return value


@dataclass
class DetectionResult:
    cycler: str
    confidence: float
    reason: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class ValidationIssue:
    level: str
    code: str
    message: str
    column: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class ValidationReport:
    valid: bool
    schema_version: str
    rows: int
    columns: list[str]
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class ColumnProvenance:
    column: str
    source: str
    source_unit: str | None = None
    transform: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class ConversionReport:
    input_path: str
    output_path: str | None
    cycler: str
    schema_version: str
    rows: int
    columns: list[str]
    validation: ValidationReport
    warnings: list[str] = field(default_factory=list)
    provenance: list[ColumnProvenance] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    current_sign: str = "charge-positive"
    adapter_version: str | None = None
    support_tier: str = "best_effort"
    evidence_tier: str = "best-effort"
    detection_confidence: float | None = None
    encoding: str | None = None
    delimiter: str | None = None
    header_row: int | None = None
    sheet_name: str | None = None
    raw_rows: int | None = None
    repair_operations: list[str] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def write_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
            ) as handle:
                temp_name = handle.name
            temp_path = Path(temp_name)
            temp_path.write_text(self.to_json() + "\n", encoding="utf-8")
            with temp_path.open("r+b") as handle:
                os.fsync(handle.fileno())
            temp_path.replace(path)
        finally:
            if temp_name is not None:
                temp_path = Path(temp_name)
                if temp_path.exists():
                    temp_path.unlink()
