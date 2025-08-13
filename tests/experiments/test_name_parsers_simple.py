"""Simple test to verify nameparser and probablepeople are installed and working."""

import pytest


def test_nameparser_import():
    """Test that nameparser can be imported."""
    from nameparser import HumanName  # type: ignore[import-untyped]
    
    name = HumanName("John Doe")
    assert name.first == "John"
    assert name.last == "Doe"


def test_probablepeople_import():
    """Test that probablepeople can be imported."""
    import probablepeople as pp  # type: ignore[import-untyped]
    
    parsed, label_type = pp.tag("John Doe")
    assert parsed.get("GivenName") == "John"
    assert parsed.get("Surname") == "Doe"
    assert label_type == "Person"


def test_both_parsers_basic():
    """Test both parsers on a simple name."""
    from nameparser import HumanName  # type: ignore[import-untyped]
    import probablepeople as pp  # type: ignore[import-untyped]
    
    test_name = "Dr. Jane Smith"
    
    # Test nameparser
    np_result = HumanName(test_name)
    assert np_result.title == "Dr."
    assert np_result.first == "Jane"
    assert np_result.last == "Smith"
    
    # Test probablepeople
    pp_result, pp_type = pp.tag(test_name)
    assert pp_result.get("PrefixOther") == "Dr."
    assert pp_result.get("GivenName") == "Jane"
    assert pp_result.get("Surname") == "Smith"
    assert pp_type == "Person"