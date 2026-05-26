"""Low-level file readers for delimited text and Excel exports."""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pandas as pd
import polars as pl

from .exceptions import UnsupportedFeatureError, UnsupportedFormatError

DEFAULT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "cp1252", "latin-1")
logger = logging.getLogger(__name__)


@dataclass
class TableReadResult:
    data: pl.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)


def read_text(path: str | Path, encodings: tuple[str, ...] = DEFAULT_ENCODINGS) -> tuple[str, str]:
    data = Path(path).read_bytes()
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return data.decode("utf-8", errors="replace"), "utf-8"


def sample_text(path: str | Path, limit: int = 65536) -> str:
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        try:
            return "\n".join(xlsx_sheet_names(path))[:limit]
        except Exception:
            pass
    if path.suffix.lower() == ".xls":
        try:
            workbook = pd.ExcelFile(path)
            parts: list[str] = []
            for name in workbook.sheet_names[:5]:
                df = pd.read_excel(workbook, sheet_name=name, nrows=20)
                parts.append(str(name))
                parts.append("\t".join(str(col) for col in df.columns))
                parts.append(df.head(5).to_csv(sep="\t", index=False))
            return "\n".join(parts)[:limit]
        except Exception:
            pass
    if path.suffix.lower() == ".mat":
        try:
            return sample_matlab(path, limit=limit)
        except Exception:
            pass
    if path.suffix.lower() == ".parquet":
        try:
            df = pl.read_parquet(path, n_rows=20)
            return ("\t".join(str(col) for col in df.columns) + "\n" + df.head(5).write_csv(separator="\t"))[
                :limit
            ]
        except Exception:
            pass
    data = path.read_bytes()[:limit]
    for encoding in DEFAULT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def xlsx_sheet_names(path: str | Path) -> list[str]:
    """Return workbook sheet names without loading worksheet cell data."""
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        workbook_xml = archive.read("xl/workbook.xml")
    root = ElementTree.fromstring(workbook_xml)
    names: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "sheet":
            name = element.attrib.get("name")
            if name is not None:
                names.append(str(name))
    return names


def read_table(
    path: str | Path,
    *,
    encodings: tuple[str, ...] = DEFAULT_ENCODINGS,
    options: dict[str, Any] | None = None,
) -> pl.DataFrame:
    return read_table_with_metadata(path, encodings=encodings, options=options).data


