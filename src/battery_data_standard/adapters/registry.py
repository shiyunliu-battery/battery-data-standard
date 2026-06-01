"""Adapter registry and detection."""

from __future__ import annotations

import logging
from pathlib import Path

from ..exceptions import AmbiguousDetectionError, DetectionError, UnsupportedFormatError
from ..io import sample_text
from ..reports import DetectionResult
from .arbin import ArbinAdapter
from .base import Adapter
from .basytec import BasytecAdapter
from .biologic import BiologicAdapter
from .generic import GenericAdapter
from .landt import LandtAdapter
from .maccor import MaccorAdapter
from .neware import NewareAdapter
from .novonix import NovonixAdapter
from .pec import PecAdapter
from .repower import RepowerAdapter

logger = logging.getLogger(__name__)

_ADAPTERS: tuple[Adapter, ...] = (
    NewareAdapter(),
    ArbinAdapter(),
    MaccorAdapter(),
    BiologicAdapter(),
    RepowerAdapter(),
    PecAdapter(),
    NovonixAdapter(),
    BasytecAdapter(),
    LandtAdapter(),
    GenericAdapter(),
)


def all_adapters() -> tuple[Adapter, ...]:
    return _ADAPTERS


def get_adapter(
    cycler: str | None,
    path: str | Path | None = None,
    *,
    detection_threshold: float = 0.1,
    ambiguity_margin: float = 0.05,
) -> Adapter:
    if cycler is None or cycler == "auto":
        if path is None:
            return GenericAdapter()
        result = detect_adapter(path)
        _ensure_detection_is_actionable(
            result, threshold=detection_threshold, ambiguity_margin=ambiguity_margin
        )
        cycler = result.cycler
    key = cycler.lower().replace("_", "-")
    aliases = {
        "neware": "neware",
        "arbin": "arbin",
        "maccor": "maccor",
        "biologic": "biologic",
        "bio-logic": "biologic",
        "repower": "repower",
        "pec": "pec",
        "novonix": "novonix",
        "basytec": "basytec",
        "landt": "landt",
        "generic": "generic",
        "csv": "generic",
    }
    target = aliases.get(key, key)
    for adapter in _ADAPTERS:
        if adapter.id == target:
            return adapter
    raise UnsupportedFormatError(f"Unsupported cycler {cycler!r}. Available: {[a.id for a in _ADAPTERS]}")


def detect_adapter(path: str | Path) -> DetectionResult:
    path = Path(path)
    sample = sample_text(path)
    candidates = []
    best: DetectionResult | None = None
    for adapter in _ADAPTERS:
        if path.suffix.lower() in getattr(adapter, "unsupported_extensions", ()):
            result = DetectionResult(
                adapter.id,
                1.0,
                f"{path.suffix.lower()} is a known unsupported {adapter.display_name} extension",
            )
        else:
            result = adapter.sniff(path, sample)
        candidates.append(
            {
                "cycler": result.cycler,
                "confidence": result.confidence,
                "reason": result.reason,
            }
        )
        if best is None or result.confidence > best.confidence:
            best = result
    if best is None:
        best = DetectionResult("generic", 0.0, "no adapters registered")
    best.path = str(path)
    best.candidates = sorted(candidates, key=lambda item: item["confidence"], reverse=True)
    logger.info("detected cycler=%s confidence=%.2f path=%s", best.cycler, best.confidence, path)
    logger.debug("detection candidates=%s", best.candidates)
    return best


def adapter_metadata() -> list[dict[str, object]]:
    return [
        {
            "cycler": adapter.id,
            "display_name": adapter.display_name,
            "support_tier": adapter.support_tier,
            "extensions": list(adapter.extensions),
            "unsupported_extensions": list(getattr(adapter, "unsupported_extensions", ())),
            "adapter_version": adapter.adapter_version,
        }
        for adapter in _ADAPTERS
    ]


def _ensure_detection_is_actionable(
    result: DetectionResult, *, threshold: float, ambiguity_margin: float
) -> None:
    if result.confidence < threshold:
        raise DetectionError(
            f"Detection confidence {result.confidence:.2f} is below threshold {threshold:.2f}; "
            "specify --cycler explicitly."
        )
    if len(result.candidates) < 2:
        return
    if result.cycler == "generic":
        return
    non_generic = [candidate for candidate in result.candidates if candidate.get("cycler") != "generic"]
    if len(non_generic) < 2:
        return
    first, second = non_generic[0], non_generic[1]
    first_confidence = float(first.get("confidence", 0.0))
    second_confidence = float(second.get("confidence", 0.0))
    if first_confidence - second_confidence <= ambiguity_margin and second_confidence >= threshold:
        raise AmbiguousDetectionError(
            "Ambiguous cycler detection between "
            f"{first.get('cycler')} ({first_confidence:.2f}) and "
            f"{second.get('cycler')} ({second_confidence:.2f}); specify --cycler explicitly."
        )
