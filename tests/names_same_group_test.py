"""A generated person's given and family names come from one ethnic group of the package's names.json."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    from engine.person_ecology import generated_name_for, given_name_for, FIRST_MALE, FIRST_FEMALE
    from engine.world_package import load_package

    # Caerness (no groups): unchanged independent draw from the built-in or flat pools.
    cae = load_package("caerness")
    assert cae.name_groups == {}
    for uid in range(40):
        g, f = generated_name_for(7, uid, "male", cae.name_pools, cae.name_groups)
        assert g == given_name_for(7, uid, "male", cae.name_pools)

    pkg = load_package("saintjude")
    groups = pkg.name_groups
    assert len(groups) == 11  # Part I 14.1 names eleven communities
    seen = {k: 0 for k in groups}
    n = 4000
    for uid in range(n):
        sex = "female" if uid % 2 else "male"
        g, f = generated_name_for(11, uid, sex, pkg.name_pools, groups)
        homes = [k for k, v in groups.items() if g in v[sex] and f in v["family"]]
        assert homes, (g, f, sex)
        seen[homes[0]] += 1
    for k, v in groups.items():  # the draw follows the group weights
        assert abs(seen[k] / n - v["weight"]) < 0.04, (k, seen[k] / n, v["weight"])

    # A taken name gives way to another name of the same sex from the same group, never a cross-group pair.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.environ["CAERNESS_DB_PATH"] = str(Path(tmp) / "n.db")
        from engine.db import connect, init_db
        from engine.person_ecology import _free_name
        from engine.world_package import set_campaign_package
        init_db()
        conn = connect()
        set_campaign_package(conn, "saintjude")
        fam = groups["italian"]["family"][0]
        taken = list(groups["italian"]["male"])[:10]
        for g in taken:
            conn.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')", (f"{g} {fam}",))
        out = _free_name(conn, taken[0], fam, "male", 5)
        g = out.split(" ", 1)[0]
        assert out.endswith(fam) and g in groups["italian"]["male"] and g not in taken, out
        conn.close()
    print("names_same_group_test: ok")


if __name__ == "__main__":
    run()