def read_table_with_metadata(
    path: str | Path,
    *,
    encodings: tuple[str, ...] = DEFAULT_ENCODINGS,
    options: dict[str, Any] | None = None,
) -> TableReadResult:
    path = Path(path)
    options = options or {}
    suffix = path.suffix.lower()
    if suffix == ".mpr":
        raise UnsupportedFeatureError(
            "BioLogic .mpr is a binary EC-Lab format and is not supported yet; export .mpt text instead."
        )
    if suffix in {".xlsx", ".xls"}:
        return read_excel_with_metadata(
            path,
            sheet=options.get("sheet"),
            sheet_policy=str(options.get("excel_sheets") or "auto"),
        )
    if suffix == ".mat":
        data = read_matlab(path)
        return TableReadResult(
            data,
            {
                "source_format": "matlab",
                "backend": "scipy/h5py",
                "raw_rows": data.height,
                "raw_columns": list(data.columns),
            },
        )
    if suffix == ".parquet":
        data = pl.read_parquet(path)
        return TableReadResult(
            data,
            {
                "source_format": "parquet",
                "backend": "polars",
                "raw_rows": data.height,
                "raw_columns": list(data.columns),
            },
        )
    text, _encoding = read_text(path, encodings)
    lines = text.splitlines()
    header_idx = find_biologic_mpt_header_line(text) if suffix == ".mpt" else find_header_line(text)
    delimiter = infer_delimiter_from_lines(lines[header_idx : header_idx + 25])
    has_header = not _looks_like_data_header_line(
        lines[header_idx] if header_idx < len(lines) else "", delimiter
    )
    table_text = "\n".join(lines[header_idx:])
    source = StringIO(table_text)
    metadata = {
        "source_format": suffix.lstrip(".") or "text",
        "encoding": _encoding,
        "delimiter": delimiter,
        "header_row": header_idx,
        "has_header": has_header,
    }
    try:
        data = pl.read_csv(
            source,
            separator=delimiter,
            skip_rows=0,
            has_header=has_header,
            truncate_ragged_lines=True,
            null_values=["", "NaN", "nan", "-", "--"],
            infer_schema_length=10000,
        )
        if _looks_like_data_header(data.columns):
            source.seek(0)
            data = pl.read_csv(
                source,
                separator=delimiter,
                skip_rows=0,
                has_header=False,
                truncate_ragged_lines=True,
                null_values=["", "NaN", "nan", "-", "--"],
                infer_schema_length=10000,
            )
            metadata["has_header"] = False
        data = _drop_unit_row(data)
        data = _apply_positional_columns(data)
        metadata.update({"backend": "polars", "raw_rows": data.height, "raw_columns": list(data.columns)})
        return TableReadResult(data, metadata)
    except Exception as exc:
        logger.info("polars CSV reader failed for %s; falling back to pandas: %s", path, exc)
        source.seek(0)
        df = pd.read_csv(
            source,
            sep=delimiter,
            skiprows=0,
            header=0 if has_header else None,
            engine="python",
            on_bad_lines="warn",
        )
        data = _pandas_to_polars(df)
        if _looks_like_data_header(data.columns):
            source.seek(0)
            df = pd.read_csv(
                source,
                sep=delimiter,
                skiprows=0,
                header=None,
                engine="python",
                on_bad_lines="warn",
            )
            data = _pandas_to_polars(df)
            metadata["has_header"] = False
        data = _drop_unit_row(data)
        data = _apply_positional_columns(data)
        metadata.update({"backend": "pandas", "raw_rows": data.height, "raw_columns": list(data.columns)})
        return TableReadResult(data, metadata)


def read_excel(path: str | Path, *, sheet: str | int | None = None) -> pl.DataFrame:
    return read_excel_with_metadata(path, sheet=sheet).data


def read_excel_with_metadata(
    path: str | Path,
    *,
    sheet: str | int | None = None,
    sheet_policy: str = "auto",
) -> TableReadResult:
    path = Path(path)
    if sheet is not None:
        data = pd.read_excel(path, sheet_name=sheet)
        if isinstance(data, dict):
            if not data:
                return TableReadResult(pl.DataFrame(), {"source_format": path.suffix.lower().lstrip(".")})
            sheet_name, df = next(iter(data.items()))
        else:
            sheet_name, df = str(sheet), data
        df, excel_header_row = _prepare_excel_dataframe(df)
        frame = _pandas_to_polars(df)
        frame = _drop_unit_row(frame)
        frame = _apply_positional_columns(frame)
        return TableReadResult(
            frame,
            {
                "source_format": path.suffix.lower().lstrip("."),
                "backend": "pandas",
                "sheet_names": [sheet_name],
                "selected_sheets": [sheet_name],
                "sheet_name": sheet_name,
                "excel_header_row": excel_header_row,
                "raw_rows": frame.height,
                "raw_columns": list(frame.columns),
            },
        )

    sheets = pd.read_excel(path, sheet_name=None)
    frames: list[tuple[str, pd.DataFrame]] = []
    for name, df in sheets.items():
        if str(name).lower() in {"info", "metadata", "readme"} or df.empty:
            continue
        frames.append((str(name), df))
    if not frames:
        return TableReadResult(
            pl.DataFrame(),
            {
                "source_format": path.suffix.lower().lstrip("."),
                "backend": "pandas",
                "sheet_names": list(sheets),
                "selected_sheets": [],
            },
        )

    scored = [(name, df, _score_excel_sheet(df)) for name, df in frames]
    selected = scored[0] if sheet_policy == "first" else _select_excel_sheet(path, scored)
    selected_df, excel_header_row = _prepare_excel_dataframe(selected[1])
    data = _pandas_to_polars(selected_df)
    data = _drop_unit_row(data)
    data = _apply_positional_columns(data)
    return TableReadResult(
        data,
        {
            "source_format": path.suffix.lower().lstrip("."),
            "backend": "pandas",
            "sheet_names": list(sheets),
            "selected_sheets": [selected[0]],
            "sheet_name": selected[0],
            "excel_header_row": excel_header_row,
            "raw_rows": data.height,
            "raw_columns": list(data.columns),
        },
    )


