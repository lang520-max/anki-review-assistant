# Changelog

## AnkiDroid routing8 — 2026-11-06

- Before entering the repair deck, Easy cancels one existing per-card Again, floored at zero; Hard/Good leave the counter unchanged. Entry remains at five, and repair still requires five consecutive Easy answers to return.
- Preserve existing counters/history without replaying old answers. Native undo/redo includes cancellation; analysis events report the actual entry count.
- 45 update/diversion/analysis tests passed, four ABI builds completed, and an isolated Android emulator verified an in-place upgrade with synthetic counters followed by a real UI Easy answer. Physical-phone acceptance remains pending. See [rules and evidence](docs/easy-offset.md).

## 0.1.0 — 2026-10-24

- Initial Kotlin/Compose Android application with official read-only AnkiDroid integration.
- Local datasets, bounded legacy/Zstandard archive import, daily/retention/difficult-word statistics and JSON export.
- Opt-in private synchronization with OAuth PKCE, Keystore, selected decks, incremental updates and retries.
- Authenticated private service with eight read-only MCP tools and PostgreSQL support.
- APK CI, unit/integration/device tests, signing-ready manual draft release workflow and Chinese/English documentation.
- Known limits: no official Provider revlog; history requires explicit export/import; live deployment and physical-device acceptance remain separate.
