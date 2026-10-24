"""Build worlds/saintjude/bible.md from the seven setting-bible files, byte for byte.

    python tools/build_saintjude_bible.py [SOURCE_DIR]         write bible.md and bible_sources.json
    python tools/build_saintjude_bible.py [SOURCE_DIR] --check  compare only; exit 1 on any difference

The files are joined in order (Index, Parts I to VI) with one blank line between them. Their content is never edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "worlds" / "saintjude"
DEFAULT_SRC = Path(r"C:\Users\NozzE\Downloads")
FILES = (
    "Saint_Jude_Bible_Index.md",
    "Saint_Jude_Bible_Part_I_The_City.md",
    "Saint_Jude_Bible_Part_II_The_Law.md",
    "Saint_Jude_Bible_Part_III_The_Underworld.md",
    "Saint_Jude_Bible_Part_IV_The_Upperworld.md",
    "Saint_Jude_Bible_Part_V_The_Outside_Groups.md",
    "Saint_Jude_Bible_Part_VI_The_Price_Book.md",
)


def build(src: Path) -> tuple[bytes, dict]:
    parts, sources = [], []
    for name in FILES:
        data = (src / name).read_bytes()
        parts.append(data)
        sources.append({"file": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    joined = b"\n\n".join(p.rstrip(b"\r\n") + b"\n" if False else p for p in parts)
    return joined, {"about": "Setting bible files concatenated into bible.md by tools/build_saintjude_bible.py, in this order, joined by one blank line.",
                    "files": sources, "bible_md_sha256": hashlib.sha256(joined).hexdigest()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default=str(DEFAULT_SRC))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    joined, manifest = build(Path(a.src))
    bible, meta = PKG / "bible.md", PKG / "bible_sources.json"
    text = json.dumps(manifest, indent=2) + "\n"
    if a.check:
        ok = bible.is_file() and bible.read_bytes() == joined and meta.is_file() and meta.read_text(encoding="utf-8") == text
        print("bible.md matches the source files" if ok else "bible.md or bible_sources.json differs from the source files")
        return 0 if ok else 1
    bible.write_bytes(joined)
    meta.write_text(text, encoding="utf-8")
    print(f"wrote {bible} ({len(joined)} bytes) and {meta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
