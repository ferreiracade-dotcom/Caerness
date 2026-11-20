"""How lethal a blow is, as data (task B12c).

The engine holds no figure for it. `engine/lethality_default.json` carries what the code held before (so a package with no
lethality data behaves exactly as it did), and a package may override any key with its own file (world.json data key
`lethality`; `null` removes a key, so a null `cap` is no cap). Curves are `clamp((x - offset) / scale, floor, cap)`.

A *method* (fists, blunt, blade, handgun at range, handgun point-blank, execution: the package names them) carries its own
fatal curve, its own kill ceiling for a planned hit and its own untreated-wound pressure. A *style* of hostile move
(`hit.styles`) names the mix of methods it is carried out with. Rates are Design proposals in the package file, each with its
reasoning; real-world case-fatality rates are calibration targets reported after a run, never caps, shares or clamps.
No world words here.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

_DEFAULT_PATH = Path(__file__).with_name("lethality_default.json")
_CACHE: dict = {}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load(path: Path) -> dict:
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if key not in _CACHE:
        try:
            _CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            _CACHE[key] = {}
    return _CACHE[key]


def config(conn) -> dict:
    """The engine defaults with the connected package's lethality file laid over them (defaults alone when `conn` is None)."""
    base = _load(_DEFAULT_PATH)
    if conn is None:
        return base
    from .world_package import package_for
    path = package_for(conn).data.get("lethality")
    if path is None:
        return base
    try:
        key = ("merged", str(path), path.stat().st_mtime_ns)
    except OSError:
        return base
    if key not in _CACHE:
        _CACHE[key] = _merge(base, _load(path))
    return _CACHE[key]


def curve(spec: dict | None, x: float) -> float:
    """clamp((x - offset) / scale, floor, cap); a null cap is no cap. No spec gives 0."""
    if not spec:
        return 0.0
    cap = spec.get("cap")
    v = (float(x) - float(spec["offset"])) / float(spec["scale"])
    return max(float(spec.get("floor") or 0.0), v if cap is None else min(float(cap), v))


def hit_cfg(conn, cls: str | None = None) -> dict:
    """The planned-hit figures, with the outfit class's own overrides laid over them."""
    h = config(conn)["hit"]
    over = (h.get("by_class") or {}).get(cls) if cls else None
    return _merge(h, over) if over else h


def pick_method(conn, style: str | None, cls: str | None, rng: random.Random) -> str | None:
    """A method drawn from the style's mix (weights in data); None when the package names none (then no draw is made)."""
    if conn is None or style is None:
        return None
    mix = ((hit_cfg(conn, cls).get("styles") or {}).get(style) or {}).get("methods") or {}
    names = [k for k in sorted(mix) if float(mix[k]) > 0]
    if not names:
        return None
    return rng.choices(names, weights=[float(mix[k]) for k in names], k=1)[0]


def fatal_probability(cfg: dict, intent: str, severity: float, method: str | None = None) -> float:
    if intent == "controlled":
        return 0.0
    m = (cfg.get("methods") or {}).get(method) if method else None
    spec = (m or {}).get("fatal") or cfg["fatal"].get(intent)
    return curve(spec, severity)


def persistent_probability(cfg: dict, intent: str, severity: float, method: str | None = None) -> float:
    m = (cfg.get("methods") or {}).get(method) if method else None
    spec = (m or {}).get("persistent") or cfg["persistent"][intent]
    return curve(spec, severity)


def untreated_pressure(cfg: dict, severity: float, method: str | None = None) -> float:
    """Fatality pressure a persistent wound carries (the health system turns it into a rate of dying later)."""
    u = dict(cfg["untreated"])
    m = (cfg.get("methods") or {}).get(method) if method else None
    if m and m.get("untreated"):
        u.update(m["untreated"])
    return max(0.0, float(severity) - float(u["start"])) * float(u["mul"])


def untreated_progression(cfg: dict, severity: float, method: str | None = None) -> float:
    """Per-30-day worsening of a persistent wound with no care (infection, bleeding); treatment cuts it. 0 when the package has none."""
    u = dict(cfg["untreated"])
    m = (cfg.get("methods") or {}).get(method) if method else None
    if m and m.get("untreated"):
        u.update(m["untreated"])
    return max(0.0, float(severity) - float(u["start"])) * float(u.get("progression_mul") or 0.0)


def kill_chance(h: dict, p: float, lethal: bool, method: str | None, cfg: dict, guard: float = 0.0) -> float:
    """Chance that a blow which landed kills. A planned killing takes the method's kill ceiling; a beating the non-lethal scale."""
    m = (cfg.get("methods") or {}).get(method) if method else None
    kmax = float((m or {}).get("kill_max", h["kill_max"]))
    span = max(1e-9, float(h["knee"]) - float(h["floor"]))
    shape = min(1.0, max(0.0, (p - float(h["floor"])) / span)) ** float(h["exp"])
    pk = kmax * shape * (1.0 if lethal else float(h["nonlethal_scale"]))
    return max(0.0, min(1.0, pk * (1.0 - float(h.get("guard_weight") or 0.0) * max(0.0, min(1.0, guard)))))


def _weighted(mix: dict | None, rng: random.Random) -> str | None:
    names = [k for k in sorted(mix or {}) if float(mix[k]) > 0]
    return rng.choices(names, weights=[float(mix[k]) for k in names], k=1)[0] if names else None


def incident_cfg(conn, outfit_key: str | None = None) -> dict:
    """The weekly-incident figures, with the offender outfit's own overrides laid over them."""
    inc = config(conn).get("incident") or {}
    over = (inc.get("by_outfit") or {}).get(outfit_key) if outfit_key else None
    return _merge(inc, over) if over else inc


def incident_roll(conn, outfit_key: str | None, severity: float, rng: random.Random) -> tuple[float, str | None, bool]:
    """(severity, method, went_too_far) for one weekly incident. `severity` is the ordinary draw the caller already made; a
    package with a tail turns a share of incidents into ones that run at the tail's severity with the tail's method mix, and
    gives the rest the ordinary method mix. A package with no incident data leaves the caller's draw alone and draws nothing."""
    inc = incident_cfg(conn, outfit_key)
    share = float(inc.get("tail_share") or 0.0)
    if share <= 0.0 and not inc.get("methods"):
        return severity, None, False
    if share > 0.0 and rng.random() < share:
        lo, hi = float(inc["tail_lo"]), float(inc["tail_hi"])
        return lo + (hi - lo) * rng.random(), _weighted(inc.get("tail_methods") or inc.get("methods"), rng), True
    return severity, _weighted(inc.get("methods"), rng), False


def bystander_hurt(conn, outfit_key: str | None, method: str | None, rng: random.Random) -> float | None:
    """When a tail incident's method can reach someone else, the severity a bystander takes (None: no bystander hurt)."""
    inc = incident_cfg(conn, outfit_key)
    if method not in (inc.get("bystander_methods") or []) or rng.random() >= float(inc.get("bystander_share") or 0.0):
        return None
    lo, hi = float(inc["bystander_lo"]), float(inc["bystander_hi"])
    return lo + (hi - lo) * rng.random()
