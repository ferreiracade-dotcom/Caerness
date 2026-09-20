from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.canon import DEFAULT_CANON, canon_status, index_canon, search_canon
from engine.db import (
    ENGINE_VERSION, SCHEMA_VERSION, backup_db, connect, database_path, init_db, migration_status, reset_db, restore_db,
)
from engine.decisions import build_actor_context, decide_actor, recent_decisions
from engine.interactions import create_interaction, interaction_history, recent_interactions
from engine.information import actor_knowledge, process_information, recent_rumours, register_event_information
from engine.player import build_scene_packet, render_scene_brief, set_player, designate_camera_successor, camera_history
from engine.turns import export_journal, play_turn, recent_turns
from engine.local_model import local_health, runtime_config, set_runtime_config
from engine.router import assess_model_task
from engine.competence import active_matters, add_intention, add_obligation, add_possession, pending_attention
from engine.emergence import active_emergent_threads, important_memories
from engine.discovery import player_information_hub
from engine.mobile_server import serve as serve_mobile
from engine.agency import request_interrupt
from engine.world import world_activity_summary
from engine.model_gateway import (
    apply_model_request, bridge_play, configured_provider, create_decision_request,
    export_request, import_response, model_status, pending_requests, request_row, set_model_config,
    assess_request_route, run_request_local,
)
from engine.simulation import SimEvent, advance, log_event, recent_events, seed_demo, status
from engine.expertise import (
    actor_competence_profile, add_advisor_judgment, advisor_judgments, build_scene_competence_packet,
    decision_context, prepare_professional_reading, professional_reading, record_professional_reading,
    set_actor_competence,
)
from engine.embodiment import (
    assess_autonomous_expression, get_embodiment_profile, prepare_speech_mediation,
    recent_speech_mediations, record_expression, update_embodiment_profile,
)
from engine.crystallization import (
    apply_crystallization_proposal, crystallization_run, export_crystallization_packet,
    parse_crystallization_response, prepare_crystallization_context, validate_crystallization_proposal,
)
from engine.timeskip import prepare_time_skip, resolve_time_skip, time_skip_run
from engine.combat import (
    add_battle_side, add_battle_unit, battle_view, create_battle, create_duel, duel_view,
    engagement_summary, resolve_battle_round, resolve_duel_exchange, submit_battle_intent, submit_duel_intent,
    link_duel_to_battle,
)
from engine.battle_tactics import (
    add_vein_asset, apply_personal_combat_consequence, assign_vein_asset,
    set_battle_doctrine, set_zone_current, submit_tactical_choice,
)
from engine.battlefield import (
    add_battle_zone, assign_unit_to_zone, set_command_link, issue_battle_order, set_command_profile,
)
from engine.civilian_life import (
    create_building, ensure_style_movement, set_style_adoption, set_succession_plan, set_inheritance_claim,
    resolve_household_succession, create_credit_agreement, make_credit_payment, set_enterprise_partner,
    create_professional_membership, civilian_life_summary,
)
from engine.business import (
    business_catalog, business_ecology_summary, business_profile, configure_enterprise_business,
    resolve_business_cycle, set_commercial_context,
)
from engine.household_life import (
    set_life_profile, create_union, end_union, update_family_plan, register_birth, create_guardianship, end_guardianship,
    split_household, add_service_term, schedule_household_migration, set_demographic_cohort,
    household_life_summary, mark_actor_deceased,
)
from engine.health import (
    ensure_health_profile, configure_health_profile, add_condition, add_treatment, add_disability, resolve_disability,
    set_demographic_mortality, health_summary,
)
from engine.religion import (
    set_affiliation, end_affiliation, configure_religious_institution, add_religious_office, add_observance,
    add_obligation as add_religious_obligation, fulfill_obligation, create_sacred_site, configure_cultural_institution,
    add_cultural_program, add_patronage, religion_summary,
)
from engine.ecology import (
    configure_environment, add_seasonal_window, add_environmental_condition, add_route, add_route_condition,
    start_travel, cancel_travel, register_current_use, ecology_summary, ecology_context,
)
from engine.politics import (
    configure_polity, create_dynasty, add_dynasty_member, set_ruler, add_succession_claim, resolve_succession,
    set_territorial_control, transfer_territory, add_territorial_claim, set_relation, create_political_link,
    end_political_link, add_political_process, dissolve_polity, politics_summary,
)
from engine.education import (
    create_program, create_teaching_relationship, end_teaching_relationship, create_knowledge_asset, add_knowledge_custody,
    grant_knowledge_access, revoke_knowledge_access, link_program_knowledge, create_transmission_line, set_actor_transmission,
    enroll, pause_enrollment, resume_enrollment, withdraw_enrollment, configure_reproduction, set_successor_candidate,
    choose_successor_candidate, education_summary, education_context,
)
from engine.stress import run_horizon, stress_report, contradiction_scan, world_snapshot
from engine.bootstrap import bootstrap_campaign, bootstrap_status, create_player_character
from engine.civilian import (
    add_auction_lot, add_household_member, add_production_site, add_provenance, add_shadow_link,
    civilian_summary, create_auction, create_cultural_object, create_enterprise, create_household, create_project,
    ensure_good, process_due_civilian, resolve_auction, set_auction_interest, set_market_condition,
)
from engine.current_seed import import_current_seed, DEFAULT_CURRENT_SEED, SOURCE_NAMESPACE as CURRENT_SEED_NAMESPACE
from engine.activation import activate_existing_loops
from engine.coverage import start_coverage_run, snapshot_coverage, coverage_gate, ten_year_gate, finish_coverage_run


