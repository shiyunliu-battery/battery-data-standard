"""Public API for conversion, detection, and reading."""

from __future__ import annotations

import json
import logging
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import polars as pl

from .adapters.base import Adapter, AdapterResult
from .adapters.neware import group_neware_record_files
from .adapters.registry import adapter_metadata, all_adapters, detect_adapter, get_adapter
from .archive import batch_sources
from .eis import convert_eis as _convert_eis
from .eis import read_eis as _read_eis
from .eis import validate_eis as _validate_eis
from .exceptions import BatteryDataStandardError, ConversionError, FileIOError, ValidationFailed
from .export import EXPORT_FORMAT_VERSION, looks_like_export_frame, to_export_frame, validate_export_frame
from .io import read_bdf_like, write_dataframe, write_json, write_jsonl
from .kind import DataKindResult
from .kind import detect_kind as _detect_kind
from .profiles import load_profile
from .reports import ConversionReport, DetectionResult, ValidationReport
from .schema import BDF_SCHEMA_VERSION
from .validation import validate

logger = logging.getLogger(__name__)


def list_supported_formats() -> list[dict[str, object]]:
    return adapter_metadata()


def group_neware_files(paths: list[str | Path]) -> list[dict[str, Any]]:
    """Group NEWARE record exports into complete tests using file content."""
    return group_neware_record_files(paths)


def detect(path: str | Path) -> DetectionResult:
    """Detect the most likely cycler adapter for a source file.

    Parameters
    ----------
    path:
        Raw cycler export or BDF-like file to inspect.

    Returns
    -------
    DetectionResult
        The selected cycler id, confidence score, reason, and candidate list.
    """
    input_path = Path(path)
    _ensure_input_file(input_path)
    try:
        return detect_adapter(input_path)
    except OSError as exc:
        raise FileIOError(f"Could not inspect {input_path}: {exc}") from exc


def detect_kind(path: str | Path, *, sheet: str | int | None = None) -> DataKindResult:
    """Detect whether a file is BDF time-series, EIS, unsupported, or unknown."""
    input_path = Path(path)
    _ensure_input_file(input_path)
    return _detect_kind(input_path, sheet=sheet)


def read_eis(path: str | Path, *, sheet: str | int | None = None) -> pl.DataFrame:
    """Read EIS data into an eisfit-compatible standardized table."""
    input_path = Path(path)
    _ensure_input_file(input_path)
    return _read_eis(input_path, sheet=sheet)


def validate_eis(df: pl.DataFrame) -> ValidationReport:
    """Validate an EIS standardized table."""
    return _validate_eis(df)


def read(
    path: str | Path,
    cycler: str | None = None,
    profile: str | Path | dict[str, Any] | None = None,
    strict: bool = True,
    keep_raw: bool = False,
    current_sign: str = "charge-positive",
    repair_policy: str = "warn",
    detection_threshold: float = 0.1,
    sheet: str | int | None = None,
) -> pl.DataFrame:
    """Read a raw cycler export into a normalized BDF-style dataframe.

    This is the primary library entry point. Use ``read_with_report`` when
    conversion warnings, provenance, and metadata are needed alongside the
    dataframe.

    Parameters
    ----------
    path:
        Input file path.
    cycler:
        Adapter id such as ``"neware"``, ``"arbin"``, ``"generic"``, or
        ``"auto"``. ``None`` is treated as ``"auto"``.
    profile:
        Optional profile dict or JSON/YAML path used to map custom column names.
    strict:
        Raise ``ValidationFailed`` when the normalized dataframe is invalid.
    keep_raw:
        Preserve unused source columns under ``raw:`` names.
    current_sign:
        ``"charge-positive"``, ``"discharge-positive"``, or ``"preserve"``.
    repair_policy:
        ``"none"``, ``"warn"``, or ``"repair"`` for repairable table issues.

    Returns
    -------
    polars.DataFrame
        Normalized row-wise time-series table.
    """
    df, _report = read_with_report(
        path,
        cycler=cycler,
        profile=profile,
        strict=strict,
        keep_raw=keep_raw,
        current_sign=current_sign,
        repair_policy=repair_policy,
        detection_threshold=detection_threshold,
        sheet=sheet,
    )
    return df


