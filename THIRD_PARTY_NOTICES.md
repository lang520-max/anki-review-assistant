# Third-party notices and reference review

Original application and server code is Apache-2.0. Calling a separately installed AnkiDroid ContentProvider does not copy its implementation into this project.

| Component/reference | License | Treatment |
|---|---|---|
| [AnkiDroid](https://github.com/ankidroid/Anki-Android) | Application GPL-3.0; API LGPL-3.0, individual contract header permits copying | Reviewed public contract and Provider semantics; no application/API implementation vendored |
| [Anki-Connect](https://github.com/FooSoft/anki-connect/blob/master/LICENSE) | GPL-3.0-or-later | Design reference only, no code copied, no runtime dependency |
| [Anki MCP addon](https://github.com/ankimcp/anki-mcp-server-addon/blob/main/LICENSE) | AGPL-3.0-or-later | Tool design reference only; no implementation copied |
| [Gradle](https://github.com/gradle/gradle/tree/v8.11.1) | Apache-2.0 | Gradle 8.11.1 wrapper JAR redistributed unmodified; Copyright Gradle, Inc. and contributors |
| Kotlin, kotlinx.serialization, AndroidX, Compose, Room, WorkManager | Apache-2.0 | Maven dependencies, not copied source |
| [zstd-jni](https://github.com/luben/zstd-jni) | BSD-2-Clause; bundled Zstandard BSD-3-Clause | Android native decompression dependency; retain upstream notices |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MIT | Dependency, official protocol implementation |
| FastAPI / Pydantic / PyJWT / HTTPX / Uvicorn | MIT / MIT / MIT / BSD-3-Clause / BSD-3-Clause | Python dependencies |
| Psycopg | LGPL-3.0 | Server dependency; no library code modified; keep package licensing and corresponding source available from upstream |
| PostgreSQL / Caddy / Keycloak | PostgreSQL License / Apache-2.0 / Apache-2.0 | Separately distributed deployment containers |

Gradle wrapper SHA-256: `2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046`.

Gradle wrapper source is available in the exact linked upstream tag; this repository's LICENSE includes the Apache-2.0 text. Dependency updates must review licenses and upstream security advisories. No Anki artwork or logos are copied. Anki is a third-party product; this is an independent companion project.
