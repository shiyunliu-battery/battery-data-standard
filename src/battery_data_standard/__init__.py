"""Battery cycler conversion and intake QA library."""

from ._version import __version__
from .api import (
    batch_convert,
    convert,
    convert_eis,
    convert_neware_groups,
    detect,
    detect_kind,
    group_neware_files,
    list_export_targets,
    list_supported_formats,
    read,
    read_eis,
    read_with_report,
    validate_eis,
    validate_file,
)
from .audit import AuditRecord, AuditReport, audit, audit_file
from .diagnostics import ExplainReport, explain
from .exceptions import (
    AmbiguousDetectionError,
    BatteryDataStandardError,
    ConversionError,
    DetectionError,
    FileIOError,
    UnsupportedFeatureError,
    UnsupportedFormatError,
    ValidationFailed,
)
from .export import to_export_frame
from .reporting import (
    render_explain_html,
    write_conversion_report,
    write_conversion_reports,
    write_explain_report,
    write_explain_reports,
)
from .reports import ConversionReport, DetectionResult, ValidationReport
from .schema import BDF_SCHEMA_VERSION, BDS_SCHEMA_VERSION
from .summary import summarize_cycles, summarize_steps
from .validation import validate

__all__ = [
    "AmbiguousDetectionError",
    "AuditRecord",
    "AuditReport",
    "BDF_SCHEMA_VERSION",
    "BDS_SCHEMA_VERSION",
    "BatteryDataStandardError",
    "ConversionReport",
    "ConversionError",
    "DetectionResult",
    "DetectionError",
    "ExplainReport",
    "FileIOError",
    "UnsupportedFeatureError",
    "UnsupportedFormatError",
    "ValidationFailed",
    "ValidationReport",
    "__version__",
    "batch_convert",
    "audit",
    "audit_file",
    "convert",
    "convert_eis",
    "convert_neware_groups",
    "detect",
    "detect_kind",
    "explain",
    "group_neware_files",
    "list_export_targets",
    "list_supported_formats",
    "read",
    "read_eis",
    "read_with_report",
    "render_explain_html",
    "summarize_cycles",
    "summarize_steps",
    "to_export_frame",
    "validate",
    "validate_file",
    "validate_eis",
    "write_explain_report",
    "write_explain_reports",
    "write_conversion_report",
    "write_conversion_reports",
]