def read_with_report(
    path: str | Path,
    cycler: str | None = None,
    profile: str | Path | dict[str, Any] | None = None,
    strict: bool = True,
    keep_raw: bool = False,
    current_sign: str = "charge-positive",
    repair_policy: str = "warn",
    detection_threshold: float = 0.1,
    sheet: str | int | None = None,
) -> tuple[pl.DataFrame, ConversionReport]:
    """Read a file and return both normalized data and a conversion report.

    The report includes validation issues, conversion warnings, column
    provenance, source metadata, and the current sign convention used.
    """
    input_path = Path(path)
    _ensure_input_file(input_path)
    try:
        profile_data = load_profile(profile)
        options = {"sheet": sheet}
        detection = detect_adapter(input_path)
        if cycler is None or cycler == "auto":
            adapter, result = _auto_process_bdf(
                input_path,
                detection=detection,
                profile=profile_data,
                strict=strict,
                keep_raw=keep_raw,
                current_sign=current_sign,
                repair_policy=repair_policy,
                detection_threshold=detection_threshold,
                options=options,
            )
        else:
            adapter = get_adapter(cycler, input_path, detection_threshold=detection_threshold)
            result = adapter.process(
                input_path,
                profile=profile_data,
                strict=strict,
                keep_raw=keep_raw,
                current_sign=current_sign,
                repair_policy=repair_policy,
                options=options,
            )
    except BatteryDataStandardError:
        raise
    except OSError as exc:
        raise FileIOError(f"Could not read {input_path}: {exc}") from exc
    except Exception as exc:
        raise ConversionError(f"Could not convert {input_path}: {exc}") from exc
    validation = validate(result.data, strict=strict)
    if strict and not validation.valid:
        raise ValidationFailed(validation)
    report = ConversionReport(
        input_path=str(input_path),
        output_path=None,
        cycler=adapter.id,
        schema_version=BDF_SCHEMA_VERSION,
        rows=result.data.height,
        columns=list(result.data.columns),
        validation=validation,
        warnings=result.warnings,
        provenance=result.provenance,
        metadata=result.metadata,
        current_sign=current_sign,
        adapter_version=result.metadata.get("adapter_version"),
        support_tier=result.metadata.get("support_tier", "best_effort"),
        detection_confidence=_candidate_confidence(detection, adapter.id),
        encoding=result.metadata.get("encoding"),
        delimiter=result.metadata.get("delimiter"),
        header_row=result.metadata.get("header_row"),
        sheet_name=result.metadata.get("sheet_name"),
        raw_rows=result.metadata.get("raw_rows"),
        repair_operations=list(result.metadata.get("repair_operations", [])),
        unmapped_columns=list(result.metadata.get("unmapped_columns", [])),
    )
    return result.data, report


def convert(
    input_path: str | Path,
    output_path: str | Path,
    format: str = "csv",
    cycler: str | None = None,
    profile: str | Path | dict[str, Any] | None = None,
    metadata: dict[str, Any] | str | Path | None = None,
    strict: bool = True,
    keep_raw: bool = False,
    current_sign: str = "charge-positive",
    repair_policy: str = "warn",
    detection_threshold: float = 0.1,
    report_path: str | Path | None = None,
    write_sidecars: bool = False,
    sheet: str | int | None = None,
) -> ConversionReport:
    """Convert a raw cycler export and write a BDF-style CSV or Parquet file.

    Parameters are the same as ``read_with_report`` with additional output,
    metadata, report, and sidecar controls.

    Returns
    -------
    ConversionReport
        Serializable report describing the conversion and validation result.
    """
    df, report = read_with_report(
        input_path,
        cycler=cycler,
        profile=profile,
        strict=strict,
        keep_raw=keep_raw,
        current_sign=current_sign,
        repair_policy=repair_policy,
        detection_threshold=detection_threshold,
        sheet=sheet,
    )
    output_path = Path(output_path)
    logger.info("writing converted data input=%s output=%s format=%s", input_path, output_path, format)
    export_df = to_export_frame(df)
    try:
        write_dataframe(export_df, output_path, fmt=format)
    except BatteryDataStandardError:
        raise
    except OSError as exc:
        raise FileIOError(f"Could not write {output_path}: {exc}") from exc

    user_metadata = _load_metadata(metadata)
    if user_metadata:
        report.metadata.update(user_metadata)
    _set_export_report_metadata(report, df, export_df)
    report.output_path = str(output_path)
    report.columns = list(export_df.columns)

    try:
        if report_path is not None:
            write_json(report_path, report.to_dict())
        elif write_sidecars:
            write_json(
                output_path.with_suffix(output_path.suffix + ".conversion-report.json"),
                report.to_dict(),
            )

        if write_sidecars and report.metadata:
            write_json(output_path.with_suffix(output_path.suffix + ".metadata.json"), report.metadata)
    except OSError as exc:
        raise FileIOError(f"Could not write conversion sidecar for {output_path}: {exc}") from exc
    return report


