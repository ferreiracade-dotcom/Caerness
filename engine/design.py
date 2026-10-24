"""Design figures: drawn once per run, held, logged (Saint Jude bible Index 4, Engine Implications E-005 to E-008).

A package may carry data "design" (e.g. worlds/saintjude/design_figures.json) with `figures`, each
{default, range, kind: draw|derived|fixed, formula?, tag, source}. At the opening every `draw` figure is drawn
once from its range with the run seed (triangular, peaked at the default), every `fixed` figure takes its
default, and every `derived` figure is recomputed from the drawn values by its formula. Each value is stored
with the seed, day and cause, so a run can say why a figure has the value it has. `set_figure` moves a figure
later only with a cause and clamps to its range unless the cause is marked as an exception (E-008).

A package without design data gets nothing: no table, no rows (Caerness openings are unchanged).
"""
from __future__ import annotations

import ast
import hashlib
import json
import operator
import random
import sqlite3
from typing import Any

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow}
_FUNCS = {"min": min, "max": max, "abs": abs, "sum": sum, "round": round}

_DDL = """CREATE TABLE IF NOT EXISTS design_figures (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    value REAL,
    text_value TEXT,
    default_value REAL,
    lo REAL,
    hi REAL,
    tag TEXT,
    source TEXT,
    seed INTEGER,
    day INTEGER NOT NULL,
    cause TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS design_figure_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    day INTEGER NOT NULL,
    old_value REAL,
    new_value REAL,
    seed INTEGER,
    cause TEXT NOT NULL
);"""


class DesignError(ValueError):
    pass