def _select_excel_sheet(
    path: Path, scored: list[tuple[str, pd.DataFrame, int]]
) -> tuple[str, pd.DataFrame, int]:
    if len(scored) == 1:
        return scored[0]

    positive = [item for item in scored if item[2] > 0]
    candidates = positive or scored
    best_score = max(score for _name, _df, score in candidates)
    best = [item for item in candidates if item[2] == best_score]
    if len(best) == 1 and (best_score > 0 or len(candidates) == 1):
        return best[0]

    names = ", ".join(name for name, _df, score in best)
    raise UnsupportedFormatError(
        f"Excel file {path} has multiple plausible data sheets ({names}); "
        "export the record sheet as CSV or keep only one data sheet before conversion."
    )


def _score_excel_sheet(df: pd.DataFrame) -> int:
    score = _score_header_values(df.columns)
    for _idx, row in df.head(30).iterrows():
        score = max(score, _score_header_values(row.to_list()))
    return score


def _score_header_values(values: Any) -> int:
    header_tokens = (
        "time",
        "test",
        "voltage",
        "current",
        "cycle",
        "step",
        "capacity",
        "energy",
        "电压",
        "电流",
        "时间",
    )
    text = " ".join(str(value).lower() for value in values if not pd.isna(value))
    return sum(token in text for token in header_tokens)


def _prepare_excel_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, int | None]:
    """Promote an in-sheet header row when Excel has title or metadata rows."""
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.empty:
        return df, None

    current_score = _score_header_values(df.columns)
    best_row: int | None = None
    best_score = current_score
    for position, (_idx, row) in enumerate(df.head(30).iterrows()):
        score = _score_header_values(row.to_list())
        if score > best_score:
            best_score = score
            best_row = position

    if best_row is None or best_score < 2:
        return df, None

    header = df.iloc[best_row].to_list()
    data = df.iloc[best_row + 1 :].reset_index(drop=True)
    data.columns = _dedupe_excel_columns(header)
    data = data.dropna(axis=0, how="all").dropna(axis=1, how="all")
    return data, best_row


def _dedupe_excel_columns(values: list[Any]) -> list[str]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(values):
        if pd.isna(value) or not str(value).strip() or str(value).lower().startswith("unnamed:"):
            name = f"column_{index + 1}"
        else:
            name = str(value).strip()
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count:
            name = f"{name}_{count}"
        names.append(name)
    return names


def _pandas_to_polars(df: pd.DataFrame) -> pl.DataFrame:
    try:
        return pl.from_pandas(df)
    except Exception as exc:
        logger.info("polars from_pandas failed; using dtype-normalized fallback: %s", exc)

    columns: dict[str, Any] = {}
    for column in df.columns:
        series = df[column]
        if pd.api.types.is_integer_dtype(series.dtype) or pd.api.types.is_float_dtype(series.dtype):
            columns[str(column)] = pd.to_numeric(series, errors="coerce").to_list()
        elif pd.api.types.is_bool_dtype(series.dtype):
            columns[str(column)] = series.astype("object").where(pd.notna(series), None).to_list()
        else:
            columns[str(column)] = series.astype("object").where(pd.notna(series), None).to_list()
    series_list = [pl.Series(name, values, strict=False) for name, values in columns.items()]
    return pl.DataFrame(series_list)


