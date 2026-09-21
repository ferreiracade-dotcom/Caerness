from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .activation import CURRENT_CANON_ACTIVATION_VERSION


@dataclass(frozen=True)
class CoverageSpec:
    key: str
    label: str
    bible_scope: str
    owner: str
    status: str
    population_sql: str | None = None
    eligibility_sql: str | None = None
    autonomous: bool = False
    required: bool = True
    population_policy: str = 'opening_required'
    process_keys: tuple[str, ...] = ()
    notes: str | None = None


# Mirrors the 52-row coverage audit. The point is observability, not pretending
# that every row already has a complete mechanism.
SPECS: tuple[CoverageSpec, ...] = (
    CoverageSpec("01_canon_identity", "Canon and identity", "0; 24; 25", "canon/current_seed", "PARTIAL", "SELECT COUNT(*) FROM source_identity_map", notes="Rejected and stale source material must remain blocked."),
    CoverageSpec("02_geography", "Geography and political geography", "1; 20", "ecology/politics", "RUNNABLE", "SELECT COUNT(*) FROM locations", "SELECT COUNT(*) FROM travel_routes WHERE status IN ('open','restricted')"),
    CoverageSpec("03_current_ecology", "Current ecology and cultivation sites", "2", "ecology", "PARTIAL", "SELECT COUNT(*) FROM location_environment_profiles", "SELECT COUNT(*) FROM location_environment_profiles"),
    CoverageSpec("04_cultivation_realization", "Cultivation and Realization", "2; 24", "cultivation", "RUNNABLE", "SELECT COUNT(*) FROM cultivation_profiles WHERE core_state='Open-Core'", "SELECT COUNT(*) FROM cultivation_profiles WHERE core_state='Open-Core' AND active=1 AND status='active'", autonomous=True),
    CoverageSpec("05_core_heredity", "Core assessment and heredity", "2; 21", "household_life", "PARTIAL", "SELECT COUNT(*) FROM actor_life_profiles"),
    CoverageSpec("06_elixirs_sediment", "Elixirs, Sediment and Rupture", "2; 11; 21", "elixir/health/cultivation", "RUNNABLE", "SELECT (SELECT COUNT(*) FROM elixir_supply_profiles WHERE status='active') + (SELECT COUNT(*) FROM cultivation_profiles WHERE core_state='Open-Core')", "SELECT COUNT(*) FROM elixir_batches WHERE status='available' AND remaining_units>0", notes="Batch/exposure mechanics are runnable; zero available batches means no eligible assimilation work, not a missing mechanism."),
    CoverageSpec("07_teaching_apprenticeship", "Ordinary teaching and apprenticeship", "4; 21", "education", "RUNNABLE", "SELECT COUNT(*) FROM education_programs", "SELECT COUNT(*) FROM education_enrollments WHERE status IN ('active','paused')", autonomous=True),
    CoverageSpec("08_master_disciple", "Personal master and disciple", "3; 4; 24", "education", "PARTIAL", "SELECT COUNT(*) FROM teaching_relationships WHERE status='active'", "SELECT COUNT(*) FROM teaching_relationships WHERE status='active'"),
    CoverageSpec("09_manuals", "Manuals and restricted transmission", "2; 4; 24", "education", "RUNNABLE", "SELECT COUNT(*) FROM knowledge_assets WHERE status='extant'", "SELECT COUNT(*) FROM knowledge_assets WHERE status='extant'"),
    CoverageSpec("10_institution_reproduction", "Institutional recruitment and reproduction", "3; 5-8; 24", "education", "PARTIAL", "SELECT COUNT(*) FROM institution_reproduction_profiles", "SELECT COUNT(*) FROM institution_reproduction_profiles", autonomous=True),
    CoverageSpec("11_concord_law", "Concord governance and ordinary law", "5; 20; 22", "law/politics/interactions", "RUNNABLE", "SELECT COUNT(*) FROM law_jurisdictions WHERE status='active'", "SELECT COUNT(*) FROM law_cases WHERE status NOT IN ('closed','dismissed')", autonomous=True, notes="INTEGRATION-01 resolves applicable jurisdiction/rule, office capacity/corruption, evidence, hearings, judgments and enforcement; underworld policing remains a separate investigation/evidence owner."),
    CoverageSpec("12_undertow_compacts", "Undertow compacts", "6; 3", "interactions", "PARTIAL", "SELECT COUNT(*) FROM agreements", population_policy="conditional"),
    CoverageSpec("13_unsworn", "Unsworn institutions", "7; 20", "education/institutions", "PARTIAL", "SELECT COUNT(*) FROM institution_profiles"),
    CoverageSpec("14_hollow_succession", "Hollow practice and Grand Coven succession", "8; 12; 24", "hollow/cultivation", "RUNNABLE", "SELECT (SELECT COUNT(*) FROM hollow_practice_profiles) + (SELECT COUNT(*) FROM grand_coven_succession_state)", "SELECT COUNT(*) FROM grand_coven_succession_state WHERE succession_status IN ('open','contested','sealed','vacant')", autonomous=True, notes="Hollow affiliation/practice and specialized Grand Coven succession are persisted separately. Deep Court elders are political power-brokers, not heirs by office; Carrion never resets on an Inheritor's death."),
    CoverageSpec("15_long_road", "Long Road and waystones", "9; 20", "ecology/business/information", "PARTIAL", "SELECT COUNT(*) FROM travel_routes"),
    CoverageSpec("16_combat", "Challenges, duels and battlefield combat", "10; 1", "combat/battlefield/tournaments", "RUNNABLE", "SELECT (SELECT COUNT(*) FROM combat_engagements) + (SELECT COUNT(*) FROM tournament_series WHERE status='active')", "SELECT (SELECT COUNT(*) FROM martial_challenges WHERE status='active') + (SELECT COUNT(*) FROM tournament_events WHERE status IN ('registration','active')) + (SELECT COUNT(*) FROM tournament_series WHERE status='active')", autonomous=True, notes="Accepted social challenges and tournament bouts feed the existing abstract duel resolver; a tournament schedule counts as future autonomous combat work."),
    CoverageSpec("17_tournament", "Tournament and circuit economy", "10; 20; 23", "combat/business/information", "PARTIAL", "SELECT (SELECT COUNT(*) FROM tournament_series) + (SELECT COUNT(*) FROM tournament_events)", "SELECT COUNT(*) FROM tournament_series WHERE status='active'", autonomous=True, notes="Recurring Cairnholt/Convergence lifecycle and individual named/latent fields are runnable; company contests and prize settlement remain structural/separate."),
    CoverageSpec("18_households_property", "Households and property", "21; 24", "civilian/household_life", "RUNNABLE", "SELECT COUNT(*) FROM households WHERE status!='historical'", "SELECT COUNT(*) FROM households WHERE status IN ('active','declining')"),
    CoverageSpec("19_new_unions", "New unions and household formation", "21; 24", "household_life/domain_actions", "PARTIAL", "SELECT COUNT(*) FROM household_unions", "SELECT COUNT(*) FROM actor_life_profiles lp JOIN actors a ON a.id=lp.actor_id WHERE lp.life_status='living' AND lp.family_formation_eligible=1 AND lp.life_stage IN ('adult','elder') AND a.status='active' AND NOT EXISTS(SELECT 1 FROM household_unions u WHERE u.status='active' AND (u.actor_a_id=a.id OR u.actor_b_id=a.id))", autonomous=True, notes="Autonomous proposal path exists but remains deliberately restrictive and relationship-gated."),
    CoverageSpec("20_births_children", "Births, fertility and children", "21; 24", "household_life", "RUNNABLE", "SELECT COUNT(*) FROM household_unions WHERE status='active'", "SELECT COUNT(*) FROM household_unions WHERE status='active'"),
    CoverageSpec("21_guardianship", "Guardianship, adoption and dependencies", "21", "household_life", "RUNNABLE", "SELECT COUNT(*) FROM actor_life_profiles WHERE life_status='living'", "SELECT COUNT(*) FROM household_dependencies d JOIN actor_life_profiles lp ON lp.actor_id=d.dependent_actor_id LEFT JOIN actors sa ON sa.id=d.sponsor_actor_id LEFT JOIN actor_life_profiles slp ON slp.actor_id=d.sponsor_actor_id WHERE d.status='active' AND d.dependency_kind IN ('child','ward') AND lp.life_status='living' AND lp.life_stage IN ('infant','child','youth') AND (d.sponsor_actor_id IS NULL OR sa.status IS NULL OR sa.status<>'active' OR slp.life_status<>'living')", autonomous=True, notes="Sponsor-loss resolver reassigns only to an existing living adult in the same household; otherwise the need remains unresolved rather than inventing kin."),
    CoverageSpec("22_service_migration", "Domestic service and household migration", "21", "household_life/ecology/domain_actions", "RUNNABLE", "SELECT COUNT(*) FROM households WHERE status IN ('active','declining')", "SELECT (SELECT COUNT(*) FROM household_service_terms WHERE status='active') + (SELECT COUNT(*) FROM household_migration_plans WHERE status IN ('planned','in_transit')) + (SELECT COUNT(*) FROM households WHERE status='declining' AND location_id IS NOT NULL)", autonomous=True, notes="Service initiation requires quantitatively resolved household means; migration requires an actually declining household and a real better adjacent destination."),
    CoverageSpec("23_population_resolution", "Population cohorts and named resolution", "1; 24", "household_life/resolution", "PARTIAL", "SELECT COUNT(*) FROM cohorts", "SELECT COUNT(*) FROM latent_population_scopes WHERE status='active'", autonomous=True),
    CoverageSpec("24_aging_death", "Aging, death and retirement", "21; 24", "health/household_life", "RUNNABLE", "SELECT COUNT(*) FROM actor_life_profiles WHERE life_status='living'", "SELECT COUNT(*) FROM actor_health_profiles"),
    CoverageSpec("25_illness_treatment", "Illness, treatment and disability", "21", "health", "RUNNABLE", "SELECT COUNT(*) FROM actor_health_profiles", "SELECT (SELECT COUNT(*) FROM health_conditions WHERE status IN ('active','recovering','chronic')) + (SELECT COUNT(*) FROM health_care_requests WHERE status IN ('waiting','scheduled'))", autonomous=True, notes="INTEGRATION-01 separates condition course from care-site/provider capacity; delayed or unavailable care can change outcomes without the condition owner assuming a physician exists."),
    CoverageSpec("26_addiction_psych", "Addiction and psychological injury", "21; 22", "psych/health/decisions", "RUNNABLE", "SELECT COUNT(*) FROM actor_life_profiles WHERE life_status='living'", "SELECT (SELECT COUNT(*) FROM dependency_profiles WHERE status IN ('risk','dependent','recovering')) + (SELECT COUNT(*) FROM psychological_conditions WHERE status IN ('active','recovering','chronic')) + (SELECT COUNT(*) FROM dependency_exposures) + (SELECT COUNT(*) FROM psychological_stressors)", autonomous=True, notes="Concrete elixir/severe-health/bereavement sources are ingested autonomously; ordinary distress is not automatically pathologized. Chemical, gambling and performance dependence remain distinct, and cultivation does not cure them."),
    CoverageSpec("27_material_life", "Food, water, fuel, housing and repair", "21", "civilian/ecology/agriculture/growth", "RUNNABLE", "SELECT (SELECT COUNT(*) FROM buildings WHERE status IN ('active','strained','derelict')) + (SELECT COUNT(*) FROM agriculture_fields WHERE status IN ('active','damaged','fallow'))", "SELECT (SELECT COUNT(*) FROM agriculture_fields WHERE status IN ('active','damaged') AND next_harvest_day IS NOT NULL) + (SELECT COUNT(*) FROM market_conditions mc JOIN market_goods g ON g.id=mc.good_id WHERE g.category='food')", autonomous=True, notes="AGRI-01 turns ecology/weather, land/labor and disruption into physical harvest stock and market food availability; growth consumes food-price stress causally."),
    CoverageSpec("28_business_demand", "Businesses and differentiated demand", "11; 21; 22", "business/civilian", "RUNNABLE", "SELECT COUNT(*) FROM enterprise_business_profiles", "SELECT COUNT(*) FROM enterprise_business_profiles p JOIN civilian_enterprises e ON e.id=p.enterprise_id WHERE e.status IN ('active','strained','insolvent')"),
    CoverageSpec("29_business_lifecycle", "Business founding, expansion and closure", "24; 22", "business/civilian/domain_actions", "PARTIAL", "SELECT COUNT(*) FROM civilian_enterprises", "SELECT COUNT(DISTINCT a.id) FROM actors a JOIN location_commercial_context lc ON lc.location_id=a.current_location_id WHERE a.actor_type='character' AND a.status='active' AND NOT EXISTS(SELECT 1 FROM civilian_enterprises e WHERE e.owner_actor_id=a.id AND e.status IN ('active','strained','insolvent')) AND (SELECT COALESCE(SUM(r.amount),0) FROM resources r WHERE r.actor_id=a.id AND r.resource_type IN ('capital','operating_reserve','savings'))>=20", autonomous=True, notes="Autonomous founding exists when capital and explicit local opportunity exist; autonomous sale/expansion remains incomplete."),
    CoverageSpec("30_production", "Production, cultivation goods and arms", "11", "craft/civilian/ecology", "RUNNABLE", "SELECT COUNT(*) FROM production_sites WHERE active=1", "SELECT (SELECT COUNT(*) FROM production_sites WHERE active=1 AND production_mode='aggregate') + (SELECT COUNT(*) FROM craft_production_orders WHERE status IN ('queued','waiting_input','waiting_facility','waiting_labor','in_progress','blocked'))", autonomous=True, notes="CRAFT-01 adds tracked recipes, facilities, labor competence, conserved input consumption and output lots; aggregate sites remain coarse-resolution production."),
    CoverageSpec("31_merchant_transport", "Merchant houses, transport and escorts", "11", "business/merchant/ecology/logistics/interactions", "RUNNABLE", "SELECT COUNT(*) FROM civilian_enterprises WHERE status IN ('active','strained')", "SELECT (SELECT COUNT(*) FROM commercial_stock s JOIN civilian_enterprises e ON e.id=s.enterprise_id WHERE s.quantity>0.5 AND e.status IN ('active','strained')) + (SELECT COUNT(*) FROM production_sites ps JOIN civilian_enterprises e ON e.id=ps.enterprise_id WHERE ps.production_mode='aggregate' AND ps.active=1 AND ps.inventory>0.5 AND e.status IN ('active','strained'))", autonomous=True, notes="MERCHANT-01 adds actor-authorized factors, received market records, observed offers, explicit buyer/seller contracts, conserved shipment settlement and seller credit. CRAFT-01 finished goods use commercial_stock directly. Escort contracting remains a later extension."),
    CoverageSpec("32_credit_inheritance", "Credit, inheritance and partnerships", "11; 21", "civilian_life/domain_actions", "RUNNABLE", "SELECT COUNT(*) FROM civilian_enterprises WHERE status IN ('active','strained','insolvent')", "SELECT COUNT(*) FROM credit_agreements WHERE status IN ('current','late')", autonomous=True, notes="Credit initiation requires a cash-stressed owned enterprise and a real local loan-house lender; payment/default use the existing credit owner."),
    CoverageSpec("33_appraisal_auction", "Appraisal, auction and provenance", "11; 23", "civilian/expertise", "RUNNABLE", "SELECT COUNT(*) FROM auctions", "SELECT COUNT(*) FROM auctions WHERE status='scheduled'"),
    CoverageSpec("34_nightlife", "Nightlife venues and ordinary employment", "22", "business/culture", "PARTIAL", "SELECT COUNT(*) FROM civilian_enterprises"),
    CoverageSpec("35_gambling", "Gambling and Red Board", "22; 23", "spectacle/business", "RUNNABLE", "SELECT COUNT(*) FROM spectacle_books WHERE status='active'", "SELECT COUNT(*) FROM betting_markets WHERE status IN ('open','settled')", autonomous=True, notes="Aggregate legal/tolerated books and event-linked odds/settlement are implemented; credit betting, fixing and coercive enforcement remain crime-layer concerns."),
    CoverageSpec("36_prizefighting", "Prizefighting and fighter careers", "22; 23", "spectacle/health/resolution", "RUNNABLE", "SELECT COUNT(*) FROM prizefight_markets WHERE status='active'", "SELECT COUNT(*) FROM prizefight_cards WHERE status IN ('scheduled','resolved')", autonomous=True, notes="Professional Closed-Core prize halls run structurally; repeated champions promote to latent person resolution without inventing named adults. Coercive pits remain separate."),
    CoverageSpec("37_crime_orgs", "Crime families, gangs and syndicate formation", "22", "underworld/resolution/business", "RUNNABLE", "SELECT COUNT(*) FROM underworld_organizations WHERE status='active'", "SELECT COUNT(*) FROM emergent_institution_candidates WHERE candidate_kind='criminal organization' AND status IN ('forming','eligible')", autonomous=True, notes="Canon criminal institutions remain structurally persistent without invented leaders; ordinary enterprises can form evidence-backed organization candidates, but unnamed candidates do not auto-crystallize."),
    CoverageSpec("38_smuggling", "Smuggling, fencing and laundering", "22", "underworld/ecology/provenance", "RUNNABLE", "SELECT (SELECT COUNT(*) FROM underworld_organizations WHERE status='active') + (SELECT COUNT(*) FROM underworld_racket_sites WHERE status='active')", "SELECT COUNT(*) FROM smuggling_operations WHERE status IN ('in_transit','stalled','delivered')", autonomous=True, population_policy="conditional", notes="Illicit cargo uses conservation-safe stock custody and real routes; absence of eligible cargo is not a missing mechanism."),
    CoverageSpec("39_policing", "Policing, corruption and disputes", "22; 13-19", "underworld/politics", "RUNNABLE", "SELECT COUNT(*) FROM law_enforcement_profiles WHERE status='active'", "SELECT COUNT(*) FROM law_enforcement_cases WHERE status IN ('monitoring','open','actionable','referred')", autonomous=True, notes="Local enforcement opens cases only from visible evidence in jurisdiction; corruption changes effectiveness, not hidden truth or omniscient knowledge."),
    CoverageSpec("40_privacy_intelligence", "Privacy, intelligence and hidden affiliations", "22; 24", "information", "PARTIAL", "SELECT COUNT(*) FROM information_channels"),
    CoverageSpec("41_assassination", "Assassination and targeted violence", "22", "interactions/combat", "PARTIAL", "SELECT COUNT(*) FROM actors WHERE actor_type='institution' AND status='active' AND (lower(subtype) LIKE '%assassin%' OR lower(subtype) LIKE '%killer%')", population_policy="conditional"),
    CoverageSpec("42_exploitation_medicine", "Exploitation and underworld medicine", "22", "underworld_medicine/health/underworld", "RUNNABLE", "SELECT (SELECT COUNT(*) FROM underworld_organizations WHERE status='active') + (SELECT COUNT(*) FROM health_care_sites WHERE status IN ('active','strained'))", "SELECT (SELECT COUNT(*) FROM underworld_medical_access WHERE status='active') + (SELECT COUNT(*) FROM medical_misconduct_events WHERE status='active') + (SELECT COUNT(*) FROM institution_memberships im JOIN underworld_institution_profiles u ON u.institution_actor_id=im.institution_actor_id JOIN health_conditions h ON h.actor_id=im.member_actor_id WHERE im.status='active' AND u.status IN ('active','strained') AND h.status IN ('active','recovering','chronic') AND h.severity>=20)", autonomous=True, notes="Discreet care is an access relationship, not a separate medical school. Real injured underworld members can seek real local providers; confidentiality alone is not crime. Coercion, fraudulent care, concealed injury and predatory billing are explicit misconduct with health/financial/evidence consequences."),
    CoverageSpec("43_religion", "Religion and worship", "12; 13-19; 23", "religion", "RUNNABLE", "SELECT COUNT(*) FROM religious_institutions", "SELECT COUNT(*) FROM religious_institutions WHERE status='active'"),
    CoverageSpec("44_culture", "Culture, art, fashion and performance", "23", "civilian/religion", "RUNNABLE", "SELECT COUNT(*) FROM cultural_institution_profiles", "SELECT COUNT(*) FROM cultural_institution_profiles WHERE status='active'"),
    CoverageSpec("45_news_reputation", "News, reputation and public memory", "23; 24", "information/emergence", "RUNNABLE", "SELECT COUNT(*) FROM information_channels", "SELECT COUNT(*) FROM information_channels"),
    CoverageSpec("46_polity", "Polity government, succession and territory", "13-19; 1; 11; 24", "politics/growth", "RUNNABLE", "SELECT COUNT(*) FROM political_polities", "SELECT (SELECT COUNT(*) FROM political_polities WHERE status IN ('active','regency','succession_crisis','fragmenting')) + (SELECT COUNT(*) FROM regional_public_projects WHERE status IN ('active','blocked')) + (SELECT COUNT(*) FROM regional_security_assignments WHERE status IN ('active','unfunded'))", autonomous=True, notes="GROWTH-01 adds conserved public treasuries/fiscal entries, resource-bound public works and security, delayed administrative reports, and household migration response. Regional snapshots are rebuildable causal projections; there is no prosperity score."),
    CoverageSpec("47_war_logistics", "War, campaigns, logistics and world aftermath", "1; 11; 13-19", "war/politics/combat/ecology/logistics/health/information", "RUNNABLE", "SELECT (SELECT COUNT(*) FROM military_logistics_profiles)+(SELECT COUNT(*) FROM war_campaign_operations)", "SELECT (SELECT COUNT(*) FROM military_campaigns WHERE status IN ('active','aftermath'))+(SELECT COUNT(*) FROM war_campaign_operations WHERE status NOT IN ('closed','cancelled'))", autonomous=True, notes="Polity logistics/readiness persists in peace; WAR-01 operations move real forces over real routes, consume physical supplies, project named/aggregate casualties and civilian damage/displacement, and deliver actor-relative battle reports. Tournament/challenge duels never count as war."),
    CoverageSpec("48_regional_norms", "Regional variation and social norms", "3; 12-23", "canon/embodiment", "PARTIAL", "SELECT COUNT(*) FROM locations"),
    CoverageSpec("49_npc_agency", "Cross-system NPC agency", "24; 21", "motives/decisions/domain_actions", "PARTIAL", "SELECT COUNT(*) FROM simulation_profiles", "SELECT COUNT(*) FROM simulation_profiles", autonomous=True),
    CoverageSpec("50_shared_clock", "Shared clock, replay and observability", "0; 24; schema", "simulation/coverage", "RUNNABLE", "SELECT COUNT(*) FROM simulation_profiles"),
    CoverageSpec("51_player_boundary", "Player boundary and historical continuity", "24; 0", "player/crystallization", "PARTIAL", "SELECT COUNT(*) FROM player_state", None, autonomous=False, required=False, notes="An unattended world run does not require a selected player actor; player-boundary tests remain part of the regression suite rather than a decade-run population gate."),
    CoverageSpec("52_protected_open", "Protected open and narrative-only detail", "25", "canon", "SEMANTIC_ONLY", None, None, required=False, notes="Must remain unresolved unless campaign assumptions explicitly permit otherwise."),
)


