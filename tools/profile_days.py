"""Profile N simulated days on a copy of a save.  Usage: python tools/profile_days.py SAVE.db [days] [top]"""
import cProfile, os, pstats, shutil, sys, tempfile
from pathlib import Path
src = Path(sys.argv[1]); days = int(sys.argv[2]) if len(sys.argv) > 2 else 30; top = int(sys.argv[3]) if len(sys.argv) > 3 else 40
db = Path(tempfile.gettempdir()) / f"caerness_profile_{os.getpid()}.db"
shutil.copy2(src, db)
os.environ["CAERNESS_DB_PATH"] = str(db); os.environ["CAERNESS_BACKUP_DIR"] = str(db.parent / "profile_backups")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.db import init_db, connect
from engine.simulation import advance_connection
init_db(); c = connect()
pr = cProfile.Profile(); pr.enable(); advance_connection(c, days); c.commit(); pr.disable()
rows = []
for (fn, ln, name), (cc, nc, tt, ct, _) in pstats.Stats(pr).stats.items():
    f = fn.replace(os.sep, "/")
    if "/engine/" in f:
        rows.append((ct, tt, nc, f.split("/engine/")[-1], ln, name))
for ct, tt, nc, f, ln, name in sorted(rows, reverse=True)[:top]:
    print(f"{ct:7.1f}s cum {tt:6.1f}s self {nc:7d}  {f}:{ln} {name}")
c.close(); db.unlink(missing_ok=True)