def convert_neware_groups(
    paths: list[str | Path],
    output_dir: str | Path,
    *,
    format: str = "csv",
    profile: str | Path | dict[str, Any] | None = None,
    metadata: dict[str, Any] | str | Path | None = None,
    strict: bool = True,
    keep_raw: bool = False,
    current_sign: str = "charge-positive",
    repair_policy: str = "warn",
    write_sidecars: bool = True,
) -> list[ConversionReport]:
    """Convert content-grouped NEWARE record exports into one output per test."""
    groups = group_neware_record_files(paths)
    profile_data = load_profile(profile)
    user_metadata = _load_metadata(metadata)
    output_root = Path(output_dir)
    reports: list[ConversionReport] = []
    used_outputs: set[Path] = set()

    for index, group in enumerate(groups, start=1):
        primary = Path(str(group["primary_path"]))
        output_stem = _unique_output_stem(str(group.get("output_stem") or primary.stem), index, used_outputs)
        output_path = output_root / f"{output_stem}.bdf.{format}"
        used_outputs.add(output_path)

        adapter = get_adapter("neware", primary)
        detection = detect_adapter(primary)
        result = adapter.process(
            primary,
            profile=profile_data,
            strict=strict,
            keep_raw=keep_raw,
            current_sign=current_sign,
            repair_policy=repair_policy,
            options={"neware_record_paths": list(group.get("record_paths", []))},
        )
        validation = validate(result.data, strict=strict)
        if strict and not validation.valid:
            raise ValidationFailed(validation)

        export_df = to_export_frame(result.data)
        report = ConversionReport(
            input_path=str(primary),
            output_path=str(output_path),
            cycler=adapter.id,
            schema_version=BDF_SCHEMA_VERSION,
            rows=result.data.height,
            columns=list(export_df.columns),
            validation=validation,
            warnings=result.warnings,
            provenance=result.provenance,
            metadata={
                **result.metadata,
                **user_metadata,
                "neware_file_group": group,
            },
            current_sign=current_sign,
            adapter_version=result.metadata.get("adapter_version"),
            support_tier=result.metadata.get("support_tier", "best_effort"),
            detection_confidence=_candidate_confidence(detection, adapter.id),
            encoding=result.metadata.get("encoding"),
            delimiter=result.metadata.get("delimiter"),
            header_row=result.metadata.get("header_row"),
            sheet_name=result.metadata.get("sheet_name"),
            raw_rows=result.metadata.get("raw_rows"),
            repair_operations=list(result.metadata.get("repair_operations", [])),
            unmapped_columns=list(result.metadata.get("unmapped_columns", [])),
        )
        _set_export_report_metadata(report, result.data, export_df)
        write_dataframe(export_df, output_path, fmt=format)
        if write_sidecars:
            write_json(
                output_path.with_suffix(output_path.suffix + ".conversion-report.json"), report.to_dict()
            )
            write_json(output_path.with_suffix(output_path.suffix + ".metadata.json"), report.metadata)
        reports.append(report)

    manifest_path = output_root / "neware-group-manifest.json"
    write_json(manifest_path, {"groups": groups, "outputs": [report.to_dict() for report in reports]})
    return reports


