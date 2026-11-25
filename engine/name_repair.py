"""Repair names an older namer spoiled: a descriptive tag or a number stuck onto a person's name, or a middle initial added
only to tell two namesakes apart. The family name is kept; where the plain name is already borne, the person takes another
given name of the same sex and community. Worlds without their own name pools use such tags on purpose and are left alone."""
from __future__ import annotations

import random
import re
import sqlite3

from . import demographic_sex
from .person_ecology import _EPITHETS
from .world_package import package_for

_TAGS = tuple(sorted(_EPITHETS, key=len, reverse=True))
_TAILS = frozenset(t.split()[-1] for t in _TAGS)  # what a tag leaves as the "family name" of a child
_NUMBERED = re.compile(r"( \d+)+$")
_INITIALS = re.compile(r"^(\S+)(?: [A-Z]\.)+ (\S.*)$")


def _strip(name: str) -> str:
    out = _NUMBERED.sub("", name)
    for tag in _TAGS:
        if out.endswith(" " + tag) and len(out[: -len(tag) - 1].split()) >= 2:
            return out[: -len(tag) - 1]
    return out


def _free(conn: sqlite3.Connection, actor_id: int, base: str) -> str | None:
    """`base` when nobody else bears it, else another given name of the same sex and community with the same family name,
    else another family name of that community; None when every such name is borne."""
    taken = lambda n: conn.execute("SELECT 1 FROM actors WHERE name=? AND id<>?", (n, actor_id)).fetchone()
    if not taken(base):
        return base
    given, _, rest = base.partition(" ")
    rest = re.sub(r"^(?:[A-Z]\. )+", "", rest)
    row = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    sex = row[0] if row and row[0] in ("female", "male") else demographic_sex._given_name_sex(base, conn)
    if not sex:
        return None
    rng = random.Random(f"namesake:{actor_id}")
    usual = list(demographic_sex.package_given_pool(conn, sex, rest) or ())
    further = demographic_sex.package_namesake_pool(conn, sex, rest)
    for pool in (usual, further):
        rng.shuffle(pool)
        for other in pool:
            if not taken(f"{other} {rest}"):
                return f"{other} {rest}"
    groups = demographic_sex.family_home_groups(conn, package_for(conn).name_groups or {}, rest)
    families = sorted({n for g in groups for n in g.get("family", ())})
    rng.shuffle(families)
    for family in families:
        for other in [given] + usual + further:
            if not taken(f"{other} {family}"):
                return f"{other} {family}"
    return None


def _parent_family(conn: sqlite3.Connection, actor_id: int) -> str | None:
    for r in conn.execute("""SELECT a.name FROM kinship_links k JOIN actors a ON a.id=k.actor_a_id
                             WHERE k.actor_b_id=? AND k.kin_kind IN ('parent','mother','father') ORDER BY a.id""", (actor_id,)):
        words = _strip(str(r[0])).split()
        if len(words) >= 2 and words[-1] not in _TAILS:
            return words[-1]
    return None