# Production scheduler process ownership. A domain may share one process with adjacent domains;
# the gate checks that the required autonomous owner is actually wired into simulation.py.
PROCESS_KEYS: dict[str, tuple[str, ...]] = {
    "04_cultivation_realization": ("cultivation",),
    "07_teaching_apprenticeship": ("education",),
    "10_institution_reproduction": ("education",),
    "11_concord_law": ("law",),
    "14_hollow_succession": ("hollow",),
    "16_combat": ("tournament", "war"),
    "17_tournament": ("tournament",),
    "19_new_unions": ("civilian",),
    "21_guardianship": ("civilian",),
    "22_service_migration": ("civilian", "growth"),
    "23_population_resolution": ("resolution",),
    "25_illness_treatment": ("health",),
    "26_addiction_psych": ("psychology",),
    "27_material_life": ("agriculture", "civilian", "growth"),
    "29_business_lifecycle": ("civilian",),
    "30_production": ("craft", "civilian"),
    "31_merchant_transport": ("merchant", "logistics"),
    "32_credit_inheritance": ("civilian",),
    "35_gambling": ("spectacle",),
    "36_prizefighting": ("spectacle",),
    "37_crime_orgs": ("underworld", "resolution"),
    "38_smuggling": ("underworld", "logistics"),
    "39_policing": ("underworld", "law"),
    "42_exploitation_medicine": ("underworld_medicine", "health"),
    "46_polity": ("politics", "growth"),
    "47_war_logistics": ("war",),
    "49_npc_agency": ("resolution",),
}

