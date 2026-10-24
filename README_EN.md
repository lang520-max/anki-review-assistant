# Anki Review Assistant

Read-only, local-first Android companion for existing AnkiDroid collections. Kotlin, Jetpack Compose, Android 8+. No card creation, modification, scheduling writes, or AnkiWeb credentials. Cloud upload is off by default.

## Install

Sign in to GitHub, open **Actions → Android APK → successful run → Artifacts**, download the debug ZIP, extract and install `app-debug.apk`. Checksums and the triggering commit are included. CI debug keys are ephemeral; upgrades between builds may require exporting local data and reinstalling. Production signing keys are never committed.

## Data sources

AnkiDroid's official ContentProvider supplies available decks, notes, and card state. It currently does **not** expose a review-log endpoint. Detailed answers, buttons and durations come from explicitly selected Anki exports containing learning history. No history means unavailable metrics, never fabricated zeros.

The importer supports SQLite `collection.anki2` / `collection.anki21` and Zstandard `collection.anki21b`, with supported schema checks and size limits. It opens a private copy read-only, ignores media and never extracts arbitrary archive paths. New imports are isolated; explicitly replacing the same collection reconciles undone/deleted events without double-counting.

The Chinese UI offers overview, date/deck filters, daily trends, observed young/mature review success, note-level difficult words, JSON export, offline cache and privacy settings. Observed success includes Hard/Good/Easy on normal reviews; it is not predicted FSRS retention.

## Build and verify

JDK 17, Android SDK 35:

```sh
cd android
bash gradlew :core:test :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

Python 3.12, from repository root:

```sh
python -m pip install -r server/requirements.txt
python -m unittest discover -s server/tests -v
python scripts/check_read_only.py
```

Actions also runs PostgreSQL integration and Android emulator tests. Real-device AnkiDroid behavior and live HTTPS/OIDC/ChatGPT connectivity require separate validation; see [validation](docs/validation.md).

## Private service

FastAPI, PostgreSQL, official MCP Python SDK and Streamable HTTP. Eight read-only tools cover overview, daily reviews, retention, difficult words, review history, future workload, deck statistics and sync status. Tools return data provenance and limitations.

Explicit opt-in sync uses OAuth with PKCE, Keystore-protected credentials, deck/content selection, incremental row updates, retry backoff, owner-scoped storage, revision leases and deletion tombstones. Upload/delete routes are separate from MCP and require distinct scopes. JWT signatures, audience, issuer, expiry and online token activity are checked.

No service has been purchased or deployed. Deployment templates use Caddy, Keycloak and private PostgreSQL containers; see [deployment](docs/deployment.md). Custom MCP access depends on ChatGPT account/client/workspace availability. JSON export works independently.

Original code: [Apache-2.0](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md), [privacy](docs/privacy.md), [metrics](docs/metrics.md), [API compatibility](docs/api-compatibility.md) and [contributing](CONTRIBUTING.md).
