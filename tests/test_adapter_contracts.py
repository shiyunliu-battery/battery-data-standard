from __future__ import annotations

from battery_data_standard.adapters.registry import adapter_metadata, all_adapters


def test_all_adapters_publish_maturity_metadata():
    metadata = adapter_metadata()

    assert len(metadata) == len(all_adapters())
    for item in metadata:
        assert item["cycler"]
        assert item["display_name"]
        assert item["adapter_version"]
        assert item["support_tier"] in {"stable", "fixture-backed", "experimental", "best_effort"}
        assert item["evidence_tier"] in {
            "public-fixture-backed",
            "unit-test-backed",
            "best-effort",
        }
        assert isinstance(item["extensions"], list)
        assert isinstance(item["unsupported_extensions"], list)


def test_biologic_mpr_is_marked_supported_with_optional_backend():
    biologic = next(item for item in adapter_metadata() if item["cycler"] == "biologic")

    assert ".mpr" in biologic["extensions"]
    assert ".mpr" not in biologic["unsupported_extensions"]


def test_vendor_adapters_publish_public_fixture_evidence_tier():
    tiers = {item["cycler"]: item["evidence_tier"] for item in adapter_metadata()}

    assert tiers["generic"] == "unit-test-backed"
    for cycler in {
        "neware",
        "arbin",
        "maccor",
        "biologic",
        "basytec",
        "landt",
        "novonix",
        "repower",
        "pec",
    }:
        assert tiers[cycler] == "public-fixture-backed"
