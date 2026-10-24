# Contributing

Use a feature branch and PR. Keep Android, domain statistics, imports and server interfaces separate. Run the commands in README plus relevant emulator tests. Document changes to JSON schema, metric definitions, API capability handling and privacy defaults.

Do not add an Anki write operation, silently enable uploads or replace unknown metrics with zero. Review all new dependency licenses. Use synthetic fixtures only; never attach a real collection, credential or signing key to a public issue or test.

UI strings are Simplified Chinese first. Preserve raw scheduler units and source timestamps. New schema support needs fixtures for that schema and compatibility documentation, not a wider version allowlist alone.

Before release: update versionCode/versionName, CHANGELOG, device compatibility results and reviewed dependency checksums; use the protected `release` environment for private signing. Review generated reports and all workflow conclusions before publishing a Release.
