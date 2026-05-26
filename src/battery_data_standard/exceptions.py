"""Package-specific exceptions."""

from __future__ import annotations

from .reports import ValidationReport


class BatteryDataStandardError(Exception):
    """Base class for package errors."""


class DetectionError(BatteryDataStandardError):
    """Raised when a cycler format cannot be detected or loaded."""


class AmbiguousDetectionError(DetectionError):
    """Raised when multiple cycler formats are plausible."""


class UnsupportedFormatError(BatteryDataStandardError):
    """Raised when an input or output format is not supported."""


class UnsupportedFeatureError(BatteryDataStandardError):
    """Raised when a known but unavailable feature is requested."""


class ConversionError(BatteryDataStandardError):
    """Raised when conversion cannot be completed."""


class FileIOError(BatteryDataStandardError):
    """Raised when a file cannot be read or written."""


class ValidationFailed(BatteryDataStandardError):
    """Raised when strict validation fails."""

    def __init__(self, report: ValidationReport):
        self.report = report
        errors = [issue.message for issue in report.issues if issue.level == "error"]
        message = "Validation failed"
        if errors:
            message += ": " + "; ".join(errors)
        super().__init__(message)
