"""Command-line interface for battery_data_standard."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from ._version import __version__
from .api import (
    batch_convert,
    convert,
    convert_eis,
    detect,
    detect_kind,
    list_supported_formats,
    read_eis,
    validate_eis,
    validate_file,
)
from .exceptions import (
    BatteryDataStandardError,
    DetectionError,
    FileIOError,
    UnsupportedFeatureError,
    UnsupportedFormatError,
    ValidationFailed,
)
from .schema import BDF_SCHEMA_VERSION, schema_dict

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_UNSUPPORTED = 3
EXIT_VALIDATION = 4
EXIT_IO = 5
EXIT_PARTIAL = 6


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bds", description="BDF-first battery cycler converter")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--verbose", action="store_true", help="Enable informational logs on stderr.")
    parser.add_argument("--quiet", action="store_true", help="Suppress non-error logs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect", help="Detect the likely cycler format")
    detect_parser.add_argument("file")

    detect_kind_parser = subparsers.add_parser(
        "detect-kind", help="Detect BDF time-series, EIS, or unsupported data"
    )
    detect_kind_parser.add_argument("file")
    detect_kind_parser.add_argument("--sheet")

    convert_parser = subparsers.add_parser("convert", help="Convert raw cycler data to BDF-style data")
    convert_parser.add_argument("input")
    convert_parser.add_argument("output")
    convert_parser.add_argument("--cycler", default="auto")
    convert_parser.add_argument("--detect-threshold", type=float, default=0.1)
    convert_parser.add_argument("--profile")
    convert_parser.add_argument("--sheet")
    convert_parser.add_argument("--format", choices=("csv", "parquet"), default="csv")
    convert_parser.add_argument("--report")
    convert_parser.add_argument("--metadata")
    convert_parser.add_argument("--keep-raw", action="store_true")
    convert_parser.add_argument(
        "--current-sign",
        choices=("preserve", "discharge-positive", "charge-positive"),
        default="charge-positive",
    )
    convert_parser.add_argument("--no-strict", action="store_true")
    convert_parser.add_argument("--sidecars", action="store_true")
    convert_parser.add_argument(
        "--repair-policy",
        choices=("none", "warn", "repair"),
        default="warn",
        help="How to handle repairable table issues before validation.",
    )

    convert_eis_parser = subparsers.add_parser(
        "convert-eis", help="Convert EIS data to a standardized EIS table"
    )
    convert_eis_parser.add_argument("input")
    convert_eis_parser.add_argument("output")
    convert_eis_parser.add_argument("--sheet")
    convert_eis_parser.add_argument("--format", choices=("csv", "parquet"), default="csv")

    validate_parser = subparsers.add_parser("validate", help="Validate a BDF-style file")
    validate_parser.add_argument("file")
    validate_parser.add_argument("--schema", default=BDF_SCHEMA_VERSION)
    validate_parser.add_argument("--no-strict", action="store_true")

    validate_eis_parser = subparsers.add_parser("validate-eis", help="Validate an EIS standard file")
    validate_eis_parser.add_argument("file")
    validate_eis_parser.add_argument("--sheet")

    batch_parser = subparsers.add_parser("batch", help="Convert a directory of raw cycler files")
    batch_parser.add_argument("input_dir")
    batch_parser.add_argument("output_dir")
    batch_parser.add_argument("--recursive", action="store_true")
    batch_parser.add_argument("--manifest")
    batch_parser.add_argument("--fail-fast", action="store_true")
    batch_parser.add_argument(
        "--continue-on-error",
        action="store_false",
        dest="fail_fast",
        help="Continue converting remaining files after an error. This is the default.",
    )
    batch_parser.add_argument("--cycler", default="auto")
    batch_parser.add_argument("--detect-threshold", type=float, default=0.1)
    batch_parser.add_argument("--profile")
    batch_parser.add_argument("--sheet")
    batch_parser.add_argument("--excel-sheets", choices=("auto", "all", "first", "name"), default="auto")
    batch_parser.add_argument("--format", choices=("csv", "parquet"), default="csv")
    batch_parser.add_argument("--metadata")
    batch_parser.add_argument("--keep-raw", action="store_true")
    batch_parser.add_argument(
        "--current-sign",
        choices=("preserve", "discharge-positive", "charge-positive"),
        default="charge-positive",
    )
    batch_parser.add_argument("--no-strict", action="store_true")
    batch_parser.add_argument("--sidecars", action="store_true")
    batch_parser.add_argument(
        "--repair-policy",
        choices=("none", "warn", "repair"),
        default="warn",
        help="How to handle repairable table issues before validation.",
    )

    subparsers.add_parser("formats", help="Print supported cycler formats and maturity tiers")
    subparsers.add_parser("inspect-schema", help="Print the pinned schema")

    args = parser.parse_args(argv)
    _configure_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        if args.command == "detect":
            print(json.dumps(detect(args.file).to_dict(), indent=2))
        elif args.command == "detect-kind":
            print(json.dumps(detect_kind(args.file, sheet=args.sheet).to_dict(), indent=2))
        elif args.command == "convert":
            report = convert(
                args.input,
                args.output,
                format=args.format,
                cycler=args.cycler,
                profile=args.profile,
                metadata=args.metadata,
                strict=not args.no_strict,
                keep_raw=args.keep_raw,
                current_sign=args.current_sign,
                repair_policy=args.repair_policy,
                detection_threshold=args.detect_threshold,
                report_path=args.report,
                write_sidecars=args.sidecars,
                sheet=args.sheet,
            )
            print(report.to_json())
        elif args.command == "convert-eis":
            report = convert_eis(args.input, args.output, format=args.format, sheet=args.sheet)
            print(report.to_json())
        elif args.command == "validate":
            validation_report = validate_file(
                args.file, schema_version=args.schema, strict=not args.no_strict
            )
            print(validation_report.to_json())
            return EXIT_OK if validation_report.valid else EXIT_VALIDATION
        elif args.command == "validate-eis":
            validation_report = validate_eis(read_eis(args.file, sheet=args.sheet))
            print(validation_report.to_json())
            return EXIT_OK if validation_report.valid else EXIT_VALIDATION
        elif args.command == "batch":
            records = batch_convert(
                args.input_dir,
                args.output_dir,
                recursive=args.recursive,
                manifest_path=args.manifest,
                fail_fast=args.fail_fast,
                format=args.format,
                cycler=args.cycler,
                profile=args.profile,
                metadata=args.metadata,
                strict=not args.no_strict,
                keep_raw=args.keep_raw,
                current_sign=args.current_sign,
                repair_policy=args.repair_policy,
                detection_threshold=args.detect_threshold,
                write_sidecars=args.sidecars,
                sheet=args.sheet,
                excel_sheets=args.excel_sheets,
            )
            converted = sum(record.get("record_type") == "converted" for record in records)
            skipped = sum(record.get("record_type") == "skipped" for record in records)
            errors = sum(record.get("status") == "error" for record in records)
            print(
                json.dumps(
                    {
                        "files": len(records),
                        "converted": converted,
                        "skipped": skipped,
                        "errors": errors,
                        "records": records,
                    },
                    indent=2,
                )
            )
            return EXIT_OK if errors == 0 and converted > 0 else EXIT_PARTIAL
        elif args.command == "formats":
            print(json.dumps({"formats": list_supported_formats()}, indent=2))
        elif args.command == "inspect-schema":
            print(json.dumps(schema_dict(), indent=2))
    except ValidationFailed as exc:
        print(f"bds: validation failed: {exc}", file=sys.stderr)
        return EXIT_VALIDATION
    except (UnsupportedFormatError, UnsupportedFeatureError) as exc:
        print(f"bds: unsupported: {exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED
    except DetectionError as exc:
        print(f"bds: detection error: {exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED
    except FileIOError as exc:
        print(f"bds: io error: {exc}", file=sys.stderr)
        return EXIT_IO
    except BatteryDataStandardError as exc:
        print(f"bds: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


def _configure_logging(*, verbose: bool, quiet: bool) -> None:
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s:%(name)s:%(message)s")


if __name__ == "__main__":
    raise SystemExit(main())
