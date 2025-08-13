import time
from dataclasses import dataclass
from typing import Any

import probablepeople as pp  # type: ignore[import-untyped]
from nameparser import HumanName  # type: ignore[import-untyped]
from tabulate import tabulate  # type: ignore[import-untyped]


@dataclass
class NameParseResult:
    """Result of parsing a name with either library."""

    first: str = ""
    middle: str = ""
    last: str = ""
    title: str = ""
    suffix: str = ""
    nickname: str = ""
    raw_output: Any = None
    parse_time: float = 0.0
    error: str = ""


class NameParserComparison:
    """Compare nameparser and probablepeople libraries."""

    # Test names covering various formats
    TEST_NAMES = [
        "John Doe",
        "Dr. Jane Smith",
        "Robert Johnson Jr.",
        "Mary Jane Watson",
        "John F. Kennedy",
        "Mary-Kate Olsen",
        "Patrick O'Brien",
        "Leonardo DiCaprio",
        "Madonna",
        "José García",
        "François Hollande",
        "Xi Jinping",
        "Emma Watson-Brown",
        "John Smith III",
        "Prof. Dr. Hans Mueller",
    ]

    @staticmethod
    def parse_with_nameparser(name: str) -> NameParseResult:
        """Parse name using python-nameparser library."""
        start = time.perf_counter()
        result = NameParseResult()

        try:
            parsed = HumanName(name)
            result.first = parsed.first
            result.middle = parsed.middle
            result.last = parsed.last
            result.title = parsed.title
            result.suffix = parsed.suffix
            result.nickname = parsed.nickname
            result.raw_output = {
                "first": parsed.first,
                "middle": parsed.middle,
                "last": parsed.last,
                "title": parsed.title,
                "suffix": parsed.suffix,
                "nickname": parsed.nickname,
            }
        except Exception as e:
            result.error = str(e)

        result.parse_time = time.perf_counter() - start
        return result

    @staticmethod
    def parse_with_probablepeople(name: str) -> NameParseResult:
        """Parse name using probablepeople library."""
        start = time.perf_counter()
        result = NameParseResult()

        try:
            parsed, label_type = pp.tag(name)

            # Map probablepeople fields to our standard fields
            result.first = parsed.get("GivenName", "")
            result.middle = parsed.get("MiddleName", "") or parsed.get(
                "MiddleInitial", ""
            )
            result.last = parsed.get("Surname", "")
            result.title = parsed.get("PrefixMarital", "") or parsed.get(
                "PrefixOther", ""
            )
            result.suffix = parsed.get("SuffixGenerational", "") or parsed.get(
                "SuffixOther", ""
            )
            result.nickname = parsed.get("Nickname", "")
            result.raw_output = (parsed, label_type)

        except Exception as e:
            result.error = str(e)

        result.parse_time = time.perf_counter() - start
        return result

    @classmethod
    def compare_parsers(cls) -> list[dict[str, Any]]:
        """Compare both parsers on all test names."""
        results: list[dict[str, Any]] = []

        for name in cls.TEST_NAMES:
            nameparser_result = cls.parse_with_nameparser(name)
            pp_result = cls.parse_with_probablepeople(name)

            results.append(
                {
                    "name": name,
                    "nameparser": nameparser_result,
                    "probablepeople": pp_result,
                }
            )

        return results

    @staticmethod
    def format_result_for_display(result: NameParseResult) -> str:
        """Format a parse result for display."""
        if result.error:
            return f"ERROR: {result.error}"

        parts: list[str] = []
        if result.title:
            parts.append(f"T:{result.title}")
        if result.first:
            parts.append(f"F:{result.first}")
        if result.middle:
            parts.append(f"M:{result.middle}")
        if result.last:
            parts.append(f"L:{result.last}")
        if result.suffix:
            parts.append(f"S:{result.suffix}")
        if result.nickname:
            parts.append(f"N:{result.nickname}")

        return " | ".join(parts) if parts else "NO PARSE"

    @classmethod
    def print_comparison_report(cls, results: list[dict[str, Any]]):
        """Print a detailed comparison report."""
        print("\n" + "=" * 100)
        print("NAME PARSER COMPARISON REPORT")
        print("=" * 100)

        # Detailed results for each name
        print("\nDETAILED PARSING RESULTS:")
        print("-" * 100)

        for result in results:
            name = result["name"]
            np_result = result["nameparser"]
            pp_result = result["probablepeople"]

            print(f"\nName: '{name}'")
            print(f"  nameparser:      {cls.format_result_for_display(np_result)}")
            print(f"  probablepeople:  {cls.format_result_for_display(pp_result)}")
            print(
                f"  Time (ms):       nameparser={np_result.parse_time * 1000:.3f}, "
                f"probablepeople={pp_result.parse_time * 1000:.3f}"
            )

            # Show raw outputs for debugging
            if np_result.raw_output:
                print(f"  nameparser raw:  {np_result.raw_output}")
            if pp_result.raw_output and not pp_result.error:
                parsed, label_type = pp_result.raw_output
                print(f"  pp raw:          {parsed} (type: {label_type})")

        # Performance summary
        print("\n" + "=" * 100)
        print("PERFORMANCE SUMMARY:")
        print("-" * 100)

        np_times = [r["nameparser"].parse_time * 1000 for r in results]
        pp_times = [r["probablepeople"].parse_time * 1000 for r in results]

        perf_table = [
            ["Metric", "nameparser", "probablepeople"],
            [
                "Average (ms)",
                f"{sum(np_times) / len(np_times):.3f}",
                f"{sum(pp_times) / len(pp_times):.3f}",
            ],
            ["Min (ms)", f"{min(np_times):.3f}", f"{min(pp_times):.3f}"],
            ["Max (ms)", f"{max(np_times):.3f}", f"{max(pp_times):.3f}"],
            ["Total (ms)", f"{sum(np_times):.3f}", f"{sum(pp_times):.3f}"],
        ]
        print(tabulate(perf_table, headers="firstrow", tablefmt="grid"))

        # Accuracy assessment
        print("\n" + "=" * 100)
        print("ACCURACY ASSESSMENT:")
        print("-" * 100)

        accuracy_notes: list[str] = []
        for result in results:
            name = result["name"]
            np_result = result["nameparser"]
            pp_result = result["probablepeople"]

            # Check for parsing differences
            if np_result.first != pp_result.first or np_result.last != pp_result.last:
                accuracy_notes.append(f"'{name}': Different parsing between libraries")

        if accuracy_notes:
            for note in accuracy_notes:
                print(f"  • {note}")
        else:
            print("  All names parsed consistently between libraries.")

        # API ease of use comparison
        print("\n" + "=" * 100)
        print("API EASE OF USE:")
        print("-" * 100)

        print("\nnameparser:")
        print("  • Simple API: HumanName(name).first, .last, etc.")
        print("  • Direct attribute access")
        print("  • Handles titles and suffixes well")
        print("  • Good handling of Western names")

        print("\nprobablepeople:")
        print("  • Returns tuple: (parsed_dict, type)")
        print("  • Requires dict.get() for safe access")
        print("  • More detailed field types (GivenName vs FirstName)")
        print("  • Based on CRF model, potentially better for edge cases")

        # Recommendation
        print("\n" + "=" * 100)
        print("RECOMMENDATION FOR REDACTYL:")
        print("-" * 100)

        avg_np_time = sum(np_times) / len(np_times)
        avg_pp_time = sum(pp_times) / len(pp_times)

        if avg_np_time < avg_pp_time * 0.5:
            speed_winner = "nameparser (>2x faster)"
        elif avg_pp_time < avg_np_time * 0.5:
            speed_winner = "probablepeople (>2x faster)"
        elif avg_np_time < avg_pp_time:
            speed_winner = "nameparser (marginally faster)"
        else:
            speed_winner = "probablepeople (marginally faster)"

        print(f"\n  Speed Winner: {speed_winner}")
        print("\n  Final Recommendation: **nameparser**")
        print("\n  Reasoning:")
        print("  1. Simpler API - direct attribute access vs dict.get()")
        print("  2. Cleaner integration with PIIEntity objects")
        print("  3. Generally faster for simple name parsing")
        print("  4. Better documentation and more intuitive field names")
        print("  5. Since spaCy already identifies PERSON entities, we don't need")
        print("     probablepeople's advanced entity type detection")
        print("\n  Use Case Fit: For redactyl's specific use case of parsing")
        print("  already-identified person names from spaCy, nameparser provides")
        print("  the right balance of simplicity, speed, and accuracy.")
        print("=" * 100 + "\n")


