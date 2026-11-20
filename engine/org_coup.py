"""The violent half of a succession (generic layer, driven by the package's data; names no role or organisation).

  plots       Before any vacancy an ambitious, backed man may plot against the living head (or against a head's shown heir): he
              sounds out the backers one by one (a `plot` agenda row holds who joined, refused, or went to the head), the plot
              can leak, and with enough backing and the nerve he strikes. Rare, temperament-driven, never scheduled.
  coups       The head killed by one of his own men (`coup`, called when the contest opens): with the backing of the unit leaders
              (set up beforehand in a plot, or the weights of the moment) he takes over and the loyalists accept him, are bought,
              or are removed; without it the factions go to war, or the loyalists kill him, or the contest runs with the stain
              on him.
  civil war   An internal war between factions that form along the unit leaders' relationships (`civil_war` agenda row): killings,
              defections and money, ending in a win (the losers killed, demoted or absorbed), a settlement, or a split.
  a split     The losing faction leaves as a new organisation of the same kind: its men, units, lines and holdings move to a new
              institution built through the ordinary org tables.

Every weight and rate is the package's data (`lifecycle.coup`, `.plot`, `.civil_war`, `.split`): a number or a design figure.
"""
from __future__ import annotations

import json
import math
import sqlite3

from . import ledger, org_motives, orgs
from .org_choices import register_agenda_action, register_executor
from .org_lifecycle import fill_post, leave_life, mark_for_history, membership_text, role_level
from .org_succession import (WEEK, active_seat, after_choice, backer_weight, backers, block, candidates, close_row, contest_orgs, drive, early, heir_of, install_head,
                             lean, meta_of, name_of, pick, pressure, put_row, rel, roll, save_meta, seat_the_unit, set_acting, acting_marker, v, weigh)
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, kind_rules, seat_of
from .relationships import adjust_relationship


def _utility(conn: sqlite3.Connection, x: float) -> float:
    return float(org_motives._fig(conn, "org_choice_utility_base", default=8.0)) + float(org_motives._fig(conn, "org_choice_utility_span", default=10.0)) * clamp01(x)


def _pay(conn: sqlite3.Connection, src: int, dst: int, amount: float, flow: str | None, purpose: str) -> float:
    from .world_package import org_rules, package_for
    if amount <= 0.0:
        return 0.0
    lk = org_rules(package_for(conn))["ledger_kinds"][flow]
    return ledger.transfer(conn, ("person", int(src)), ("person", int(dst)), amount, flow_kind=lk, purpose=purpose, allow_partial=True)


def violence_bias(conn: sqlite3.Connection, org: int) -> float:
    """An outfit's own lean toward violence (outfits data `violence_bias`, a number or a figure): canon makes some outfits quicker to
    it than others. An outfit with no entry has none (an optional key, not a default)."""
    key = conn.execute("SELECT package_key FROM org_profiles WHERE org_actor_id=?", (int(org),)).fetchone()[0]
    spec = ((org_motives._sphere_data(conn).get("outfits") or {}).get(str(key).split("~")[0]) or {}).get("violence_bias")
    return 0.0 if spec is None else v(conn, spec)


def temper(conn: sqlite3.Connection, org: int, actor: int) -> float:
    """A man's aggression with his outfit's lean toward violence added, 0..1."""
    return clamp01(drive(conn, int(actor), "aggression") + violence_bias(conn, org))


def _kill(conn: sqlite3.Connection, killer: int, victim: int, day: int, sanctioned: bool = True) -> None:
    from .outfit_choices import kill
    if is_living(conn, victim):
        kill(conn, int(killer), int(victim), int(day), sanctioned=sanctioned)


def tension(conn: sqlite3.Connection, org: int, leaders: list[int]) -> float:
    """How bitter two claimants are: their resentment of each other against their tempers, 0..1 (the share of bitterness is the data's)."""
    a, b = int(leaders[0]), int(leaders[1])
    r1, r2 = rel(conn, a, b), rel(conn, b, a)
    bitter = ((float(r1["resentment"]) if r1 else 0.0) + (float(r2["resentment"]) if r2 else 0.0)) / 200.0
    w = v(conn, block(conn, org, "civil_war")["tension_bitter"])
    return clamp01(w * clamp01(bitter) + (1.0 - w) * (drive(conn, a, "aggression") + drive(conn, b, "aggression")) / 2.0)


# ---- plots against a living head (or his heir) ----

def _plot_row(conn: sqlite3.Connection, plotter: int, target: int | None = None):
    q, a = "SELECT * FROM org_agenda WHERE kind='plot' AND status='open' AND actor_id=?", [int(plotter)]
    if target is not None:
        q += " AND subject_id=?"
        a.append(int(target))
    return conn.execute(q + " ORDER BY id DESC LIMIT 1", a).fetchone()


def _plotters(conn: sqlite3.Connection, org: int, blk: dict, head: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        """SELECT s.actor_id FROM org_seats s JOIN actor_drives d ON d.actor_id=s.actor_id WHERE s.org_actor_id=? AND s.status='active' AND s.inducted_day IS NOT NULL
             AND s.actor_id<>? AND s.standing>=? AND d.ambition>=? ORDER BY s.actor_id""", (int(org), int(head), v(conn, blk.get("min_standing")), v(conn, blk.get("min_ambition")))).fetchall()
            if not _plot_row(conn, int(r[0]))]


def start_chance(conn: sqlite3.Connection, org: int, p: int, target: int, head: int, day: int, blk: dict) -> float:
    """The weekly chance that the man starts a plot against the target: the rate x his ambition x how little he is bound to the
    target (loyalty) x what drives him (resentment of the target; the head's showing another man as his heir) x his nerve."""
    r = rel(conn, p, target)
    resent = 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)
    loyal = 0.0 if r is None else clamp01(float(r["loyalty"]) / 100.0)
    heir = heir_of(conn, org, head, shown_only=True)
    blocked = 1.0 if heir is not None and heir != p and target == head else 0.0
    push = clamp01(v(conn, blk.get("w_resentment")) * resent + v(conn, blk.get("w_blocked")) * blocked)
    rate = v(conn, blk.get("heir_rate" if target != head else "start_week"))
    return rate * drive(conn, p, "ambition") * (1.0 - loyal) * push * lean(conn, org, drive(conn, p, "risk_tolerance"))


def start_plot(conn: sqlite3.Connection, org: int, plotter: int, target: int, day: int) -> int:
    imposed(conn, plotter)
    return put_row(conn, int(plotter), "plot", int(day), int(target), {"org": int(org), "started": int(day), "joined": [], "refused": [], "sounded": []})