def sample_matlab(path: str | Path, *, limit: int = 65536) -> str:
    variables = _load_matlab_variables(path)
    lines: list[str] = []
    for name, value in variables.items():
        shape = getattr(value, "shape", None)
        dtype = getattr(value, "dtype", None)
        lines.append(f"{name}\tshape={shape}\tdtype={dtype}")
    return "\n".join(lines)[:limit]


def read_matlab(path: str | Path) -> pl.DataFrame:
    variables = _load_matlab_variables(path)
    vector_frame = _matlab_vectors_to_frame(variables)
    if vector_frame is not None:
        return vector_frame

    matrix_frame = _matlab_matrix_to_frame(variables)
    if matrix_frame is not None:
        return matrix_frame

    raise UnsupportedFormatError(
        f"No MATLAB variables could be mapped to time/voltage/current columns. Variables: {list(variables)}"
    )


def _load_matlab_variables(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        import scipy.io
    except ImportError as exc:
        raise UnsupportedFeatureError(
            "MATLAB files require the optional MATLAB dependencies. "
            "Install with battery-data-standard[matlab]."
        ) from exc

    try:
        loaded = scipy.io.loadmat(path, squeeze_me=True, struct_as_record=False)
        return _flatten_matlab_variables({k: v for k, v in loaded.items() if not k.startswith("__")})
    except NotImplementedError:
        return _load_hdf5_matlab_variables(path)


def _load_hdf5_matlab_variables(path: Path) -> dict[str, Any]:
    import numpy as np

    try:
        import h5py
    except ImportError as exc:
        raise UnsupportedFeatureError(
            "MATLAB v7.3 files require h5py. Install with battery-data-standard[matlab]."
        ) from exc

    values: dict[str, Any] = {}
    with h5py.File(path, "r") as handle:
        _flatten_hdf5_group(handle, "", values, np)
    return _flatten_matlab_variables(values)


def _flatten_hdf5_group(group: Any, prefix: str, values: dict[str, Any], np: Any) -> None:
    for key in group:
        item = group[key]
        name = f"{prefix}_{key}" if prefix else str(key)
        if hasattr(item, "keys"):
            _flatten_hdf5_group(item, name, values, np)
            continue
        if hasattr(item, "shape"):
            array = np.array(item)
            if array.ndim > 1:
                array = array.T
            values[name] = array.squeeze()


def _flatten_matlab_variables(variables: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in variables.items():
        _flatten_matlab_value(str(key), value, flattened, depth=0)
    return flattened


def _flatten_matlab_value(name: str, value: Any, output: dict[str, Any], *, depth: int) -> None:
    if depth > 6:
        output[name] = value
        return
    import numpy as np

    if hasattr(value, "_fieldnames"):
        for field in getattr(value, "_fieldnames", []) or []:
            _flatten_matlab_value(f"{name}_{field}", getattr(value, field), output, depth=depth + 1)
        return
    array = np.asarray(value)
    if array.dtype == object:
        squeezed = array.squeeze()
        if squeezed.shape == ():
            _flatten_matlab_value(name, squeezed.item(), output, depth=depth + 1)
            return
        for index, item in enumerate(squeezed.reshape(-1).tolist()):
            _flatten_matlab_value(f"{name}_{index}", item, output, depth=depth + 1)
        return
    output[name] = value


def _matlab_vectors_to_frame(variables: dict[str, Any]) -> pl.DataFrame | None:
    import numpy as np

    aliases = {
        "Time": ("time", "t", "test_time", "testtime", "seconds", "sec"),
        "Voltage": ("voltage", "volt", "volts", "v", "ewe", "ecell"),
        "Current": ("current", "curr", "i", "amps", "ampere"),
        "Cycle": ("cycle", "cycle_index", "cycleid"),
        "Step": ("step", "step_index", "stepid"),
        "SOC": ("soc", "stateofcharge"),
        "Temperature": ("temperature", "temp", "degc"),
    }
    selected: dict[str, list[float | int | None]] = {}
    expected_length: int | None = None
    for label, names in aliases.items():
        for name, value in variables.items():
            slug = _slug(name)
            if slug not in names and not any(slug.endswith(alias) for alias in names):
                continue
            array = np.asarray(value).squeeze()
            if array.ndim != 1 or array.size == 0:
                continue
            if expected_length is None:
                expected_length = int(array.size)
            if int(array.size) != expected_length:
                continue
            selected[label] = _array_to_values(array)
            break
    if {"Time", "Voltage", "Current"}.issubset(selected):
        return pl.DataFrame(selected)
    paired = _matlab_paired_vectors_to_frame(variables)
    if paired is not None:
        return paired
    return None


def _matlab_paired_vectors_to_frame(variables: dict[str, Any]) -> pl.DataFrame | None:
    import numpy as np

    by_suffix: dict[str, dict[str, list[float | int | None]]] = {}
    for name, value in variables.items():
        array = np.asarray(value).squeeze()
        if array.ndim != 1 or array.size == 0:
            continue
        slug = _slug(name)
        kind: str | None = None
        suffix = slug
        for prefix, label in (
            ("cur", "Current"),
            ("current", "Current"),
            ("volt", "Voltage"),
            ("voltage", "Voltage"),
            ("time", "Time"),
            ("t", "Time"),
        ):
            if slug == prefix or slug.startswith(prefix):
                kind = label
                suffix = slug.removeprefix(prefix).strip("_")
                break
        if kind is None:
            continue
        by_suffix.setdefault(suffix, {})[kind] = _array_to_values(array)

    for values in by_suffix.values():
        if {"Time", "Voltage", "Current"}.issubset(values):
            lengths = {len(v) for v in values.values()}
            if len(lengths) == 1:
                return pl.DataFrame(values)
    return None


def _matlab_matrix_to_frame(variables: dict[str, Any]) -> pl.DataFrame | None:
    import numpy as np

    matrices = []
    for name, value in variables.items():
        array = np.asarray(value).squeeze()
        if array.ndim == 2 and min(array.shape) >= 3:
            matrices.append((name, array))
    if not matrices:
        return None

    name, array = max(matrices, key=lambda item: item[1].shape[0])
    lower_name = name.lower()
    if "ocv" in lower_name and array.shape[1] >= 8:
        return pl.DataFrame(
            {
                "Time": _array_to_values(array[:, 2]),
                "Current": _array_to_values(array[:, 6]),
                "Voltage": _array_to_values(array[:, 7]),
            }
        )
    if array.shape[1] == 3:
        return pl.DataFrame(
            {
                "Time": _array_to_values(array[:, 0]),
                "Voltage": _array_to_values(array[:, 1]),
                "Current": _array_to_values(array[:, 2]),
            }
        )
    return None


def _array_to_values(array: Any) -> list[float | int | None]:
    import math

    import numpy as np

    values: list[float | int | None] = []
    for value in np.asarray(array).reshape(-1).tolist():
        if value is None:
            values.append(None)
            continue
        if isinstance(value, (int, np.integer)):
            values.append(int(value))
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            values.append(None)
            continue
        values.append(number if math.isfinite(number) else None)
    return values


def infer_delimiter(line: str) -> str:
    if not line:
        return ","
    candidates = [",", "\t", ";", "|"]
    best = max(candidates, key=lambda sep: line.count(sep))
    if line.count(best) > 0:
        return best
    return " " if re.search(r"\S+\s+\S+", line.strip()) else ","


def infer_delimiter_from_lines(lines: list[str]) -> str:
    candidates = [",", "\t", ";", "|", " "]
    nonempty = [line for line in lines if line.strip()][:25]
    if not nonempty:
        return ","
    scores: dict[str, float] = dict.fromkeys(candidates, 0.0)
    for candidate in candidates:
        row_lengths: list[int] = []
        residual_delimiters = 0
        for line in nonempty:
            try:
                cells = next(csv.reader([line], delimiter=candidate))
            except csv.Error:
                continue
            row_lengths.append(len(cells))
            if candidate != ";":
                residual_delimiters += sum(";" in cell for cell in cells)
        useful_lengths = [length for length in row_lengths if length > 1]
        if not useful_lengths:
            continue
        median = sorted(useful_lengths)[len(useful_lengths) // 2]
        consistent = sum(length == median for length in useful_lengths)
        spread = max(useful_lengths) - min(useful_lengths)
        scores[candidate] = median * 10 + consistent * 5 - spread * 3 - residual_delimiters * 4
        scores[candidate] += sum(line.count(candidate) for line in nonempty) * 0.2
    non_space = [candidate for candidate in candidates if candidate != " "]
    best_non_space = max(non_space, key=lambda sep: scores[sep])
    if scores[best_non_space] > 0:
        return best_non_space
    return " " if scores[" "] > 0 else best_non_space


def _looks_like_data_header(columns: list[str]) -> bool:
    if not columns:
        return False
    suspicious = sum(_looks_like_data_token(str(column)) for column in columns)
    return suspicious >= max(2, int(len(columns) * 0.6))


def _looks_like_data_header_line(line: str, delimiter: str) -> bool:
    if not line.strip():
        return False
    cells = [cell.strip() for cell in next(csv.reader([line], delimiter=delimiter))]
    if len(cells) < 2:
        return False
    suspicious = sum(_looks_like_data_token(cell) for cell in cells)
    return suspicious >= max(2, int(len(cells) * 0.6))


def _looks_like_data_token(value: str) -> bool:
    text = str(value).strip()
    if not text:
        return True
    if re.match(r"^\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}(?:\s+\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)?", text):
        return True
    if re.match(r"^-?\d+(?:[.,]\d+)?(?:e[+-]?\d+)?$", text, flags=re.IGNORECASE):
        return True
    if re.match(r"^\d+d?\s*\d{1,2}:\d{2}:\d{2}(?:\.\d+)?$", text, flags=re.IGNORECASE):
        return True
    return bool(re.match(r"^column_\d+$|^_\d+$", text, flags=re.IGNORECASE))


def _apply_positional_columns(data: pl.DataFrame) -> pl.DataFrame:
    if data.width < 10:
        return data
    if not _looks_like_generic_columns(data.columns):
        return data
    first_row = data.row(0, named=True) if data.height else {}
    values = [first_row.get(column) for column in data.columns]
    if not values or not _looks_like_data_token(str(values[0])):
        return data
    rename = {
        data.columns[0]: "Date Time",
        data.columns[1]: "Cycle Count",
        data.columns[2]: "Status",
        data.columns[3]: "Test Time",
        data.columns[4]: "Step Time",
        data.columns[7]: "Step Type",
        data.columns[8]: "Voltage (V)",
        data.columns[9]: "Current (A)",
        data.columns[10]: "Temperature (C)",
    }
    return data.rename({old: new for old, new in rename.items() if old in data.columns})


def _drop_unit_row(data: pl.DataFrame) -> pl.DataFrame:
    if data.is_empty():
        return data
    values = list(data.row(0))
    if not _looks_like_unit_row(values):
        return data
    return data.slice(1)


def _looks_like_unit_row(values: list[Any]) -> bool:
    unit_like = 0
    data_like = 0
    for value in values:
        text = "" if value is None else str(value).strip()
        if not text:
            continue
        if _looks_like_data_token(text):
            data_like += 1
            continue
        if re.match(r"^\[?[A-Za-zµμ°%/(). -]+\]?$", text):
            unit_like += 1
    return unit_like >= 2 and data_like == 0


def _looks_like_generic_columns(columns: list[str]) -> bool:
    return all(re.match(r"^column_\d+$|^_\d+$|^\d+$", str(column), flags=re.IGNORECASE) for column in columns)


def find_biologic_mpt_header_line(text: str) -> int:
    """Find the column header row in BioLogic EC-Lab text exports."""
    lines = text.splitlines()
    for idx, line in enumerate(lines[:200]):
        lower = line.lower()
        if "time/s" in lower and ("ewe/v" in lower or "i/ma" in lower or "i/a" in lower):
            return idx

    for line in lines[:50]:
        match = re.search(r"nb\s+header\s+lines\s*[:=]\s*(\d+)", line, flags=re.IGNORECASE)
        if not match:
            continue
        header_count = int(match.group(1))
        for candidate in range(max(0, header_count - 3), min(len(lines), header_count + 3)):
            lower = lines[candidate].lower()
            if "time" in lower and ("ewe" in lower or "ecell" in lower or "\ti/" in lower):
                return candidate
        return max(0, min(header_count - 1, len(lines) - 1))

    return find_header_line(text)


def find_header_line(text: str) -> int:
    """Find the likely header line in text exports with optional preambles."""
    lines = text.splitlines()
    if not lines:
        return 0
    best_idx = 0
    best_score = -1
    header_tokens = (
        "time",
        "test",
        "voltage",
        "current",
        "cycle",
        "step",
        "date",
        "capacity",
        "energy",
        "电压",
        "电流",
        "时间",
    )
    for idx, line in enumerate(lines[:200]):
        if not line.strip():
            continue
        lower = line.lower()
        if "~time[h]" in lower and "u[v]" in lower and "i[a]" in lower:
            return idx
        if "time stamp" in lower and "step time" in lower and "voltage" in lower and "current" in lower:
            return idx
        delimiter = infer_delimiter(line)
        cells = [c.strip().lower() for c in next(csv.reader([line], delimiter=delimiter))]
        score = sum(1 for cell in cells for token in header_tokens if token in cell)
        score += line.count(delimiter)
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


def write_dataframe(df: pl.DataFrame, path: str | Path, *, fmt: str | None = None) -> None:
    path = Path(path)
    output_format = (fmt or format_from_suffix(path)).lower()
    if output_format == "csv":
        _atomic_write(path, lambda tmp_path: df.write_csv(tmp_path))
    elif output_format == "parquet":
        _atomic_write(path, lambda tmp_path: df.write_parquet(tmp_path))
    else:
        raise UnsupportedFormatError(f"Unsupported output format: {fmt}")


def write_json(path: str | Path, data: Any) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    _atomic_write_text(Path(path), text)


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    _atomic_write_text(Path(path), text)


def _atomic_write_text(path: Path, text: str) -> None:
    def writer(tmp_path: Path) -> None:
        tmp_path.write_text(text, encoding="utf-8")

    _atomic_write(path, writer)


def _atomic_write(path: Path, writer: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        ) as handle:
            temp_name = handle.name
        temp_path = Path(temp_name)
        writer(temp_path)
        with temp_path.open("r+b") as handle:
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        if temp_name is not None:
            temp_path = Path(temp_name)
            if temp_path.exists():
                temp_path.unlink()


def read_bdf_like(path: str | Path) -> pl.DataFrame:
    path = Path(path)
    if ".parquet" in "".join(path.suffixes).lower():
        return pl.read_parquet(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return read_excel(path)
    return pl.read_csv(path, null_values=["", "NaN", "nan"])


def format_from_suffix(path: Path) -> str:
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(".parquet"):
        return "parquet"
    return "csv"


def cleaned_column_names(df: pl.DataFrame) -> pl.DataFrame:
    rename = {col: re.sub(r"[\t\"]+", "", str(col)).strip() for col in df.columns}
    rename = {old: new for old, new in rename.items() if old != new}
    return df.rename(rename) if rename else df


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())