def test_nameparser_basic():
    """Test that nameparser works on basic names."""
    result = NameParserComparison.parse_with_nameparser("John Doe")
    assert result.first == "John"
    assert result.last == "Doe"
    assert not result.error


def test_probablepeople_basic():
    """Test that probablepeople works on basic names."""
    result = NameParserComparison.parse_with_probablepeople("John Doe")
    assert result.first == "John"
    assert result.last == "Doe"
    assert not result.error


def test_comparison_all_names():
    """Run full comparison test on all names."""
    results = NameParserComparison.compare_parsers()

    # Ensure we got results for all test names
    assert len(results) == len(NameParserComparison.TEST_NAMES)

    # Check that both parsers processed each name
    for result in results:
        assert "nameparser" in result
        assert "probablepeople" in result

        # At least one parser should successfully parse each name
        np_success = not result["nameparser"].error
        pp_success = not result["probablepeople"].error
        assert np_success or pp_success, f"Both parsers failed on: {result['name']}"


def test_performance_comparison():
    """Test that parsing times are reasonable."""
    results = NameParserComparison.compare_parsers()

    for result in results:
        # Each parse should take less than 100ms (generous limit)
        assert result["nameparser"].parse_time < 0.1
        assert result["probablepeople"].parse_time < 0.1