def _respond(conn: sqlite3.Connection, org: int, blk: dict, s: int, p: int, target: int, day: int) -> str:
    """One man sounded out: he joins (trust in the plotter, fear of him, a favour owed, his own ambition against his loyalty to
    the target), refuses and keeps quiet, or goes to the head."""
    r_sp, r_st = rel(conn, s, p), rel(conn, s, target)
    trust = 0.0 if r_sp is None else clamp01((float(r_sp["trust"]) + float(r_sp["loyalty"])) / 200.0)
    fear = 0.0 if r_sp is None else clamp01(float(r_sp["fear"]) / 100.0)
    owed = 0.0 if r_sp is None else clamp01(float(r_sp["obligation"]) / 100.0)
    loyal = 0.0 if r_st is None else clamp01(float(r_st["loyalty"]) / 100.0)
    rel_s = float(seat_of(conn, s, org)["reliability"])
    r = blk.get("respond") or {}
    join = v(conn, r.get("join_base")) + v(conn, r.get("trust")) * trust + v(conn, r.get("fear")) * fear + v(conn, r.get("favour")) * owed + v(conn, r.get("ambition")) * drive(conn, s, "ambition") * (1.0 - loyal)
    tell = v(conn, r.get("tell_base")) + v(conn, r.get("loyalty")) * loyal * rel_s * (1.0 - fear)
    keep = v(conn, r.get("refuse_base"))
    return pick(conn, s, int(day), f"sound:{p}", [("join", join), ("tell", tell), ("refuse", keep)], v(conn, r.get("temp")))


def _plot_share(conn: sqlite3.Connection, org: int, meta: dict, p: int, target: int, cblk: dict) -> float:
    bs = [b for b in backers(conn, org) if b not in (p, target)]
    tot = sum(backer_weight(conn, org, b, cblk) for b in bs)
    got = sum(backer_weight(conn, org, b, cblk) for b in bs if b in meta["joined"])
    return got / tot if tot else 0.0


def _found(conn: sqlite3.Connection, org: int, row, meta: dict, how: str, day: int) -> None:
    """The plot is known: the head gets `plot_found` about the plotter."""
    target = int(row["subject_id"])
    head = head_of(conn, org)
    close_row(conn, int(row["id"]), int(day), **meta, found=how)
    if head is None or not is_living(conn, head):
        return
    add_agenda(conn, head, "plot_found", int(day), subject_kind="actor", subject_id=int(row["actor_id"]),
               metadata={"org": int(org), "holder": int(row["actor_id"]), "target": target, "joined": meta["joined"], "how": how})
    imposed(conn, int(row["actor_id"]))


def _advance_plot(conn: sqlite3.Connection, row, day: int) -> str | None:
    meta = meta_of(row)
    org, p, target = int(meta["org"]), int(row["actor_id"]), int(row["subject_id"])
    blk, cblk = block(conn, org, "plot"), block(conn, org, "contest")
    if active_seat(conn, p, org) is None or not is_living(conn, target) or seat_of(conn, target, org) is None or seat_of(conn, target, org)["status"] != "active":
        close_row(conn, int(row["id"]), int(day), **meta, ended="gone")
        return "gone"
    weeks = (int(day) - int(meta["started"])) / WEEK
    dr = blk["drop"]  # nothing ends a plot by the calendar: the weekly chance it is dropped rises with weariness, a cooled grudge and the head's temper
    r_pt = rel(conn, p, target)
    mix = (v(conn, dr["w_weary"]) * (1.0 - math.exp(-weeks / v(conn, dr["typical_weeks"]))) + v(conn, dr["w_cool"]) * (1.0 - (clamp01(float(r_pt["resentment"]) / 100.0) if r_pt else 0.0))
           + v(conn, dr["w_fear"]) * drive(conn, head_of(conn, org) or target, "aggression")) / (v(conn, dr["w_weary"]) + v(conn, dr["w_cool"]) + v(conn, dr["w_fear"]))
    if roll(conn, p, int(day), f"drop:{row['id']}") < v(conn, dr["week"]) * mix:
        close_row(conn, int(row["id"]), int(day), **meta, ended="dropped")
        return "dropped"
    if meta["sounded"] and roll(conn, p, int(day), f"leak:{row['id']}") < v(conn, blk.get("leak_week")) * len(meta["sounded"]):
        _found(conn, org, row, meta, "leak", int(day))
        return "found"
    if roll(conn, p, int(day), f"soundweek:{row['id']}") < v(conn, blk.get("sound_week")):
        pool = [b for b in backers(conn, org) if b not in (p, target) and b not in meta["sounded"]]
        sc = [(b, weigh(conn, org, p, b, int(day), {"weights": blk["sound_weights"]})) for b in pool]
        s = pick(conn, p, int(day), f"soundwho:{row['id']}", sc, v(conn, blk["sound_temp"]))
        if s is not None:
            meta["sounded"].append(s)
            how = _respond(conn, org, blk, s, p, target, int(day))
            if how == "join":
                meta["joined"].append(s)
                adjust_relationship(conn, s, p, int(day), obligation_delta=v(conn, blk.get("join_obligation")))
            elif how == "tell":
                _found(conn, org, row, meta, "betrayed", int(day))
                return "found"
            else:
                meta["refused"].append(s)
            imposed(conn, s)
    share = _plot_share(conn, org, meta, p, target, cblk)
    if meta["joined"] and share >= v(conn, blk.get("ready_share")) and roll(conn, p, int(day), f"strike:{row['id']}") < v(conn, blk.get("strike_week")) * drive(conn, p, "aggression"):
        _kill(conn, p, target, int(day), sanctioned=False)
        from .org_lifecycle import _process_vacancies
        _process_vacancies(conn, int(day))  # the coup follows at once, not a week later (it reads and closes this plot)
        if conn.execute("SELECT status FROM org_agenda WHERE id=?", (int(row["id"]),)).fetchone()[0] == "open":
            close_row(conn, int(row["id"]), int(day), **meta, struck=True)
        return "struck"
    save_meta(conn, int(row["id"]), meta)
    return None


def _plots(conn: sqlite3.Connection, day: int) -> dict:
    out = {"plots": 0, "plots_found": 0, "plots_struck": 0}
    for org in contest_orgs(conn):
        blk = block(conn, org, "plot")
        head = head_of(conn, org)
        if not blk or head is None:
            continue
        for row in conn.execute("SELECT * FROM org_agenda WHERE kind='plot' AND status='open' AND json_extract(metadata_json,'$.org')=? ORDER BY id", (int(org),)).fetchall():
            r = _advance_plot(conn, row, int(day))
            out["plots_found"] += 1 if r == "found" else 0
            out["plots_struck"] += 1 if r == "struck" else 0
        head = head_of(conn, org)
        if head is None:
            continue
        heir = heir_of(conn, org, head, shown_only=True)
        for p in _plotters(conn, org, blk, head):
            for target in [head] + ([heir] if heir is not None and heir != p else []):
                if roll(conn, p, int(day), f"plot:{target}") < start_chance(conn, org, p, target, head, int(day), blk):
                    start_plot(conn, org, p, target, int(day))
                    out["plots"] += 1
                    break
    return out


