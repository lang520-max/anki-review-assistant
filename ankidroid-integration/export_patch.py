"""Export a reproducible source-only diff; never includes signing keys or build output."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = "4f2ec681da36b8307a865f05192498b8425adf0f"
ROOTS = ("AnkiDroid/", "common/", "libanki/", "deploy/")


def main():
    checkout = Path(sys.argv[1]).resolve()
    destination = Path(__file__).parent
    def git(*args, **kwargs):
        return subprocess.check_output(["git", "-C", str(checkout), *args], **kwargs)
    if git("rev-parse", "HEAD").decode().strip() != BASE:
        raise ValueError("Unexpected AnkiDroid baseline")
    patch = git("diff", "--binary", "--no-ext-diff", BASE)
    added = git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
    count = 0
    for relative in sorted(filter(None, added)):
        if not (relative.startswith(ROOTS) or relative.startswith("README")):
            raise ValueError(f"Unreviewed source path: {relative}")
        if Path(relative).suffix.lower() in (".apk", ".keystore", ".jks", ".sqlite3", ".db", ".zip"):
            raise ValueError("Non-source artifact must not enter patch")
        content = (checkout / relative).read_text(encoding="utf-8")
        if "PRIVATE KEY-----" in content:
            raise ValueError("Private signing material detected")
        if not content.endswith("\n"):
            raise ValueError(f"Missing final newline: {relative}")
        diff = f"diff --git a/{relative} b/{relative}\nnew file mode 100644\n"
        diff += "".join(difflib.unified_diff([], content.splitlines(True), fromfile="/dev/null", tofile=f"b/{relative}"))
        patch += diff.encode()
        count += 1
    target = destination / "integrated.patch"
    target.write_bytes(patch)
    with tempfile.TemporaryDirectory() as temporary:
        environment = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary)/"index"))
        git("read-tree", BASE, env=environment)
        git("apply", "--cached", "--check", str(target), env=environment)
    metadata = {"upstream": "https://github.com/ankidroid/Anki-Android.git", "base": BASE,
                "patchSha256": hashlib.sha256(patch).hexdigest(), "bytes": len(patch), "addedFiles": count}
    (destination / "upstream.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(json.dumps(metadata))


if __name__ == "__main__": main()
