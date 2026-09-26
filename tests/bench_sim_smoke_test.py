"""bench_sim: the full-engine phone benchmark runs a segment on a copy and reports timings."""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent


def run():
    out = Path(tempfile.gettempdir()) / f"bench_sim_smoke_{os.getpid()}.json"
    out.unlink(missing_ok=True)
    before = (ROOT / "data" / "caerness.db").stat().st_mtime
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "bench_sim.py"), "--segments", "1",
                        "--out", str(out), "--label", "smoke"], cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(out.read_text())
    assert data["label"] == "smoke"
    for key in ("platform", "python", "numpy", "sqlite", "cpu_count"):
        assert key in data["device"], key
    seg = data["segments"][0]
    assert seg["days"] == 1 and seg["day_reached"] == 1, seg
    assert seg["wall_secs"] > 0 and abs(seg["secs_per_day"] - seg["wall_secs"]) < 1e-9, seg
    # The packaged opening is never touched.
    assert (ROOT / "data" / "caerness.db").stat().st_mtime == before
    out.unlink(missing_ok=True)
    print("bench_sim smoke PASS", seg)


if __name__ == "__main__":
    run()