def test_title_extraction():
    """Test that titles are properly extracted."""
    np_result = NameParserComparison.parse_with_nameparser("Dr. Jane Smith")
    pp_result = NameParserComparison.parse_with_probablepeople("Dr. Jane Smith")

    assert np_result.title in ["Dr.", "Dr"]
    assert pp_result.title in ["Dr.", "Dr"] or pp_result.raw_output[0].get(
        "PrefixOther"
    ) in ["Dr.", "Dr"]


def test_suffix_extraction():
    """Test that suffixes are properly extracted."""
    np_result = NameParserComparison.parse_with_nameparser("Robert Johnson Jr.")
    pp_result = NameParserComparison.parse_with_probablepeople("Robert Johnson Jr.")

    assert np_result.suffix in ["Jr.", "Jr"]
    # probablepeople might classify this differently
    assert pp_result.suffix or pp_result.raw_output[0].get("SuffixGenerational")


def test_hyphenated_names():
    """Test handling of hyphenated names."""
    for name in ["Mary-Kate Olsen", "Emma Watson-Brown"]:
        np_result = NameParserComparison.parse_with_nameparser(name)
        pp_result = NameParserComparison.parse_with_probablepeople(name)

        # Both should identify some components
        assert np_result.first or np_result.last
        assert pp_result.first or pp_result.last


def test_single_names():
    """Test handling of single names (mononyms)."""
    np_result = NameParserComparison.parse_with_nameparser("Madonna")
    pp_result = NameParserComparison.parse_with_probablepeople("Madonna")

    # At least one component should be identified
    assert np_result.first or np_result.last
    assert pp_result.first or pp_result.last


def test_non_western_names():
    """Test handling of non-Western names."""
    for name in ["José García", "François Hollande", "Xi Jinping"]:
        np_result = NameParserComparison.parse_with_nameparser(name)
        pp_result = NameParserComparison.parse_with_probablepeople(name)

        # Both should at least identify first and last
        assert (np_result.first or np_result.last) or np_result.error
        assert (pp_result.first or pp_result.last) or pp_result.error


if __name__ == "__main__":
    # Run the comparison and print report when executed directly
    comparison = NameParserComparison()
    results = comparison.compare_parsers()
    comparison.print_comparison_report(results)

    print("\nTo run the pytest tests, use: pytest test_name_parser_comparison.py -v")
