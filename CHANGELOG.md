# Changelog

All notable changes to this project are documented here. This project adheres to semantic versioning.

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