def plot_found_offers(conn: sqlite3.Connection, head: int, item, day: int) -> list[dict]:
    meta = meta_of(item)
    org, p = int(meta["org"]), int(item["subject_id"])
    blk = (block(conn, org, "plot").get("found") or {})
    s = seat_of(conn, p, org)
    if s is None or s["status"] != "active" or not is_living(conn, p):
        return [{"kind": "plot_pardon", "utility": _utility(conn, 1.0), "rationale": "The man is gone.", "payload": {"org": org, "holder": p}}]
    k, e, d = blk.get("kill") or {}, blk.get("exile") or {}, blk.get("pardon") or {}
    joined = clamp01(len(meta.get("joined") or []) / max(1e-9, v(conn, blk.get("joined_scale"))))
    r = rel(conn, head, p)
    fond = 0.0 if r is None else clamp01((float(r["trust"]) + float(r["affection"])) / 200.0)
    xs = {"plot_kill": v(conn, k.get("base")) + v(conn, k.get("aggression")) * drive(conn, head, "aggression") + v(conn, k.get("joined")) * joined + v(conn, k.get("low_standing")) * (1.0 - float(s["standing"])),
          "plot_exile": v(conn, e.get("base")) + v(conn, e.get("caution")) * (1.0 - drive(conn, head, "aggression")) + v(conn, e.get("joined")) * joined,
          "plot_pardon": v(conn, d.get("base")) + v(conn, d.get("fond")) * fond + v(conn, d.get("standing")) * float(s["standing"])}
    payload = {"org": org, "holder": p, "joined": meta.get("joined")}
    why = {"plot_kill": f"Has {name_of(conn, p)} killed for plotting.", "plot_exile": f"Puts {name_of(conn, p)} out of the life for plotting.", "plot_pardon": f"Lets {name_of(conn, p)}'s plot pass."}
    return [{"kind": k2, "utility": _utility(conn, x), "rationale": why[k2], "payload": payload, **({"target_actor_id": p, "risk": 0.8} if k2 == "plot_kill" else {})} for k2, x in xs.items()]


def _finish(conn: sqlite3.Connection, payload: dict, day: int) -> None:
    if payload.get("agenda_id") is not None:
        orgs.resolve_agenda(conn, int(payload["agenda_id"]), int(day))


