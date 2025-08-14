# Changelog

All notable changes to this project are documented here. This project adheres to semantic versioning.

## v0.4.0 — 2025-08-14

### New Features
- Added `pii(unredact=False)` option to keep fields redacted in outputs
  - Useful for audit logs, compliance scenarios, and downstream pipelines
  - Applies to entire field subtree (nested models and containers)
  - Works seamlessly with streaming (sync/async generators)

### Improvements
- Enhanced `pii()` docstring with comprehensive examples
- Added dedicated README section explaining the unredact feature

## v0.3.1 — 2025-08-14

### Fixed
- Updated all remaining `pii_field` references to `pii` in documentation and examples

## v0.3.0 — 2025-08-14

### Breaking Changes
- Renamed `pii_field` to `pii` for better ergonomics in field annotations

### Improvements
- Simplified architecture by removing all output entity detection (stronger membrane principle)
- Removed `detect_output_entities` parameter - no longer needed
- `on_stream_complete` now only receives input-derived state
- Documented spaCy's 1M character limit for text processing

### Philosophy
The membrane principle is now absolute: functions cannot produce PII they never received. This eliminates false positives on generated content and makes the library more predictable.

## v0.2.2 — 2025-08-14

- Breaking: Removed all output/yield entity detection to uphold the membrane principle.
- Breaking: Removed `detect_output_entities` parameter from `PIIConfig`.
- Change: `on_stream_complete` now receives the input-derived `RedactionState` (args only).
- Simplified: Reduced complexity and false-positive surface on generated content.
- Tests/Docs: Updated streaming tests and README to reflect input-only state.

## v0.2.1 — 2025-08-13

- Fixed: Critical streaming bug where generators were yielding redacted tokens instead of unredacted values.
- Improved: Clearer membrane principle - `@pii.protect` acts as a two-way membrane that redacts on entry and unredacts on exit.
- Fixed: Token collision between input arguments and yielded values in generators.
- Improved: Streaming state tracking now separately tracks observed tokens for persistence while using input-only state for unredaction.

## v0.2.0 — 2025-08-13

- New: Container traversal for `list`, `dict`, `set`, `tuple`, and `frozenset` (inputs and return values).
- New: Streaming persistence with `on_stream_complete` callback to capture the final `RedactionState` after generators complete.
- New: Intelligent name component handling with full names as the source of truth; partial mentions (e.g., "John", "Appleseed") reuse the same index.
- Improved: 100% test pass rate (206/206 tests).
- Fixed: Type safety improvements; 0 Pyright errors on strict settings.

## v0.1.4 — 2025-08-09

- Internal: Packaging and metadata updates.

## v0.1.2 — 2025-01-12

- New: Sensible defaults in `PIIConfig()` with a cached default detector.
- Improved: Entity numbering by document order; GLiNER model caching.
- Fixed: Overlapping entity detection in batch mode and consistent numbering across nested models.

## v0.1.1 — 2025-01-05

- Fixed: Entity tracking stability and partial-reference handling.

## v0.1.0 — 2025-01-01

- Initial release with token-based redaction/unredaction, Pydantic integration, name component parsing, batch processing, and session management.