def batch_convert(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    recursive: bool = False,
    manifest_path: str | Path | None = None,
    fail_fast: bool = False,
    format: str = "csv",
    cycler: str | None = "auto",
    profile: str | Path | dict[str, Any] | None = None,
    metadata: dict[str, Any] | str | Path | None = None,
    strict: bool = True,
    keep_raw: bool = False,
    current_sign: str = "charge-positive",
    repair_policy: str = "warn",
    detection_threshold: float = 0.1,
    write_sidecars: bool = False,
    sheet: str | int | None = None,
    excel_sheets: str = "auto",
) -> list[dict[str, Any]]:
    """Convert a directory or archive of raw exports and optionally write a JSONL manifest."""
    input_root = Path(input_dir)
    if not input_root.exists():
        raise FileIOError(f"Input path does not exist: {input_root}")
    if not input_root.is_dir() and not input_root.is_file():
        raise FileIOError(f"Input path is not a file or directory: {input_root}")
    output_root = Path(output_dir)
    if output_root.exists() and not output_root.is_dir():
        raise FileIOError(f"Output path is not a directory: {output_root}")
    if excel_sheets == "name" and sheet is None:
        raise ConversionError("batch excel_sheets='name' requires sheet=<sheet name> or CLI --sheet.")

    records: list[dict[str, Any]] = []
    with batch_sources(input_root, recursive=recursive, supported_suffixes=_BATCH_INPUT_SUFFIXES) as sources:
        for source in sources:
            path = source.path
            relative = source.relative_path
            try:
                records.extend(
                    _batch_convert_one(
                        path,
                        output_root,
                        relative,
                        format=format,
                        cycler=cycler,
                        profile=profile,
                        metadata=metadata,
                        strict=strict,
                        keep_raw=keep_raw,
                        current_sign=current_sign,
                        repair_policy=repair_policy,
                        detection_threshold=detection_threshold,
                        write_sidecars=write_sidecars,
                        sheet=sheet,
                        excel_sheets=excel_sheets,
                        archive_path=source.archive_path,
                        archive_member=source.archive_member,
                    )
                )
            except Exception as exc:
                output_path = output_root / relative.parent / f"{relative.stem}.bdf.{format}"
                record = {
                    "status": "error",
                    "record_type": "error",
                    "input_path": str(path),
                    "output_path": str(output_path),
                    "archive_path": str(source.archive_path) if source.archive_path else None,
                    "archive_member": source.archive_member,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                records.append(record)
                if fail_fast:
                    _write_manifest(manifest_path, records)
                    raise

    _write_manifest(manifest_path, records)
    return records


def validate_file(
    path: str | Path,
    *,
    schema_version: str = BDF_SCHEMA_VERSION,
    strict: bool = True,
) -> ValidationReport:
    """Validate an existing BDF-style CSV, Excel, or Parquet file."""
    input_path = Path(path)
    _ensure_input_file(input_path)
    try:
        df = read_bdf_like(input_path)
        report = validate(df, schema_version=schema_version, strict=strict)
        if report.valid or not looks_like_export_frame(df):
            return report
        return validate_export_frame(df, strict=strict)
    except OSError as exc:
        raise FileIOError(f"Could not read {input_path}: {exc}") from exc


_BATCH_INPUT_SUFFIXES = {
    ".csv",
    ".txt",
    ".tsv",
    ".xlsx",
    ".xls",
    ".mpt",
    ".mpr",
    ".mat",
    ".parquet",
    ".zip",
    ".tar",
    ".tgz",
}


def convert_eis(
    input_path: str | Path,
    output_path: str | Path,
    *,
    format: str = "csv",
    sheet: str | int | None = None,
) -> ValidationReport:
    """Convert an EIS file to an eisfit-compatible standardized table."""
    input_path = Path(input_path)
    _ensure_input_file(input_path)
    try:
        return _convert_eis(input_path, output_path, format=format, sheet=sheet)
    except BatteryDataStandardError:
        raise
    except OSError as exc:
        raise FileIOError(f"Could not convert EIS file {input_path}: {exc}") from exc


def _set_export_report_metadata(
    report: ConversionReport,
    internal_df: pl.DataFrame,
    export_df: pl.DataFrame,
) -> None:
    report.metadata["export_format"] = EXPORT_FORMAT_VERSION
    report.metadata["internal_columns"] = list(internal_df.columns)
    report.metadata["export_columns"] = list(export_df.columns)


def _load_metadata(metadata: dict[str, Any] | str | Path | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata
    path = Path(metadata)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileIOError(f"Could not read metadata file {path}: {exc}") from exc
    except JSONDecodeError as exc:
        raise ConversionError(f"Metadata file {path} is not valid JSON: {exc}") from exc


def _ensure_input_file(path: Path) -> None:
    if not path.exists():
        raise FileIOError(f"Input file does not exist: {path}")
    if not path.is_file():
        raise FileIOError(f"Input path is not a file: {path}")


def _write_manifest(path: str | Path | None, records: list[dict[str, Any]]) -> None:
    if path is None:
        return
    write_jsonl(path, records)


def _unique_output_stem(stem: str, index: int, used_outputs: set[Path]) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in stem).strip("._")
    safe = safe or f"neware-test-{index:03d}"
    candidate = safe
    counter = 2
    while any(path.stem.startswith(candidate) for path in used_outputs):
        candidate = f"{safe}-{counter}"
        counter += 1
    return candidate


def _auto_process_bdf(
    input_path: Path,
    *,
    detection: DetectionResult,
    profile: dict[str, Any],
    strict: bool,
    keep_raw: bool,
    current_sign: str,
    repair_policy: str,
    detection_threshold: float,
    options: dict[str, Any],
) -> tuple[Adapter, AdapterResult]:
    adapter_by_id = {adapter.id: adapter for adapter in all_adapters()}
    candidates = [
        candidate
        for candidate in detection.candidates
        if float(candidate.get("confidence") or 0.0) >= detection_threshold
        and candidate.get("cycler") in adapter_by_id
    ]
    if not candidates and detection.cycler in adapter_by_id:
        candidates = [{"cycler": detection.cycler, "confidence": detection.confidence}]
    if not any(candidate.get("cycler") == "generic" for candidate in candidates):
        candidates.append({"cycler": "generic", "confidence": 0.0})

    failures: list[str] = []
    fallback: tuple[Adapter, AdapterResult] | None = None
    for candidate in candidates:
        adapter = adapter_by_id[str(candidate["cycler"])]
        try:
            result = adapter.process(
                input_path,
                profile=profile,
                strict=False,
                keep_raw=keep_raw,
                current_sign=current_sign,
                repair_policy=repair_policy,
                options=options,
            )
            report = validate(result.data, strict=True)
            if report.valid:
                if strict:
                    return adapter, result
                return adapter, result
            fallback = fallback or (adapter, result)
            failures.append(f"{adapter.id}: " + "; ".join(issue.message for issue in report.issues))
        except BatteryDataStandardError as exc:
            failures.append(f"{adapter.id}: {exc}")

    if fallback is not None and not strict:
        return fallback
    raise ConversionError("Auto detection could not produce a valid BDF table. " + " | ".join(failures))


def _batch_convert_one(
    path: Path,
    output_root: Path,
    relative: Path,
    *,
    format: str,
    cycler: str | None,
    profile: str | Path | dict[str, Any] | None,
    metadata: dict[str, Any] | str | Path | None,
    strict: bool,
    keep_raw: bool,
    current_sign: str,
    repair_policy: str,
    detection_threshold: float,
    write_sidecars: bool,
    sheet: str | int | None,
    excel_sheets: str,
    archive_path: Path | None,
    archive_member: str | None,
) -> list[dict[str, Any]]:
    sheet_values: list[str | int | None] = [sheet]
    if path.suffix.lower() in {".xlsx", ".xls"} and excel_sheets in {"all", "first"} and sheet is None:
        import pandas as pd

        sheet_names = list(pd.ExcelFile(path).sheet_names)
        sheet_values = sheet_names if excel_sheets == "all" else sheet_names[:1]

    records: list[dict[str, Any]] = []
    for sheet_value in sheet_values:
        kind = detect_kind(path, sheet=sheet_value)
        output_suffix = "eis" if kind.kind == "eis" else "bdf"
        sheet_stem = f"{relative.stem}_{sheet_value}" if sheet_value is not None else relative.stem
        output_path = output_root / relative.parent / f"{sheet_stem}.{output_suffix}.{format}"
        base_record = {
            "input_path": str(path),
            "archive_path": str(archive_path) if archive_path else None,
            "archive_member": archive_member,
            "sheet_name": sheet_value,
            "data_kind": kind.kind,
            "kind_confidence": kind.confidence,
            "kind_reason": kind.reason,
        }
        if kind.kind == "unsupported":
            records.append(
                {
                    "status": "unsupported",
                    "record_type": "skipped",
                    "output_path": None,
                    "skip_reason": kind.reason,
                    **base_record,
                }
            )
            continue
        if kind.kind == "eis":
            report = convert_eis(path, output_path, format=format, sheet=sheet_value)
            records.append(
                {
                    "status": "ok",
                    "record_type": "converted",
                    "output_path": str(output_path),
                    "validation": report.to_dict(),
                    "rows": report.rows,
                    "columns": report.columns,
                    **base_record,
                }
            )
            continue

        report = convert(
            path,
            output_path,
            format=format,
            cycler=cycler,
            profile=profile,
            metadata=metadata,
            strict=strict,
            keep_raw=keep_raw,
            current_sign=current_sign,
            repair_policy=repair_policy,
            detection_threshold=detection_threshold,
            write_sidecars=write_sidecars,
            sheet=sheet_value,
        )
        records.append(
            {
                "status": "ok",
                "record_type": "converted",
                **base_record,
                **report.to_dict(),
                "data_kind": "bdf-timeseries",
            }
        )
    return records


def _candidate_confidence(detection: DetectionResult, cycler: str) -> float | None:
    if detection.cycler == cycler:
        return detection.confidence
    for candidate in detection.candidates:
        if candidate.get("cycler") == cycler:
            value = candidate.get("confidence")
            return float(value) if value is not None else None
    return None
