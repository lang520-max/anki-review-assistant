"""Guard the sole Anki API boundary against accidental write calls."""
from pathlib import Path
import re

root=Path(__file__).resolve().parents[1]/"android/app/src/main/java"
reader=root/"org/ankireview/assistant/AnkiReader.kt"
for path in root.rglob("*.kt"):
    source=path.read_text()
    if "content://" in source and path!=reader:
        raise SystemExit(f"Unexpected Anki provider boundary: {path.name}")
    if path==reader and re.search(r"\.(insert|update|delete|bulkInsert|applyBatch|call)\s*\(",source):
        raise SystemExit("Anki write operation is forbidden")
assert 'query("schedule"' not in reader.read_text()
print("Anki boundary is query-only")
