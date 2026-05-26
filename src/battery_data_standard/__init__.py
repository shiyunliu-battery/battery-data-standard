"""BDF-first battery cycler conversion library."""

from ._version import __version__
from .api import (
    batch_convert,
    convert,
    convert_eis,
    convert_neware_groups,
    detect,
    detect_kind,
    group_neware_files,
    list_supported_formats,
    read,
    read_eis,
    read_with_report,
    validate_eis,
)
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
from .reports import ConversionReport, DetectionResult, ValidationReport
from .schema import BDF_SCHEMA_VERSION
from .summary import summarize_cycles, summarize_steps
from .validation import validate

__all__ = [
    "AmbiguousDetectionError",
    "BDF_SCHEMA_VERSION",
    "BatteryDataStandardError",
    "ConversionReport",
    "ConversionError",
    "DetectionResult",
    "DetectionError",
    "FileIOError",
    "UnsupportedFeatureError",
    "UnsupportedFormatError",
    "ValidationFailed",
    "ValidationReport",
    "__version__",
    "batch_convert",
    "convert",
    "convert_eis",
    "convert_neware_groups",
    "detect",
    "detect_kind",
    "group_neware_files",
    "list_supported_formats",
    "read",
    "read_eis",
    "read_with_report",
    "summarize_cycles",
    "summarize_steps",
    "validate",
    "validate_eis",
]
