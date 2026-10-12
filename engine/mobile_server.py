from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .agency import request_interrupt
from .canon import DEFAULT_CANON, index_canon
from .db import ENGINE_VERSION, ROOT, backup_db, connect, init_db, migration_status
from .local_model import local_health, runtime_config, set_runtime_config
from .mobile_runtime import maybe_auto_backup, mobile_state, process_player_input, referral_for_request
from .model_gateway import apply_model_request, import_response, request_row, run_request_local
from .bootstrap import bootstrap_campaign, bootstrap_status, create_player_character
from .player import get_player
from .health import health_summary
from .ecology import ecology_context
from .education import education_context
from .motives import derive_actor_motives
from .stress import contradiction_scan

MOBILE_DIR = ROOT / "mobile"


def _ledger_state(conn):
    """Player-facing reference state plus explicit campaign/admin setup diagnostics.

    This deliberately does not expose hidden NPC truth. Domain details are limited to the
    current camera character; the admin block contains save/setup health, not secret world state.
    """
    setup = bootstrap_status(conn)
    player = get_player(conn)
    out = {
        "setup": setup,
        "admin": {
            "engine_version": ENGINE_VERSION,
            "schema_version": migration_status(conn)["schema_version"],
            "contradiction_count": len([x for x in contradiction_scan(conn) if x.get("severity") == "error"]),
        },
        "player": None,
    }
    if not player:
        return out
    aid = int(player["player_actor_id"])
    loc = player["current_location_id"]
    household = conn.execute(
        """SELECT h.id,h.name,hm.role,h.status,h.cohesion,h.wealth,h.liquidity
           FROM household_members hm JOIN households h ON h.id=hm.household_id
           WHERE hm.actor_id=? AND hm.status='active' AND h.status NOT IN ('dissolved','historical')
           ORDER BY hm.authority DESC,h.id LIMIT 1""", (aid,)
    ).fetchone()
    affiliations = [dict(r) for r in conn.execute(
        """SELECT rt.name tradition,ra.affiliation_kind,ra.status,ra.practice_intensity,ra.publicness
           FROM religious_affiliations ra JOIN religious_traditions rt ON rt.id=ra.tradition_id
           WHERE ra.actor_id=? ORDER BY ra.status,rt.name""", (aid,)
    ).fetchall()]
    obligations = [dict(r) for r in conn.execute(
        """SELECT obligation_kind,description,due_day,status FROM religious_obligations
           WHERE actor_id=? AND status IN ('pending','overdue') ORDER BY due_day,id""", (aid,)
    ).fetchall()]
    travel = conn.execute(
        """SELECT tp.*,l.name destination_name FROM travel_plans tp
           LEFT JOIN locations l ON l.id=tp.destination_location_id
           WHERE tp.subject_kind='actor' AND tp.subject_id=? AND tp.status IN ('active','stalled')
           ORDER BY tp.id DESC LIMIT 1""", (aid,)
    ).fetchone()
    offices = [dict(r) for r in conn.execute(
        """SELECT a.name polity_name,p.status polity_status FROM political_polities p
           JOIN actors a ON a.id=p.institution_actor_id WHERE p.ruler_actor_id=?""", (aid,)
    ).fetchall()]
    out["player"] = {
        "actor_id": aid, "name": player["actor_name"], "location": player["location_name"],
        "household": dict(household) if household else None,
        "health": health_summary(conn, aid),
        "religion": {"affiliations": affiliations, "obligations": obligations},
        "travel": dict(travel) if travel else None,
        "environment": ecology_context(conn, int(loc)) if loc is not None else None,
        "education": education_context(conn, aid),
        "political_offices": offices,
        "derived_motives": derive_actor_motives(conn, aid),
    }
    return out


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")