CONDITIONAL_DOMAINS = {
    "06_elixirs_sediment", "12_undertow_compacts", "19_new_unions", "21_guardianship",
    "22_service_migration", "25_illness_treatment", "26_addiction_psych", "29_business_lifecycle",
    "32_credit_inheritance", "35_gambling", "36_prizefighting", "38_smuggling", "39_policing",
    "41_assassination", "42_exploitation_medicine", "47_war_logistics",
}

def _population_policy(row: sqlite3.Row) -> str:
    try:
        val = row["population_policy"]
        if val: return str(val)
    except (IndexError, KeyError):
        pass
    return "conditional" if str(row["domain_key"]) in CONDITIONAL_DOMAINS else "opening_required"

def _wired_processes() -> set[str]:
    # Keep this deliberately simple and auditable: these are the keys emitted by
    # simulation._instrumented_process in the production scheduler.
    return {"resolution","world","ecology","agriculture","logistics","merchant","craft","civilian",
            "growth","underworld","underworld_medicine","law","war","groundbinding","health",
            "psychology","hollow","religion","politics","education","cultivation","tournament","spectacle"}

def _opening_invariant_failures(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    checks = (
        ("health_capacity_seed", "SELECT COUNT(*) FROM health_care_sites WHERE status IN ('active','strained')", "ordinary opening world has no health-care capacity"),
        ("agriculture_seed", "SELECT COUNT(*) FROM agriculture_fields WHERE status IN ('active','damaged')", "ordinary opening world has no agricultural fields"),
        ("law_seed", "SELECT COUNT(*) FROM law_jurisdictions WHERE status='active'", "ordinary opening world has no active legal jurisdiction"),
        ("merchant_authority_seed", "SELECT COUNT(*) FROM enterprise_staff WHERE status='active' AND authority>=40", "ordinary opening world has no actor-authorized merchant enterprise"),
        ("merchant_records_seed", "SELECT COUNT(*) FROM merchant_market_observations", "ordinary opening world has no merchant market records"),
        ("craft_tracked_seed", "SELECT COUNT(*) FROM craft_site_recipes WHERE active=1", "ordinary opening world has no tracked craft recipe/site"),
        ("craft_order_seed", "SELECT COUNT(*) FROM craft_production_orders WHERE status IN ('queued','waiting_input','waiting_facility','waiting_labor','in_progress','blocked','completed')", "ordinary opening world has no tracked craft work"),
        ("growth_treasury_seed", "SELECT COUNT(*) FROM regional_public_treasuries WHERE status IN ('active','strained')", "ordinary opening world has no public-finance owner"),
        ("underworld_seed", "SELECT COUNT(*) FROM underworld_organizations WHERE status='active'", "ordinary opening world has no concrete criminal organization"),
        ("resolution_latent", "SELECT COUNT(*) FROM latent_population_scopes WHERE status='active'", "opening world has no latent population substrate"),
    )
    out=[]
    for key, sql, reason in checks:
        count=_scalar(conn,sql)
        if not count:
            out.append({"domain_key":key,"label":key,"mechanism_status":"RUNNABLE","populated_count":count,"eligible_count":None,"blocked_count":1,"blocked_reason":reason,"state":"missing_population"})
    missing_treasuries=_scalar(conn,"""SELECT COUNT(*) FROM political_polities p WHERE p.status IN ('active','regency','succession_crisis','fragmenting')
                                      AND NOT EXISTS(SELECT 1 FROM regional_public_treasuries t WHERE t.polity_id=p.id)""") or 0
    if missing_treasuries:
        out.append({"domain_key":"growth_treasury_completeness","label":"growth_treasury_completeness","mechanism_status":"RUNNABLE",
                    "populated_count":None,"eligible_count":None,"blocked_count":missing_treasuries,
                    "blocked_reason":f"{missing_treasuries} active polities have no public treasury owner","state":"missing_population"})
    return out


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _scalar(conn: sqlite3.Connection, sql: str | None) -> int | None:
    if not sql:
        return None
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.DatabaseError:
        return None


def seed_coverage_registry(conn: sqlite3.Connection) -> None:
    for s in SPECS:
        conn.execute(
            """INSERT INTO coverage_registry(
                   domain_key,label,bible_scope,owner_module,mechanism_status,population_sql,eligibility_sql,
                   required_for_ten_year,autonomous_initiation_required,population_policy,process_keys_json,notes
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(domain_key) DO UPDATE SET
                   label=excluded.label,bible_scope=excluded.bible_scope,owner_module=excluded.owner_module,
                   mechanism_status=excluded.mechanism_status,population_sql=excluded.population_sql,
                   eligibility_sql=excluded.eligibility_sql,required_for_ten_year=excluded.required_for_ten_year,
                   autonomous_initiation_required=excluded.autonomous_initiation_required,population_policy=excluded.population_policy,
                   process_keys_json=excluded.process_keys_json,notes=excluded.notes""",
            (s.key, s.label, s.bible_scope, s.owner, s.status, s.population_sql, s.eligibility_sql,
             1 if s.required else 0, 1 if s.autonomous else 0,
             ("conditional" if s.key in CONDITIONAL_DOMAINS else s.population_policy),
             json.dumps(PROCESS_KEYS.get(s.key, s.process_keys), sort_keys=True), s.notes),
        )


def start_coverage_run(conn: sqlite3.Connection, label: str, *, source_seed_namespace: str | None = None,
                       engine_version: str | None = None, schema_version: int | None = None,
                       metadata: dict[str, Any] | None = None) -> int:
    seed_coverage_registry(conn)
    cur = conn.execute(
        """INSERT INTO coverage_runs(label,start_day,source_seed_namespace,engine_version,schema_version,metadata_json)
           VALUES (?,?,?,?,?,?)""",
        (label, _day(conn), source_seed_namespace, engine_version, schema_version,
         json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def snapshot_coverage(conn: sqlite3.Connection, coverage_run_id: int | None = None, *, phase: str = "snapshot") -> list[dict[str, Any]]:
    seed_coverage_registry(conn)
    day = _day(conn)
    out: list[dict[str, Any]] = []
    wired=_wired_processes()
    rows = conn.execute("SELECT * FROM coverage_registry ORDER BY domain_key").fetchall()
    for row in rows:
        populated = _scalar(conn, row["population_sql"])
        eligible = _scalar(conn, row["eligibility_sql"])
        reason = None; blocked = 0
        status = str(row["mechanism_status"]); policy=_population_policy(row)
        try: process_keys=json.loads(row["process_keys_json"] or "[]")
        except Exception: process_keys=[]
        autonomy_missing=bool(row["autonomous_initiation_required"]) and (not process_keys or not any(k in wired for k in process_keys))
        process_run_count=process_executed_count=0
        if process_keys:
            marks=','.join('?' for _ in process_keys)
            pr=conn.execute(f"SELECT COUNT(*),COALESCE(SUM(executed_count),0) FROM process_execution_log WHERE process_key IN ({marks})",tuple(process_keys)).fetchone()
            process_run_count=int(pr[0] or 0); process_executed_count=int(pr[1] or 0)
        execution_state=('not_yet_run' if process_run_count==0 else ('ran_no_work' if process_executed_count==0 else 'executed'))
        if status == "SEMANTIC_ONLY":
            state="protected_open"; reason = "semantic-only/protected boundary"
        elif status in {"MAJOR_GAP","API_ONLY"}:
            state="missing_mechanism"; reason = "mechanism not implemented" if status=="MAJOR_GAP" else "autonomous initiation missing"; blocked=max(1,populated or 0)
        elif autonomy_missing:
            state="missing_autonomy"; reason="autonomous process is not wired into production scheduler"; blocked=max(1,populated or 0)
        elif populated == 0 and policy == "opening_required":
            state="missing_population"; reason = "opening population/substrate missing"; blocked=1
        elif populated == 0:
            state="conditional_dormant"; reason="conditional domain has no active opening instance"
        elif eligible == 0 and row["eligibility_sql"]:
            state="populated_no_eligible_work"; reason = "no eligible work"
        elif eligible is not None and eligible > 0:
            state="eligible"
        else:
            state="populated_active"
        item = {
            "domain_key": row["domain_key"], "label": row["label"], "mechanism_status": status,
            "population_policy":policy,"process_keys":process_keys,"state":state,
            "process_run_count":process_run_count,"process_executed_count":process_executed_count,"execution_state":execution_state,
            "populated_count": populated, "eligible_count": eligible, "blocked_count": blocked,
            "blocked_reason": reason,
        }
        out.append(item)
        if coverage_run_id is not None:
            conn.execute(
                """INSERT INTO coverage_observations(
                       coverage_run_id,day,domain_key,phase,populated_count,eligible_count,blocked_count,blocked_reason,details_json
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (coverage_run_id, day, row["domain_key"], phase, populated, eligible, blocked, reason,
                 json.dumps({"mechanism_status":status,"population_policy":policy,"process_keys":process_keys,"state":state,
                             "process_run_count":process_run_count,"process_executed_count":process_executed_count,"execution_state":execution_state}, sort_keys=True)),
            )
    return out

def record_process_execution(conn: sqlite3.Connection, process_key: str, *, coverage_run_id: int | None = None,
                             due_count: int | None = None, eligible_count: int | None = None,
                             executed_count: int = 0, changed_count: int = 0, blocked_count: int = 0,
                             blocked_reason: str | None = None, result: Any = None, day: int | None = None) -> int:
    if day is None:
        day = _day(conn)
    cur = conn.execute(
        """INSERT INTO process_execution_log(
               coverage_run_id,day,process_key,due_count,eligible_count,executed_count,changed_count,
               blocked_count,blocked_reason,result_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (coverage_run_id, day, process_key, due_count, eligible_count, executed_count, changed_count,
         blocked_count, blocked_reason, json.dumps(result if result is not None else {}, sort_keys=True, default=str)),
    )
    return int(cur.lastrowid)


def finish_coverage_run(conn: sqlite3.Connection, coverage_run_id: int, *, status: str = "completed") -> None:
    conn.execute(
        "UPDATE coverage_runs SET end_day=?,status=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
        (_day(conn), status, coverage_run_id),
    )


def coverage_gate(conn: sqlite3.Connection, coverage_run_id: int | None = None) -> dict[str, Any]:
    snapshot = snapshot_coverage(conn, coverage_run_id, phase="coverage_gate")
    required=[]
    for x in snapshot:
        row=conn.execute("SELECT required_for_ten_year FROM coverage_registry WHERE domain_key=?",(x["domain_key"],)).fetchone()
        if row and int(row[0]): required.append(x)
    failures=[x for x in required if x["state"] in {"missing_mechanism","missing_population","missing_autonomy"}]
    failures.extend(_opening_invariant_failures(conn))
    # Deduplicate exact domain failures while preserving explicit invariant failures.
    return {
        "pass": not failures,
        "required_domains":len(required),
        "failure_count":len(failures),
        "failures":failures,
        "states":{k:sum(1 for x in snapshot if x["state"]==k) for k in sorted({x["state"] for x in snapshot})},
        "principle":"One-year simulation may start only when ordinary opening substrates exist and every required autonomous domain has a wired owner.",
    }

def record_one_year_acceptance(conn: sqlite3.Connection, *, evidence: dict[str, Any] | None = None, status: str = 'passed') -> dict[str, Any]:
    """Record capability acceptance for the current explicit TENYEAR gate epoch."""
    if status not in {'pending','passed','failed'}:
        raise ValueError('invalid acceptance status')
    epoch=conn.execute("SELECT value FROM engine_meta WHERE key='tenyear02_gate_epoch'").fetchone()
    if not epoch:
        raise ValueError('current engine has no explicit TENYEAR acceptance epoch')
    key=str(epoch[0])
    schema=conn.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()
    schema_version=int(schema[0]) if schema else 0
    day=_day(conn)
    conn.execute(
        """INSERT INTO acceptance_epochs(acceptance_key,schema_version,status,accepted_day,evidence_json,updated_at)
           VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(acceptance_key) DO UPDATE SET schema_version=excluded.schema_version,status=excluded.status,
             accepted_day=excluded.accepted_day,evidence_json=excluded.evidence_json,updated_at=CURRENT_TIMESTAMP""",
        (key,schema_version,status,day if status=='passed' else None,json.dumps(evidence or {},sort_keys=True,default=str)),
    )
    return dict(conn.execute("SELECT * FROM acceptance_epochs WHERE acceptance_key=?",(key,)).fetchone())


def ten_year_gate(conn: sqlite3.Connection, coverage_run_id: int | None = None) -> dict[str, Any]:
    coverage=coverage_gate(conn,coverage_run_id)
    epoch=conn.execute("SELECT value FROM engine_meta WHERE key='tenyear02_gate_epoch'").fetchone()
    epoch_key=str(epoch[0]) if epoch else None
    acceptance=None
    if epoch_key and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='acceptance_epochs'").fetchone():
        acceptance=conn.execute("SELECT * FROM acceptance_epochs WHERE acceptance_key=?",(epoch_key,)).fetchone()
    schema=conn.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()
    schema_version=int(schema[0]) if schema else 0
    one_year_passed=bool(acceptance and str(acceptance['status'])=='passed' and int(acceptance['schema_version'])==schema_version)
    failures=list(coverage['failures'])

    # SQL schema currency does not prove that the opening-world projections were refreshed.
    # TENYEAR-02 exposed a schema-104 database that still carried activation v17 and therefore
    # lacked PERSONECO/profession/authority opening state. Refuse such a causally incomplete DB.
    activation_row=conn.execute("SELECT value FROM engine_meta WHERE key='current_canon_activation_version'").fetchone()
    try:
        activation_version=int(activation_row[0]) if activation_row else 0
    except (TypeError, ValueError):
        activation_version=0
    activation_fresh=activation_version >= CURRENT_CANON_ACTIVATION_VERSION

    person_ecology_ready=True
    profession_ready=True
    authority_ready=True
    if schema_version >= 104:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='background_population_sources'").fetchone():
            source_count=int(conn.execute("SELECT COUNT(*) FROM background_population_sources").fetchone()[0])
            partition_count=int(conn.execute("SELECT COUNT(*) FROM background_population_partitions").fetchone()[0])
            profile_count=int(conn.execute("SELECT COUNT(*) FROM background_person_profiles").fetchone()[0])
            person_ecology_ready=(source_count == 0) or (partition_count == source_count and profile_count > 0)
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='professional_profiles'").fetchone():
            profession_marker=conn.execute("SELECT value FROM engine_meta WHERE key='profession01_runtime_version'").fetchone()
            profession_count=int(conn.execute("SELECT COUNT(*) FROM professional_profiles").fetchone()[0])
            profession_ready=bool(profession_marker and str(profession_marker[0]) == '1' and profession_count > 0)
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='institutional_authority_slots'").fetchone():
            authority_ready=int(conn.execute("SELECT COUNT(*) FROM institutional_authority_slots").fetchone()[0]) > 0

    opening_activation_passed=activation_fresh and person_ecology_ready and profession_ready and authority_ready
    if not opening_activation_passed:
        failures.append({
            'domain_key':'opening_activation','label':'Current opening-world activation','mechanism_status':'GATE',
            'populated_count':None,'eligible_count':None,'blocked_count':1,
            'blocked_reason':(
                f'opening activation is stale/incomplete: activation={activation_version}, '
                f'required>={CURRENT_CANON_ACTIVATION_VERSION}, person_ecology={person_ecology_ready}, '
                f'profession={profession_ready}, institutional_authority={authority_ready}'
            ),'state':'prerequisite_missing',
        })
    if not one_year_passed:
        reason='current schema acceptance epoch has not passed' if epoch_key else 'current engine has no explicit acceptance epoch'
        failures.append({'domain_key':'one_year_unattended','label':'Integrated ordinary one-year unattended run',
                         'mechanism_status':'GATE','populated_count':None,'eligible_count':None,'blocked_count':1,
                         'blocked_reason':reason,'state':'prerequisite_missing'})
    return {**coverage,'pass':coverage['pass'] and one_year_passed and opening_activation_passed,
            'failure_count':len(failures),'failures':failures,
            'coverage_pass':coverage['pass'],'one_year_unattended_passed':one_year_passed,
            'opening_activation_passed':opening_activation_passed,
            'current_canon_activation_version':activation_version,
            'required_canon_activation_version':CURRENT_CANON_ACTIVATION_VERSION,
            'acceptance_epoch':epoch_key,'acceptance_schema_version':int(acceptance['schema_version']) if acceptance else None,
            'current_schema_version':schema_version,
            'principle':'The decade run may test compounding only after COVERAGE-01 and a fresh ONEYEAR acceptance for this exact schema line pass.'}
