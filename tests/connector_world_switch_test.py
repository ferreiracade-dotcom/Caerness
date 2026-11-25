"""One connector serves every world: resume(world=...) switches campaigns between tool calls.

Runs the connector's server-module functions against a temp campaign dir; openings are the packaged
data/*.db copied by open_campaign, exactly as in production (the packaged files are never written).
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"ws-{_n[0]:03d}"


def db_name() -> str:
    return Path(os.environ["CAERNESS_DB_PATH"]).name


def _scalar(sql: str):
    from connector.campaign import connect_campaign
    with connect_campaign() as conn:
        return conn.execute(sql).fetchone()[0]


def day_of_current() -> int:
    return int(_scalar("SELECT current_day FROM world_state WHERE id=1"))


def package_of_current() -> str:
    from connector.campaign import connect_campaign
    from engine.world_package import current_package
    with connect_campaign() as conn:
        return current_package(conn).id


def make_protagonist_if_needed() -> None:
    from connector import server
    r = server.resume_current()
    if not r.get("needs_character"):
        return
    prop = {"name": "Danny Ruane", "sex": "male", "age": 28, "place": "Kerrytown", "work": "bartender at a Kerrytown tavern",
            "concept": "a 28-year-old tavern worker in Kerrytown", "draw": 0, "accept": True}
    out = server.author(cid(), "protagonist", prop)
    assert out.get("status") == "created", out


@contextlib.contextmanager
def unshelved():
    """Caerness is shelved by its package flag; these tests exercise world switching, so turn the shelf off for them."""
    os.environ["CAERNESS_SHELVED_WORLDS"] = "none"
    try:
        yield
    finally:
        os.environ.pop("CAERNESS_SHELVED_WORLDS", None)


def test_switch_creates_and_resumes_each_world():
    from connector import server
    out = server.resume(world="saintjude")
    assert not out.get("error"), out
    assert out["world"] == "Saint Jude" and "Caerness" not in out["other_worlds"], (out.get("world"), out.get("other_worlds"))
    assert db_name() == "saintjude.db"
    assert "error" in server.resume(world="caerness") and db_name() == "saintjude.db"  # shelved: not offered, not opened
    with unshelved():
        out = server.resume(world="caerness")
        assert out["world"] == "Caerness" and "Saint Jude" in out["other_worlds"]
        assert db_name() == "main.db"


def test_round_trip_keeps_each_world():
    from connector import server
    server.resume(world="saintjude")
    make_protagonist_if_needed()
    sj_day = day_of_current()
    adv = server.advance(cid(), 3, "pass time", from_day=server.scene()["day"])
    assert not adv.get("error"), adv
    moved = day_of_current() - sj_day
    assert moved == int(adv["elapsed_days"]) and moved >= 1, (moved, adv.get("elapsed_days"))
    sj_after = day_of_current()
    with unshelved():
        server.resume(world="caerness")
    assert package_of_current() == "caerness"
    out = server.lore("Hearth")
    assert out["passages"], out
    from connector.campaign import connect_campaign
    from engine.world_package import current_package
    with connect_campaign() as conn:
        bible = str(current_package(conn).bible_path.name)
        src = conn.execute("SELECT s.source_path FROM canon_chunks c JOIN canon_sources s ON s.id=c.source_id WHERE c.id=?",
                           (out["passages"][0]["chunk"],)).fetchone()[0]
    assert Path(src).name == bible and "saintjude" not in src.lower(), (src, bible)
    server.resume(world="saintjude")
    assert package_of_current() == "saintjude" and day_of_current() == sj_after


def test_resume_without_world_uses_last_played():
    from connector import campaign, server
    server.resume(world="saintjude")
    assert campaign.last_played() == "saintjude"
    os.environ["CAERNESS_DB_PATH"] = str(Path(os.environ["CAERNESS_CAMPAIGN_DIR"]) / "main.db")  # simulate a restart elsewhere
    campaign.open_startup("main")  # what start-up does: the last-played world wins over the configured campaign
    assert server.resume_current()["world"] == "Saint Jude"


def test_unknown_world_is_an_error_not_a_switch():
    from connector import campaign, server
    server.resume(world="saintjude")
    before = os.environ["CAERNESS_DB_PATH"]
    out = server.resume(world="atlantis")
    assert "error" in out and package_of_current() == "saintjude" and os.environ["CAERNESS_DB_PATH"] == before
    assert campaign.last_played() == "saintjude"
    out = server.resume(world="../x")
    assert "error" in out and os.environ["CAERNESS_DB_PATH"] == before


def test_list_worlds_and_names():
    from connector import campaign
    assert campaign.campaign_name_for("caerness") == "main" and campaign.campaign_name_for("saintjude") == "saintjude"
    rows = {r["world"]: r for r in campaign.list_worlds()}
    assert rows["saintjude"]["display_name"] == "Saint Jude" and rows["caerness"]["campaign"] == "main"
    assert all(set(r) == {"world", "display_name", "campaign", "exists", "shelved"} for r in rows.values())


def test_instructions_name_every_playable_world():
    from connector import server
    text = server.make_mcp().instructions
    assert "Caerness" not in text and "resume" in text and "which world" in text, text  # a shelved world is never offered in play


def test_backup_all_snapshots_every_campaign():
    from connector import backup, campaign, server
    from connector.campaign import campaign_dir
    server.resume(world="saintjude")
    with unshelved():
        server.resume(world="caerness")
    with tempfile.TemporaryDirectory() as bd:
        os.environ["CAERNESS_BACKUP_DIR"] = bd
        try:
            assert backup.main(["--all", "--label", "manual"]) == 0
            stems = {p.name.split("-")[0] for p in Path(bd).glob("*.db")}
            assert {"main", "saintjude"} <= stems, stems
        finally:
            os.environ.pop("CAERNESS_BACKUP_DIR", None)


def test_resume_lists_worlds_and_saves_and_new_save_never_overwrites():
    from connector import campaign, server
    out = server.resume()  # one save among the playable worlds: straight into it, with nothing to choose
    assert not out.get("error") and "ask" not in out and db_name() == "saintjude.db", out
    assert "Caerness" not in str(out)  # shelved: never listed
    # one save (or none yet): straight in
    first = server.resume(world="saintjude")
    assert not first.get("error") and "ask" not in first and db_name() == "saintjude.db", first
    make_protagonist_if_needed()
    adv = server.advance(cid(), 2, "pass time", from_day=server.scene()["day"])
    assert not adv.get("error"), adv
    day1 = day_of_current()
    listed = campaign.worlds_and_saves()[0]["saves"]
    assert [x["save"] for x in listed] == ["saintjude"] and listed[0]["protagonist"] == "Danny Ruane", listed
    assert listed[0]["story_date"] and listed[0]["last_played"], listed
    # a second save with a new character; the first is untouched
    new = server.resume(world="saintjude", new_save=True)
    assert new.get("needs_character") and db_name() == "saintjude-2.db", new
    assert [x["save"] for x in campaign.list_saves("saintjude")] == ["saintjude", "saintjude-2"]
    named = server.resume(world="saintjude", save="saintjude-2")
    assert named.get("needs_character") and db_name() == "saintjude-2.db"
    # several saves and no save named: ask, do not pick
    ask = server.resume(world="saintjude")
    assert "ask" in ask and [x["save"] for x in ask["saves"]] == ["saintjude", "saintjude-2"], ask
    # resume a named save: the first one, where we left it
    back = server.resume(world="saintjude", save="saintjude")
    assert not back.get("error") and back["protagonist"]["name"] == "Danny Ruane" and db_name() == "saintjude.db", back
    assert day_of_current() == day1
    # never overwrite; unknown save is an error and changes nothing
    assert "error" in server.resume(world="saintjude", save="saintjude", new_save=True)
    assert "error" in server.resume(world="saintjude", save="nope") and db_name() == "saintjude.db"
    assert "error" in server.resume(world="saintjude", save="../x", new_save=True)
    assert day_of_current() == day1
    # a named new save
    mine = server.resume(world="saintjude", save="second-run", new_save=True)
    assert mine.get("needs_character") and db_name() == "second-run.db"


def test_shelving_is_a_setting_not_a_delete():
    from connector import campaign
    assert campaign.shelved_worlds() == {"caerness"}
    os.environ["CAERNESS_SHELVED_WORLDS"] = "saintjude"
    try:
        assert campaign.shelved_worlds() == {"saintjude"}
        assert [w["world"] for w in campaign.worlds_and_saves()] == ["caerness"]
    finally:
        os.environ.pop("CAERNESS_SHELVED_WORLDS", None)
    assert (Path(campaign.__file__).resolve().parent.parent / "worlds" / "caerness" / "world.json").is_file()


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CAERNESS_CAMPAIGN_DIR"] = tmp
        os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        failures = 0
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print("PASS", name)
                except Exception as e:
                    failures += 1
                    import traceback
                    print("FAIL", name, f"{type(e).__name__}: {e}")
                    traceback.print_exc(limit=4)
        if failures:
            raise SystemExit(f"{failures} failed")
    print("connector_world_switch_test OK")


if __name__ == "__main__":
    run()