class CaernessHandler(BaseHTTPRequestHandler):
    server_version = f"CaernessMobile/{ENGINE_VERSION}"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep Termux output readable: only log errors unless explicitly requested later.
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(format, *args)

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = _json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object")
        return value

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/state":
                with connect() as conn:
                    self._send_json(mobile_state(conn))
                return
            if path == "/api/local-health":
                with connect() as conn:
                    self._send_json(local_health(conn))
                return
            if path == "/api/runtime":
                with connect() as conn:
                    self._send_json(runtime_config(conn))
                return
            if path == "/api/ledger":
                with connect() as conn:
                    self._send_json(_ledger_state(conn))
                return
            if path == "/manifest.json":
                return self._serve_file(MOBILE_DIR / "manifest.json", "application/manifest+json")
            if path in {"/", "/index.html"}:
                return self._serve_file(MOBILE_DIR / "index.html", "text/html; charset=utf-8")
            candidate = (MOBILE_DIR / path.lstrip("/")).resolve()
            if MOBILE_DIR.resolve() in candidate.parents and candidate.is_file():
                return self._serve_file(candidate)
            self._send_json({"error": "Not found"}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def _serve_file(self, path: Path, content_type: str | None = None) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/api/appointment-confirm":
                from .actions import confirm_appointment_scope
                with connect() as conn:
                    result = confirm_appointment_scope(conn, int(body["action_id"]))
                    conn.commit()
                self._send_json({"status": "complete", "turn": result, "narration": result["narration"]})
                return
            if path == "/api/play":
                text = str(body.get("text") or "")
                mode = str(body.get("mode") or "auto")
                force = bool(body.get("force_local", False))
                with connect() as conn:
                    result = process_player_input(conn, text, mode=mode, force_local=force)
                    conn.commit()
                # Backups intentionally happen only after the authoritative transaction commits.
                with connect() as conn:
                    backup = maybe_auto_backup(conn)
                if backup:
                    result["backup"] = backup
                self._send_json(result)
                return
            if path == "/api/narrative-play":
                from .narrative_runtime import play
                with connect() as conn:
                    result = play(conn, body.get("text", ""), body.get("session_id"), body.get("plan_id"))
                    conn.commit()
                self._send_json(result)
                return
            if path == "/api/plan-play":
                from .planning_gateway import play
                with connect() as conn:
                    result = play(conn,str(body.get("text") or ""),body.get("session_id"),body.get("plan_id"),force_local=bool(body.get("force_local",False)))
                    conn.commit()
                self._send_json(result)
                return
            if path == "/api/plan-approve":
                from .ai_planning import approve_plan
                from .planning_gateway import feedback_request, record_execution_narration
                with connect() as conn:
                    result = approve_plan(conn,int(body["plan_id"]),str(body["digest"]))
                    if result.get("plan") and body.get("narrative"):
                        from .narrative_runtime import after_execution
                        from .planning_gateway import run_local
                        queued=after_execution(conn,result)
                        try:
                            result=run_local(conn,queued['next_request']['request_id'],force=runtime_config(conn).get('remote_model',False))
                        except (ConnectionError,RuntimeError,ValueError):
                            result={**queued,'summary':'The consequences are saved. Narration is awaiting the configured model.'}
                    elif result.get("plan"):
                        result.update(record_execution_narration(conn,result["plan"]))
                        if result["plan"]["status"] in ("blocked","refused","awaiting_response"):
                            result["planning_feedback_request"] = feedback_request(conn,result["plan"])
                    conn.commit()
                self._send_json(result)
                return
            if path == "/api/interrupt":
                with connect() as conn:
                    request_interrupt(conn)
                    conn.commit()
                self._send_json({"status": "interrupt_requested"})
                return
            if path.startswith("/api/model/") and path.endswith("/local"):
                request_id = int(path.split("/")[3])
                with connect() as conn:
                    row=conn.execute("SELECT input_json FROM model_requests WHERE id=?",(request_id,)).fetchone()
                    if row and json.loads(row[0]).get("protocol") in {"world_plan_v1", "narrative_play_v1", "narrative_scope_v1"} and bool(body.get("apply",True)):
                        from .planning_gateway import run_local
                        try:
                            result=run_local(conn,request_id,force=bool(body.get("force",False)))
                        except (ConnectionError,RuntimeError,ValueError):
                            latest=conn.execute("SELECT id FROM model_requests WHERE target_kind='ai_session' AND target_id=(SELECT target_id FROM model_requests WHERE id=?) AND status IN ('pending','responded') ORDER BY id DESC LIMIT 1",(request_id,)).fetchone()
                            result=referral_for_request(conn,latest[0] if latest else request_id,{'recommendation':'external_recommended'},reason='Model continuation unavailable. Confirmed outcomes and the conversation remain saved.')
                    else:
                        result = run_request_local(conn, request_id, force=bool(body.get("force", False)), apply=bool(body.get("apply", True)))
                    conn.commit()
                self._send_json(result)
                return
            if path.startswith("/api/model/") and path.endswith("/import"):
                request_id = int(path.split("/")[3])
                raw = str(body.get("response") or "")
                with connect() as conn:
                    parsed = import_response(conn, request_id, raw)
                    applied = apply_model_request(conn, request_id) if bool(body.get("apply", True)) else None
                    followup = None
                    if body.get("auto_continue", True) and isinstance(applied, dict) and applied.get("next_request"):
                        next_id = int(applied["next_request"]["request_id"])
                        next_row = conn.execute("SELECT input_json FROM model_requests WHERE id=?",(next_id,)).fetchone()
                        if json.loads(next_row[0]).get("protocol") in {"world_plan_v1", "narrative_play_v1", "narrative_scope_v1"}:
                            followup = referral_for_request(conn,next_id,{"recommendation":"external_recommended"},reason="Continue the same planning conversation with the tool feedback.")
                        else:
                            followup = run_request_local(conn, next_id, force=False, apply=True)
                        if isinstance(followup, dict) and followup.get("status") == "external_recommended":
                            followup = referral_for_request(conn, next_id, followup["assessment"], reason=followup.get("message", ""))
                    conn.commit()
                self._send_json({"status": "ok", "parsed": parsed, "applied": applied, "followup": followup})
                return
            if path == "/api/campaign/bootstrap":
                with connect() as conn:
                    result = bootstrap_campaign(conn)
                    conn.commit()
                self._send_json(result)
                return
            if path == "/api/campaign/player":
                with connect() as conn:
                    actor_id = create_player_character(
                        conn, str(body.get("name") or ""),
                        start_location=str(body.get("start_location") or "Cairnholt"),
                        age=int(body["age"]) if body.get("age") not in (None, "") else None,
                        campaign_name=str(body.get("campaign_name") or "Caerness Campaign"),
                    )
                    conn.commit()
                self._send_json({"player_actor_id": actor_id})
                return
            if path == "/api/runtime":
                with connect() as conn:
                    cfg = set_runtime_config(conn, **body)
                    conn.commit()
                self._send_json(cfg)
                return
            if path == "/api/backup":
                self._send_json({"path": backup_db(str(body.get("label") or "manual"))})
                return
            self._send_json({"error": "Not found"}, 404)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    init_db()
    index_canon(DEFAULT_CANON)
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("WARNING: Caerness is being bound beyond localhost. the local UI has no authentication; use localhost for phone-local play.")
    server = ThreadingHTTPServer((host, port), CaernessHandler)
    print(f"Caerness v{ENGINE_VERSION} mobile UI: http://{host}:{port}")
    print("Story time advances only through play. Closing the browser/app does not advance Caerness time.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
