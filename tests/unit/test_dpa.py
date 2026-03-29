from backend.core.dpa import DPA_REGISTRY, get_dpa_for_country


def test_get_dpa_for_known_country():
    dpa = get_dpa_for_country("DE")
    assert dpa is not None
    assert dpa["short_name"] == "BfDI"
    assert "bfdi" in dpa["email"]


def test_get_dpa_for_unknown_country():
    dpa = get_dpa_for_country("XX")
    assert dpa is None


def test_dpa_registry_has_major_eu_countries():
    for code in ["DE", "FR", "NL", "IE", "GB", "AT", "IT", "ES", "FI", "PT", "CZ", "GR", "HU", "RO", "BE"]:
        assert code in DPA_REGISTRY, f"Missing DPA for {code}"


def test_dpa_entries_have_required_fields():
    for code, dpa in DPA_REGISTRY.items():
        assert "name" in dpa, f"{code} missing name"
        assert "short_name" in dpa, f"{code} missing short_name"
        assert "url" in dpa, f"{code} missing url"
        assert "language" in dpa, f"{code} missing language"


def test_dpa_registry_has_expected_count():
    assert len(DPA_REGISTRY) == 21, f"Expected 21 DPAs, got {len(DPA_REGISTRY)}"
