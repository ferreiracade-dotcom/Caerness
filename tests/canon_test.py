from engine.canon import DEFAULT_CANON, index_canon, search_canon
from engine.db import connect, init_db, reset_db


def run():
    reset_db()
    init_db()
    result = index_canon(DEFAULT_CANON)
    assert result["chunks"] >= 50, "World bible should produce a substantive canon index."
    hits = search_canon("Counting House merchant Houses", limit=5)
    assert hits, "Canon search should return results."
    assert any("Counting House" in h.text for h in hits), "Counting House section should be retrievable."
    with connect() as conn:
        chunk_count = conn.execute("SELECT COUNT(*) FROM canon_chunks").fetchone()[0]
        assert chunk_count == result["chunks"]
    print(f"Canon test passed: indexed {result['chunks']} chunks and retrieved relevant evidence.")


if __name__ == "__main__":
    run()