def _spoiled(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    out = []
    for r in conn.execute("SELECT id,name FROM actors WHERE actor_type='character' ORDER BY id").fetchall():
        aid, name = int(r[0]), str(r[1])
        base = _strip(name)
        words = base.split()
        if len(words) >= 2 and words[-1] in _TAILS:  # born to a tagged parent
            family = _parent_family(conn, aid)
            if family:
                base = " ".join(words[:-1] + [family])
        if base != name and len(base.split()) >= 2:
            out.append((aid, name, base))
    return out


def _named_in_play(conn: sqlite3.Connection) -> set[int]:
    """Whoever the player or the GM named for himself: a middle initial there is the name they have been told."""
    out = {int(r[0]) for r in conn.execute("""SELECT actor_id FROM actor_life_profiles
                                             WHERE json_extract(metadata_json,'$.source')='new_character'""")}
    out |= {int(str(r[0]).rsplit(":", 1)[1]) for r in conn.execute("SELECT fact_key FROM knowledge WHERE fact_key LIKE 'lived:tie:%'")}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='authored_entities'").fetchone():  # the connector's own list
        out |= {int(r[0]) for r in conn.execute("SELECT entity_id FROM authored_entities WHERE entity_table='actors'")}
    return out


def _doubled(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """People set apart from a namesake only by a middle initial (never the protagonist, anyone named in play, or a real
    figure of history)."""
    out = []
    named = _named_in_play(conn)
    for r in conn.execute("""SELECT id,name FROM actors WHERE actor_type='character' AND name LIKE '% _. %'
                             AND id NOT IN (SELECT player_actor_id FROM player_state WHERE player_actor_id IS NOT NULL)
                             AND id NOT IN (SELECT actor_id FROM real_figures WHERE actor_id IS NOT NULL) ORDER BY id""").fetchall():
        m = _INITIALS.match(str(r[1]))
        if not m or int(r[0]) in named:
            continue
        base = f"{m[1]} {m[2]}"
        if conn.execute("SELECT 1 FROM actors WHERE name=? AND id<>?", (base, int(r[0]))).fetchone():
            out.append((int(r[0]), str(r[1]), base))
    return out


def _spoiled_businesses(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """Businesses called after a tag the namer read as the owner's family name ("<tag>'s Bar"): they take the owner's own."""
    out, claimed = [], set()
    for r in conn.execute("SELECT e.id,e.name,a.name,e.location_id FROM civilian_enterprises e JOIN actors a ON a.id=e.owner_actor_id "
                          "ORDER BY e.id").fetchall():
        head, mark, rest = str(r[1]).partition("'s ")
        owner = _strip(str(r[2]))
        family = owner.split()[-1]
        if not (mark and head in _TAILS and family not in _TAILS):
            continue
        for new in (f"{family}'s {rest}", f"{owner}'s {rest}"):  # two of one name in one place: the owner's whole name
            if (new, r[3]) not in claimed and not conn.execute("SELECT 1 FROM civilian_enterprises WHERE name=? AND location_id IS ?",
                                                              (new, r[3])).fetchone():
                claimed.add((new, r[3]))
                out.append((int(r[0]), str(r[1]), new))
                break
    return out


def repair_names(conn: sqlite3.Connection) -> dict[str, str]:
    """Rename every spoiled person and every stored copy of the old name. Returns {old: new}; a second call finds nothing."""
    if not package_for(conn).name_pools:
        return {}
    changed: dict[str, str] = {}
    for find in (_spoiled, _doubled):  # the second looks at the names as the first leaves them
        for aid, old, base in find(conn):
            new = _free(conn, aid, base)
            if new is None or new == old:
                continue
            conn.execute("UPDATE actors SET name=? WHERE id=?", (new, aid))
            first = next((k for k, v in changed.items() if v == old), old)  # stored copies still carry the first name
            changed[first] = new
    # the background identities a tag was split into
    for r in conn.execute("SELECT partition_id,local_uid,family_name FROM background_person_profiles WHERE family_name LIKE '% %'").fetchall():
        for tag in _TAGS:
            fam = str(r[2])
            if fam.endswith(" " + tag):
                conn.execute("UPDATE background_person_profiles SET family_name=? WHERE partition_id=? AND local_uid=?",
                             (fam[: -len(tag) - 1], r[0], r[1]))
                break
    for eid, old, new in _spoiled_businesses(conn):
        conn.execute("UPDATE civilian_enterprises SET name=? WHERE id=?", (new, eid))  # `new` was checked free at that place
        changed.setdefault(old, new)
    if changed:
        _rewrite_copies(conn, changed)
    return changed


def _rewrite_copies(conn: sqlite3.Connection, changed: dict[str, str]) -> None:
    # old names share few last words (a tag, a number, a family name): look for those, then check what stands before each one
    by_last: dict[str, list[str]] = {}
    for old in sorted(changed, key=len, reverse=True):
        by_last.setdefault(old.split()[-1], []).append(old)
    ends = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in by_last) + r")(?!\w)(?! \d)")  # "<name> <digits>" is someone else

    def fix(text: str) -> str:
        for m in reversed(list(ends.finditer(text))):
            for old in by_last[m.group(0)]:
                at = m.end() - len(old)
                if at >= 0 and text.startswith(old, at) and (at == 0 or not text[at - 1].isalnum()):
                    text = text[:at] + changed[old] + text[m.end():]
                    break
        return text

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                                         "AND sql NOT LIKE '%WITHOUT ROWID%' AND sql NOT LIKE 'CREATE VIRTUAL%'")]
    for t in tables:
        for c in [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")') if "TEXT" in (r[2] or "").upper()]:
            updates = []
            for rid, text in conn.execute(f'SELECT rowid,"{c}" FROM "{t}" WHERE "{c}" IS NOT NULL'):
                if isinstance(text, str):
                    fixed = fix(text)
                    if fixed != text:
                        updates.append((fixed, rid))
            if updates:
                conn.executemany(f'UPDATE OR IGNORE "{t}" SET "{c}"=? WHERE rowid=?', updates)