def execute_plot_kill(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    p = int(payload["holder"])
    imposed(conn, int(actor_id))
    for j in payload.get("joined") or []:
        adjust_relationship(conn, int(j), int(actor_id), int(day), fear_delta=v(conn, block(conn, int(payload["org"]), "plot").get("found", {}).get("fear")))
        imposed(conn, int(j))
    _kill(conn, int(actor_id), p, int(day), sanctioned=True)
    return {"summary": f"{name_of(conn, actor_id)} had {name_of(conn, p)} killed for plotting."}


def execute_plot_exile(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    leave_life(conn, int(payload["holder"]), int(payload["org"]), int(day))
    imposed(conn, int(actor_id))
    return {"summary": f"{name_of(conn, actor_id)} put {name_of(conn, payload['holder'])} out."}


def execute_plot_pardon(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    p = int(payload["holder"])
    f = block(conn, int(payload["org"]), "plot").get("found") or {}
    if p != int(actor_id):
        adjust_relationship(conn, p, int(actor_id), int(day), fear_delta=v(conn, f.get("pardon_fear")), resentment_delta=v(conn, f.get("pardon_resentment")))
        imposed(conn, p)
    return {"summary": f"{name_of(conn, actor_id)} let {name_of(conn, p)}'s plot pass."}


# ---- a coup: the head killed by one of his own ----

def coup(conn: sqlite3.Connection, org: int, late: int, killer: int, cid: int, day: int) -> bool:
    """The head was killed by a man of the organisation. Returns True when this settled it (he took over, or the factions went
    to war); False when the ordinary contest should run (with the killer's stain, or after the loyalists killed him)."""
    blk, cblk = block(conn, org, "coup"), block(conn, org, "contest")
    if not blk or active_seat(conn, killer, org) is None:
        return False
    row = conn.execute("SELECT * FROM org_agenda WHERE id=?", (int(cid),)).fetchone()
    cmeta = meta_of(row)
    plot = _plot_row(conn, killer, late)
    joined = set(meta_of(plot)["joined"]) if plot is not None else set()
    if plot is not None:
        close_row(conn, int(plot["id"]), int(day), **meta_of(plot), struck=True)
    cands = candidates(conn, org, exclude=(late,))
    cands.setdefault(killer, 0.0)
    ctx = {"heir": cmeta.get("heir"), "customary": cands, "tainted": killer}
    bs = [b for b in backers(conn, org) if b != killer]
    total = with_killer = 0.0
    loyal: list[int] = []
    for b in bs:
        w = backer_weight(conn, org, b, cblk)
        total += w
        sc = [(c, weigh(conn, org, b, c, int(day), cblk, ctx)) for c in sorted(cands)]
        if b in joined or pick(conn, b, int(day), f"coupback:{cid}", sc, v(conn, cblk.get("pick_temp"))) == killer:
            with_killer += w
        else:
            loyal.append(b)
    share = with_killer / total if total else 1.0
    cmeta.update(coup_share=round(share, 3), tainted=int(killer))
    save_meta(conn, int(cid), cmeta)
    for b in bs:
        imposed(conn, b)
    if share >= v(conn, blk.get("share")):
        if loyal and roll(conn, killer, int(day), f"coupwar:{cid}") < v(conn, blk.get("backed_war")) * (1.0 - share):
            best = _loyal_leader(conn, org, loyal, cands, killer, late, int(day), cblk, ctx)
            if best is not None:
                close_row(conn, int(cid), int(day), **cmeta, outcome="civil_war")
                start_civil_war(conn, org, [killer, best], int(day), cause="coup", late=late)
                return True
        _take_over(conn, org, killer, late, loyal, int(day), blk, cblk)
        close_row(conn, int(cid), int(day), **cmeta, outcome="coup", winner=killer)
        mark_for_history(conn, late, f"was killed by {name_of(conn, killer)}, who took the seat", int(day))
        return True
    w = blk.get("unbacked") or {}
    bal = 1.0 - abs(share - 0.5) * 2.0
    aggr = max([drive(conn, b, "aggression") for b in loyal] or [0.0])
    opts = [("war", v(conn, w.get("war")) * bal), ("loyalists_kill", v(conn, w.get("loyalists_kill")) * (1.0 - share) * aggr), ("contest", v(conn, w.get("contest")))]
    how = pick(conn, killer, int(day), f"unbacked:{cid}", opts, v(conn, w.get("temp")))
    if how == "war":
        best = _loyal_leader(conn, org, loyal, cands, killer, late, int(day), cblk, ctx)
        if best is not None:
            close_row(conn, int(cid), int(day), **cmeta, outcome="civil_war")
            start_civil_war(conn, org, [killer, best], int(day), cause="coup", late=late)
            return True
    if how == "loyalists_kill" and loyal:
        avenger = max(loyal, key=lambda b: (drive(conn, b, "aggression"), -b))
        _kill(conn, avenger, killer, int(day), sanctioned=True)
        adjust_relationship(conn, avenger, late, int(day), loyalty_delta=0.0)
        cmeta.update(avenged_by=avenger)
        cmeta["killed"] = int(cmeta.get("killed", 0)) + 1
        cmeta.pop("tainted", None)
        save_meta(conn, int(cid), cmeta)
    return False


def _loyal_leader(conn, org, loyal, cands, killer, late, day, cblk, ctx) -> int | None:
    """The man the loyalists rally round: the claimant (not the killer) most of them would back."""
    others = [c for c in sorted(cands) if c != killer]
    if not others:
        return None
    tallies = {c: 0.0 for c in others}
    for b in loyal or backers(conn, org):
        if b == killer:
            continue
        best = max(others, key=lambda c: (weigh(conn, org, b, c, int(day), cblk, ctx), -c))
        tallies[best] += 1.0
    return max(others, key=lambda c: (tallies[c], -c))


def _take_over(conn, org, killer, late, loyal, day, blk, cblk) -> None:
    """The killer holds the seat. Each loyalist accepts (trust in him, fear of him), is bought (money, his greed) or is removed
    (the killer's temper against the loyalist's loyalty to the late head)."""
    install_head(conn, org, killer, int(day), "coup")
    w = blk.get("loyalists") or {}
    for b in loyal:
        r_bk, r_bl = rel(conn, b, killer), rel(conn, b, late)
        trust = 0.0 if r_bk is None else clamp01((float(r_bk["trust"]) + float(r_bk["loyalty"])) / 200.0)
        fear = 0.0 if r_bk is None else clamp01(float(r_bk["fear"]) / 100.0)
        loyal_late = 0.0 if r_bl is None else clamp01(float(r_bl["loyalty"]) / 100.0)
        purse = clamp01(ledger.balance(conn, ("person", int(killer))) * v(conn, w.get("buy_share")) / max(1e-9, v(conn, w.get("buy_scale"))))
        opts = [("accept", v(conn, w.get("accept_base")) + v(conn, w.get("accept_trust")) * trust + v(conn, w.get("accept_fear")) * fear),
                ("bought", v(conn, w.get("buy_base")) * purse * lean(conn, org, drive(conn, b, "greed", org))),
                ("removed", v(conn, w["remove_base"]) * temper(conn, org, killer) * loyal_late * (1.0 - fear)),
                ("exile", v(conn, w["exile_base"]) + v(conn, w["exile_loyalty"]) * loyal_late * (1.0 - fear))]
        how = pick(conn, b, int(day), f"loyalist:{late}", opts, v(conn, w.get("temp")))
        if how == "bought":
            paid = _pay(conn, killer, b, ledger.balance(conn, ("person", int(killer))) * v(conn, w.get("buy_share")), w.get("flow"), "what he paid a loyalist")
            adjust_relationship(conn, b, killer, int(day), obligation_delta=v(conn, w.get("buy_obligation")))
        elif how == "removed":
            _kill(conn, killer, b, int(day), sanctioned=True)
        elif how == "exile":
            exile_man(conn, org, b, killer, int(day))
        else:
            adjust_relationship(conn, b, killer, int(day), fear_delta=v(conn, w.get("accept_fear_gain")), resentment_delta=v(conn, w.get("accept_resentment")))
        imposed(conn, b)


# ---- civil war ----

def war_row(conn: sqlite3.Connection, org: int):
    return conn.execute("SELECT * FROM org_agenda WHERE kind='civil_war' AND status='open' AND actor_id=? ORDER BY id DESC LIMIT 1", (int(org),)).fetchone()


def _factions(conn: sqlite3.Connection, org: int, meta: dict) -> dict[int, int]:
    """actor id -> faction index for every living seated man: leaders and the backers who joined a side by name; everyone else
    with the man he answers to, up the chain, until a man of a side."""
    side = {}
    for i, f in enumerate(meta["factions"]):
        side[int(f["leader"])] = i
        for m in f["members"]:
            side.setdefault(int(m), i)
    side.update({int(k): int(x) for k, x in (meta.get("overrides") or {}).items()})
    sup = {int(a): (None if s is None else int(s)) for a, s in conn.execute("SELECT actor_id,superior_actor_id FROM org_seats WHERE org_actor_id=? AND status='active'", (int(org),))}
    out = {}
    for a in sup:
        cur, seen = a, set()
        while cur is not None and cur not in side and cur not in seen:
            seen.add(cur)
            cur = sup.get(cur)
        if cur is not None and cur in side:
            out[a] = side[cur]
    return out


def start_civil_war(conn: sqlite3.Connection, org: int, leaders: list[int], day: int, *, cause: str, late: int | None = None) -> int | None:
    """Two claimants, each with the backers who weigh him above the other; the stronger holds the seat meanwhile."""
    blk = block(conn, org, "civil_war")
    if not blk or len(leaders) < 2 or war_row(conn, org) is not None:
        return None
    cblk = block(conn, org, "contest")
    ctx = {"customary": {int(x): 1.0 for x in leaders}, "war": True}
    sides = [{"leader": int(x), "members": []} for x in leaders[:2]]
    for b in backers(conn, org):
        if b in leaders:
            continue
        sc = [(i, weigh(conn, org, b, int(sides[i]["leader"]), int(day), cblk, ctx)) for i in (0, 1)]
        sides[pick(conn, b, int(day), "warside", sc, v(conn, blk["side_temp"]))]["members"].append(b)
    meta = {"org": int(org), "started": int(day), "cause": cause, "late": late, "factions": sides, "overrides": {}, "killed": [0, 0], "spent": [0.0, 0.0], "defected": 0}
    rid = put_row(conn, int(org), "civil_war", int(day), late, meta)
    side = _factions(conn, org, meta)
    strength = _strength(conn, org, meta, side, blk)
    if acting_marker(conn, org) is None and head_of(conn, org) is None:
        stronger = max((0, 1), key=lambda i: (strength[i], -i))
        set_acting(conn, org, int(sides[stronger]["leader"]), int(late if late is not None else sides[stronger]["leader"]), int(day), rid)
    for a, i in side.items():
        imposed(conn, a)
        for j, f in enumerate(sides):
            if j != i and a != int(f["leader"]):
                adjust_relationship(conn, a, int(f["leader"]), int(day), resentment_delta=v(conn, blk.get("start_resentment")))
    for f in sides:
        mark_for_history(conn, int(f["leader"]), f"led a side in the war over the {name_of(conn, org)}", int(day))
    return rid


def _strength(conn: sqlite3.Connection, org: int, meta: dict, side: dict[int, int], blk: dict) -> list[float]:
    out = [0.0, 0.0]
    dep = v(conn, blk.get("dependant_weight"))
    for a, inducted in conn.execute("SELECT actor_id,inducted_day IS NOT NULL FROM org_seats WHERE org_actor_id=? AND status='active'", (int(org),)):
        i = side.get(int(a))
        if i is not None and is_living(conn, int(a)):
            out[i] += 1.0 if inducted else dep
    for i, f in enumerate(meta["factions"]):
        out[i] += v(conn, blk["money_weight"]) * min(1.0, ledger.balance(conn, ("person", int(f["leader"]))) / max(1e-9, v(conn, blk["money_scale"]))) * v(conn, blk["money_men"])
    return out


def _war_killing(conn, org, meta, side, blk, day, rid, strength) -> None:
    weeks = (int(day) - int(meta["started"])) // WEEK
    inten = min(1.0, v(conn, blk.get("start_intensity")) + weeks / max(1.0, v(conn, blk.get("ramp_weeks"))))
    leaders = [int(f["leader"]) for f in meta["factions"]]
    opts = [(i, drive(conn, leaders[i], "aggression") * strength[i]) for i in (0, 1) if is_living(conn, leaders[i])]
    if not opts or roll(conn, org, int(day), f"warkill:{rid}") >= v(conn, blk.get("kill_week")) * inten:
        return
    atk = pick(conn, org, int(day), f"warwho:{rid}", [(i, s / max(1e-9, max(x for _j, x in opts))) for i, s in opts], v(conn, blk["target_temp"]))
    mine = [(a, drive(conn, a, "aggression")) for a, i in sorted(side.items()) if i == atk and a != leaders[atk] and seat_of(conn, a, org)["inducted_day"] is not None]
    theirs = []
    for a, i in sorted(side.items()):
        if i != atk:
            s = seat_of(conn, a, org)
            lead = v(conn, blk.get("leader_target")) if a == leaders[1 - atk] or s["role_key"] == kind_rules(conn, org).get("unit_leader") else 0.0
            theirs.append((a, float(s["standing"]) + lead + (v(conn, blk.get("men_target")) if s["inducted_day"] is not None else 0.0)))
    killer = pick(conn, org, int(day), f"warkiller:{rid}", mine, v(conn, blk["target_temp"])) if mine else leaders[atk]
    victim = pick(conn, org, int(day), f"warvictim:{rid}", theirs, v(conn, blk["target_temp"]))
    if victim is None:
        return
    _kill(conn, int(killer), int(victim), int(day), sanctioned=True)
    meta["killed"][1 - atk] += 1
    adjust_relationship(conn, leaders[1 - atk], leaders[atk], int(day), resentment_delta=v(conn, blk.get("kill_resentment")))
    if int(victim) == leaders[1 - atk]:  # his side's strongest man takes his place
        rest = [a for a, i in side.items() if i == 1 - atk and a != int(victim) and active_seat(conn, a, org) is not None]
        if rest:
            meta["factions"][1 - atk]["leader"] = max(rest, key=lambda a: (float(seat_of(conn, a, org)["standing"]), -a))


def _war_defections(conn, org, meta, side, blk, cblk, day, rid) -> None:
    ctx = {"customary": {int(f["leader"]): 1.0 for f in meta["factions"]}, "war": True}
    for b in backers(conn, org):
        i = side.get(b)
        if i is None or b == int(meta["factions"][i]["leader"]) or roll(conn, b, int(day), f"defect:{rid}") >= v(conn, blk.get("defect_week")):
            continue
        own, other = int(meta["factions"][i]["leader"]), int(meta["factions"][1 - i]["leader"])
        if weigh(conn, org, b, other, int(day), cblk, ctx) - weigh(conn, org, b, own, int(day), cblk, ctx) > v(conn, blk.get("defect_margin")):
            meta["overrides"][str(b)] = 1 - i
            meta["defected"] += 1
            adjust_relationship(conn, b, own, int(day), loyalty_delta=-v(conn, blk.get("defect_loyalty")))
            imposed(conn, b)


def tick_war(conn: sqlite3.Connection, row, day: int) -> str | None:
    meta = meta_of(row)
    org, rid = int(meta["org"]), int(row["id"])
    blk, cblk = block(conn, org, "civil_war"), block(conn, org, "contest")
    weeks = (int(day) - int(meta["started"])) / WEEK
    side = _factions(conn, org, meta)
    strength = _strength(conn, org, meta, side, blk)
    _war_killing(conn, org, meta, side, blk, day, rid, strength)
    side = _factions(conn, org, meta)
    _war_defections(conn, org, meta, side, blk, cblk, day, rid)
    side = _factions(conn, org, meta)
    for i, f in enumerate(meta["factions"]):  # the war costs money
        cost = v(conn, blk.get("cost_week")) * sum(1 for a, j in side.items() if j == i)
        if cost > 0.0 and is_living(conn, int(f["leader"])):
            meta["spent"][i] += ledger.spend(conn, ("person", int(f["leader"])), cost, purpose="paying for a war")
    strength = _strength(conn, org, meta, side, blk)
    tot = sum(strength) or 1.0
    share = [strength[0] / tot, strength[1] / tot]
    live = [active_seat(conn, int(f["leader"]), org) is not None for f in meta["factions"]]
    leaders = [int(f["leader"]) for f in meta["factions"]]
    young = early(conn, weeks, blk["early_weeks"], blk["early_floor"])  # a quick end is unlikely in the first days, never impossible
    press = pressure(conn, org, blk["press"], opened=meta["started"], day=day, typical=blk["typical_weeks"], spent=sum(meta["spent"]), leaders=leaders)
    lead_i = max((0, 1), key=lambda i: (share[i], -i))
    weak = 1 - lead_i
    out = None
    if not all(live):
        out = ("win", max((0, 1), key=lambda i: (live[i], share[i], -i)))
    else:
        p_win = v(conn, blk["win_week"]) * young * clamp01((max(share) - 0.5) / (v(conn, blk["win_share"]) - 0.5))
        r = rel(conn, leaders[weak], leaders[lead_i])
        bitter = 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)
        men_weak = sum(1 for a, j in side.items() if j == weak and seat_of(conn, a, org)["inducted_day"] is not None)
        p_split = (v(conn, blk["split_week"]) * young * drive(conn, leaders[weak], "ambition") * lean(conn, org, bitter)
                   * clamp01(share[weak] / v(conn, blk["split_ref_share"])) * clamp01(men_weak / v(conn, blk["split_ref_men"])))
        p_settle = v(conn, blk["settle_week"]) * young * press * (1.0 - abs(share[0] - share[1])) * (1.0 - (drive(conn, leaders[0], "aggression") + drive(conn, leaders[1], "aggression")) / 2.0)
        if roll(conn, org, int(day), f"win:{rid}") < p_win:
            out = ("win", lead_i)
        elif roll(conn, org, int(day), f"split:{rid}") < p_split:
            out = ("split", lead_i)
        elif roll(conn, org, int(day), f"settle:{rid}") < p_settle:
            out = ("settle", lead_i)
    if out is None:
        save_meta(conn, rid, meta)
        return None
    how, winner = out
    _end_war(conn, row, meta, side, blk, how, int(winner), int(day))
    return how


def _end_war(conn, row, meta, side, blk, how: str, winner: int, day: int) -> None:
    org = int(meta["org"])
    wl = int(meta["factions"][winner]["leader"])
    ll = int(meta["factions"][1 - winner]["leader"])
    if active_seat(conn, wl, org) is None:  # no living man on the winning side: the other side's leader, if there is one
        wl, winner, ll = ll, 1 - winner, wl
    losers = [a for a, i in sorted(side.items()) if i == 1 - winner]
    out = {"how": how, "winner": wl}
    if how == "split":
        new = split_org(conn, org, [a for a, i in side.items() if i == 1 - winner], ll, int(day), blk)
        out["new_org"] = new
        install_head(conn, org, wl, int(day), "civil_war")
    elif how == "settle":
        install_head(conn, org, wl, int(day), "settled")
        for a, b in ((wl, ll), (ll, wl)):
            if a != b and is_living(conn, a) and is_living(conn, b):
                r = rel(conn, a, b)
                if r is not None:
                    adjust_relationship(conn, a, b, int(day), resentment_delta=-min(float(r["resentment"]), v(conn, blk.get("settle_thaw"))), trust_delta=v(conn, blk.get("settle_trust")))
        for a in losers:
            imposed(conn, a)
        if ll != wl and active_seat(conn, ll, org) is not None:
            add_agenda(conn, wl, "rival", int(day) + int(v(conn, orgs.kind_rules(conn, org)["lifecycle"]["rivals"]["delay_days"])), subject_kind="actor", subject_id=int(ll),
                       metadata={"org": int(org), "rival": int(ll), "how": "settle"})
    else:
        install_head(conn, org, wl, int(day), "civil_war")
        out["dealt"] = _deal_with_losers(conn, org, wl, losers, blk, int(day), leaders=(ll,))
    for a in side:
        imposed(conn, a)
    mark_for_history(conn, wl, f"won the war over the {name_of(conn, org)}" if how == "win" else f"ended the war over the {name_of(conn, org)} ({how})", int(day))
    close_row(conn, int(row["id"]), int(day), **{**meta, **out, "closed": int(day), "weeks": (int(day) - int(meta["started"])) // WEEK})


def demote_man(conn: sqlite3.Connection, org: int, man: int, by: int, day: int) -> None:
    """His lines pass to the man who decided, his standing goes, and the role the data says a returning man takes is his; a unit
    leader's unit and any post of the data's succession he held are put to the head to fill."""
    s = seat_of(conn, man, org)
    unit_role = kind_rules(conn, org).get("unit_leader")
    back = (orgs.kind_rules(conn, org).get("lifecycle") or {}).get("returns_as")
    old_role = s["role_key"]
    conn.execute("UPDATE org_lines SET holder_actor_id=? WHERE holder_actor_id=? AND status='active'", (int(by), int(man)))
    conn.execute("UPDATE org_seats SET standing=0 WHERE id=?", (int(s["id"]),))
    if back and old_role != back:
        conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=? WHERE id=?", (back, int(by), int(s["id"])))
        membership_text(conn, org, man, back)
        lv = role_level(conn, org, back)
        if lv is not None:
            orgs.set_level(conn, man, lv, int(day), org)
        if old_role == unit_role and s["unit_id"]:
            seat_the_unit(conn, org, int(s["unit_id"]), int(day), deciding=int(by))
        elif old_role in ((orgs.kind_rules(conn, org).get("lifecycle") or {}).get("succession") or {}):
            fill_post(conn, org, old_role, int(day))
    imposed(conn, int(man))
    imposed(conn, int(by))


def _deal_with_losers(conn, org, winner: int, losers: list[int], blk: dict, day: int, leaders: tuple = ()) -> dict:
    """What the winner does with each made man on the losing side. A side's leader and the unit leaders are weighed like any rival of
    a head (`rival_weights` for a war: killed, exiled, sidelined or kept; the data makes killing common here). The rest are killed
    (the winner's temper, the man's weight, his lack of fear), demoted, exiled or absorbed (he stays, afraid)."""
    w = blk["losers"]
    counts = {"killed": 0, "demoted": 0, "exiled": 0, "absorbed": 0}
    unit_role = kind_rules(conn, org).get("unit_leader")
    for a in losers:
        s = seat_of(conn, a, org)
        if s is None or s["status"] != "active" or s["inducted_day"] is None or not is_living(conn, a):
            continue
        if int(a) in leaders or s["role_key"] == unit_role:
            xs = rival_weights(conn, org, winner, a, "civil_war")
            how = {"keep": "absorb", "sideline": "demote", "exile": "exile", "remove": "kill"}[pick(conn, a, int(day), "loser_leader", list(xs.items()), v(conn, orgs.kind_rules(conn, org)["lifecycle"]["rivals"]["temp"]))]
        else:
            r = rel(conn, a, winner)
            fear = 0.0 if r is None else clamp01(float(r["fear"]) / 100.0)
            trust = 0.0 if r is None else clamp01((float(r["trust"]) + float(r["loyalty"])) / 200.0)
            weight = v(conn, w["standing_weight"]) * float(s["standing"])
            opts = [("kill", v(conn, w["kill_base"]) + v(conn, w["kill_aggression"]) * temper(conn, org, winner) * weight * (1.0 - fear)),
                    ("demote", v(conn, w["demote_base"]) + v(conn, w["demote_weight"]) * weight),
                    ("exile", v(conn, w["exile_base"]) + v(conn, w["exile_weight"]) * weight * (1.0 - fear)),
                    ("absorb", v(conn, w["absorb_base"]) + v(conn, w["absorb_fear"]) * fear + v(conn, w["absorb_trust"]) * trust)]
            how = pick(conn, a, int(day), "loser", opts, v(conn, w["temp"]))
        if how == "kill":
            _kill(conn, winner, a, int(day), sanctioned=True)
            counts["killed"] += 1
        elif how == "demote":
            demote_man(conn, org, a, winner, int(day))
            adjust_relationship(conn, a, winner, int(day), resentment_delta=v(conn, w["demote_resentment"]))
            counts["demoted"] += 1
        elif how == "exile":
            exile_man(conn, org, a, winner, int(day))
            counts["exiled"] += 1
        else:
            adjust_relationship(conn, a, winner, int(day), fear_delta=v(conn, w["absorb_fear_gain"]))
            counts["absorbed"] += 1
        imposed(conn, a)
    return counts


def exile_man(conn: sqlite3.Connection, org: int, man: int, by: int, day: int) -> None:
    """Sent away (to another city or territory), retired off, told never to come back: his lines pass to the man who decided, his seat
    is out with the record kept (an `exiled` marker, so he is not a man who walked away) and he leaves the living organisation."""
    d = orgs.kind_rules(conn, org)["lifecycle"]["rivals"]["exile"]
    imposed(conn, int(man))
    conn.execute("UPDATE org_lines SET holder_actor_id=? WHERE holder_actor_id=? AND status='active'", (int(by), int(man)))
    put_row(conn, int(man), "exiled", int(day), int(org), {"org": int(org), "by": int(by)}, "org")
    leave_life(conn, int(man), int(org), int(day))
    adjust_relationship(conn, int(man), int(by), int(day), resentment_delta=v(conn, d["resentment_gain"]), fear_delta=v(conn, d["fear_gain"]))
    mark_for_history(conn, int(man), f"was sent away from the {name_of(conn, org)}", int(day))
    imposed(conn, int(by))


# ---- a split: the losing side becomes a new organisation of the same kind ----

def split_org(conn: sqlite3.Connection, org: int, men: list[int], leader: int, day: int, blk: dict) -> int | None:
    """The men (and, with their unit leader, his unit and lines) leave `org` for a new institution of the same kind, headed by
    `leader`. The new organisation is built through the org tables: an institution actor, a profile, seats, units, lines and
    holdings of its own, so the weekly layers and the money rules run on it like on any other."""
    spec = block(conn, org, "split")
    rules = kind_rules(conn, org)
    leader = int(leader)
    if active_seat(conn, leader, org) is None:
        return None
    moved = {int(a) for a in men if active_seat(conn, a, org) is not None} | {leader}
    units = {int(r[0]) for r in conn.execute("SELECT id FROM org_units WHERE org_actor_id=? AND leader_actor_id IN (%s)" % ",".join("?" * len(moved)), (int(org), *sorted(moved)))}
    uargs = sorted(units) or [-1]
    for (a,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND unit_id IN (%s)" % ",".join("?" * len(uargs)), (int(org), *uargs)).fetchall():
        moved.add(int(a))
    surname = name_of(conn, leader).split()[-1]
    base = str(spec.get("name") or "{surname} splinter").format(surname=surname)
    name, n = base, 1
    while conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
        n += 1
        name = f"{base} {'I' * n}" if n < 4 else f"{base} {n}"
    prof = conn.execute("SELECT * FROM org_profiles WHERE org_actor_id=?", (int(org),)).fetchone()
    inducted = [a for a in moved if seat_of(conn, a, org)["inducted_day"] is not None]
    deps = len(moved) - len(inducted)
    new = int(conn.execute("INSERT INTO actors(name,actor_type,subtype,status) VALUES (?, 'institution', ?, 'active')",
                           (name, conn.execute("SELECT subtype FROM actors WHERE id=?", (int(org),)).fetchone()[0])).lastrowid)
    n_split = int(conn.execute("SELECT COUNT(*) FROM org_profiles WHERE package_key LIKE ?", (f"{prof['package_key']}~split%",)).fetchone()[0]) + 1
    conn.execute("INSERT INTO org_profiles(org_actor_id,org_kind,sphere,package_key,metadata_json) VALUES (?,?,?,?,?)",
                 (new, prof["org_kind"], prof["sphere"], f"{str(prof['package_key']).split('~')[0]}~split{n_split}",
                  json.dumps({"split_of": int(org), "day": int(day), "spec": {"members_figure": len(inducted), "dependents_figure": round(deps / max(1, len(inducted)), 3)}}, sort_keys=True)))
    ph = ",".join("?" * len(moved))
    conn.execute(f"UPDATE org_seats SET org_actor_id=? WHERE org_actor_id=? AND actor_id IN ({ph})", (new, int(org), *sorted(moved)))
    conn.execute(f"UPDATE org_units SET org_actor_id=? WHERE id IN ({','.join('?' * len(uargs))})", (new, *uargs))
    head_role = rules["head"]
    conn.execute("UPDATE org_seats SET role_key=?, unit_id=NULL, superior_actor_id=NULL WHERE actor_id=? AND org_actor_id=?", (head_role, leader, new))
    for (a, sup, unit) in conn.execute("SELECT actor_id,superior_actor_id,unit_id FROM org_seats WHERE org_actor_id=? AND actor_id<>?", (new, leader)).fetchall():
        if sup is None or int(sup) not in moved:
            conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE actor_id=? AND org_actor_id=?", (leader, int(a), new))
    conn.execute(f"UPDATE institution_memberships SET institution_actor_id=? WHERE institution_actor_id=? AND membership_kind='member' AND member_actor_id IN ({ph})", (new, int(org), *sorted(moved)))
    for a in moved:
        membership_text(conn, new, a, seat_of(conn, a, new)["role_key"])
    lines = conn.execute(f"SELECT l.*,h.pool_key,h.share_pct,h.yearly_take,h.id AS hid FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active' "
                         f"AND (l.holder_actor_id IN ({ph}) OR l.unit_id IN ({','.join('?' * len(uargs))}))", (int(org), *sorted(moved), *uargs)).fetchall()
    holdings: dict[int, int] = {}
    for ln in lines:
        hid = int(ln["hid"])
        if hid not in holdings:
            total = conn.execute("SELECT COALESCE(SUM(weekly_take),0) FROM org_lines WHERE holding_id=? AND status='active'", (hid,)).fetchone()[0] or 1.0
            take = sum(float(x["weekly_take"]) for x in lines if int(x["hid"]) == hid)
            frac = min(1.0, take / total)
            holdings[hid] = int(conn.execute("INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,source,started_day) VALUES (?,?,?,?,'taken',?)",
                                             (new, ln["pool_key"], float(ln["share_pct"]) * frac, float(ln["yearly_take"]) * frac, int(day))).lastrowid)
            conn.execute("UPDATE org_holdings SET share_pct=share_pct*?, yearly_take=yearly_take*? WHERE id=?", (1.0 - frac, 1.0 - frac, hid))
        conn.execute("UPDATE org_lines SET holding_id=? WHERE id=?", (holdings[hid], int(ln["id"])))
    lv = role_level(conn, new, head_role)
    for a in sorted(moved):
        imposed(conn, a)
    if lv is not None:
        orgs.set_level(conn, leader, lv, int(day), new)
    mark_for_history(conn, leader, f"split from the {name_of(conn, org)} and took his men", int(day))
    return new


# ---- the new head and the men who stood against him ----

def rival_weights(conn: sqlite3.Connection, org: int, head: int, rv: int, how: str) -> dict[str, float]:
    """The head's pull toward each answer to a man who stood against him: keep, sideline, exile, remove. Each answer starts from the
    base the data gives for how the matter ended (`rivals.how[how]`: an agreed contest keeps its losers more often; a forced or bought
    one, a killing, a coup or a war removes them more often) and adds the rival's trust and fear, his resentment and ambition, his
    strength, and the head's own temper (his aggression and the outfit's lean toward violence). A missing outcome fails loudly."""
    d = orgs.kind_rules(conn, org)["lifecycle"]["rivals"]
    base = d["how"][how]
    r = rel(conn, rv, head)
    trust = 0.0 if r is None else clamp01((float(r["trust"]) + float(r["loyalty"])) / 200.0)
    fear = 0.0 if r is None else clamp01(float(r["fear"]) / 100.0)
    resent = 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)
    from .org_succession import _under
    strength = clamp01(len(_under(conn, org, rv)) / v(conn, d["strength_scale"]))
    k, sd, ex, rm = d["keep"], d["sideline"], d["exile"], d["remove"]
    return {"keep": v(conn, base["keep"]) + v(conn, k["trust"]) * trust + v(conn, k["fear"]) * fear + v(conn, k["strength"]) * strength,
            "sideline": v(conn, base["sideline"]) + v(conn, sd["resentment"]) * resent + v(conn, sd["ambition"]) * drive(conn, rv, "ambition") * (1.0 - fear),
            "exile": v(conn, base["exile"]) + v(conn, ex["resentment"]) * resent + v(conn, ex["strength"]) * strength + v(conn, ex["caution"]) * (1.0 - temper(conn, org, head)),
            "remove": v(conn, base["remove"]) + v(conn, rm["aggression"]) * temper(conn, org, head) * resent * (1.0 - fear) * (1.0 - v(conn, rm["strength"]) * strength)}


def rival_offers(conn: sqlite3.Connection, head: int, item, day: int) -> list[dict]:
    """The new head weighs what to do about a man who stood against him (`rival_weights`), by how the matter ended."""
    meta = meta_of(item)
    org, rv = int(meta["org"]), int(item["subject_id"])
    payload = {"org": org, "rival": rv}
    s = seat_of(conn, rv, org)
    if s is None or s["status"] != "active" or not is_living(conn, rv):
        return [{"kind": "rival_keep", "utility": _utility(conn, 1.0), "rationale": "The man is gone.", "payload": payload}]
    xs = rival_weights(conn, org, head, rv, meta["how"])
    why = {"keep": f"Keeps {name_of(conn, rv)}, who stood against him.", "sideline": f"Sidelines {name_of(conn, rv)}, who stood against him.",
           "exile": f"Sends {name_of(conn, rv)} away, for standing against him.", "remove": f"Has {name_of(conn, rv)} removed, for standing against him."}
    return [{"kind": "rival_" + k2, "utility": _utility(conn, x), "rationale": why[k2], "payload": payload, **({"target_actor_id": rv, "risk": 0.8} if k2 == "remove" else {})} for k2, x in xs.items()]


def execute_rival_exile(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    org, rv = int(payload["org"]), int(payload["rival"])
    s = seat_of(conn, rv, org)
    if s is None or s["status"] != "active":
        return {"summary": "There was no one to send away.", "blocked": True}
    exile_man(conn, org, rv, int(actor_id), int(day))
    return {"summary": f"{name_of(conn, actor_id)} sent {name_of(conn, rv)} away."}


def execute_rival_keep(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    rv = int(payload["rival"])
    d = (orgs.kind_rules(conn, int(payload["org"])).get("lifecycle") or {})["rivals"]
    if rv != int(actor_id):
        adjust_relationship(conn, rv, int(actor_id), int(day), resentment_delta=-v(conn, d["keep"]["thaw"]), trust_delta=v(conn, d["keep"]["trust_gain"]))
        imposed(conn, rv)
    return {"summary": f"{name_of(conn, actor_id)} kept {name_of(conn, rv)} on."}


def execute_rival_sideline(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    org, rv = int(payload["org"]), int(payload["rival"])
    s = seat_of(conn, rv, org)
    if s is None or s["status"] != "active":
        return {"summary": "There was no one to sideline.", "blocked": True}
    d = (orgs.kind_rules(conn, org).get("lifecycle") or {})["rivals"]
    demote_man(conn, org, rv, int(actor_id), int(day))
    adjust_relationship(conn, rv, int(actor_id), int(day), resentment_delta=v(conn, d["sideline"]["resentment_gain"]))
    return {"summary": f"{name_of(conn, actor_id)} sidelined {name_of(conn, rv)}."}


def execute_rival_remove(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    rv = int(payload["rival"])
    if not is_living(conn, rv):
        return {"summary": "The man was already gone.", "blocked": True}
    imposed(conn, int(actor_id))
    _kill(conn, int(actor_id), rv, int(day), sanctioned=True)
    return {"summary": f"{name_of(conn, actor_id)} had {name_of(conn, rv)} removed."}


# ---- the weekly pass ----

def _wars(conn: sqlite3.Connection, day: int) -> dict:
    out = {"war_weeks": 0, "wars_ended": 0}
    for row in conn.execute("SELECT * FROM org_agenda WHERE kind='civil_war' AND status='open' ORDER BY id").fetchall():
        out["war_weeks"] += 1
        out["wars_ended"] += 1 if tick_war(conn, row, int(day)) else 0
    return out


def weekly(conn: sqlite3.Connection, day: int) -> dict:
    out = _plots(conn, int(day))
    for k, n in _wars(conn, int(day)).items():
        out[k] = out.get(k, 0) + n
    return out


for _kind, _fn in (("plot_kill", execute_plot_kill), ("plot_exile", execute_plot_exile), ("plot_pardon", execute_plot_pardon)):
    register_executor(_kind, _fn)
register_agenda_action("plot_found", plot_found_offers)
for _kind, _fn in (("rival_keep", execute_rival_keep), ("rival_sideline", execute_rival_sideline), ("rival_exile", execute_rival_exile), ("rival_remove", execute_rival_remove)):
    register_executor(_kind, _fn)
register_agenda_action("rival", rival_offers)
