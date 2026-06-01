"""Adapter base classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from ..reports import ColumnProvenance, DetectionResult


@dataclass
class AdapterResult:
    data: pl.DataFrame
    warnings: list[str] = field(default_factory=list)
    provenance: list[ColumnProvenance] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Adapter:
    id = "abstract"
    display_name = "Abstract"
    adapter_version = "1"
    support_tier = "best_effort"
    extensions: tuple[str, ...] = ()
    signatures: tuple[str, ...] = ()
    column_aliases: dict[str, tuple[str, ...]] = {}
    raw_current_sign: str = "unknown"

    def sniff(self, path: Path, sample: str) -> DetectionResult:
        common_table_suffixes = {".csv", ".txt", ".tsv", ".xlsx", ".xls", ".mat", ".parquet"}
        suffix = path.suffix.lower()
        suffix_score = (
            0.1
            if (not self.extensions or suffix in self.extensions) and suffix not in common_table_suffixes
            else 0.0
        )
        sample_lower = sample.lower()
        hits = [token for token in self.signatures if token.lower() in sample_lower]
        confidence = suffix_score + min(0.8, 0.2 * len(hits))
        reason = "signature match" if hits else "extension fallback"
        return DetectionResult(self.id, confidence, reason)

    def read_raw(self, path: Path, options: dict[str, Any] | None = None) -> pl.DataFrame:
        raise NotImplementedError

    def read_raw_with_metadata(self, path: Path, options: dict[str, Any] | None = None) -> AdapterResult:
        return AdapterResult(self.read_raw(path, options=options))

    def normalize(
        self,
        raw: pl.DataFrame,
        *,
        profile: dict[str, Any] | None = None,
        strict: bool = True,
        keep_raw: bool = False,
        current_sign: str = "charge-positive",
        repair_policy: str = "warn",
    ) -> AdapterResult:
        from .normalization import normalize_raw_frame

        return normalize_raw_frame(
            raw,
            adapter_id=self.id,
            aliases=self.column_aliases,
            profile=profile,
            strict=strict,
            keep_raw=keep_raw,
            current_sign=current_sign,
            raw_current_sign=self.raw_current_sign,
        )

    def repair(self, data: pl.DataFrame, *, repair_policy: str = "warn") -> AdapterResult:
        from .normalization import repair_bds_frame

        df, warnings = repair_bds_frame(data, policy=repair_policy)
        return AdapterResult(df, warnings=warnings, metadata={"repair_operations": list(warnings)})

    def extract_metadata(self, raw: pl.DataFrame) -> dict[str, Any]:
        return {"source_adapter": self.id, "raw_columns": list(raw.columns)}

    def process(
        self,
        path: Path,
        *,
        profile: dict[str, Any] | None = None,
        strict: bool = True,
        keep_raw: bool = False,
        current_sign: str = "charge-positive",
        repair_policy: str = "warn",
        options: dict[str, Any] | None = None,
    ) -> AdapterResult:
        raw_result = self.read_raw_with_metadata(path, options=options)
        raw = raw_result.data
        normalized = self.normalize(
            raw,
            profile=profile,
            strict=strict,
            keep_raw=keep_raw,
            current_sign=current_sign,
            repair_policy=repair_policy,
        )
        repaired = self.repair(normalized.data, repair_policy=repair_policy)
        normalized.data = repaired.data
        normalized.warnings[:0] = raw_result.warnings
        normalized.warnings.extend(repaired.warnings)
        normalized.metadata.update(raw_result.metadata)
        normalized.metadata.update(self.extract_metadata(raw))
        normalized.metadata.update(repaired.metadata)
        normalized.metadata.update(
            {
                "source_backend": "native",
                "raw_current_sign": self.raw_current_sign,
                "repair_policy": repair_policy,
                "adapter_version": self.adapter_version,
                "support_tier": self.support_tier,
                "output_rows": normalized.data.height,
            }
        )
        return normalized