def _eval(expr: str, env: dict) -> float:
    """Arithmetic over figure names only (same grammar as tools/check_saintjude_pools.py)."""
    def go(n):
        if isinstance(n, ast.Expression):
            return go(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in env:
                raise KeyError(n.id)
            return env[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](go(n.left), go(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -go(n.operand) if isinstance(n.op, ast.USub) else go(n.operand)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[go(a) for a in n.args])
        raise ValueError(f"disallowed expression element {type(n).__name__}")
    return go(ast.parse(expr, mode="eval"))


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def package_figures(conn: sqlite3.Connection) -> dict[str, dict]:
    from .world_package import package_for
    path = package_for(conn).data.get("design")
    if path is None:
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8")).get("figures") or {})


def _ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)


def _has_table(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='design_figures'").fetchone())


def _seed_day(conn: sqlite3.Connection) -> tuple[int, int]:
    row = conn.execute("SELECT rng_seed,current_day FROM world_state WHERE id=1").fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def _rng(seed: int, key: str) -> random.Random:
    h = hashlib.sha256(f"design:{seed}:{key}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def _draw(seed: int, key: str, f: dict) -> float:
    lo, hi = (float(x) for x in f["range"])
    d = float(f["default"])
    if hi <= lo:
        return d
    v = _rng(seed, key).triangular(lo, hi, min(max(d, lo), hi))
    return int(round(v)) if isinstance(f["default"], int) and isinstance(f["range"][0], int) else v


def _derive(figs: dict[str, dict], env: dict[str, float]) -> dict[str, float]:
    """Recompute derived figures in dependency order; a formula the engine cannot evaluate keeps its default."""
    out: dict[str, float] = {}
    pending = {k: f for k, f in figs.items() if f.get("kind") == "derived"}
    for _ in range(len(pending) + 1):
        progressed = False
        for k in list(pending):
            expr = str(pending[k].get("formula") or "")
            try:
                out[k] = env[k] = float(_eval(expr, env))
            except KeyError as e:
                if str(e).strip("'") in pending:
                    continue  # input not derived yet
                out[k] = env[k] = float(pending[k]["default"])
            except (ValueError, SyntaxError, ZeroDivisionError):
                out[k] = env[k] = float(pending[k]["default"])  # e.g. "table:protection": the table holds defaults
            del pending[k]
            progressed = True
        if not pending or not progressed:
            break
    for k, f in pending.items():  # a cycle: hold the default
        out[k] = env[k] = float(f["default"])
    return out


def draw_all(conn: sqlite3.Connection) -> dict[str, int]:
    """Draw every figure once (idempotent: figures already drawn are held). Returns counts."""
    figs = package_figures(conn)
    if not figs:
        return {}
    _ensure(conn)
    seed, day = _seed_day(conn)
    have = {r[0] for r in conn.execute("SELECT key FROM design_figures")}
    env: dict[str, float] = {r[0]: r[1] for r in conn.execute("SELECT key,value FROM design_figures WHERE value IS NOT NULL")}
    drawn = 0
    for k, f in figs.items():
        if k in have or f.get("kind") == "derived":
            continue
        kind = f.get("kind")
        rng = f.get("range") if isinstance(f.get("range"), list) else None
        if not _num(f.get("default")):
            conn.execute("INSERT INTO design_figures(key,kind,text_value,tag,source,seed,day,cause) VALUES (?,?,?,?,?,?,?,?)",
                         (k, kind, json.dumps(f.get("default")), f.get("tag"), f.get("source"), seed, day, "opening: non-numeric, held"))
            continue
        if kind == "draw" and rng:
            value, cause = _draw(seed, k, f), "opening draw (triangular on range, peak at default)"
        else:
            value, cause = f["default"], "opening: fixed" if kind == "fixed" else "opening: default (no range)"
        env[k] = float(value)
        conn.execute("INSERT INTO design_figures(key,kind,value,default_value,lo,hi,tag,source,seed,day,cause) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (k, kind, float(value), float(f["default"]), rng[0] if rng else None, rng[1] if rng else None,
                      f.get("tag"), f.get("source"), seed, day, cause))
        conn.execute("INSERT INTO design_figure_log(key,day,old_value,new_value,seed,cause) VALUES (?,?,?,?,?,?)",
                     (k, day, None, float(value), seed, cause))
        drawn += 1
    derived = _recompute_derived(conn, figs, env, day, seed, cause="opening: derived from drawn inputs")
    return {"design_figures_drawn": drawn, "design_figures_derived": derived}


def _recompute_derived(conn, figs, env, day, seed, *, cause: str) -> int:
    n = 0
    for k, v in _derive(figs, dict(env)).items():
        f = figs[k]
        row = conn.execute("SELECT value FROM design_figures WHERE key=?", (k,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO design_figures(key,kind,value,default_value,tag,source,seed,day,cause) VALUES (?,?,?,?,?,?,?,?,?)",
                         (k, "derived", v, float(f["default"]), f.get("tag"), f.get("source"), seed, day, cause))
        elif row[0] is None or abs(float(row[0]) - v) > 1e-12:
            conn.execute("UPDATE design_figures SET value=?,day=?,cause=? WHERE key=?", (v, day, cause, k))
        else:
            continue
        conn.execute("INSERT INTO design_figure_log(key,day,old_value,new_value,seed,cause) VALUES (?,?,?,?,?,?)",
                     (k, day, None if row is None else row[0], v, seed, cause))
        n += 1
    return n


def figure(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """The run's value of a figure (drawn on first use if the opening did not draw it); `default` if the package has none."""
    figs = package_figures(conn)
    if key not in figs:
        return default
    if not _has_table(conn) or not conn.execute("SELECT 1 FROM design_figures WHERE key=?", (key,)).fetchone():
        draw_all(conn)
    row = conn.execute("SELECT value,text_value FROM design_figures WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    return row[0] if row[0] is not None else json.loads(row[1])


def set_figure(conn: sqlite3.Connection, key: str, value: float, *, cause: str, exception: bool = False) -> float:
    """Move a figure for a stated cause. Clamped to its range unless `exception` (the cause is then logged as such)."""
    if not cause or not str(cause).strip():
        raise DesignError(f"figure {key}: a change needs a cause")
    figs = package_figures(conn)
    f = figs.get(key)
    if f is None:
        raise DesignError(f"no design figure named {key}")
    if f.get("kind") == "derived":
        raise DesignError(f"figure {key} is derived; move its inputs instead")
    figure(conn, key)
    seed, day = _seed_day(conn)
    v = float(value)
    rng = f.get("range") if isinstance(f.get("range"), list) else None
    note = cause
    if rng and not exception:
        lo, hi = float(rng[0]), float(rng[1])
        if not lo <= v <= hi:
            note = f"{cause} (asked {v:g}, clamped to range {lo:g} to {hi:g})"
            v = min(max(v, lo), hi)
    elif rng and exception:
        note = f"{cause} (exception to range {rng[0]} to {rng[1]})"
    old = conn.execute("SELECT value FROM design_figures WHERE key=?", (key,)).fetchone()[0]
    conn.execute("UPDATE design_figures SET value=?,day=?,cause=? WHERE key=?", (v, day, note, key))
    conn.execute("INSERT INTO design_figure_log(key,day,old_value,new_value,seed,cause) VALUES (?,?,?,?,?,?)",
                 (key, day, old, v, seed, note))
    env = {r[0]: r[1] for r in conn.execute("SELECT key,value FROM design_figures WHERE value IS NOT NULL AND kind!='derived'")}
    _recompute_derived(conn, figs, env, day, seed, cause=f"derived: {key} moved ({cause})")
    return v