def _find_actor(conn, name: str):
    row = conn.execute("SELECT * FROM actors WHERE name=?", (name,)).fetchone()
    if row:
        return row
    rows = conn.execute(
        "SELECT * FROM actors WHERE lower(name) LIKE ? ORDER BY length(name),name LIMIT 3",
        (f"%{name.lower()}%",),
    ).fetchall()
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise SystemExit(f"No actor matched: {name}")
    raise SystemExit("Ambiguous actor name. Matches: " + ", ".join(r["name"] for r in rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Caerness Engine v{ENGINE_VERSION}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("seed-demo")
    sub.add_parser("status")
    p_reset = sub.add_parser("reset")
    p_reset.add_argument("--force", action="store_true", help="Required for a non-test campaign database")
    p_reset.add_argument("--no-backup", action="store_true", help="Skip the default safety backup (not recommended)")

    sub.add_parser("migration-status", help="Show schema version, database path, and applied migrations")
    p_cb = sub.add_parser("campaign-bootstrap", help="Seed the legacy production starting world from its versioned manifest")
    p_cb.add_argument("--seed", default=None, help="Optional alternate seed manifest JSON")
    p_ccb = sub.add_parser("current-canon-bootstrap", help="Import the current v1.2 Caerness seed into a clean runtime and activate safe ordinary loops")
    p_ccb.add_argument("--seed", default=str(DEFAULT_CURRENT_SEED), help="Current-canon seed JSON (defaults to packaged v1.1 seed)")
    p_ccb.add_argument("--without-activation", action="store_true", help="Import current canon but do not activate aggregate teaching/commercial contexts")
    sub.add_parser("coverage-status", help="Show the 52-domain current coverage snapshot and decade-run gate")
    sub.add_parser("campaign-status", help="Show campaign bootstrap/player setup status")
    p_pc = sub.add_parser("campaign-player-create", help="Create the player character explicitly after campaign bootstrap")
    p_pc.add_argument("name")
    p_pc.add_argument("--start-location", default="Cairnholt")
    p_pc.add_argument("--age", type=int, default=None)
    p_pc.add_argument("--campaign", default="Caerness Campaign")

    p_hp = sub.add_parser("health-profile-set")
    p_hp.add_argument("actor")
    p_hp.add_argument("--longevity", choices=["ordinary","first","temper","third","breach","fifth","sixth"], default=None)
    p_hp.add_argument("--baseline", type=float, default=None)

    p_hc = sub.add_parser("health-condition-add")
    p_hc.add_argument("actor")
    p_hc.add_argument("kind", choices=["injury","illness","chronic","vein_channel","vein_core","rupture","fatigue","other"])
    p_hc.add_argument("label")
    p_hc.add_argument("--severity", type=float, required=True)
    p_hc.add_argument("--capacity-impact", type=float, default=0)
    p_hc.add_argument("--pain-impact", type=float, default=0)
    p_hc.add_argument("--recovery", type=float, default=0)
    p_hc.add_argument("--progression", type=float, default=0)
    p_hc.add_argument("--fatality", type=float, default=0)
    p_hc.add_argument("--specialist", choices=["none","physician","vein_mender","legendary_vein_mender"], default="none")

    p_ht = sub.add_parser("health-treatment-add")
    p_ht.add_argument("actor")
    p_ht.add_argument("kind", choices=["rest","ordinary_medicine","surgery","rehabilitation","vein_mending","guided_circulation","elixir_stabilization","other"])
    p_ht.add_argument("--condition", type=int, default=None)
    p_ht.add_argument("--provider", default=None)
    p_ht.add_argument("--quality", type=float, default=50)
    p_ht.add_argument("--adherence", type=float, default=70)
    p_ht.add_argument("--end-day", type=int, default=None)

    p_hd = sub.add_parser("health-disability-add")
    p_hd.add_argument("actor")
    p_hd.add_argument("label")
    p_hd.add_argument("--mobility", type=float, default=0)
    p_hd.add_argument("--stamina", type=float, default=0)
    p_hd.add_argument("--capacity", type=float, default=0)
    p_hd.add_argument("--source-condition", type=int, default=None)

    p_hdr = sub.add_parser("health-disability-resolve")
    p_hdr.add_argument("disability_id", type=int)
    p_hdr.add_argument("--reason", default="impairment resolved")

    p_hs = sub.add_parser("health-status")
    p_hs.add_argument("actor", nargs="?", default=None)

    # v0.21 religion and cultural institutions
    p_ra = sub.add_parser("religion-affiliation-set")
    p_ra.add_argument("actor"); p_ra.add_argument("tradition")
    p_ra.add_argument("--kind", default="adherent"); p_ra.add_argument("--practice", type=float, default=50); p_ra.add_argument("--publicness", type=float, default=50)

    p_ri = sub.add_parser("religion-institution-set")
    p_ri.add_argument("institution"); p_ri.add_argument("tradition")
    p_ri.add_argument("--treasury", type=float, default=0); p_ri.add_argument("--charity", type=float, default=10)

    p_ro = sub.add_parser("religion-observance-add")
    p_ro.add_argument("tradition"); p_ro.add_argument("name"); p_ro.add_argument("due_day", type=int)
    p_ro.add_argument("--recurrence", type=int, default=None); p_ro.add_argument("--institution", default=None); p_ro.add_argument("--location", type=int, default=None)

    p_rq = sub.add_parser("religion-obligation-add")
    p_rq.add_argument("actor"); p_rq.add_argument("kind"); p_rq.add_argument("description"); p_rq.add_argument("due_day", type=int)
    p_rq.add_argument("--tradition", default=None); p_rq.add_argument("--recurrence", type=int, default=None)

    p_rf = sub.add_parser("religion-obligation-fulfill"); p_rf.add_argument("obligation_id", type=int)

    p_cp = sub.add_parser("culture-institution-set")
    p_cp.add_argument("institution"); p_cp.add_argument("domain")
    p_cp.add_argument("--resources", type=float, default=0); p_cp.add_argument("--prestige", type=float, default=50)

    p_cpg = sub.add_parser("culture-program-add")
    p_cpg.add_argument("institution"); p_cpg.add_argument("name"); p_cpg.add_argument("kind"); p_cpg.add_argument("due_day", type=int)
    p_cpg.add_argument("--recurrence", type=int, default=None); p_cpg.add_argument("--location", type=int, default=None)

    sub.add_parser("religion-status")

    # v0.22 ecology, seasons, travel and environmental pressure
    p_es = sub.add_parser("environment-set")
    p_es.add_argument("location", type=int)
    p_es.add_argument("--climate", default=None); p_es.add_argument("--terrain", default=None)
    p_es.add_argument("--year-length", type=int, default=360); p_es.add_argument("--travel-factor", type=float, default=1.0)
    p_es.add_argument("--production-factor", type=float, default=1.0); p_es.add_argument("--health-pressure", type=float, default=0.0)
    p_es.add_argument("--current-density", type=float, default=50); p_es.add_argument("--current-replenishment", type=float, default=50)
    p_es.add_argument("--current-capacity", type=float, default=100)

    p_sw = sub.add_parser("season-window-add")
    p_sw.add_argument("location", type=int); p_sw.add_argument("name"); p_sw.add_argument("start", type=int); p_sw.add_argument("end", type=int)
    p_sw.add_argument("--travel-factor", type=float, default=1.0); p_sw.add_argument("--production-factor", type=float, default=1.0)
    p_sw.add_argument("--health-pressure", type=float, default=0.0); p_sw.add_argument("--replenishment-factor", type=float, default=1.0)

    p_er = sub.add_parser("route-add")
    p_er.add_argument("origin", type=int); p_er.add_argument("destination", type=int); p_er.add_argument("days", type=float)
    p_er.add_argument("--kind", default="road"); p_er.add_argument("--one-way", action="store_true")

    p_rc = sub.add_parser("route-condition-add")
    p_rc.add_argument("route_id", type=int); p_rc.add_argument("kind"); p_rc.add_argument("label"); p_rc.add_argument("start", type=int)
    p_rc.add_argument("--end", type=int, default=None); p_rc.add_argument("--accessibility", type=float, default=100)
    p_rc.add_argument("--delay-factor", type=float, default=1.0); p_rc.add_argument("--hazard", type=float, default=0.0)

    p_ts = sub.add_parser("travel-start")
    p_ts.add_argument("subject_kind", choices=["actor","household"]); p_ts.add_argument("subject_id", type=int); p_ts.add_argument("destination", type=int)
    p_tc = sub.add_parser("travel-cancel"); p_tc.add_argument("plan_id", type=int)

    p_cu = sub.add_parser("current-use")
    p_cu.add_argument("location", type=int); p_cu.add_argument("amount", type=float); p_cu.add_argument("--description", default=None)
    p_ec = sub.add_parser("ecology-status"); p_ec.add_argument("location", nargs="?", type=int, default=None)

    # v0.23 politics, state transformation, and macro-history
    p_ps = sub.add_parser("polity-set")
    p_ps.add_argument("institution"); p_ps.add_argument("kind"); p_ps.add_argument("--ruler", default=None)
    p_ps.add_argument("--succession", choices=["designated","hereditary","elective","appointment","custom","unsettled"], default="custom")
    p_ps.add_argument("--legitimacy", type=float, default=50); p_ps.add_argument("--stability", type=float, default=50)
    p_tc2 = sub.add_parser("territory-set")
    p_tc2.add_argument("polity_id", type=int); p_tc2.add_argument("location_id", type=int); p_tc2.add_argument("--kind", default="direct")
    p_cl = sub.add_parser("political-claim-add")
    p_cl.add_argument("polity_id", type=int); p_cl.add_argument("location_id", type=int); p_cl.add_argument("--pressure", type=float, default=0)
    p_cl.add_argument("--rate", type=float, default=0); p_cl.add_argument("--threshold", type=float, default=75); p_cl.add_argument("--policy", choices=["none","dispute","recognize","transfer"], default="dispute")
    p_scl = sub.add_parser("succession-claim-add")
    p_scl.add_argument("polity_id", type=int); p_scl.add_argument("actor"); p_scl.add_argument("--legitimacy", type=float, default=50); p_scl.add_argument("--support", type=float, default=0); p_scl.add_argument("--priority", type=float, default=50)
    p_sres = sub.add_parser("polity-succession-resolve"); p_sres.add_argument("polity_id", type=int); p_sres.add_argument("--actor", default=None)
    p_pl = sub.add_parser("political-link-add")
    p_pl.add_argument("senior", type=int); p_pl.add_argument("junior", type=int); p_pl.add_argument("kind", choices=["vassalage","protectorate","federation","personal_union","tributary"]); p_pl.add_argument("--autonomy", type=float, default=50)
    sub.add_parser("politics-status")

    # v0.24 education, transmission, and institutional reproduction
    p_ep = sub.add_parser("education-program-add")
    p_ep.add_argument("key"); p_ep.add_argument("name"); p_ep.add_argument("domain"); p_ep.add_argument("kind")
    p_ep.add_argument("--institution", default=None); p_ep.add_argument("--duration", type=int, default=365); p_ep.add_argument("--capacity", type=int, default=10)
    p_ep.add_argument("--min-entry", type=float, default=0); p_ep.add_argument("--min-teacher", type=float, default=0); p_ep.add_argument("--gain", type=float, default=5); p_ep.add_argument("--max-score", type=float, default=70)
    p_ep.add_argument("--certificate", default=None); p_ep.add_argument("--lineage", default=None); p_ep.add_argument("--review-days", type=int, default=30)

    p_tr = sub.add_parser("teaching-link-add")
    p_tr.add_argument("teacher"); p_tr.add_argument("student"); p_tr.add_argument("kind"); p_tr.add_argument("domain"); p_tr.add_argument("--institution", default=None); p_tr.add_argument("--responsibility", type=float, default=50)
    p_te = sub.add_parser("teaching-link-end"); p_te.add_argument("relationship_id", type=int); p_te.add_argument("--status", default="ended", choices=["ended","interrupted","repudiated"])

    p_ka = sub.add_parser("knowledge-asset-add")
    p_ka.add_argument("title"); p_ka.add_argument("kind"); p_ka.add_argument("domain"); p_ka.add_argument("--institution", default=None); p_ka.add_argument("--lineage", default=None)
    p_ka.add_argument("--access-tier", default="limited"); p_ka.add_argument("--preservation", default="documented"); p_ka.add_argument("--loss-days", type=int, default=None)
    p_kc = sub.add_parser("knowledge-custody-add"); p_kc.add_argument("asset_id", type=int); p_kc.add_argument("kind"); p_kc.add_argument("--actor", default=None); p_kc.add_argument("--institution", default=None)
    p_kag = sub.add_parser("knowledge-access-grant"); p_kag.add_argument("asset_id", type=int); p_kag.add_argument("actor"); p_kag.add_argument("--level", default="study")
    p_kar = sub.add_parser("knowledge-access-revoke"); p_kar.add_argument("asset_id", type=int); p_kar.add_argument("actor")
    p_pka = sub.add_parser("program-knowledge-link"); p_pka.add_argument("program_id", type=int); p_pka.add_argument("asset_id", type=int); p_pka.add_argument("--requirement", default="supporting", choices=["supporting","required_access","required_teacher_access"])

    p_tl = sub.add_parser("transmission-line-add")
    p_tl.add_argument("lineage_key"); p_tl.add_argument("name"); p_tl.add_argument("domain"); p_tl.add_argument("--institution", default=None); p_tl.add_argument("--founder", default=None); p_tl.add_argument("--vitality", type=float, default=70); p_tl.add_argument("--fragility", type=float, default=8)
    p_at = sub.add_parser("transmission-member-set"); p_at.add_argument("line_id", type=int); p_at.add_argument("actor"); p_at.add_argument("relation", choices=["student","teacher","inheritor","keeper","former"]); p_at.add_argument("--depth", type=float, default=0)

    p_en = sub.add_parser("education-enroll"); p_en.add_argument("actor"); p_en.add_argument("program_id", type=int); p_en.add_argument("--teacher", default=None); p_en.add_argument("--quality", type=float, default=1.0)
    p_epa = sub.add_parser("education-pause"); p_epa.add_argument("enrollment_id", type=int); p_epa.add_argument("reason")
    p_er = sub.add_parser("education-resume"); p_er.add_argument("enrollment_id", type=int); p_er.add_argument("--teacher", default=None)
    p_ew = sub.add_parser("education-withdraw"); p_ew.add_argument("enrollment_id", type=int); p_ew.add_argument("--reason", default=None)

    p_ir = sub.add_parser("institution-reproduction-set"); p_ir.add_argument("institution"); p_ir.add_argument("--recruitment", type=float, default=50); p_ir.add_argument("--training", type=float, default=50); p_ir.add_argument("--instructors", type=float, default=50); p_ir.add_argument("--archives", type=float, default=50); p_ir.add_argument("--review-days", type=int, default=90)
    p_isc = sub.add_parser("institution-successor-candidate"); p_isc.add_argument("institution"); p_isc.add_argument("actor"); p_isc.add_argument("role"); p_isc.add_argument("--readiness", type=float, default=0); p_isc.add_argument("--legitimacy", type=float, default=50); p_isc.add_argument("--transmission-depth", type=float, default=0)
    p_isch = sub.add_parser("institution-successor-choose"); p_isch.add_argument("candidate_id", type=int)
    p_es = sub.add_parser("education-show"); p_es.add_argument("actor", nargs="?", default=None)
    sub.add_parser("education-status")

    # v0.25 long-run stress and camera continuity
    p_csuc = sub.add_parser("camera-successor-set")
    p_csuc.add_argument("from_actor"); p_csuc.add_argument("successor"); p_csuc.add_argument("--priority", type=int, default=50); p_csuc.add_argument("--notes", default=None)
    sub.add_parser("camera-history")
    p_sr = sub.add_parser("stress-run")
    p_sr.add_argument("years", type=float); p_sr.add_argument("--label", default="manual long-run stress"); p_sr.add_argument("--scenario", default="manual"); p_sr.add_argument("--checkpoint-years", type=float, default=5.0)
    p_ss = sub.add_parser("stress-status"); p_ss.add_argument("run_id", nargs="?", type=int, default=None)
    sub.add_parser("stress-scan")

    p_adv = sub.add_parser("advance")
    p_adv.add_argument("days", type=int)

    p_events = sub.add_parser("events")
    p_events.add_argument("limit", nargs="?", type=int, default=20)

    p_ci = sub.add_parser("canon-index")
    p_ci.add_argument("path", nargs="?", default=str(DEFAULT_CANON))
    p_ci.add_argument("--force", action="store_true")

    p_cs = sub.add_parser("canon-search")
    p_cs.add_argument("query")
    p_cs.add_argument("--limit", type=int, default=6)

    sub.add_parser("canon-status")

    p_ctx = sub.add_parser("actor-context")
    p_ctx.add_argument("actor")
    p_ctx.add_argument("--canon-limit", type=int, default=5)

    p_decide = sub.add_parser("decide-now")
    p_decide.add_argument("actor")

    p_decisions = sub.add_parser("decisions")
    p_decisions.add_argument("limit", nargs="?", type=int, default=20)

    p_interactions = sub.add_parser("interactions")
    p_interactions.add_argument("limit", nargs="?", type=int, default=20)

    p_interaction = sub.add_parser("interaction")
    p_interaction.add_argument("interaction_id", type=int)

    p_propose = sub.add_parser("propose")
    p_propose.add_argument("proposer")
    p_propose.add_argument("recipient")
    p_propose.add_argument("interaction_type", choices=[
        "conversation", "offer", "request", "contract", "alliance", "negotiation", "mediation",
        "demand", "threat", "investigation", "attack"
    ])
    p_propose.add_argument("--purpose", default="")
    p_propose.add_argument("--urgency", type=int, default=2)
    p_propose.add_argument("--stakes", type=int, default=2)

    sub.add_parser("agreements")

    p_causes = sub.add_parser("causes")
    p_causes.add_argument("kind", choices=["decision", "interaction", "event", "clock", "agreement"] )
    p_causes.add_argument("object_id", type=int)

    p_player = sub.add_parser("player-set")
    p_player.add_argument("actor")
    p_player.add_argument("--campaign", default="Campaign 01")

    p_scene = sub.add_parser("scene")
    p_scene.add_argument("request", nargs="*", default=[])
    p_scene.add_argument("--json", action="store_true", dest="as_json")
    p_scene.add_argument("--canon-limit", type=int, default=6)

    p_play = sub.add_parser("play")
    p_play.add_argument("action", nargs="+", help="Freeform player action")
    p_play.add_argument("--json", action="store_true", dest="as_json")
    p_play.add_argument("--canon-limit", type=int, default=6)

    p_bridge = sub.add_parser("bridge-play", help="Play using a manual ChatGPT/Claude bridge without an API")
    p_bridge.add_argument("action", nargs="+", help="Freeform player action")
    p_bridge.add_argument("--provider", choices=["chatgpt","claude","local"], default=None)

    p_mcfg = sub.add_parser("model-config")
    p_mcfg.add_argument("--action", choices=["rules","local","manual_chatgpt","manual_claude"], default=None)
    p_mcfg.add_argument("--decision", choices=["rules","local","manual_chatgpt","manual_claude"], default=None)
    p_mcfg.add_argument("--narrator", choices=["rules","local","manual_chatgpt","manual_claude"], default=None)
    p_mcfg.add_argument("--packet-dir", default=None)

    sub.add_parser("model-status")

    p_mpending = sub.add_parser("model-pending")
    p_mpending.add_argument("limit", nargs="?", type=int, default=20)

    p_mshow = sub.add_parser("model-show")
    p_mshow.add_argument("request_id", type=int)

    p_mexport = sub.add_parser("model-export")
    p_mexport.add_argument("request_id", type=int)
    p_mexport.add_argument("--provider", choices=["chatgpt","claude","generic"], default=None)
    p_mexport.add_argument("--path", default=None)

    p_mimport = sub.add_parser("model-import")
    p_mimport.add_argument("request_id", type=int)
    p_mimport.add_argument("response_file")

    p_mapply = sub.add_parser("model-apply")
    p_mapply.add_argument("request_id", type=int)

    p_mdecide = sub.add_parser("model-decide", help="Queue one major NPC decision for ChatGPT or Claude")
    p_mdecide.add_argument("actor")
    p_mdecide.add_argument("--provider", choices=["chatgpt","claude"], default=None)
    p_mdecide.add_argument("--canon-limit", type=int, default=6)

    p_route = sub.add_parser("model-route", help="Score a model request for local vs ChatGPT/Claude")
    p_route.add_argument("request_id", type=int)

    p_localrun = sub.add_parser("model-run-local", help="Run a queued request on the configured phone-local model")
    p_localrun.add_argument("request_id", type=int)
    p_localrun.add_argument("--force", action="store_true")
    p_localrun.add_argument("--apply", action="store_true")

    sub.add_parser("local-health")
    sub.add_parser("runtime-status")
    p_runtime = sub.add_parser("runtime-config")
    p_runtime.add_argument("--backend", choices=["openai_compatible","ollama_native","disabled"], default=None)
    p_runtime.add_argument("--endpoint", default=None)
    p_runtime.add_argument("--model", default=None)
    p_runtime.add_argument("--context", type=int, default=None)
    p_runtime.add_argument("--heavy-context", type=int, default=None)
    p_runtime.add_argument("--output", type=int, default=None)
    p_runtime.add_argument("--referral", choices=["rare","balanced","quality_first"], default=None)

    p_serve = sub.add_parser("serve", help="Start the phone-first local web UI")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)

    p_backup = sub.add_parser("backup")
    p_backup.add_argument("--label", default="manual")
    p_restore = sub.add_parser("restore")
    p_restore.add_argument("path")

    sub.add_parser("matters")
    sub.add_parser("attention")
    sub.add_parser("worldbook")
    p_mem = sub.add_parser("memories")
    p_mem.add_argument("actor")
    p_mem.add_argument("--limit", type=int, default=20)
    p_eth = sub.add_parser("emergent-threads")
    p_eth.add_argument("--limit", type=int, default=20)
    sub.add_parser("interrupt")

    p_pos = sub.add_parser("possession-add")
    p_pos.add_argument("actor")
    p_pos.add_argument("name")
    p_pos.add_argument("--type", default="item", dest="item_type")
    p_int = sub.add_parser("intention-add")
    p_int.add_argument("actor")
    p_int.add_argument("description")
    p_int.add_argument("--target-actor", default=None)
    p_int.add_argument("--target-location", default=None)
    p_int.add_argument("--possession-id", type=int, default=None)
    p_int.add_argument("--kind", default="follow_through")
    p_int.add_argument("--trigger", choices=["manual","actor_present","location_present","due_day","on_departure","on_arrival"], default="manual")
    p_int.add_argument("--policy", choices=["routine","remind","ask_if_changed","manual"], default="routine")
    p_int.add_argument("--due-day", type=int, default=None)
    p_ob = sub.add_parser("obligation-add")
    p_ob.add_argument("actor")
    p_ob.add_argument("description")
    p_ob.add_argument("--counterparty", default=None)
    p_ob.add_argument("--due-day", type=int, default=None)
    p_ob.add_argument("--importance", type=int, default=2)
    p_ob.add_argument("--intention-id", type=int, default=None)

    p_turns = sub.add_parser("turns")
    p_turns.add_argument("limit", nargs="?", type=int, default=20)

    p_journal = sub.add_parser("export-journal")
    p_journal.add_argument("path", nargs="?", default="game/campaign_01/journal.md")

    p_pulse = sub.add_parser("world-pulse")
    p_pulse.add_argument("--since", type=int, default=0)

    p_knowledge = sub.add_parser("knowledge")
    p_knowledge.add_argument("actor")
    p_knowledge.add_argument("--limit", type=int, default=30)

    p_rumours = sub.add_parser("rumours")
    p_rumours.add_argument("limit", nargs="?", type=int, default=20)

    p_event_info = sub.add_parser("event-info")
    p_event_info.add_argument("event_id", type=int)

    p_demo_event = sub.add_parser("demo-event")
    p_demo_event.add_argument("title")
    p_demo_event.add_argument("summary")
    p_demo_event.add_argument("--actor", default="")
    p_demo_event.add_argument("--location", default="")
    p_demo_event.add_argument("--visibility", choices=["public","limited","private","secret"], default="public")
    p_demo_event.add_argument("--severity", type=int, default=3)
    p_demo_event.add_argument("--rumorability", type=float, default=0.7)


    p_eshow = sub.add_parser("embodiment-show", help="Show a character's persistent embodiment model")
    p_eshow.add_argument("actor")
    p_eset = sub.add_parser("embodiment-set", help="Merge a JSON patch into a character embodiment model")
    p_eset.add_argument("actor")
    p_eset.add_argument("patch_file")
    p_eset.add_argument("--source", choices=["campaign","canon","crystallization","admin","generated"], default="admin")
    p_speech = sub.add_parser("speech-mediate", help="Prepare character-voiced speech from intent/guided/exact player wording")
    p_speech.add_argument("actor")
    p_speech.add_argument("text")
    p_speech.add_argument("--mode", choices=["intent","guided","exact"], default="intent")
    p_speech.add_argument("--audience", default=None)
    p_speech.add_argument("--tone", default=None)
    p_speech.add_argument("--objective", default=None)
    p_speech.add_argument("--commitment", default=None)
    p_aut = sub.add_parser("autonomy-check", help="Check whether protagonist behavior may be inferred without stealing agency")
    p_aut.add_argument("actor")
    p_aut.add_argument("expression_kind")
    p_aut.add_argument("--confidence", type=float, default=0.85)
    p_aut.add_argument("--stakes", type=int, default=1)
    p_aut.add_argument("--irreversible", action="store_true")
    p_aut.add_argument("--commitment", default=None)
    p_expr = sub.add_parser("expression-record", help="Audit one inferred protagonist expression through the commitment firewall")
    p_expr.add_argument("actor")
    p_expr.add_argument("summary")
    p_expr.add_argument("--kind", default="gesture")
    p_expr.add_argument("--confidence", type=float, default=0.85)
    p_expr.add_argument("--stakes", type=int, default=1)
    p_expr.add_argument("--irreversible", action="store_true")
    p_expr.add_argument("--commitment", default=None)
    p_expr.add_argument("--related-actor", default=None)
    p_srecent = sub.add_parser("speech-history", help="Show recent speech mediation packets")
    p_srecent.add_argument("actor")
    p_srecent.add_argument("--limit", type=int, default=10)

    p_cset = sub.add_parser("competence-set", help="Set one domain-specific character competence")
    p_cset.add_argument("actor")
    p_cset.add_argument("domain")
    p_cset.add_argument("score", type=float)
    p_cset.add_argument("--specialty", default=None)
    p_cset.add_argument("--source", choices=["canon","campaign","career","crystallization","admin","generated"], default="admin")
    p_cprof = sub.add_parser("competence-show", help="Show an actor's domain competence profile")
    p_cprof.add_argument("actor")
    p_cread = sub.add_parser("professional-read", help="Prepare a professional interpretation packet from accessible evidence")
    p_cread.add_argument("actor")
    p_cread.add_argument("domain")
    p_cread.add_argument("situation")
    p_cread.add_argument("--specialty", default=None)
    p_cread.add_argument("--stakes", type=int, default=2)
    p_cread.add_argument("--uncertainty", type=float, default=0.3)
    p_cresolve = sub.add_parser("professional-resolve", help="Record a grounded professional reading result")
    p_cresolve.add_argument("reading_id", type=int)
    p_cresolve.add_argument("summary")
    p_cresolve.add_argument("--confidence", type=float, default=None)
    p_cresolve.add_argument("--provider", default="rules")
    p_cshow = sub.add_parser("professional-show", help="Show one professional reading")
    p_cshow.add_argument("reading_id", type=int)
    p_adv = sub.add_parser("advisor-judgment", help="Record one communicated advisor judgment separately from character expertise")
    p_adv.add_argument("recipient")
    p_adv.add_argument("advisor")
    p_adv.add_argument("domain")
    p_adv.add_argument("situation_key")
    p_adv.add_argument("judgment")
    p_adv.add_argument("--confidence", type=float, default=0.6)
    p_adv.add_argument("--private", action="store_true", help="Record as not communicated to the recipient")
    p_dctx = sub.add_parser("decision-context", help="Show separated character reading and advisor judgments")
    p_dctx.add_argument("actor")
    p_dctx.add_argument("domain")
    p_dctx.add_argument("situation_key")
    p_dctx.add_argument("--reading-id", type=int, default=None)

    p_tsp = sub.add_parser("timeskip-prepare", help="Prepare a compressed in-world time skip")
    p_tsp.add_argument("actor")
    p_tsp.add_argument("days", type=int)
    p_tsp.add_argument("--focus", action="append", default=[], help="Focus key or domain; repeatable")
    p_tsp.add_argument("--policy", choices=["all","meaningful","critical_only"], default="meaningful")
    p_tsp.add_argument("--chunk", type=int, default=30)
    p_tsp.add_argument("--delegation-file", default=None)
    p_tsr = sub.add_parser("timeskip-resolve", help="Run a prepared time skip until completion or meaningful interruption")
    p_tsr.add_argument("run_id", type=int)
    p_tss = sub.add_parser("timeskip-show", help="Inspect one time-skip run")
    p_tss.add_argument("run_id", type=int)

    p_bc = sub.add_parser("battle-create", help="Create an abstract battle engagement")
    p_bc.add_argument("title")
    p_bc.add_argument("--player", default=None)
    p_bc.add_argument("--objective", default=None)
    p_bc.add_argument("--stakes", type=int, default=3)
    p_bs = sub.add_parser("battle-side-add", help="Add a side to a battle")
    p_bs.add_argument("engagement_id", type=int)
    p_bs.add_argument("name")
    p_bs.add_argument("--controller", default=None)
    p_bs.add_argument("--objective", default=None)
    p_bs.add_argument("--posture", choices=["cautious","balanced","assertive"], default="balanced")
    p_bu = sub.add_parser("battle-unit-add", help="Add an abstract unit to a battle side")
    p_bu.add_argument("side_id", type=int)
    p_bu.add_argument("name")
    p_bu.add_argument("--commander", default=None)
    p_bu.add_argument("--role", choices=["line","support","reserve","specialist","command"], default="line")
    p_bi = sub.add_parser("battle-intent", help="Submit a high-level battle intent")
    p_bi.add_argument("engagement_id", type=int)
    p_bi.add_argument("actor")
    p_bi.add_argument("intent", choices=["hold","probe","press","reposition","reinforce","commit_reserve","recover","disengage"])
    p_bi.add_argument("--risk", choices=["low","balanced","high"], default="balanced")
    p_bi.add_argument("--commitment", type=float, default=0.5)
    p_bi.add_argument("--objective", default=None)
    p_br = sub.add_parser("battle-resolve", help="Resolve the next abstract battle round")
    p_br.add_argument("engagement_id", type=int)
    p_bv = sub.add_parser("battle-view", help="Show a rank-sensitive battle view for one actor")
    p_bv.add_argument("engagement_id", type=int)
    p_bv.add_argument("actor")

    p_bz = sub.add_parser("battle-zone-add", help="Add a persistent battlefield zone/front")
    p_bz.add_argument("engagement_id", type=int)
    p_bz.add_argument("name")
    p_bz.add_argument("--importance", type=float, default=50)
    p_bz.add_argument("--terrain", default=None)
    p_bz.add_argument("--objective", default=None)
    p_buz = sub.add_parser("battle-unit-zone", help="Assign a battle unit to a battlefield zone")
    p_buz.add_argument("unit_id", type=int)
    p_buz.add_argument("zone_id", type=int)
    p_buz.add_argument("--kind", choices=["primary","support","reserve"], default="primary")
    p_bcl = sub.add_parser("battle-command-link", help="Persist a senior/junior command relationship")
    p_bcl.add_argument("engagement_id", type=int)
    p_bcl.add_argument("side_id", type=int)
    p_bcl.add_argument("--senior", default=None)
    p_bcl.add_argument("--junior-unit", type=int, required=True)
    p_bcl.add_argument("--communication", type=float, default=70)
    p_bcl.add_argument("--discretion", type=float, default=50)
    p_bcl.add_argument("--trust", type=float, default=50)
    p_bo = sub.add_parser("battle-order", help="Issue a delayed high-level order to a subordinate unit")
    p_bo.add_argument("engagement_id", type=int)
    p_bo.add_argument("side_id", type=int)
    p_bo.add_argument("directive", choices=["hold","probe","press","support","reposition","recover","commit","disengage"])
    p_bo.add_argument("--issuer", default=None)
    p_bo.add_argument("--unit", type=int, required=True)
    p_bo.add_argument("--zone", type=int, default=None)
    p_bo.add_argument("--objective", default=None)
    p_bo.add_argument("--priority", type=int, choices=[1,2,3], default=2)
    p_bcp = sub.add_parser("battle-command-profile", help="Set abstract command strengths for an actor")
    p_bcp.add_argument("actor")
    p_bcp.add_argument("--planning", type=float, default=50)
    p_bcp.add_argument("--adaptation", type=float, default=50)
    p_bcp.add_argument("--presence", type=float, default=50)
    p_bcp.add_argument("--delegation", type=float, default=50)
    p_bcp.add_argument("--nerve", type=float, default=50)

    p_bd = sub.add_parser("battle-doctrine-set", help="Set abstract tactical-family preferences for a commander")
    p_bd.add_argument("actor")
    for _k in ["pressure","fixing","misdirection","isolation","depth","reserve_play","mobility","attrition","disruption","exploitation"]:
        p_bd.add_argument(f"--{_k.replace('_','-')}", dest=_k, type=float, default=50)
    p_bt = sub.add_parser("battle-tactic", help="Submit one abstract tactical family for the next battle round")
    p_bt.add_argument("engagement_id", type=int)
    p_bt.add_argument("side_id", type=int)
    p_bt.add_argument("family", choices=["pressure","fixing","misdirection","isolation","depth","reserve_play","mobility","attrition","disruption","exploitation"])
    p_bt.add_argument("--actor", default=None)
    p_bt.add_argument("--zone", type=int, default=None)
    p_bt.add_argument("--commitment", type=float, default=0.5)
    p_bvc = sub.add_parser("battle-zone-current", help="Set abstract local current conditions for a battle zone")
    p_bvc.add_argument("zone_id", type=int)
    p_bvc.add_argument("--density", type=float, default=50)
    p_bvc.add_argument("--stability", type=float, default=50)
    p_bvc.add_argument("--replenishment", type=float, default=50)
    p_bva = sub.add_parser("battle-vein-add", help="Add a Vein-bearing strategic asset to a battle")
    p_bva.add_argument("engagement_id", type=int)
    p_bva.add_argument("side_id", type=int)
    p_bva.add_argument("stage", choices=["First","Temper","Third","Breach","Fifth","Sixth"])
    p_bva.add_argument("--actor", default=None)
    p_bva.add_argument("--zone", type=int, default=None)
    p_bva.add_argument("--role", choices=["anchor","reserve","screen","support","hunter","flexible"], default="flexible")
    p_bva.add_argument("--commitment", type=float, default=0.5)

    p_dc = sub.add_parser("duel-create", help="Create an abstract duel")
    p_dc.add_argument("title")
    p_dc.add_argument("actor_a")
    p_dc.add_argument("actor_b")
    p_dc.add_argument("--player", default=None)
    p_dc.add_argument("--objective", default=None)
    p_dc.add_argument("--stakes", type=int, default=3)
    p_di = sub.add_parser("duel-intent", help="Submit a high-level duel intent")
    p_di.add_argument("engagement_id", type=int)
    p_di.add_argument("actor")
    p_di.add_argument("intent", choices=["measure","press","defend","conserve","commit","control","disengage"])
    p_di.add_argument("--risk", choices=["low","balanced","high"], default="balanced")
    p_di.add_argument("--reserve", type=float, default=0.25)
    p_di.add_argument("--objective", default=None)
    p_dr = sub.add_parser("duel-resolve", help="Resolve the next abstract duel exchange")
    p_dr.add_argument("engagement_id", type=int)
    p_dv = sub.add_parser("duel-view", help="Show a character-relative duel view")
    p_dv.add_argument("engagement_id", type=int)
    p_dv.add_argument("actor")
    p_dlb = sub.add_parser("duel-link-battle", help="Link a duel to battle assets so its result can feed battlefield consequence automatically")
    p_dlb.add_argument("duel_engagement_id", type=int)
    p_dlb.add_argument("battle_engagement_id", type=int)
    p_dlb.add_argument("zone_id", type=int)
    p_dlb.add_argument("actor_a_asset_id", type=int)
    p_dlb.add_argument("actor_b_asset_id", type=int)
    p_cs = sub.add_parser("combat-show", help="Inspect authoritative combat state")
    p_cs.add_argument("engagement_id", type=int)

    p_cp = sub.add_parser("crystallize-prepare", help="Prepare a constrained historical crystallization context")
    p_cp.add_argument("latent_id", type=int)
    p_cp.add_argument("--depth", choices=["shallow","developed","deep"], default="shallow")
    p_ce = sub.add_parser("crystallize-export", help="Export a model/manual proposal packet for a prepared crystallization")
    p_ce.add_argument("run_id", type=int)
    p_ce.add_argument("--path", default=None)
    p_cv = sub.add_parser("crystallize-validate", help="Validate a JSON biography proposal without mutating campaign history")
    p_cv.add_argument("run_id", type=int)
    p_cv.add_argument("proposal_file")
    p_cv.add_argument("--non-strict", action="store_true")
    p_ca = sub.add_parser("crystallize-apply", help="Commit a previously validated crystallization")
    p_ca.add_argument("run_id", type=int)
    p_cshow = sub.add_parser("crystallize-show")
    p_cshow.add_argument("run_id", type=int)

    # v0.16 civilian simulation commands
    sub.add_parser("civilian-status")

    p_hh = sub.add_parser("household-create")
    p_hh.add_argument("name")
    p_hh.add_argument("--head")
    p_hh.add_argument("--location", type=int)
    p_hh.add_argument("--wealth", type=float, default=0)
    p_hh.add_argument("--liquidity", type=float, default=0)

    p_ent = sub.add_parser("enterprise-create")
    p_ent.add_argument("name")
    p_ent.add_argument("kind", choices=["merchant_house","workshop","estate","shop","studio","shipping","construction","service","other"])
    p_ent.add_argument("--owner")
    p_ent.add_argument("--location", type=int)
    p_ent.add_argument("--cash", type=float, default=0)
    p_ent.add_argument("--capital", type=float, default=0)
    p_ent.add_argument("--debt", type=float, default=0)

    p_good = sub.add_parser("market-good")
    p_good.add_argument("key")
    p_good.add_argument("name")
    p_good.add_argument("category")
    p_good.add_argument("base_price", type=float)
    p_good.add_argument("--unit", default="unit")
    p_good.add_argument("--luxury", type=float, default=0)

    p_market = sub.add_parser("market-set")
    p_market.add_argument("location_id", type=int)
    p_market.add_argument("good_id", type=int)
    p_market.add_argument("--supply", type=float, default=50)
    p_market.add_argument("--demand", type=float, default=50)
    p_market.add_argument("--transport", type=float, default=0)
    p_market.add_argument("--risk", type=float, default=0)
    p_market.add_argument("--tax", type=float, default=0)

    p_prod = sub.add_parser("production-add")
    p_prod.add_argument("enterprise_id", type=int)
    p_prod.add_argument("good_id", type=int)
    p_prod.add_argument("--capacity", type=float, default=10)
    p_prod.add_argument("--efficiency", type=float, default=50)
    p_prod.add_argument("--materials", type=float, default=50)
    p_prod.add_argument("--skill", type=float, default=50)

    p_proj = sub.add_parser("project-create")
    p_proj.add_argument("title")
    p_proj.add_argument("kind", choices=["architecture","artwork","textile","manuscript","craft","public_work","household","business"])
    p_proj.add_argument("--patron")
    p_proj.add_argument("--creator")
    p_proj.add_argument("--enterprise", type=int)
    p_proj.add_argument("--location", type=int)
    p_proj.add_argument("--target-day", type=int)
    p_proj.add_argument("--quality", type=float, default=50)

    p_obj = sub.add_parser("object-create")
    p_obj.add_argument("title")
    p_obj.add_argument("kind", choices=["painting","sculpture","textile","garment","manuscript","book","jewelry","furniture","instrument","weapon","armor","architectural_element","other"])
    p_obj.add_argument("--creator")
    p_obj.add_argument("--owner")
    p_obj.add_argument("--location", type=int)
    p_obj.add_argument("--quality", type=float, default=50)
    p_obj.add_argument("--value", type=float, default=0)

    p_auc = sub.add_parser("auction-create")
    p_auc.add_argument("title")
    p_auc.add_argument("scheduled_day", type=int)
    p_auc.add_argument("--location", type=int)
    p_auc.add_argument("--institution")

    p_lot = sub.add_parser("auction-lot")
    p_lot.add_argument("auction_id", type=int)
    p_lot.add_argument("object_id", type=int)
    p_lot.add_argument("--seller")
    p_lot.add_argument("--reserve", type=float, default=0)
    p_lot.add_argument("--low", type=float, default=0)
    p_lot.add_argument("--high", type=float, default=0)

    p_interest = sub.add_parser("auction-interest")
    p_interest.add_argument("lot_id", type=int)
    p_interest.add_argument("actor")
    p_interest.add_argument("budget", type=float)
    p_interest.add_argument("--interest", type=float, default=50)
    p_interest.add_argument("--taste", type=float, default=50)
    p_interest.add_argument("--status-motive", type=float, default=0)

    p_ares = sub.add_parser("auction-resolve")
    p_ares.add_argument("auction_id", type=int)

    # v0.17 deeper civilian-life commands
    p_bld = sub.add_parser("building-create")
    p_bld.add_argument("name")
    p_bld.add_argument("kind", choices=["residence","workshop","shop","warehouse","hall","temple","fortified_residence","public_building","bridge","garden","estate_improvement","other"])
    p_bld.add_argument("--location", type=int)
    p_bld.add_argument("--owner")
    p_bld.add_argument("--household", type=int)
    p_bld.add_argument("--institution")
    p_bld.add_argument("--style")
    p_bld.add_argument("--prestige", type=float, default=50)
    p_bld.add_argument("--utility", type=float, default=50)
    p_bld.add_argument("--maintenance", type=float, default=10)

    p_style = sub.add_parser("style-create")
    p_style.add_argument("key")
    p_style.add_argument("name")
    p_style.add_argument("domain", choices=["dress","textile","architecture","interior","book","decorative"])
    p_style.add_argument("--origin-location", type=int)
    p_style.add_argument("--origin-actor")
    p_style.add_argument("--prestige", type=float, default=50)
    p_style.add_argument("--novelty", type=float, default=50)
    p_style.add_argument("--accessibility", type=float, default=50)
    p_style.add_argument("--durability", type=float, default=50)

    p_sa = sub.add_parser("style-adoption-set")
    p_sa.add_argument("style_id", type=int)
    p_sa.add_argument("location_id", type=int)
    p_sa.add_argument("--adoption", type=float, default=0)
    p_sa.add_argument("--elite-support", type=float, default=0)
    p_sa.add_argument("--craft-capacity", type=float, default=50)
    p_sa.add_argument("--resistance", type=float, default=20)

    p_sp = sub.add_parser("succession-plan")
    p_sp.add_argument("household_id", type=int)
    p_sp.add_argument("--heir")
    p_sp.add_argument("--method", choices=["designated","seniority","primogeniture","election","appointment","custom","unsettled"], default="designated")
    p_sp.add_argument("--certainty", type=float, default=50)
    p_sp.add_argument("--dispute", type=float, default=0)

    p_sc = sub.add_parser("succession-claim")
    p_sc.add_argument("household_id", type=int)
    p_sc.add_argument("actor")
    p_sc.add_argument("--priority", type=float, default=50)
    p_sc.add_argument("--legitimacy", type=float, default=50)
    p_sc.add_argument("--support", type=float, default=0)

    p_sr = sub.add_parser("succession-resolve")
    p_sr.add_argument("household_id", type=int)
    p_sr.add_argument("--head")

    p_credit = sub.add_parser("credit-create")
    p_credit.add_argument("principal", type=float)
    p_credit.add_argument("--lender")
    p_credit.add_argument("--lender-enterprise", type=int)
    p_credit.add_argument("--borrower")
    p_credit.add_argument("--borrower-enterprise", type=int)
    p_credit.add_argument("--interest", type=float, default=0)
    p_credit.add_argument("--due-day", type=int)
    p_credit.add_argument("--risk", type=float, default=20)

    p_pay = sub.add_parser("credit-pay")
    p_pay.add_argument("agreement_id", type=int)
    p_pay.add_argument("amount", type=float)

    p_partner = sub.add_parser("enterprise-partner")
    p_partner.add_argument("enterprise_id", type=int)
    p_partner.add_argument("actor")
    p_partner.add_argument("--share", type=float, default=0)
    p_partner.add_argument("--governance", type=float, default=0)
    p_partner.add_argument("--capital", type=float, default=0)
    p_partner.add_argument("--role", default="partner")

    p_pm = sub.add_parser("professional-member")
    p_pm.add_argument("actor")
    p_pm.add_argument("institution")
    p_pm.add_argument("domain")
    p_pm.add_argument("--role", default="member")
    p_pm.add_argument("--standing", type=float, default=50)
    p_pm.add_argument("--influence", type=float, default=10)
    p_pm.add_argument("--dues", type=float, default=0)

    # v0.18 differentiated business ecology
    sub.add_parser("business-archetypes", help="List configured engine business archetypes")

    p_bc = sub.add_parser("commercial-context-set", help="Set the local commercial environment used by differentiated businesses")
    p_bc.add_argument("location_id", type=int)
    for field in ["foot_traffic","traveler_flow","disposable_income","trade_flow","elite_patronage","cultural_activity",
                  "credit_demand","military_demand","health_demand","craft_demand","construction_demand",
                  "regulation","security","event_activity","reputation_climate"]:
        p_bc.add_argument(f"--{field.replace('_','-')}", dest=field, type=float, default=None)

    p_bcfg = sub.add_parser("business-configure", help="Assign a differentiated business archetype to an enterprise")
    p_bcfg.add_argument("enterprise_id", type=int)
    p_bcfg.add_argument("archetype_key")
    p_bcfg.add_argument("--quality", type=float, default=50)
    p_bcfg.add_argument("--price-position", type=float, default=50)
    p_bcfg.add_argument("--capacity", type=float, default=50)
    p_bcfg.add_argument("--clientele-fit", type=float, default=50)
    p_bcfg.add_argument("--reliability", type=float, default=50)
    p_bcfg.add_argument("--regulatory-pressure", type=float, default=0)

    p_bshow = sub.add_parser("business-show", help="Inspect one enterprise's differentiated business state")
    p_bshow.add_argument("enterprise_id", type=int)

    p_bresolve = sub.add_parser("business-resolve", help="Resolve one business cycle immediately at the current story day")
    p_bresolve.add_argument("enterprise_id", type=int)

    sub.add_parser("business-status", help="Summarize differentiated business ecology")


    # v0.19 household, kinship, demographic, and life-course commands
    p_lp = sub.add_parser("life-profile-set")
    p_lp.add_argument("actor")
    p_lp.add_argument("--birth-day", type=int)
    p_lp.add_argument("--sex", choices=["female","male","unspecified"])
    p_lp.add_argument("--household", type=int)
    p_lp.add_argument("--family-eligible", action="store_true", default=None)

    p_union = sub.add_parser("family-union-create")
    p_union.add_argument("actor_a")
    p_union.add_argument("actor_b")
    p_union.add_argument("--household", type=int)
    p_union.add_argument("--kind", choices=["marriage","recognized_partnership"], default="marriage")
    p_union.add_argument("--new-household")

    p_uend = sub.add_parser("family-union-end")
    p_uend.add_argument("union_id", type=int)
    p_uend.add_argument("--status", choices=["separated","dissolved"], default="dissolved")
    p_uend.add_argument("--reason")

    p_fp = sub.add_parser("family-plan-set")
    p_fp.add_argument("union_id", type=int)
    p_fp.add_argument("--desired-children", type=int)
    p_fp.add_argument("--auto-children", action="store_true")
    p_fp.add_argument("--birth-parent")
    p_fp.add_argument("--earliest-day", type=int)
    p_fp.add_argument("--spacing-days", type=int)

    p_birth = sub.add_parser("birth-register")
    p_birth.add_argument("union_id", type=int)
    p_birth.add_argument("--name")
    p_birth.add_argument("--sex", choices=["female","male","unspecified"], default="unspecified")

    p_guard = sub.add_parser("guardianship-create")
    p_guard.add_argument("guardian")
    p_guard.add_argument("ward")
    p_guard.add_argument("--household", type=int)

    p_gend = sub.add_parser("guardianship-end")
    p_gend.add_argument("guardianship_id", type=int)
    p_gend.add_argument("--reason")

    p_mig = sub.add_parser("household-migrate")
    p_mig.add_argument("household_id", type=int)
    p_mig.add_argument("destination_location_id", type=int)
    p_mig.add_argument("planned_day", type=int)
    p_mig.add_argument("--reason")

    p_serv = sub.add_parser("household-service-add")
    p_serv.add_argument("household_id", type=int)
    p_serv.add_argument("actor")
    p_serv.add_argument("role", choices=["servant","retainer","guard","steward","tutor","apprentice","clerk","other"])
    p_serv.add_argument("--review-days", type=int, default=365)
    p_serv.add_argument("--loyalty", type=float, default=50)
    p_serv.add_argument("--satisfaction", type=float, default=50)
    p_serv.add_argument("--renewal-bias", type=float, default=50)

    p_demo = sub.add_parser("demographic-cohort-set")
    p_demo.add_argument("location_id", type=int)
    p_demo.add_argument("cohort_key")
    p_demo.add_argument("age_band", choices=["0_4","5_12","13_17","18_39","40_59","60_plus"])
    p_demo.add_argument("population", type=float)
    p_demo.add_argument("--birth-pressure", type=float, default=0)
    p_demo.add_argument("--migration-rate", type=float, default=0)

    sub.add_parser("household-life-status")

    args = parser.parse_args()

    if args.cmd == "init":
        init_db()
        result = index_canon(DEFAULT_CANON)
        print("Initialized Caerness database and canon index.")
        print(json.dumps(result, indent=2))
    elif args.cmd == "seed-demo":
        seed_demo()
        index_canon(DEFAULT_CANON)
        print("Seeded non-canon demo actors and ensured canon is indexed.")
    elif args.cmd == "status":
        print(json.dumps(status(), indent=2))
    elif args.cmd == "migration-status":
        init_db()
        print(json.dumps(migration_status(), indent=2, default=str))
    elif args.cmd == "campaign-bootstrap":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            result = bootstrap_campaign(conn, seed_path=args.seed)
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "current-canon-bootstrap":
        init_db()
        with connect() as conn:
            imported = import_current_seed(conn, args.seed)
            activated = {} if args.without_activation else activate_existing_loops(conn)
            run_id = start_coverage_run(conn, "current-canon opening", source_seed_namespace=CURRENT_SEED_NAMESPACE,
                                        engine_version=ENGINE_VERSION, schema_version=SCHEMA_VERSION,
                                        metadata={"activation": not args.without_activation})
            coverage = snapshot_coverage(conn, run_id, phase="opening")
            gate = coverage_gate(conn, run_id)
            decade_gate = ten_year_gate(conn, run_id)
            finish_coverage_run(conn, run_id)
            conn.commit()
            print(json.dumps({"import": imported, "activation": activated, "coverage_run_id": run_id,
                              "coverage": coverage, "coverage_gate": gate, "ten_year_gate": decade_gate}, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "coverage-status":
        init_db()
        with connect() as conn:
            coverage = snapshot_coverage(conn, None, phase="status")
            gate = coverage_gate(conn, None)
            decade_gate = ten_year_gate(conn, None)
            print(json.dumps({"coverage": coverage, "coverage_gate": gate, "ten_year_gate": decade_gate}, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "campaign-status":
        init_db()
        with connect() as conn:
            print(json.dumps(bootstrap_status(conn), indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "campaign-player-create":
        init_db()
        with connect() as conn:
            actor_id = create_player_character(conn, args.name, start_location=args.start_location, age=args.age, campaign_name=args.campaign)
            conn.commit()
            print(json.dumps({"player_actor_id": actor_id, "name": args.name, "start_location": args.start_location}, indent=2))
    elif args.cmd == "advance":
        index_canon(DEFAULT_CANON)
        events = advance(args.days)
        print(f"Advanced {args.days} days. {len(events)} event(s) occurred in this span.")
        for event in events:
            print(f"Day {event['day']}: {event['title']} — {event['summary']}")
    elif args.cmd == "events":
        for event in recent_events(args.limit):
            print(f"Day {event['day']} [{event['severity']}]: {event['title']} — {event['summary']}")
    elif args.cmd == "canon-index":
        print(json.dumps(index_canon(Path(args.path), force=args.force), indent=2))
    elif args.cmd == "canon-search":
        index_canon(DEFAULT_CANON)
        rows = search_canon(args.query, args.limit)
        for row in rows:
            print(f"[{row.id}] {row.heading_path or '(no heading)'}")
            print(row.text)
            print()
    elif args.cmd == "canon-status":
        print(json.dumps(canon_status(), indent=2))
    elif args.cmd == "actor-context":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            context = build_actor_context(conn, int(actor["id"]), int(day), args.canon_limit)
            print(json.dumps(context, indent=2, default=str))
    elif args.cmd == "decide-now":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            profile = conn.execute("SELECT * FROM simulation_profiles WHERE actor_id=?", (actor["id"],)).fetchone()
            if not profile:
                raise SystemExit("Actor has no simulation profile.")
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            forced = profile["forced_tier"] if profile["forced_until_day"] is not None and day <= profile["forced_until_day"] else None
            tier = forced or profile["tier"]
            decision_id = decide_actor(conn, int(actor["id"]), str(tier), day)
            row = conn.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
            conn.commit()
            print(json.dumps(dict(row), indent=2))
    elif args.cmd == "decisions":
        init_db()
        with connect() as conn:
            for decision in recent_decisions(conn, args.limit):
                print(
                    f"Day {decision['day']} [{decision['tier']}] {decision['actor_name']}: "
                    f"{decision['action_type']} — {decision['rationale']} {decision['outcome_summary'] or ''}"
                )
    elif args.cmd == "interactions":
        init_db()
        with connect() as conn:
            for item in recent_interactions(conn, args.limit):
                print(
                    f"#{item['id']} Day {item['created_day']} [{item['status']}] "
                    f"{item['proposer_name']} -> {item['recipient_name']}: {item['interaction_type']} "
                    f"(stakes {item['stakes']}, due {item['response_due_day']})"
                )
                if item['resolution_summary']:
                    print(f"  {item['resolution_summary']}")
    elif args.cmd == "interaction":
        init_db()
        with connect() as conn:
            row = conn.execute(
                """SELECT i.*,p.name proposer_name,r.name recipient_name FROM interactions i
                   JOIN actors p ON p.id=i.proposer_actor_id JOIN actors r ON r.id=i.recipient_actor_id
                   WHERE i.id=?""", (args.interaction_id,)
            ).fetchone()
            if not row:
                raise SystemExit(f"No interaction #{args.interaction_id}")
            print(json.dumps(dict(row), indent=2))
            print("History:")
            for action in interaction_history(conn, args.interaction_id):
                print(f"  Day {action['day']} — {action['actor_name']}: {action['action_type']} — {action['summary']}")
    elif args.cmd == "propose":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            proposer = _find_actor(conn, args.proposer)
            recipient = _find_actor(conn, args.recipient)
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            iid = create_interaction(
                conn, int(proposer['id']), int(recipient['id']), args.interaction_type, day,
                urgency=args.urgency, stakes=args.stakes,
                terms={"purpose": args.purpose} if args.purpose else {},
                rationale="Manual CLI proposal",
            )
            conn.commit()
            row = conn.execute("SELECT response_due_day FROM interactions WHERE id=?", (iid,)).fetchone()
            print(f"Created interaction #{iid}; response due on day {row['response_due_day']}.")
    elif args.cmd == "agreements":
        init_db()
        with connect() as conn:
            rows = conn.execute(
                """SELECT ag.*,a.name actor_a_name,b.name actor_b_name FROM agreements ag
                   JOIN actors a ON a.id=ag.actor_a_id JOIN actors b ON b.id=ag.actor_b_id
                   ORDER BY ag.created_day,ag.id"""
            ).fetchall()
            for row in rows:
                print(
                    f"#{row['id']} [{row['status']}] {row['agreement_type']}: "
                    f"{row['actor_a_name']} <-> {row['actor_b_name']} "
                    f"(day {row['created_day']}, expires {row['expiry_day']})"
                )
    elif args.cmd == "causes":
        init_db()
        with connect() as conn:
            outgoing = conn.execute(
                """SELECT * FROM causal_links WHERE source_kind=? AND source_id=? ORDER BY day,id""",
                (args.kind, args.object_id),
            ).fetchall()
            incoming = conn.execute(
                """SELECT * FROM causal_links WHERE target_kind=? AND target_id=? ORDER BY day,id""",
                (args.kind, args.object_id),
            ).fetchall()
            print("Incoming causes:")
            for row in incoming:
                print(f"  Day {row['day']}: {row['source_kind']}#{row['source_id']} --{row['relation']}--> {row['target_kind']}#{row['target_id']}")
            print("Outgoing effects:")
            for row in outgoing:
                print(f"  Day {row['day']}: {row['source_kind']}#{row['source_id']} --{row['relation']}--> {row['target_kind']}#{row['target_id']}")
    elif args.cmd == "player-set":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            set_player(conn, int(actor['id']), args.campaign)
            conn.commit()
            print(f"Player set to {actor['name']} for {args.campaign}.")
    elif args.cmd == "scene":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            packet = build_scene_packet(conn, " ".join(args.request), canon_limit=args.canon_limit)
            conn.commit()
            print(json.dumps(packet, indent=2) if args.as_json else render_scene_brief(packet))
    elif args.cmd == "play":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            result = play_turn(conn, " ".join(args.action), canon_limit=args.canon_limit)
            conn.commit()
            if args.as_json:
                print(json.dumps(result, indent=2, default=str))
            else:
                print(f"Turn #{result['turn_id']} — Day {result['day_started']} -> {result['day_ended']}")
                print(result['narration'])
                if result['action_result']['status'] == 'needs_interpretation':
                    print("[Action requires a richer interpreter; no permanent state was guessed.]")
    elif args.cmd == "bridge-play":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            provider = args.provider or configured_provider(conn, "action_interpretation")
            if provider == "generic":
                provider = configured_provider(conn, "narration")
            if provider == "generic":
                provider = "chatgpt"
            result = bridge_play(conn, " ".join(args.action), provider)
            conn.commit()
            print(json.dumps({k: v for k, v in result.items() if k not in {"packet"}}, indent=2, default=str))
            packet_path = result.get("packet_path") or (result.get("next_request") or {}).get("packet_path")
            if packet_path:
                print(f"\nUpload or paste this packet into {provider.title()}:\n{packet_path}")
                print("Then save the model's JSON reply to a text file and run:")
                rid = result.get("request_id") or (result.get("next_request") or {}).get("request_id")
                print(f"  python run.py model-import {rid} RESPONSE.txt")
                print(f"  python run.py model-apply {rid}")
    elif args.cmd == "model-config":
        init_db()
        with connect() as conn:
            cfg = set_model_config(
                conn, action_provider=args.action, decision_provider=args.decision,
                narrator_provider=args.narrator, packet_dir=args.packet_dir,
            )
            conn.commit()
            print(json.dumps(cfg, indent=2))
    elif args.cmd == "model-status":
        init_db()
        with connect() as conn:
            print(json.dumps(model_status(conn), indent=2))
    elif args.cmd == "model-pending":
        init_db()
        with connect() as conn:
            rows = pending_requests(conn, args.limit)
            if not rows:
                print("No pending/responded model requests.")
            for item in rows:
                print(f"#{item['id']} Day {item['day']} [{item['status']}] {item['task_type']} -> {item['provider']} | {item['packet_path']}")
    elif args.cmd == "model-show":
        init_db()
        with connect() as conn:
            row = request_row(conn, args.request_id)
            packet_path = row.get("packet_path")
            if packet_path and Path(packet_path).exists():
                print(Path(packet_path).read_text(encoding="utf-8"))
            else:
                print(json.dumps(row, indent=2, default=str))
    elif args.cmd == "model-export":
        init_db()
        with connect() as conn:
            out = export_request(conn, args.request_id, provider=args.provider, path=args.path)
            conn.commit()
            print(out)
    elif args.cmd == "model-import":
        init_db()
        response_path = Path(args.response_file)
        if not response_path.exists():
            raise SystemExit(f"Response file not found: {response_path}")
        with connect() as conn:
            data = import_response(conn, args.request_id, response_path.read_text(encoding="utf-8"))
            conn.commit()
            print(json.dumps(data, indent=2, ensure_ascii=False))
    elif args.cmd == "model-apply":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            result = apply_model_request(conn, args.request_id)
            conn.commit()
            print(json.dumps({k: v for k, v in result.items() if k not in {"packet"}}, indent=2, ensure_ascii=False, default=str))
            nreq = result.get("next_request")
            if nreq:
                print(f"\nNext model packet: {nreq['packet_path']}")
                print(f"After getting the reply: python run.py model-import {nreq['request_id']} RESPONSE.txt && python run.py model-apply {nreq['request_id']}")
    elif args.cmd == "model-decide":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            profile = conn.execute("SELECT * FROM simulation_profiles WHERE actor_id=?", (actor["id"],)).fetchone()
            if not profile:
                raise SystemExit("Actor has no simulation profile.")
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            forced = profile["forced_tier"] if profile["forced_until_day"] is not None and day <= profile["forced_until_day"] else None
            tier = str(forced or profile["tier"])
            provider = args.provider or configured_provider(conn, "npc_decision")
            if provider == "generic":
                provider = "chatgpt"
            req = create_decision_request(conn, int(actor["id"]), tier, provider, canon_limit=args.canon_limit)
            conn.commit()
            print(f"Queued {provider.title()} decision request #{req['request_id']} for {actor['name']} ({tier}).")
            print(req["packet_path"])
    elif args.cmd == "model-route":
        init_db()
        with connect() as conn:
            print(json.dumps(assess_request_route(conn, args.request_id), indent=2))
            conn.commit()
    elif args.cmd == "model-run-local":
        init_db()
        index_canon(DEFAULT_CANON)
        with connect() as conn:
            result = run_request_local(conn, args.request_id, force=args.force, apply=args.apply)
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "local-health":
        init_db()
        with connect() as conn:
            print(json.dumps(local_health(conn), indent=2))
    elif args.cmd == "runtime-status":
        init_db()
        with connect() as conn:
            print(json.dumps(runtime_config(conn), indent=2))
    elif args.cmd == "runtime-config":
        init_db()
        changes = {}
        if args.backend is not None: changes["local_backend"] = args.backend
        if args.endpoint is not None: changes["local_endpoint"] = args.endpoint
        if args.model is not None: changes["local_model"] = args.model
        if args.context is not None: changes["local_max_context_tokens"] = args.context
        if args.heavy_context is not None: changes["local_heavy_context_tokens"] = args.heavy_context
        if args.output is not None: changes["local_max_output_tokens"] = args.output
        if args.referral is not None: changes["referral_sensitivity"] = args.referral
        with connect() as conn:
            cfg = set_runtime_config(conn, **changes)
            conn.commit()
            print(json.dumps(cfg, indent=2))
    elif args.cmd == "serve":
        serve_mobile(args.host, args.port)
    elif args.cmd == "backup":
        print(backup_db(args.label))
    elif args.cmd == "restore":
        restore_db(args.path)
        print(f"Restored Caerness database from {args.path}")
    elif args.cmd == "matters":
        init_db()
        with connect() as conn:
            player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
            if not player or player[0] is None: raise SystemExit("No player configured.")
            print(json.dumps(active_matters(conn, int(player[0])), indent=2, default=str))
    elif args.cmd == "attention":
        init_db()
        with connect() as conn:
            player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
            if not player or player[0] is None: raise SystemExit("No player configured.")
            print(json.dumps(pending_attention(conn, int(player[0])), indent=2, default=str))
    elif args.cmd == "worldbook":
        init_db()
        with connect() as conn:
            print(json.dumps(player_information_hub(conn), indent=2, default=str))
    elif args.cmd == "memories":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            print(json.dumps(important_memories(conn, int(actor["id"]), args.limit), indent=2, default=str))
    elif args.cmd == "emergent-threads":
        init_db()
        with connect() as conn:
            print(json.dumps(active_emergent_threads(conn, args.limit), indent=2, default=str))
    elif args.cmd == "interrupt":
        init_db()
        with connect() as conn:
            request_interrupt(conn)
            conn.commit()
            print("Interrupt requested; automatic progression will stop at the next safe causal boundary.")
    elif args.cmd == "possession-add":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            pid = add_possession(conn, int(actor["id"]), args.name, item_type=args.item_type)
            conn.commit()
            print(f"Added possession #{pid}: {args.name}")
    elif args.cmd == "intention-add":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            target_actor_id = int(_find_actor(conn, args.target_actor)["id"]) if args.target_actor else None
            target_location_id = None
            if args.target_location:
                row = conn.execute("SELECT id FROM locations WHERE lower(name)=lower(?)", (args.target_location,)).fetchone()
                if not row: raise SystemExit(f"No location matched: {args.target_location}")
                target_location_id = int(row[0])
            iid = add_intention(conn, int(actor["id"]), args.description, intention_kind=args.kind, target_actor_id=target_actor_id,
                                target_location_id=target_location_id, possession_id=args.possession_id, due_day=args.due_day,
                                trigger_kind=args.trigger, auto_policy=args.policy)
            conn.commit()
            print(f"Added intention #{iid}")
    elif args.cmd == "obligation-add":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            counterparty = int(_find_actor(conn, args.counterparty)["id"]) if args.counterparty else None
            oid = add_obligation(conn, int(actor["id"]), args.description, counterparty_actor_id=counterparty, due_day=args.due_day,
                                 importance=args.importance, intention_id=args.intention_id)
            conn.commit()
            print(f"Added obligation #{oid}")
    elif args.cmd == "turns":
        init_db()
        with connect() as conn:
            for item in recent_turns(conn, args.limit):
                action = item.get('result', {}).get('action', {})
                print(
                    f"#{item['id']} Day {item['day_started']}->{item['day_ended']} {item['player_name']}: "
                    f"{action.get('action_type','?')} [{action.get('status','?')}] — {item['raw_input']}"
                )
    elif args.cmd == "export-journal":
        init_db()
        with connect() as conn:
            print(export_journal(conn, args.path))
    elif args.cmd == "world-pulse":
        init_db()
        with connect() as conn:
            print(json.dumps(world_activity_summary(conn, args.since), indent=2))
    elif args.cmd == "knowledge":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            for item in actor_knowledge(conn, int(actor['id']), args.limit):
                print(f"Day {item['learned_day']} [{item['confidence']:.2f}] {item['fact_key']}: {item['belief_text']}")
    elif args.cmd == "rumours":
        init_db()
        with connect() as conn:
            process_information(conn, int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]))
            conn.commit()
            for item in recent_rumours(conn, args.limit):
                print(f"Day {item['created_day']} #{item['id']} from {item['origin_name'] or 'unknown'}: {item['text']}")
    elif args.cmd == "event-info":
        init_db()
        with connect() as conn:
            register_event_information(conn, args.event_id)
            row = conn.execute(
                """SELECT e.*,ei.visibility,ei.secrecy,ei.rumorability,ei.reliability,l.name location_name
                   FROM events e JOIN event_information ei ON ei.event_id=e.id
                   LEFT JOIN locations l ON l.id=e.location_id WHERE e.id=?""",
                (args.event_id,),
            ).fetchone()
            witnesses = [dict(r) for r in conn.execute(
                """SELECT ew.*,a.name actor_name FROM event_witnesses ew JOIN actors a ON a.id=ew.actor_id
                   WHERE ew.event_id=? ORDER BY a.name""", (args.event_id,)
            ).fetchall()]
            conn.commit()
            print(json.dumps({"event": dict(row), "witnesses": witnesses}, indent=2))
    elif args.cmd == "demo-event":
        init_db()
        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            source_id = int(_find_actor(conn, args.actor)['id']) if args.actor else None
            location_id = None
            if args.location:
                lrow = conn.execute("SELECT id FROM locations WHERE lower(name)=lower(?)", (args.location,)).fetchone()
                if not lrow:
                    raise SystemExit(f"No location matched: {args.location}")
                location_id = int(lrow['id'])
            eid = log_event(conn, SimEvent(
                day=day,event_type='demo:manual',title=args.title,summary=args.summary,severity=args.severity,
                source_actor_id=source_id,location_id=location_id,visibility=args.visibility,rumorability=args.rumorability
            ))
            process_information(conn, day)
            conn.commit()
            print(f"Created event #{eid} with visibility={args.visibility}.")
    elif args.cmd == "embodiment-show":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            print(json.dumps(get_embodiment_profile(conn, int(actor["id"])), indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "embodiment-set":
        init_db()
        patch = json.loads(Path(args.patch_file).read_text(encoding="utf-8"))
        if not isinstance(patch, dict):
            raise SystemExit("Embodiment patch must be one JSON object.")
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            result = update_embodiment_profile(conn, int(actor["id"]), patch, source_kind=args.source)
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "speech-mediate":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            audience_id = int(_find_actor(conn, args.audience)["id"]) if args.audience else None
            result = prepare_speech_mediation(
                conn, int(actor["id"]), args.text, mode=args.mode, audience_actor_id=audience_id,
                intended_tone=args.tone, social_objective=args.objective, commitment_kind=args.commitment,
            )
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "autonomy-check":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            result = assess_autonomous_expression(
                conn, int(actor["id"]), expression_kind=args.expression_kind, confidence=args.confidence,
                stakes=args.stakes, irreversible=args.irreversible, commitment_kind=args.commitment,
            )
            print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    elif args.cmd == "expression-record":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            related_id = int(_find_actor(conn, args.related_actor)["id"]) if args.related_actor else None
            result = record_expression(
                conn, int(actor["id"]), args.summary, expression_kind=args.kind, confidence=args.confidence,
                stakes=args.stakes, irreversible=args.irreversible, commitment_kind=args.commitment,
                related_actor_id=related_id, source_kind="admin",
            )
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "speech-history":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            print(json.dumps(recent_speech_mediations(conn, int(actor["id"]), args.limit), indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "competence-set":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            cid = set_actor_competence(conn, int(actor["id"]), args.domain, args.score, specialty=args.specialty, source_kind=args.source)
            conn.commit()
            print(f"Set competence #{cid}: {actor['name']} / {args.domain} = {args.score}")
    elif args.cmd == "competence-show":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            print(json.dumps(actor_competence_profile(conn, int(actor["id"])), indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "professional-read":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            result = prepare_professional_reading(conn, int(actor["id"]), args.domain, args.situation, specialty=args.specialty, stakes=args.stakes, uncertainty=args.uncertainty, source_kind="admin")
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "professional-resolve":
        init_db()
        with connect() as conn:
            result = record_professional_reading(conn, args.reading_id, summary=args.summary, confidence=args.confidence, provider=args.provider)
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "professional-show":
        init_db()
        with connect() as conn:
            result = professional_reading(conn, args.reading_id)
            if not result: raise SystemExit(f"No professional reading #{args.reading_id}")
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "advisor-judgment":
        init_db()
        with connect() as conn:
            recipient = _find_actor(conn, args.recipient)
            advisor = _find_actor(conn, args.advisor)
            jid = add_advisor_judgment(conn, int(recipient["id"]), int(advisor["id"]), args.domain, args.situation_key, args.judgment, confidence=args.confidence, communicated=not args.private, source_kind="admin")
            conn.commit()
            print(f"Recorded advisor judgment #{jid}")
    elif args.cmd == "decision-context":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            print(json.dumps(decision_context(conn, int(actor["id"]), args.domain, args.situation_key, reading_id=args.reading_id), indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "timeskip-prepare":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            focus = []
            for idx, raw in enumerate(args.focus):
                # A bare known competence domain doubles as the domain key; arbitrary labels remain valid focus keys.
                domain = conn.execute("SELECT 1 FROM competence_domains WHERE domain_key=?", (raw,)).fetchone()
                focus.append({"key": raw, "description": raw.replace("_", " "), "domain": raw if domain else None, "weight": 1.0 / max(1, len(args.focus))})
            delegation = {}
            if args.delegation_file:
                delegation = json.loads(Path(args.delegation_file).read_text(encoding="utf-8"))
            run_id = prepare_time_skip(conn, int(actor["id"]), args.days, focus=focus, delegation=delegation, interruption_policy=args.policy, max_chunk_days=args.chunk)
            conn.commit()
            print(json.dumps(time_skip_run(conn, run_id), indent=2, default=str))
    elif args.cmd == "timeskip-resolve":
        init_db()
        with connect() as conn:
            result = resolve_time_skip(conn, args.run_id)
            conn.commit()
            print(json.dumps(result, indent=2, default=str))
    elif args.cmd == "timeskip-show":
        init_db()
        with connect() as conn:
            result = time_skip_run(conn, args.run_id)
            if result is None:
                raise SystemExit(f"No time skip #{args.run_id}")
            print(json.dumps(result, indent=2, default=str))
    elif args.cmd == "battle-create":
        init_db()
        with connect() as conn:
            player_id = int(_find_actor(conn, args.player)["id"]) if args.player else None
            eid = create_battle(conn, args.title, player_actor_id=player_id, objective=args.objective, stakes=args.stakes)
            conn.commit()
            print(json.dumps(engagement_summary(conn, eid), indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "battle-side-add":
        init_db()
        with connect() as conn:
            controller = int(_find_actor(conn, args.controller)["id"]) if args.controller else None
            sid = add_battle_side(conn, args.engagement_id, args.name, controller_actor_id=controller, objective=args.objective, posture=args.posture)
            conn.commit()
            print(f"Added battle side #{sid}")
    elif args.cmd == "battle-unit-add":
        init_db()
        with connect() as conn:
            commander = int(_find_actor(conn, args.commander)["id"]) if args.commander else None
            uid = add_battle_unit(conn, args.side_id, args.name, commander_actor_id=commander, unit_role=args.role)
            conn.commit()
            print(f"Added battle unit #{uid}")
    elif args.cmd == "battle-intent":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            iid = submit_battle_intent(conn, args.engagement_id, int(actor["id"]), args.intent, risk_level=args.risk, commitment=args.commitment, objective=args.objective)
            conn.commit()
            print(f"Submitted battle intent #{iid}")
    elif args.cmd == "battle-resolve":
        init_db()
        with connect() as conn:
            result = resolve_battle_round(conn, args.engagement_id)
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "battle-view":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            print(json.dumps(battle_view(conn, args.engagement_id, int(actor["id"])), indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "battle-zone-add":
        init_db()
        with connect() as conn:
            metadata = {k:v for k,v in {"terrain": args.terrain, "objective": args.objective}.items() if v is not None}
            zid = add_battle_zone(conn, args.engagement_id, args.name, importance=args.importance, metadata=metadata)
            conn.commit()
            print(f"Added battle zone #{zid}")
    elif args.cmd == "battle-unit-zone":
        init_db()
        with connect() as conn:
            assign_unit_to_zone(conn, args.unit_id, args.zone_id, assignment_kind=args.kind)
            conn.commit()
            print(f"Assigned unit #{args.unit_id} to zone #{args.zone_id}")
    elif args.cmd == "battle-command-link":
        init_db()
        with connect() as conn:
            senior = int(_find_actor(conn, args.senior)["id"]) if args.senior else None
            lid = set_command_link(conn, args.engagement_id, args.side_id, senior_actor_id=senior, junior_unit_id=args.junior_unit,
                                   communication_quality=args.communication, discretion=args.discretion, trust=args.trust)
            conn.commit()
            print(f"Set battle command link #{lid}")
    elif args.cmd == "battle-order":
        init_db()
        with connect() as conn:
            issuer = int(_find_actor(conn, args.issuer)["id"]) if args.issuer else None
            oid = issue_battle_order(conn, args.engagement_id, args.side_id, args.directive, issuer_actor_id=issuer,
                                     unit_id=args.unit, zone_id=args.zone, objective=args.objective, priority=args.priority)
            conn.commit()
            print(f"Issued battle order #{oid}")
    elif args.cmd == "battle-command-profile":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            set_command_profile(conn, int(actor["id"]), planning=args.planning, adaptation=args.adaptation,
                                presence=args.presence, delegation=args.delegation, nerve=args.nerve)
            conn.commit()
            print(f"Updated command profile for {actor['name']}")
    elif args.cmd == "battle-doctrine-set":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            set_battle_doctrine(conn, int(actor["id"]), **{k:getattr(args,k) for k in ["pressure","fixing","misdirection","isolation","depth","reserve_play","mobility","attrition","disruption","exploitation"]})
            conn.commit()
            print(f"Updated battle doctrine for {actor['name']}")
    elif args.cmd == "battle-tactic":
        init_db()
        with connect() as conn:
            actor_id = int(_find_actor(conn, args.actor)["id"]) if args.actor else None
            tid = submit_tactical_choice(conn, args.engagement_id, args.side_id, args.family, actor_id=actor_id, focus_zone_id=args.zone, commitment=args.commitment, source_kind="player")
            conn.commit()
            print(f"Submitted tactical choice #{tid}")
    elif args.cmd == "battle-zone-current":
        init_db()
        with connect() as conn:
            set_zone_current(conn, args.zone_id, density=args.density, stability=args.stability, replenishment=args.replenishment)
            conn.commit()
            print(f"Updated current conditions for zone #{args.zone_id}")
    elif args.cmd == "battle-vein-add":
        init_db()
        with connect() as conn:
            actor_id = int(_find_actor(conn, args.actor)["id"]) if args.actor else None
            aid = add_vein_asset(conn, args.engagement_id, args.side_id, args.stage, actor_id=actor_id, zone_id=args.zone, battlefield_role=args.role, commitment=args.commitment)
            conn.commit()
            print(f"Added Vein asset #{aid}")
    elif args.cmd == "duel-create":
        init_db()
        with connect() as conn:
            a = _find_actor(conn, args.actor_a)
            b = _find_actor(conn, args.actor_b)
            player_id = int(_find_actor(conn, args.player)["id"]) if args.player else None
            eid = create_duel(conn, args.title, int(a["id"]), int(b["id"]), player_actor_id=player_id, objective=args.objective, stakes=args.stakes)
            conn.commit()
            print(json.dumps(engagement_summary(conn, eid), indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "duel-intent":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            iid = submit_duel_intent(conn, args.engagement_id, int(actor["id"]), args.intent, risk_level=args.risk, reserve_commitment=args.reserve, objective=args.objective)
            conn.commit()
            print(f"Submitted duel intent #{iid}")
    elif args.cmd == "duel-resolve":
        init_db()
        with connect() as conn:
            result = resolve_duel_exchange(conn, args.engagement_id)
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "duel-view":
        init_db()
        with connect() as conn:
            actor = _find_actor(conn, args.actor)
            print(json.dumps(duel_view(conn, args.engagement_id, int(actor["id"])), indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "duel-link-battle":
        init_db()
        with connect() as conn:
            link_duel_to_battle(conn, args.duel_engagement_id, args.battle_engagement_id, args.zone_id,
                                args.actor_a_asset_id, args.actor_b_asset_id)
            conn.commit()
            print(f"Linked duel #{args.duel_engagement_id} to battle #{args.battle_engagement_id}")
    elif args.cmd == "combat-show":
        init_db()
        with connect() as conn:
            result = engagement_summary(conn, args.engagement_id)
            if result is None: raise SystemExit(f"No combat engagement #{args.engagement_id}")
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "crystallize-prepare":
        init_db()
        with connect() as conn:
            context = prepare_crystallization_context(conn, args.latent_id, requested_depth=args.depth, trigger_kind="admin")
            conn.commit()
            print(json.dumps(context, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "crystallize-export":
        init_db()
        with connect() as conn:
            print(export_crystallization_packet(conn, args.run_id, args.path))
    elif args.cmd == "crystallize-validate":
        init_db()
        raw = Path(args.proposal_file).read_text(encoding="utf-8")
        proposal = parse_crystallization_response(raw)
        with connect() as conn:
            result = validate_crystallization_proposal(conn, args.run_id, proposal, strict=not args.non_strict)
            conn.commit()
            print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.cmd == "crystallize-apply":
        init_db()
        with connect() as conn:
            actor_id = apply_crystallization_proposal(conn, args.run_id)
            actor = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()
            conn.commit()
            print(f"Crystallized actor #{actor_id}: {actor['name']}")
    elif args.cmd == "crystallize-show":
        init_db()
        with connect() as conn:
            row = crystallization_run(conn, args.run_id)
            if not row: raise SystemExit(f"No crystallization run #{args.run_id}")
            print(json.dumps(row, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "civilian-status":
        init_db()
        with connect() as conn:
            print(json.dumps(civilian_summary(conn), indent=2, ensure_ascii=False))
    elif args.cmd == "household-create":
        init_db()
        with connect() as conn:
            head = int(_find_actor(conn,args.head)["id"]) if args.head else None
            hid = create_household(conn,args.name,head_actor_id=head,location_id=args.location,wealth=args.wealth,liquidity=args.liquidity)
            conn.commit(); print(f"Created household #{hid}")
    elif args.cmd == "enterprise-create":
        init_db()
        with connect() as conn:
            owner = int(_find_actor(conn,args.owner)["id"]) if args.owner else None
            eid = create_enterprise(conn,args.name,args.kind,owner_actor_id=owner,location_id=args.location,cash=args.cash,capital=args.capital,debt=args.debt)
            conn.commit(); print(f"Created enterprise #{eid}")
    elif args.cmd == "market-good":
        init_db()
        with connect() as conn:
            gid = ensure_good(conn,args.key,args.name,args.category,args.base_price,unit=args.unit,luxury=args.luxury)
            conn.commit(); print(f"Good #{gid}")
    elif args.cmd == "market-set":
        init_db()
        with connect() as conn:
            set_market_condition(conn,args.location_id,args.good_id,supply=args.supply,demand=args.demand,transport_pressure=args.transport,risk_pressure=args.risk,tax_pressure=args.tax)
            conn.commit(); print("Market condition updated")
    elif args.cmd == "production-add":
        init_db()
        with connect() as conn:
            pid = add_production_site(conn,args.enterprise_id,args.good_id,capacity_per_30=args.capacity,efficiency=args.efficiency,material_access=args.materials,skilled_labor=args.skill)
            conn.commit(); print(f"Production site #{pid}")
    elif args.cmd == "project-create":
        init_db()
        with connect() as conn:
            patron=int(_find_actor(conn,args.patron)["id"]) if args.patron else None
            creator=int(_find_actor(conn,args.creator)["id"]) if args.creator else None
            pid=create_project(conn,args.title,args.kind,patron_actor_id=patron,creator_actor_id=creator,enterprise_id=args.enterprise,location_id=args.location,target_day=args.target_day,quality_potential=args.quality)
            conn.commit(); print(f"Project #{pid}")
    elif args.cmd == "object-create":
        init_db()
        with connect() as conn:
            creator=int(_find_actor(conn,args.creator)["id"]) if args.creator else None
            owner=int(_find_actor(conn,args.owner)["id"]) if args.owner else None
            oid=create_cultural_object(conn,args.title,args.kind,creator_actor_id=creator,owner_actor_id=owner,location_id=args.location,quality=args.quality,market_value=args.value)
            conn.commit(); print(f"Object #{oid}")
    elif args.cmd == "auction-create":
        init_db()
        with connect() as conn:
            inst=int(_find_actor(conn,args.institution)["id"]) if args.institution else None
            aid=create_auction(conn,args.title,args.scheduled_day,location_id=args.location,institution_actor_id=inst)
            conn.commit(); print(f"Auction #{aid}")
    elif args.cmd == "auction-lot":
        init_db()
        with connect() as conn:
            seller=int(_find_actor(conn,args.seller)["id"]) if args.seller else None
            lid=add_auction_lot(conn,args.auction_id,args.object_id,seller_actor_id=seller,reserve_price=args.reserve,estimate_low=args.low,estimate_high=args.high)
            conn.commit(); print(f"Lot #{lid}")
    elif args.cmd == "auction-interest":
        init_db()
        with connect() as conn:
            actor=int(_find_actor(conn,args.actor)["id"])
            set_auction_interest(conn,args.lot_id,actor,interest=args.interest,budget=args.budget,taste_fit=args.taste,status_motive=args.status_motive)
            conn.commit(); print("Auction interest recorded")
    elif args.cmd == "auction-resolve":
        init_db()
        with connect() as conn:
            result=resolve_auction(conn,args.auction_id)
            conn.commit(); print(json.dumps(result,indent=2,ensure_ascii=False))

    elif args.cmd == "building-create":
        init_db()
        with connect() as conn:
            owner=int(_find_actor(conn,args.owner)["id"]) if args.owner else None
            inst=int(_find_actor(conn,args.institution)["id"]) if args.institution else None
            bid=create_building(conn,args.name,args.kind,location_id=args.location,owner_actor_id=owner,household_id=args.household,institution_actor_id=inst,style_key=args.style,prestige=args.prestige,utility=args.utility,maintenance_burden=args.maintenance)
            conn.commit(); print(f"Building #{bid}")
    elif args.cmd == "style-create":
        init_db()
        with connect() as conn:
            origin=int(_find_actor(conn,args.origin_actor)["id"]) if args.origin_actor else None
            sid=ensure_style_movement(conn,args.key,args.name,args.domain,origin_location_id=args.origin_location,origin_actor_id=origin,prestige=args.prestige,novelty=args.novelty,accessibility=args.accessibility,durability=args.durability)
            conn.commit(); print(f"Style #{sid}")
    elif args.cmd == "style-adoption-set":
        init_db()
        with connect() as conn:
            set_style_adoption(conn,args.style_id,args.location_id,adoption=args.adoption,elite_support=args.elite_support,craft_capacity=args.craft_capacity,resistance=args.resistance)
            conn.commit(); print("Style adoption updated")
    elif args.cmd == "succession-plan":
        init_db()
        with connect() as conn:
            heir=int(_find_actor(conn,args.heir)["id"]) if args.heir else None
            set_succession_plan(conn,args.household_id,designated_heir_actor_id=heir,succession_method=args.method,certainty=args.certainty,dispute_pressure=args.dispute)
            conn.commit(); print("Succession plan updated")
    elif args.cmd == "succession-claim":
        init_db()
        with connect() as conn:
            actor=int(_find_actor(conn,args.actor)["id"])
            cid=set_inheritance_claim(conn,args.household_id,actor,priority=args.priority,legitimacy=args.legitimacy,support=args.support)
            conn.commit(); print(f"Succession claim #{cid}")
    elif args.cmd == "succession-resolve":
        init_db()
        with connect() as conn:
            head=int(_find_actor(conn,args.head)["id"]) if args.head else None
            result=resolve_household_succession(conn,args.household_id,new_head_actor_id=head)
            conn.commit(); print(json.dumps(result,indent=2,ensure_ascii=False))
    elif args.cmd == "credit-create":
        init_db()
        with connect() as conn:
            lender=int(_find_actor(conn,args.lender)["id"]) if args.lender else None
            borrower=int(_find_actor(conn,args.borrower)["id"]) if args.borrower else None
            cid=create_credit_agreement(conn,principal=args.principal,lender_actor_id=lender,lender_enterprise_id=args.lender_enterprise,borrower_actor_id=borrower,borrower_enterprise_id=args.borrower_enterprise,interest_rate_per_30=args.interest,due_day=args.due_day,risk=args.risk)
            conn.commit(); print(f"Credit agreement #{cid}")
    elif args.cmd == "credit-pay":
        init_db()
        with connect() as conn:
            remaining=make_credit_payment(conn,args.agreement_id,args.amount)
            conn.commit(); print(f"Outstanding: {remaining:.2f}")
    elif args.cmd == "enterprise-partner":
        init_db()
        with connect() as conn:
            actor=int(_find_actor(conn,args.actor)["id"])
            set_enterprise_partner(conn,args.enterprise_id,actor,ownership_share=args.share,governance_weight=args.governance,capital_committed=args.capital,role=args.role)
            conn.commit(); print("Enterprise partnership updated")
    elif args.cmd == "professional-member":
        init_db()
        with connect() as conn:
            actor=int(_find_actor(conn,args.actor)["id"]); inst=int(_find_actor(conn,args.institution)["id"])
            mid=create_professional_membership(conn,actor,inst,args.domain,role=args.role,standing=args.standing,influence=args.influence,dues_per_30=args.dues)
            conn.commit(); print(f"Professional membership #{mid}")

    elif args.cmd == "life-profile-set":
        init_db()
        with connect() as conn:
            actor=int(_find_actor(conn,args.actor)["id"])
            set_life_profile(conn,actor,birth_day=args.birth_day,demographic_sex=args.sex,current_household_id=args.household,family_formation_eligible=args.family_eligible)
            conn.commit(); print("Life profile updated")
    elif args.cmd == "family-union-create":
        init_db()
        with connect() as conn:
            a=int(_find_actor(conn,args.actor_a)["id"]); b=int(_find_actor(conn,args.actor_b)["id"])
            uid=create_union(conn,a,b,household_id=args.household,union_kind=args.kind,create_new_household_name=args.new_household)
            conn.commit(); print(f"Family union #{uid}")
    elif args.cmd == "family-union-end":
        init_db()
        with connect() as conn:
            end_union(conn,args.union_id,status=args.status,reason=args.reason)
            conn.commit(); print(f"Family union #{args.union_id} ended")
    elif args.cmd == "family-plan-set":
        init_db()
        with connect() as conn:
            birth_parent=int(_find_actor(conn,args.birth_parent)["id"]) if args.birth_parent else None
            update_family_plan(conn,args.union_id,desired_children=args.desired_children,auto_children=True if args.auto_children else None,birth_parent_actor_id=birth_parent,earliest_next_child_day=args.earliest_day,spacing_days=args.spacing_days)
            conn.commit(); print("Family plan updated")
    elif args.cmd == "birth-register":
        init_db()
        with connect() as conn:
            child=register_birth(conn,args.union_id,child_name=args.name,demographic_sex=args.sex)
            conn.commit(); print(f"Registered child actor #{child}")
    elif args.cmd == "guardianship-create":
        init_db()
        with connect() as conn:
            g=int(_find_actor(conn,args.guardian)["id"]); w=int(_find_actor(conn,args.ward)["id"])
            gid=create_guardianship(conn,g,w,household_id=args.household)
            conn.commit(); print(f"Guardianship #{gid}")
    elif args.cmd == "guardianship-end":
        init_db()
        with connect() as conn:
            end_guardianship(conn,args.guardianship_id,reason=args.reason)
            conn.commit(); print(f"Guardianship #{args.guardianship_id} ended")
    elif args.cmd == "household-migrate":
        init_db()
        with connect() as conn:
            mid=schedule_household_migration(conn,args.household_id,args.destination_location_id,args.planned_day,reason=args.reason)
            conn.commit(); print(f"Migration plan #{mid}")
    elif args.cmd == "household-service-add":
        init_db()
        with connect() as conn:
            actor=int(_find_actor(conn,args.actor)["id"])
            sid=add_service_term(conn,args.household_id,actor,args.role,review_in_days=args.review_days,loyalty=args.loyalty,satisfaction=args.satisfaction,renewal_bias=args.renewal_bias)
            conn.commit(); print(f"Household service term #{sid}")
    elif args.cmd == "demographic-cohort-set":
        init_db()
        with connect() as conn:
            cid=set_demographic_cohort(conn,args.location_id,args.cohort_key,args.age_band,args.population,annual_birth_pressure=args.birth_pressure,annual_migration_rate=args.migration_rate)
            conn.commit(); print(f"Demographic cohort #{cid}")
    elif args.cmd == "household-life-status":
        init_db()
        with connect() as conn:
            print(json.dumps(household_life_summary(conn),indent=2,ensure_ascii=False))
    elif args.cmd == "business-archetypes":
        init_db()
        with connect() as conn:
            print(json.dumps(business_catalog(conn), indent=2, ensure_ascii=False))
    elif args.cmd == "commercial-context-set":
        init_db()
        with connect() as conn:
            fields = ["foot_traffic","traveler_flow","disposable_income","trade_flow","elite_patronage","cultural_activity",
                      "credit_demand","military_demand","health_demand","craft_demand","construction_demand",
                      "regulation","security","event_activity","reputation_climate"]
            values = {k:getattr(args,k) for k in fields if getattr(args,k) is not None}
            set_commercial_context(conn,args.location_id,**values)
            conn.commit(); print("Commercial context updated")
    elif args.cmd == "business-configure":
        init_db()
        with connect() as conn:
            configure_enterprise_business(conn,args.enterprise_id,args.archetype_key,quality=args.quality,price_position=args.price_position,
                                          capacity=args.capacity,clientele_fit=args.clientele_fit,service_reliability=args.reliability,
                                          regulatory_pressure=args.regulatory_pressure)
            conn.commit(); print(f"Configured enterprise #{args.enterprise_id} as {args.archetype_key}")
    elif args.cmd == "business-show":
        init_db()
        with connect() as conn:
            result=business_profile(conn,args.enterprise_id)
            if not result: raise SystemExit(f"Enterprise #{args.enterprise_id} has no business profile")
            print(json.dumps(result,indent=2,ensure_ascii=False,default=str))
    elif args.cmd == "business-resolve":
        init_db()
        with connect() as conn:
            result=resolve_business_cycle(conn,args.enterprise_id)
            conn.commit(); print(json.dumps(result,indent=2,ensure_ascii=False,default=str))
    elif args.cmd == "business-status":
        init_db()
        with connect() as conn:
            print(json.dumps(business_ecology_summary(conn),indent=2,ensure_ascii=False))

    elif args.cmd == "health-profile-set":
        with connect() as conn:
            a=_find_actor(conn,args.actor)
            configure_health_profile(conn,int(a["id"]),longevity_class=args.longevity,baseline_health=args.baseline)
            conn.commit(); print(json.dumps(health_summary(conn,int(a["id"])),indent=2,ensure_ascii=False))
    elif args.cmd == "health-condition-add":
        with connect() as conn:
            a=_find_actor(conn,args.actor)
            cid=add_condition(conn,int(a["id"]),args.kind,args.label,severity=args.severity,capacity_impact=args.capacity_impact,pain_impact=args.pain_impact,recovery_rate_per_30=args.recovery,progression_rate_per_30=args.progression,fatality_pressure=args.fatality,specialist_requirement=args.specialist)
            conn.commit(); print(cid)
    elif args.cmd == "health-treatment-add":
        with connect() as conn:
            a=_find_actor(conn,args.actor); provider=None
            if args.provider: provider=int(_find_actor(conn,args.provider)["id"])
            tid=add_treatment(conn,int(a["id"]),args.kind,condition_id=args.condition,provider_actor_id=provider,quality=args.quality,adherence=args.adherence,end_day=args.end_day)
            conn.commit(); print(tid)
    elif args.cmd == "health-disability-add":
        with connect() as conn:
            a=_find_actor(conn,args.actor)
            did=add_disability(conn,int(a["id"]),args.label,source_condition_id=args.source_condition,mobility_impact=args.mobility,stamina_impact=args.stamina,capacity_impact=args.capacity)
            conn.commit(); print(did)
    elif args.cmd == "health-disability-resolve":
        with connect() as conn:
            resolve_disability(conn,args.disability_id,reason=args.reason)
            conn.commit(); print(args.disability_id)
    elif args.cmd == "health-status":
        with connect() as conn:
            if args.actor:
                a=_find_actor(conn,args.actor); print(json.dumps(health_summary(conn,int(a["id"])),indent=2,ensure_ascii=False))
            else:
                print(json.dumps(health_summary(conn),indent=2,ensure_ascii=False))
    elif args.cmd == "religion-affiliation-set":
        with connect() as conn:
            a=_find_actor(conn,args.actor)
            rid=set_affiliation(conn,int(a["id"]),args.tradition,affiliation_kind=args.kind,practice_intensity=args.practice,publicness=args.publicness)
            conn.commit(); print(rid)
    elif args.cmd == "religion-institution-set":
        with connect() as conn:
            a=_find_actor(conn,args.institution)
            configure_religious_institution(conn,int(a["id"]),args.tradition,treasury=args.treasury,charity_commitment=args.charity)
            conn.commit(); print("ok")
    elif args.cmd == "religion-observance-add":
        with connect() as conn:
            iid=int(_find_actor(conn,args.institution)["id"]) if args.institution else None
            oid=add_observance(conn,args.tradition,args.name,due_day=args.due_day,recurrence_days=args.recurrence,institution_actor_id=iid,location_id=args.location)
            conn.commit(); print(oid)
    elif args.cmd == "religion-obligation-add":
        with connect() as conn:
            a=_find_actor(conn,args.actor)
            oid=add_religious_obligation(conn,args.description,obligation_kind=args.kind,due_day=args.due_day,actor_id=int(a["id"]),tradition=args.tradition,recurrence_days=args.recurrence)
            conn.commit(); print(oid)
    elif args.cmd == "religion-obligation-fulfill":
        with connect() as conn:
            fulfill_obligation(conn,args.obligation_id); conn.commit(); print(args.obligation_id)
    elif args.cmd == "culture-institution-set":
        with connect() as conn:
            a=_find_actor(conn,args.institution)
            configure_cultural_institution(conn,int(a["id"]),args.domain,resources=args.resources,prestige=args.prestige)
            conn.commit(); print("ok")
    elif args.cmd == "culture-program-add":
        with connect() as conn:
            a=_find_actor(conn,args.institution)
            pid=add_cultural_program(conn,int(a["id"]),args.name,args.kind,due_day=args.due_day,recurrence_days=args.recurrence,location_id=args.location)
            conn.commit(); print(pid)
    elif args.cmd == "religion-status":
        with connect() as conn:
            print(json.dumps(religion_summary(conn),indent=2,ensure_ascii=False))
    elif args.cmd == "environment-set":
        with connect() as conn:
            configure_environment(conn,args.location,climate_label=args.climate,terrain_kind=args.terrain,year_length=args.year_length,
                                  base_travel_factor=args.travel_factor,base_production_factor=args.production_factor,
                                  base_health_pressure=args.health_pressure,current_density=args.current_density,
                                  current_replenishment=args.current_replenishment,current_carrying_capacity=args.current_capacity)
            conn.commit(); print("ok")
    elif args.cmd == "season-window-add":
        with connect() as conn:
            sid=add_seasonal_window(conn,args.location,args.name,args.start,args.end,travel_factor=args.travel_factor,
                                    production_factor=args.production_factor,health_pressure=args.health_pressure,
                                    current_replenishment_factor=args.replenishment_factor)
            conn.commit(); print(sid)
    elif args.cmd == "route-add":
        with connect() as conn:
            rid=add_route(conn,args.origin,args.destination,route_kind=args.kind,base_days=args.days,bidirectional=not args.one_way)
            conn.commit(); print(rid)
    elif args.cmd == "route-condition-add":
        with connect() as conn:
            cid=add_route_condition(conn,args.route_id,args.kind,args.label,args.start,end_day=args.end,accessibility=args.accessibility,
                                    delay_factor=args.delay_factor,hazard_pressure=args.hazard)
            conn.commit(); print(cid)
    elif args.cmd == "travel-start":
        with connect() as conn:
            pid=start_travel(conn,args.subject_kind,args.subject_id,args.destination); conn.commit(); print(pid)
    elif args.cmd == "travel-cancel":
        with connect() as conn:
            cancel_travel(conn,args.plan_id); conn.commit(); print(args.plan_id)
    elif args.cmd == "current-use":
        with connect() as conn:
            uid=register_current_use(conn,args.location,args.amount,description=args.description); conn.commit(); print(uid)
    elif args.cmd == "ecology-status":
        with connect() as conn:
            print(json.dumps(ecology_context(conn,args.location) if args.location else ecology_summary(conn),indent=2,ensure_ascii=False,default=str))
    elif args.cmd == "polity-set":
        with connect() as conn:
            inst=_find_actor(conn,args.institution); ruler=int(_find_actor(conn,args.ruler)["id"]) if args.ruler else None
            pid=configure_polity(conn,int(inst["id"]),polity_kind=args.kind,ruler_actor_id=ruler,succession_method=args.succession,legitimacy=args.legitimacy,stability=args.stability)
            conn.commit(); print(pid)
    elif args.cmd == "territory-set":
        with connect() as conn:
            set_territorial_control(conn,args.polity_id,args.location_id,control_kind=args.kind); conn.commit(); print("ok")
    elif args.cmd == "political-claim-add":
        with connect() as conn:
            cid=add_territorial_claim(conn,args.polity_id,args.location_id,pressure=args.pressure,rate_per_30_days=args.rate,threshold=args.threshold,resolution_policy=args.policy)
            conn.commit(); print(cid)
    elif args.cmd == "succession-claim-add":
        with connect() as conn:
            a=_find_actor(conn,args.actor); cid=add_succession_claim(conn,args.polity_id,int(a["id"]),legitimacy=args.legitimacy,support=args.support,priority=args.priority)
            conn.commit(); print(cid)
    elif args.cmd == "polity-succession-resolve":
        with connect() as conn:
            aid=int(_find_actor(conn,args.actor)["id"]) if args.actor else None
            chosen=resolve_succession(conn,args.polity_id,chosen_actor_id=aid,require_clear_margin=(aid is None)); conn.commit(); print(chosen)
    elif args.cmd == "political-link-add":
        with connect() as conn:
            lid=create_political_link(conn,args.senior,args.junior,args.kind,autonomy=args.autonomy); conn.commit(); print(lid)
    elif args.cmd == "politics-status":
        with connect() as conn:
            print(json.dumps(politics_summary(conn),indent=2,ensure_ascii=False,default=str))
    elif args.cmd == "education-program-add":
        with connect() as conn:
            inst=int(_find_actor(conn,args.institution)["id"]) if args.institution else None
            pid=create_program(conn,args.key,args.name,args.domain,args.kind,institution_actor_id=inst,duration_days=args.duration,capacity=args.capacity,min_entry_score=args.min_entry,min_teacher_score=args.min_teacher,completion_gain=args.gain,max_score_from_program=args.max_score,certificate_key=args.certificate,lineage_key=args.lineage,review_cadence_days=args.review_days); conn.commit(); print(pid)
    elif args.cmd == "teaching-link-add":
        with connect() as conn:
            t=int(_find_actor(conn,args.teacher)["id"]); st=int(_find_actor(conn,args.student)["id"]); inst=int(_find_actor(conn,args.institution)["id"]) if args.institution else None
            rid=create_teaching_relationship(conn,t,st,args.kind,args.domain,institution_actor_id=inst,responsibility=args.responsibility); conn.commit(); print(rid)
    elif args.cmd == "teaching-link-end":
        with connect() as conn: end_teaching_relationship(conn,args.relationship_id,status=args.status); conn.commit(); print("ok")
    elif args.cmd == "knowledge-asset-add":
        with connect() as conn:
            inst=int(_find_actor(conn,args.institution)["id"]) if args.institution else None
            aid=create_knowledge_asset(conn,args.title,args.kind,args.domain,institution_actor_id=inst,lineage_key=args.lineage,access_tier=args.access_tier,preservation_mode=args.preservation,loss_threshold_days=args.loss_days); conn.commit(); print(aid)
    elif args.cmd == "knowledge-custody-add":
        with connect() as conn:
            aid=int(_find_actor(conn,args.actor)["id"]) if args.actor else None; inst=int(_find_actor(conn,args.institution)["id"]) if args.institution else None
            cid=add_knowledge_custody(conn,args.asset_id,args.kind,actor_id=aid,institution_actor_id=inst); conn.commit(); print(cid)
    elif args.cmd == "knowledge-access-grant":
        with connect() as conn:
            aid=int(_find_actor(conn,args.actor)["id"]); grant_knowledge_access(conn,args.asset_id,aid,args.level); conn.commit(); print("ok")
    elif args.cmd == "knowledge-access-revoke":
        with connect() as conn:
            aid=int(_find_actor(conn,args.actor)["id"]); revoke_knowledge_access(conn,args.asset_id,aid); conn.commit(); print("ok")
    elif args.cmd == "program-knowledge-link":
        with connect() as conn: link_program_knowledge(conn,args.program_id,args.asset_id,args.requirement); conn.commit(); print("ok")
    elif args.cmd == "transmission-line-add":
        with connect() as conn:
            inst=int(_find_actor(conn,args.institution)["id"]) if args.institution else None; founder=int(_find_actor(conn,args.founder)["id"]) if args.founder else None
            lid=create_transmission_line(conn,args.lineage_key,args.name,args.domain,institution_actor_id=inst,founding_teacher_actor_id=founder,vitality=args.vitality,fragility_per_year=args.fragility); conn.commit(); print(lid)
    elif args.cmd == "transmission-member-set":
        with connect() as conn:
            aid=int(_find_actor(conn,args.actor)["id"]); set_actor_transmission(conn,args.line_id,aid,args.relation,depth=args.depth); conn.commit(); print("ok")
    elif args.cmd == "education-enroll":
        with connect() as conn:
            aid=int(_find_actor(conn,args.actor)["id"]); teacher=int(_find_actor(conn,args.teacher)["id"]) if args.teacher else None
            eid=enroll(conn,aid,args.program_id,primary_teacher_actor_id=teacher,practice_quality=args.quality); conn.commit(); print(eid)
    elif args.cmd == "education-pause":
        with connect() as conn: pause_enrollment(conn,args.enrollment_id,args.reason); conn.commit(); print("ok")
    elif args.cmd == "education-resume":
        with connect() as conn:
            teacher=int(_find_actor(conn,args.teacher)["id"]) if args.teacher else None; resume_enrollment(conn,args.enrollment_id,teacher_actor_id=teacher); conn.commit(); print("ok")
    elif args.cmd == "education-withdraw":
        with connect() as conn: withdraw_enrollment(conn,args.enrollment_id,args.reason); conn.commit(); print("ok")
    elif args.cmd == "institution-reproduction-set":
        with connect() as conn:
            inst=int(_find_actor(conn,args.institution)["id"]); configure_reproduction(conn,inst,recruitment_capacity=args.recruitment,training_capacity=args.training,instructor_depth=args.instructors,archival_resilience=args.archives,review_cadence_days=args.review_days); conn.commit(); print("ok")
    elif args.cmd == "institution-successor-candidate":
        with connect() as conn:
            inst=int(_find_actor(conn,args.institution)["id"]); aid=int(_find_actor(conn,args.actor)["id"]); cid=set_successor_candidate(conn,inst,aid,args.role,readiness=args.readiness,legitimacy=args.legitimacy,transmission_depth=args.transmission_depth); conn.commit(); print(cid)
    elif args.cmd == "institution-successor-choose":
        with connect() as conn: choose_successor_candidate(conn,args.candidate_id); conn.commit(); print("ok")
    elif args.cmd == "education-show":
        with connect() as conn:
            print(json.dumps(education_context(conn,int(_find_actor(conn,args.actor)["id"])) if args.actor else education_summary(conn),indent=2,ensure_ascii=False,default=str))
    elif args.cmd == "education-status":
        with connect() as conn: print(json.dumps(education_summary(conn),indent=2,ensure_ascii=False,default=str))
    elif args.cmd == "camera-successor-set":
        init_db()
        with connect() as conn:
            src=_find_actor(conn,args.from_actor); dst=_find_actor(conn,args.successor)
            cid=designate_camera_successor(conn,int(src['id']),int(dst['id']),priority=args.priority,notes=args.notes)
            conn.commit(); print(cid)
    elif args.cmd == "camera-history":
        init_db()
        with connect() as conn: print(json.dumps(camera_history(conn),indent=2,default=str))
    elif args.cmd == "stress-run":
        init_db()
        with connect() as conn:
            result=run_horizon(conn,args.years,label=args.label,scenario_kind=args.scenario,checkpoint_years=args.checkpoint_years)
            conn.commit(); print(json.dumps(result,indent=2,default=str))
    elif args.cmd == "stress-status":
        init_db()
        with connect() as conn: print(json.dumps(stress_report(conn,args.run_id),indent=2,default=str))
    elif args.cmd == "stress-scan":
        init_db()
        with connect() as conn: print(json.dumps({'snapshot':world_snapshot(conn),'issues':contradiction_scan(conn)},indent=2,default=str))
    elif args.cmd == "reset":
        reset_db(force=args.force, backup=not args.no_backup)
        print(f"Database removed: {database_path()}")


if __name__ == "__main__":
    main()
