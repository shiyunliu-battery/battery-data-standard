"""Generic delimited/Excel adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from ..io import read_table, read_table_with_metadata
from ..reports import DetectionResult
from .base import Adapter, AdapterResult


class GenericAdapter(Adapter):
    id = "generic"
    display_name = "Generic CSV/Excel/MATLAB/Parquet"
    adapter_version = "1"
    support_tier = "fixture-backed"
    extensions = (".csv", ".txt", ".tsv", ".xlsx", ".xls", ".mat", ".parquet")
    signatures = ("voltage", "current", "time")
    column_aliases: dict[str, tuple[str, ...]] = {}

    def sniff(self, path: Path, sample: str) -> DetectionResult:
        if self.id != "generic":
            return super().sniff(path, sample)
        lower = sample.lower()
        hits = sum(token in lower for token in ("voltage", "current", "time", "电压", "电流"))
        confidence = 0.1 + min(0.35, hits * 0.1)
        return DetectionResult(self.id, confidence, "generic column-token match")

    def read_raw(self, path: Path, options: dict[str, Any] | None = None) -> pl.DataFrame:
        return read_table(path, options=options)

    def read_raw_with_metadata(self, path: Path, options: dict[str, Any] | None = None) -> AdapterResult:
        result = read_table_with_metadata(path, options=options)
        if self.__class__.read_raw is GenericAdapter.read_raw:
            return AdapterResult(result.data, metadata=result.metadata)
        return AdapterResult(self.read_raw(path, options=options), metadata=result.metadata)
