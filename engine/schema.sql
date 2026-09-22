PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS world_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    world_name TEXT NOT NULL DEFAULT 'Caerness',
    current_day INTEGER NOT NULL DEFAULT 0,
    epoch_label TEXT NOT NULL DEFAULT 'Day',
    rng_seed INTEGER NOT NULL DEFAULT 812197,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    parent_location_id INTEGER REFERENCES locations(id),
    political_owner TEXT,
    notes TEXT,
    is_canon INTEGER NOT NULL DEFAULT 0 CHECK (is_canon IN (0,1)),
    identity_certainty TEXT NOT NULL DEFAULT 'UNSPECIFIED',
    placement_certainty TEXT NOT NULL DEFAULT 'UNSPECIFIED',
    coordinate_status TEXT NOT NULL DEFAULT 'OPEN_NOT_REQUIRED',
    source_anchor TEXT
);

CREATE TABLE IF NOT EXISTS actors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('character','institution')),
    subtype TEXT,
    home_location_id INTEGER REFERENCES locations(id),
    current_location_id INTEGER REFERENCES locations(id),
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0,1))
);

CREATE TABLE IF NOT EXISTS simulation_profiles (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    tier TEXT NOT NULL CHECK (tier IN ('ACTIVE','STRATEGIC','DORMANT')),
    cadence_days INTEGER NOT NULL CHECK (cadence_days >= 1),
    volatility REAL NOT NULL DEFAULT 0.25 CHECK (volatility >= 0 AND volatility <= 1),
    agency REAL NOT NULL DEFAULT 0.5 CHECK (agency >= 0 AND agency <= 1),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 1,
    forced_tier TEXT CHECK (forced_tier IN ('ACTIVE','STRATEGIC','DORMANT')),
    forced_until_day INTEGER,
    wake_threshold INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    min_value REAL,
    max_value REAL,
    updated_day INTEGER NOT NULL DEFAULT 0,
    UNIQUE(actor_id, key)
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
    progress REAL NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','failed','paused')),
    created_day INTEGER NOT NULL,
    target_day INTEGER
);

CREATE TABLE IF NOT EXISTS pressures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    description TEXT NOT NULL,
    intensity REAL NOT NULL DEFAULT 0 CHECK (intensity >= 0),
    threshold REAL NOT NULL DEFAULT 10 CHECK (threshold > 0),
    updated_day INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_simulation_profiles_next_review ON simulation_profiles(next_review_day,actor_id);
CREATE INDEX IF NOT EXISTS idx_goals_actor_status_priority ON goals(actor_id,status,priority DESC,id);
CREATE INDEX IF NOT EXISTS idx_pressures_actor_intensity ON pressures(actor_id,intensity DESC,id);

CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'local',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','resolved','failed','dormant')),
    progress REAL NOT NULL DEFAULT 0,
    severity INTEGER NOT NULL DEFAULT 1 CHECK (severity BETWEEN 1 AND 5),
    location_id INTEGER REFERENCES locations(id),
    created_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS thread_actors (
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    role TEXT,
    PRIMARY KEY(thread_id, actor_id)
);

CREATE TABLE IF NOT EXISTS clocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    due_day INTEGER NOT NULL,
    owner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    thread_id INTEGER REFERENCES threads(id) ON DELETE SET NULL,
    severity INTEGER NOT NULL DEFAULT 2 CHECK (severity BETWEEN 1 AND 5),
    resolution_type TEXT NOT NULL DEFAULT 'generic',
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','resolved','cancelled')),
    created_day INTEGER NOT NULL,
    resolved_day INTEGER
);

CREATE INDEX IF NOT EXISTS idx_clocks_due ON clocks(status, due_day);

CREATE TABLE IF NOT EXISTS background_processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    process_type TEXT NOT NULL,
    metric_key TEXT,
    rate_per_30_days REAL NOT NULL DEFAULT 0,
    volatility REAL NOT NULL DEFAULT 0.25 CHECK (volatility >= 0 AND volatility <= 1),
    accumulator REAL NOT NULL DEFAULT 0,
    event_threshold REAL NOT NULL DEFAULT 10 CHECK (event_threshold > 0),
    last_resolved_day INTEGER NOT NULL DEFAULT 0,
    event_severity INTEGER NOT NULL DEFAULT 2 CHECK (event_severity BETWEEN 1 AND 5),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    severity INTEGER NOT NULL DEFAULT 1 CHECK (severity BETWEEN 1 AND 5),
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    source_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_day ON events(day, id);

CREATE TABLE IF NOT EXISTS event_targets (
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    impact TEXT,
    PRIMARY KEY(event_id, actor_id)
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    stance REAL NOT NULL DEFAULT 0 CHECK (stance BETWEEN -100 AND 100),
    familiarity REAL NOT NULL DEFAULT 0 CHECK (familiarity BETWEEN 0 AND 100),
    trust REAL NOT NULL DEFAULT 0 CHECK (trust BETWEEN -100 AND 100),
    affection REAL NOT NULL DEFAULT 0 CHECK (affection BETWEEN -100 AND 100),
    respect REAL NOT NULL DEFAULT 0 CHECK (respect BETWEEN -100 AND 100),
    fear REAL NOT NULL DEFAULT 0 CHECK (fear BETWEEN -100 AND 100),
    loyalty REAL NOT NULL DEFAULT 0 CHECK (loyalty BETWEEN -100 AND 100),
    resentment REAL NOT NULL DEFAULT 0 CHECK (resentment BETWEEN -100 AND 100),
    obligation REAL NOT NULL DEFAULT 0,
    professional_confidence REAL NOT NULL DEFAULT 0 CHECK (professional_confidence BETWEEN -100 AND 100),
    updated_day INTEGER NOT NULL DEFAULT 0,
    UNIQUE(actor_a_id, actor_b_id),
    CHECK(actor_a_id <> actor_b_id)
);

CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    unit TEXT,
    updated_day INTEGER NOT NULL DEFAULT 0,
    UNIQUE(actor_id, resource_type)
);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knower_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    fact_key TEXT NOT NULL,
    belief_text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    truth_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    learned_day INTEGER NOT NULL,
    UNIQUE(knower_actor_id, fact_key)
);

CREATE TABLE IF NOT EXISTS rumours (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_day INTEGER NOT NULL,
    origin_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    truth_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    distortion REAL NOT NULL DEFAULT 0.25 CHECK (distortion >= 0 AND distortion <= 1),
    reach REAL NOT NULL DEFAULT 0.1 CHECK (reach >= 0 AND reach <= 1),
    status TEXT NOT NULL DEFAULT 'circulating' CHECK (status IN ('circulating','faded','confirmed','disproved'))
);
CREATE INDEX IF NOT EXISTS idx_rumours_truth_event ON rumours(truth_event_id);

CREATE TABLE IF NOT EXISTS player_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    player_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    current_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    campaign_name TEXT,
    updated_day INTEGER NOT NULL DEFAULT 0
);

-- v0.2: canon retrieval and structured actor decisions
CREATE TABLE IF NOT EXISTS engine_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canon_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    chunk_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS canon_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES canon_sources(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading_path TEXT,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    UNIQUE(source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_canon_chunks_source ON canon_chunks(source_id, chunk_index);

CREATE TABLE IF NOT EXISTS actor_constraints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    constraint_type TEXT NOT NULL DEFAULT 'soft' CHECK (constraint_type IN ('hard','soft')),
    weight REAL NOT NULL DEFAULT 1.0 CHECK (weight >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);

CREATE TABLE IF NOT EXISTS actor_drives (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    aggression REAL NOT NULL DEFAULT 0.5 CHECK (aggression BETWEEN 0 AND 1),
    risk_tolerance REAL NOT NULL DEFAULT 0.5 CHECK (risk_tolerance BETWEEN 0 AND 1),
    patience REAL NOT NULL DEFAULT 0.5 CHECK (patience BETWEEN 0 AND 1),
    loyalty REAL NOT NULL DEFAULT 0.5 CHECK (loyalty BETWEEN 0 AND 1),
    ambition REAL NOT NULL DEFAULT 0.5 CHECK (ambition BETWEEN 0 AND 1),
    pragmatism REAL NOT NULL DEFAULT 0.5 CHECK (pragmatism BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    tier TEXT NOT NULL CHECK (tier IN ('ACTIVE','STRATEGIC','DORMANT')),
    action_type TEXT NOT NULL,
    target_goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    target_pressure_id INTEGER REFERENCES pressures(id) ON DELETE SET NULL,
    score REAL NOT NULL,
    rationale TEXT NOT NULL,
    canon_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    effects_json TEXT NOT NULL DEFAULT '{}',
    outcome_summary TEXT,
    status TEXT NOT NULL DEFAULT 'applied' CHECK (status IN ('proposed','applied','rejected','failed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_decisions_actor_day ON decisions(actor_id, day, id);

CREATE TABLE IF NOT EXISTS actor_context_cache (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    generated_day INTEGER NOT NULL,
    canon_query TEXT NOT NULL,
    canon_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    context_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- v0.3: causal inter-actor interaction layer
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_day INTEGER NOT NULL,
    proposer_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    recipient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    interaction_type TEXT NOT NULL CHECK (interaction_type IN (
        'conversation','offer','request','contract','alliance','negotiation','mediation','demand','threat','investigation','attack'
    )),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending','accepted','rejected','countered','resolved','expired','cancelled'
    )),
    thread_id INTEGER REFERENCES threads(id) ON DELETE SET NULL,
    parent_interaction_id INTEGER REFERENCES interactions(id) ON DELETE SET NULL,
    urgency INTEGER NOT NULL DEFAULT 2 CHECK (urgency BETWEEN 1 AND 5),
    stakes INTEGER NOT NULL DEFAULT 2 CHECK (stakes BETWEEN 1 AND 5),
    terms_json TEXT NOT NULL DEFAULT '{}',
    rationale TEXT,
    canon_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    response_due_day INTEGER NOT NULL,
    resolved_day INTEGER,
    resolution_summary TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(proposer_actor_id <> recipient_actor_id)
);

CREATE INDEX IF NOT EXISTS idx_interactions_due ON interactions(status,response_due_day,id);
CREATE INDEX IF NOT EXISTS idx_interactions_actors ON interactions(proposer_actor_id,recipient_actor_id,created_day);

CREATE TABLE IF NOT EXISTS interaction_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_id INTEGER NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_interaction_actions ON interaction_actions(interaction_id,day,id);

CREATE TABLE IF NOT EXISTS agreements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agreement_type TEXT NOT NULL CHECK (agreement_type IN (
        'contract','alliance','service','understanding','concession','truce','debt','other'
    )),
    actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    created_day INTEGER NOT NULL,
    expiry_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','fulfilled','broken','expired','cancelled')),
    terms_json TEXT NOT NULL DEFAULT '{}',
    source_interaction_id INTEGER REFERENCES interactions(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(actor_a_id <> actor_b_id)
);

CREATE INDEX IF NOT EXISTS idx_agreements_actors ON agreements(actor_a_id,actor_b_id,status);

-- v0.3 provenance graph: inspect why one piece of state exists.
CREATE TABLE IF NOT EXISTS causal_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('decision','interaction','event','clock','agreement','player_action','world_process')),
    source_id INTEGER NOT NULL,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('decision','interaction','event','thread','agreement','knowledge','pressure')),
    target_id INTEGER NOT NULL,
    relation TEXT NOT NULL DEFAULT 'caused',
    UNIQUE(source_kind,source_id,target_kind,target_id,relation)
);

CREATE INDEX IF NOT EXISTS idx_causal_source ON causal_links(source_kind,source_id);
CREATE INDEX IF NOT EXISTS idx_causal_target ON causal_links(target_kind,target_id);

-- v0.4: information ecology, player knowledge, and scene packets
CREATE TABLE IF NOT EXISTS event_information (
    event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    visibility TEXT NOT NULL DEFAULT 'limited' CHECK (visibility IN ('public','limited','private','secret')),
    secrecy REAL NOT NULL DEFAULT 0.5 CHECK (secrecy BETWEEN 0 AND 1),
    rumorability REAL NOT NULL DEFAULT 0.5 CHECK (rumorability BETWEEN 0 AND 1),
    reliability REAL NOT NULL DEFAULT 0.8 CHECK (reliability BETWEEN 0 AND 1),
    registered_day INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_information_rumourable ON event_information(visibility,rumorability,event_id);

CREATE TABLE IF NOT EXISTS event_witnesses (
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    witness_type TEXT NOT NULL DEFAULT 'participant' CHECK (witness_type IN ('source','target','participant','observer','briefed')),
    confidence REAL NOT NULL DEFAULT 0.9 CHECK (confidence BETWEEN 0 AND 1),
    learned_day INTEGER NOT NULL,
    PRIMARY KEY(event_id, actor_id)
);

CREATE TABLE IF NOT EXISTS location_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_a_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    location_b_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    route_kind TEXT NOT NULL DEFAULT 'road',
    travel_days INTEGER NOT NULL DEFAULT 7 CHECK (travel_days >= 1),
    traffic REAL NOT NULL DEFAULT 0.5 CHECK (traffic BETWEEN 0 AND 1),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    notes TEXT,
    CHECK(location_a_id <> location_b_id),
    UNIQUE(location_a_id, location_b_id)
);

CREATE TABLE IF NOT EXISTS information_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    channel_kind TEXT NOT NULL,
    owner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    speed_multiplier REAL NOT NULL DEFAULT 1.0 CHECK (speed_multiplier > 0),
    fidelity REAL NOT NULL DEFAULT 0.8 CHECK (fidelity BETWEEN 0 AND 1),
    secrecy REAL NOT NULL DEFAULT 0.5 CHECK (secrecy BETWEEN 0 AND 1),
    public_access INTEGER NOT NULL DEFAULT 0 CHECK (public_access IN (0,1)),
    notes TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0,1))
);

CREATE TABLE IF NOT EXISTS channel_locations (
    channel_id INTEGER NOT NULL REFERENCES information_channels(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    strength REAL NOT NULL DEFAULT 0.75 CHECK (strength BETWEEN 0 AND 1),
    PRIMARY KEY(channel_id, location_id)
);

CREATE TABLE IF NOT EXISTS channel_memberships (
    channel_id INTEGER NOT NULL REFERENCES information_channels(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    role TEXT,
    access_level REAL NOT NULL DEFAULT 0.5 CHECK (access_level BETWEEN 0 AND 1),
    PRIMARY KEY(channel_id, actor_id)
);

CREATE TABLE IF NOT EXISTS rumour_locations (
    rumour_id INTEGER NOT NULL REFERENCES rumours(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    first_arrived_day INTEGER NOT NULL,
    last_updated_day INTEGER NOT NULL,
    prevalence REAL NOT NULL DEFAULT 0.25 CHECK (prevalence BETWEEN 0 AND 1),
    fidelity REAL NOT NULL DEFAULT 0.7 CHECK (fidelity BETWEEN 0 AND 1),
    hop_count INTEGER NOT NULL DEFAULT 0 CHECK (hop_count >= 0),
    PRIMARY KEY(rumour_id, location_id)
);

CREATE TABLE IF NOT EXISTS rumour_transmissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rumour_id INTEGER NOT NULL REFERENCES rumours(id) ON DELETE CASCADE,
    from_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    to_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    channel_id INTEGER REFERENCES information_channels(id) ON DELETE SET NULL,
    due_day INTEGER NOT NULL,
    fidelity REAL NOT NULL DEFAULT 0.7 CHECK (fidelity BETWEEN 0 AND 1),
    prevalence REAL NOT NULL DEFAULT 0.2 CHECK (prevalence BETWEEN 0 AND 1),
    hop_count INTEGER NOT NULL DEFAULT 1 CHECK (hop_count >= 1),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','delivered','cancelled')),
    UNIQUE(rumour_id, to_location_id)
);

CREATE INDEX IF NOT EXISTS idx_rumour_transmissions_due ON rumour_transmissions(status,due_day,id);

CREATE TABLE IF NOT EXISTS rumour_exposures (
    rumour_id INTEGER NOT NULL REFERENCES rumours(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    heard_day INTEGER NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    source_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    channel_id INTEGER REFERENCES information_channels(id) ON DELETE SET NULL,
    PRIMARY KEY(rumour_id, actor_id)
);

CREATE TABLE IF NOT EXISTS knowledge_provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id INTEGER NOT NULL REFERENCES knowledge(id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('event','rumour','actor','channel','scene','admin')),
    source_id INTEGER,
    channel_id INTEGER REFERENCES information_channels(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    acquired_day INTEGER NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_knowledge_provenance_knowledge ON knowledge_provenance(knowledge_id,id);

CREATE TABLE IF NOT EXISTS information_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('event','rumour','knowledge','channel','transmission')),
    source_id INTEGER NOT NULL,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('rumour','knowledge','transmission','scene_packet','location_presence')),
    target_id INTEGER NOT NULL,
    relation TEXT NOT NULL DEFAULT 'informed',
    UNIQUE(source_kind,source_id,target_kind,target_id,relation)
);

CREATE TABLE IF NOT EXISTS scene_packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    player_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    request_text TEXT,
    canon_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scene_packets_player_day ON scene_packets(player_actor_id,day,id);


-- v0.5: player action loop and observer-independent regional simulation
CREATE TABLE IF NOT EXISTS location_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    min_value REAL,
    max_value REAL,
    updated_day INTEGER NOT NULL DEFAULT 0,
    UNIQUE(location_id, key)
);

CREATE TABLE IF NOT EXISTS world_processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    process_type TEXT NOT NULL,
    metric_key TEXT,
    rate_per_30_days REAL NOT NULL DEFAULT 0,
    volatility REAL NOT NULL DEFAULT 0.25 CHECK (volatility BETWEEN 0 AND 1),
    accumulator REAL NOT NULL DEFAULT 0,
    event_threshold REAL NOT NULL DEFAULT 10 CHECK (event_threshold > 0),
    event_severity INTEGER NOT NULL DEFAULT 2 CHECK (event_severity BETWEEN 1 AND 5),
    cadence_days INTEGER NOT NULL DEFAULT 14 CHECK (cadence_days >= 1),
    last_resolved_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 14,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    notes TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_world_process_due ON world_processes(active,next_review_day,id);

CREATE TABLE IF NOT EXISTS player_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_started INTEGER NOT NULL,
    day_resolved INTEGER,
    player_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN (
        'observe','wait','travel','speak','investigate','respond','attempt'
    )),
    target_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    target_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    interaction_id INTEGER REFERENCES interactions(id) ON DELETE SET NULL,
    response_choice TEXT CHECK (response_choice IN ('accept','reject','counter') OR response_choice IS NULL),
    proposed_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN (
        'proposed','applied','needs_interpretation','invalid','failed'
    )),
    duration_days INTEGER NOT NULL DEFAULT 0 CHECK (duration_days >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_player_actions_day ON player_actions(player_actor_id,day_started,id);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    day_started INTEGER NOT NULL,
    day_ended INTEGER NOT NULL,
    raw_input TEXT NOT NULL,
    player_action_id INTEGER REFERENCES player_actions(id) ON DELETE SET NULL,
    pre_scene_packet_id INTEGER REFERENCES scene_packets(id) ON DELETE SET NULL,
    post_scene_packet_id INTEGER REFERENCES scene_packets(id) ON DELETE SET NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    narration_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_turns_player_day ON turns(player_actor_id,day_started,id);

-- v0.6: provider-neutral model gateway and manual ChatGPT/Claude bridge
CREATE TABLE IF NOT EXISTS model_config (
    id INTEGER PRIMARY KEY CHECK (id=1),
    action_provider TEXT NOT NULL DEFAULT 'manual_chatgpt',
    decision_provider TEXT NOT NULL DEFAULT 'rules',
    narrator_provider TEXT NOT NULL DEFAULT 'manual_chatgpt',
    packet_dir TEXT NOT NULL DEFAULT 'game/campaign_01/model_requests',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO model_config(id) VALUES (1);

CREATE TABLE IF NOT EXISTS model_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    task_type TEXT NOT NULL CHECK (task_type IN ('action_interpretation','npc_decision','narration')),
    provider TEXT NOT NULL CHECK (provider IN ('chatgpt','claude','generic','local')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','responded','applied','cancelled','error')),
    target_kind TEXT,
    target_id INTEGER,
    input_json TEXT NOT NULL,
    response_raw TEXT,
    response_json TEXT,
    packet_path TEXT,
    applied_summary TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TEXT,
    applied_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_model_requests_status ON model_requests(status,task_type,id);
CREATE INDEX IF NOT EXISTS idx_model_requests_target ON model_requests(target_kind,target_id,id);


-- v0.7: mobile/local runtime, competence, emergence, agency handoffs, and player-facing attention
CREATE TABLE IF NOT EXISTS runtime_config (
    id INTEGER PRIMARY KEY CHECK (id=1),
    device_profile TEXT NOT NULL DEFAULT 'oneplus12_12gb',
    local_backend TEXT NOT NULL DEFAULT 'openai_compatible' CHECK (local_backend IN ('openai_compatible','ollama_native','disabled')),
    local_endpoint TEXT NOT NULL DEFAULT 'http://127.0.0.1:8080/v1/chat/completions',
    local_model TEXT NOT NULL DEFAULT 'local-model',
    local_timeout_seconds INTEGER NOT NULL DEFAULT 180 CHECK (local_timeout_seconds >= 5),
    local_max_context_tokens INTEGER NOT NULL DEFAULT 4096 CHECK (local_max_context_tokens >= 512),
    local_heavy_context_tokens INTEGER NOT NULL DEFAULT 6144 CHECK (local_heavy_context_tokens >= local_max_context_tokens),
    local_max_output_tokens INTEGER NOT NULL DEFAULT 1200 CHECK (local_max_output_tokens >= 128),
    referral_sensitivity TEXT NOT NULL DEFAULT 'balanced' CHECK (referral_sensitivity IN ('rare','balanced','quality_first')),
    referral_for_quality INTEGER NOT NULL DEFAULT 1 CHECK (referral_for_quality IN (0,1)),
    referral_for_reasoning INTEGER NOT NULL DEFAULT 1 CHECK (referral_for_reasoning IN (0,1)),
    referral_for_hardware INTEGER NOT NULL DEFAULT 1 CHECK (referral_for_hardware IN (0,1)),
    realtime_calendar_progression INTEGER NOT NULL DEFAULT 0 CHECK (realtime_calendar_progression IN (0,1)),
    auto_backup_every_turns INTEGER NOT NULL DEFAULT 10 CHECK (auto_backup_every_turns >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO runtime_config(id) VALUES (1);

CREATE TABLE IF NOT EXISTS possessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    holder_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    legal_owner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT 'item',
    quantity REAL NOT NULL DEFAULT 1 CHECK (quantity >= 0),
    status TEXT NOT NULL DEFAULT 'held' CHECK (status IN ('held','transferred','lost','consumed','destroyed')),
    acquired_day INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS character_intentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    intention_kind TEXT NOT NULL,
    description TEXT NOT NULL,
    target_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    target_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    possession_id INTEGER REFERENCES possessions(id) ON DELETE SET NULL,
    due_day INTEGER,
    trigger_kind TEXT NOT NULL DEFAULT 'manual' CHECK (trigger_kind IN ('manual','actor_present','location_present','due_day','on_departure','on_arrival')),
    auto_policy TEXT NOT NULL DEFAULT 'routine' CHECK (auto_policy IN ('routine','remind','ask_if_changed','manual')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','fulfilled','suspended','cancelled','blocked','failed')),
    source_kind TEXT,
    source_id INTEGER,
    condition_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL,
    fulfilled_day INTEGER,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_intentions_actor_status ON character_intentions(actor_id,status,due_day,id);
CREATE INDEX IF NOT EXISTS idx_intentions_target_actor ON character_intentions(target_actor_id,status,id);
CREATE INDEX IF NOT EXISTS idx_intentions_target_location ON character_intentions(target_location_id,status,id);

CREATE TABLE IF NOT EXISTS obligations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    counterparty_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    description TEXT NOT NULL,
    due_day INTEGER,
    target_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    target_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    importance INTEGER NOT NULL DEFAULT 2 CHECK (importance BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','fulfilled','breached','cancelled','expired')),
    intention_id INTEGER REFERENCES character_intentions(id) ON DELETE SET NULL,
    source_kind TEXT,
    source_id INTEGER,
    created_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_obligations_actor_due ON obligations(actor_id,status,due_day,id);

CREATE TABLE IF NOT EXISTS attention_cues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    cue_type TEXT NOT NULL CHECK (cue_type IN ('reminder','automatic','decision','warning','knowledge')),
    text TEXT NOT NULL,
    salience INTEGER NOT NULL DEFAULT 2 CHECK (salience BETWEEN 1 AND 5),
    related_kind TEXT,
    related_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','shown','dismissed','resolved')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attention_actor_status ON attention_cues(actor_id,status,day,id);

CREATE TABLE IF NOT EXISTS actor_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    subject_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    memory_key TEXT NOT NULL,
    summary TEXT NOT NULL,
    interpretation TEXT,
    valence REAL NOT NULL DEFAULT 0 CHECK (valence BETWEEN -1 AND 1),
    significance REAL NOT NULL DEFAULT 0.5 CHECK (significance BETWEEN 0 AND 1),
    source_kind TEXT NOT NULL CHECK (source_kind IN ('event','interaction','decision','player_action','agreement','scene','admin')),
    source_id INTEGER NOT NULL,
    created_day INTEGER NOT NULL,
    last_reinforced_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','faded','superseded')),
    UNIQUE(actor_id,memory_key)
);

CREATE INDEX IF NOT EXISTS idx_actor_memories_actor ON actor_memories(actor_id,status,significance DESC,last_reinforced_day DESC);
CREATE INDEX IF NOT EXISTS idx_actor_memories_subject ON actor_memories(subject_actor_id,status,id);

CREATE TABLE IF NOT EXISTS thread_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('event','interaction','decision','agreement','player_action','memory')),
    source_id INTEGER NOT NULL,
    relevance REAL NOT NULL DEFAULT 0.5 CHECK (relevance BETWEEN 0 AND 1),
    day INTEGER NOT NULL,
    note TEXT,
    UNIQUE(thread_id,source_kind,source_id)
);

CREATE TABLE IF NOT EXISTS narrative_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER REFERENCES turns(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL DEFAULT 0,
    day_started INTEGER NOT NULL,
    day_ended INTEGER NOT NULL,
    segment_kind TEXT NOT NULL DEFAULT 'scene' CHECK (segment_kind IN ('scene','transition','travel','downtime','arrival','conversation','aftermath')),
    outline_json TEXT NOT NULL DEFAULT '{}',
    scene_packet_id INTEGER REFERENCES scene_packets(id) ON DELETE SET NULL,
    narration_text TEXT,
    handoff_type TEXT NOT NULL DEFAULT 'none' CHECK (handoff_type IN ('none','open','hard')),
    handoff_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(turn_id,segment_index)
);

CREATE TABLE IF NOT EXISTS agency_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER REFERENCES turns(id) ON DELETE CASCADE,
    segment_id INTEGER REFERENCES narrative_segments(id) ON DELETE SET NULL,
    day INTEGER NOT NULL,
    checkpoint_type TEXT NOT NULL CHECK (checkpoint_type IN ('none','open','hard','interrupt')),
    reason TEXT NOT NULL,
    richness_score REAL NOT NULL DEFAULT 0 CHECK (richness_score BETWEEN 0 AND 100),
    can_auto_continue INTEGER NOT NULL DEFAULT 0 CHECK (can_auto_continue IN (0,1)),
    resolved INTEGER NOT NULL DEFAULT 0 CHECK (resolved IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agency_turn ON agency_checkpoints(turn_id,id);

CREATE TABLE IF NOT EXISTS model_route_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    task_type TEXT NOT NULL CHECK (task_type IN ('action_interpretation','npc_decision','narration')),
    target_kind TEXT,
    target_id INTEGER,
    reasoning_score REAL NOT NULL DEFAULT 0 CHECK (reasoning_score BETWEEN 0 AND 100),
    narrative_score REAL NOT NULL DEFAULT 0 CHECK (narrative_score BETWEEN 0 AND 100),
    context_tokens_estimate INTEGER NOT NULL DEFAULT 0,
    hardware_score REAL NOT NULL DEFAULT 0 CHECK (hardware_score BETWEEN 0 AND 100),
    recommendation TEXT NOT NULL CHECK (recommendation IN ('rules','local','local_heavy','external_recommended','external_strongly_recommended')),
    reasons_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runtime_flags (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO runtime_flags(key,value) VALUES ('interrupt_requested','0');


-- v0.8: continuity, historical anchors, cohorts, careers, institutional compression, and resolution metadata

CREATE TABLE IF NOT EXISTS continuity_cores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN ('actor','institution','location','possession','thread','cohort')),
    entity_id INTEGER NOT NULL,
    core_type TEXT NOT NULL DEFAULT 'general',
    core_json TEXT NOT NULL DEFAULT '{}',
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version >= 1),
    historical_depth TEXT NOT NULL DEFAULT 'present' CHECK (historical_depth IN ('present','shallow','developed','deep')),
    last_crystallized_day INTEGER,
    last_updated_day INTEGER NOT NULL DEFAULT 0,
    source_kind TEXT NOT NULL DEFAULT 'engine' CHECK (source_kind IN ('canon','campaign','engine','admin')),
    notes TEXT,
    UNIQUE(entity_kind,entity_id,core_type)
);

CREATE INDEX IF NOT EXISTS idx_continuity_entity ON continuity_cores(entity_kind,entity_id);
CREATE INDEX IF NOT EXISTS idx_continuity_depth ON continuity_cores(historical_depth,last_updated_day);

CREATE TABLE IF NOT EXISTS historical_anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN ('actor','location','possession','thread','cohort','institution')),
    entity_id INTEGER NOT NULL,
    anchor_type TEXT NOT NULL,
    start_day INTEGER,
    end_day INTEGER,
    summary TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    source_kind TEXT NOT NULL CHECK (source_kind IN ('canon','event','decision','interaction','agreement','player_action','memory','record','crystallization','admin')),
    source_id INTEGER,
    certainty REAL NOT NULL DEFAULT 1.0 CHECK (certainty BETWEEN 0 AND 1),
    canon_scope TEXT NOT NULL DEFAULT 'campaign' CHECK (canon_scope IN ('setting','campaign','provisional')),
    immutable INTEGER NOT NULL DEFAULT 1 CHECK (immutable IN (0,1)),
    created_day INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_anchor_entity ON historical_anchors(entity_kind,entity_id,start_day,id);
CREATE INDEX IF NOT EXISTS idx_anchor_type ON historical_anchors(anchor_type,start_day,id);
CREATE INDEX IF NOT EXISTS idx_anchor_source ON historical_anchors(source_kind,source_id);

CREATE TABLE IF NOT EXISTS public_narratives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    narrative_key TEXT NOT NULL,
    scope_kind TEXT NOT NULL DEFAULT 'world' CHECK (scope_kind IN ('world','location','institution','cohort','actor_group')),
    scope_id INTEGER,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('event','actor','location','institution','possession','cohort','thread')),
    subject_id INTEGER NOT NULL,
    claim_text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    prevalence REAL NOT NULL DEFAULT 0.5 CHECK (prevalence BETWEEN 0 AND 1),
    valence REAL NOT NULL DEFAULT 0 CHECK (valence BETWEEN -1 AND 1),
    first_day INTEGER NOT NULL,
    last_reinforced_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','fading','historical','discredited')),
    origin_kind TEXT CHECK (origin_kind IN ('event','rumour','record','institution','actor','admin')),
    origin_id INTEGER,
    UNIQUE(narrative_key,scope_kind,scope_id)
);

CREATE INDEX IF NOT EXISTS idx_public_narrative_subject ON public_narratives(subject_kind,subject_id,status);
CREATE INDEX IF NOT EXISTS idx_public_narrative_scope ON public_narratives(scope_kind,scope_id,status,prevalence DESC);

CREATE TABLE IF NOT EXISTS documentary_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type TEXT NOT NULL,
    title TEXT NOT NULL,
    author_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    created_day INTEGER NOT NULL,
    subject_kind TEXT,
    subject_id INTEGER,
    claim_text TEXT,
    reliability REAL NOT NULL DEFAULT 0.8 CHECK (reliability BETWEEN 0 AND 1),
    bias_json TEXT NOT NULL DEFAULT '{}',
    access TEXT NOT NULL DEFAULT 'limited' CHECK (access IN ('public','limited','private','secret','lost')),
    status TEXT NOT NULL DEFAULT 'extant' CHECK (status IN ('extant','damaged','lost','destroyed','disputed')),
    provenance_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_documentary_subject ON documentary_records(subject_kind,subject_id,created_day,id);
CREATE INDEX IF NOT EXISTS idx_documentary_institution ON documentary_records(institution_actor_id,created_day,id);

CREATE TABLE IF NOT EXISTS cohorts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    cohort_type TEXT NOT NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    start_day INTEGER,
    end_day INTEGER,
    population_estimate INTEGER CHECK (population_estimate IS NULL OR population_estimate >= 0),
    shared_context_json TEXT NOT NULL DEFAULT '{}',
    historical_summary TEXT,
    status TEXT NOT NULL DEFAULT 'historical' CHECK (status IN ('forming','active','historical','dissolved')),
    is_canon INTEGER NOT NULL DEFAULT 0 CHECK (is_canon IN (0,1)),
    UNIQUE(name,cohort_type,start_day)
);

CREATE TABLE IF NOT EXISTS cohort_memberships (
    cohort_id INTEGER NOT NULL REFERENCES cohorts(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    role TEXT,
    joined_day INTEGER,
    left_day INTEGER,
    membership_status TEXT NOT NULL DEFAULT 'member' CHECK (membership_status IN ('member','former','candidate','unknown')),
    significance REAL NOT NULL DEFAULT 0.5 CHECK (significance BETWEEN 0 AND 1),
    notes TEXT,
    PRIMARY KEY(cohort_id,actor_id)
);

CREATE INDEX IF NOT EXISTS idx_cohort_member_actor ON cohort_memberships(actor_id,membership_status,cohort_id);

CREATE TABLE IF NOT EXISTS career_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    description TEXT,
    typical_entry_age INTEGER,
    institution_kind TEXT,
    stage_model_json TEXT NOT NULL DEFAULT '{}',
    is_canon INTEGER NOT NULL DEFAULT 0 CHECK (is_canon IN (0,1))
);

CREATE TABLE IF NOT EXISTS career_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL REFERENCES career_tracks(id) ON DELETE CASCADE,
    stage_key TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    sequence_index INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    entry_requirements_json TEXT NOT NULL DEFAULT '{}',
    responsibilities_json TEXT NOT NULL DEFAULT '{}',
    exit_paths_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(track_id,stage_key)
);

CREATE TABLE IF NOT EXISTS actor_careers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES career_tracks(id) ON DELETE CASCADE,
    current_stage_id INTEGER REFERENCES career_stages(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    mentor_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    started_day INTEGER,
    stage_started_day INTEGER,
    ended_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','completed','abandoned','retired')),
    experience_json TEXT NOT NULL DEFAULT '{}',
    reputation_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT,
    UNIQUE(actor_id,track_id,started_day)
);

CREATE INDEX IF NOT EXISTS idx_actor_careers_actor ON actor_careers(actor_id,status,id);
CREATE INDEX IF NOT EXISTS idx_actor_careers_institution ON actor_careers(institution_actor_id,status,id);

CREATE TABLE IF NOT EXISTS institution_profiles (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    institution_kind TEXT NOT NULL,
    founded_day INTEGER,
    parent_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    primary_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    governance_json TEXT NOT NULL DEFAULT '{}',
    culture_json TEXT NOT NULL DEFAULT '{}',
    pipeline_json TEXT NOT NULL DEFAULT '{}',
    capacity_json TEXT NOT NULL DEFAULT '{}',
    economic_json TEXT NOT NULL DEFAULT '{}',
    reputation_json TEXT NOT NULL DEFAULT '{}',
    succession_json TEXT NOT NULL DEFAULT '{}',
    trajectory TEXT NOT NULL DEFAULT 'stable' CHECK (trajectory IN ('rising','stable','declining','transforming','crisis','dormant')),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_institution_profile_kind ON institution_profiles(institution_kind,trajectory);

CREATE TABLE IF NOT EXISTS entity_resolution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN ('actor','institution','location','possession','thread','cohort')),
    entity_id INTEGER NOT NULL,
    resolution_level TEXT NOT NULL CHECK (resolution_level IN ('SCENE','ACTIVE','TRACKED','STRUCTURAL','LATENT')),
    previous_level TEXT CHECK (previous_level IN ('SCENE','ACTIVE','TRACKED','STRUCTURAL','LATENT')),
    reason TEXT,
    promoted_by_kind TEXT,
    promoted_by_id INTEGER,
    review_cadence_days INTEGER CHECK (review_cadence_days IS NULL OR review_cadence_days >= 1),
    next_review_day INTEGER,
    last_changed_day INTEGER NOT NULL DEFAULT 0,
    locked_min_level TEXT CHECK (locked_min_level IN ('SCENE','ACTIVE','TRACKED','STRUCTURAL','LATENT')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(entity_kind,entity_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_resolution_level ON entity_resolution(resolution_level,next_review_day,entity_kind,entity_id);

CREATE TABLE IF NOT EXISTS resolution_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    from_level TEXT,
    to_level TEXT NOT NULL,
    reason TEXT,
    source_kind TEXT NOT NULL DEFAULT 'engine' CHECK (source_kind IN ('engine','player','event','relationship','admin','crystallization')),
    source_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_resolution_transitions_entity ON resolution_transitions(entity_kind,entity_id,day,id);

CREATE TABLE IF NOT EXISTS latent_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latent_kind TEXT NOT NULL,
    archetype TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    cohort_id INTEGER REFERENCES cohorts(id) ON DELETE SET NULL,
    count_estimate INTEGER NOT NULL DEFAULT 1 CHECK (count_estimate >= 1),
    constraints_json TEXT NOT NULL DEFAULT '{}',
    historical_context_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'latent' CHECK (status IN ('latent','partially_crystallized','crystallized','retired')),
    crystallized_entity_kind TEXT,
    crystallized_entity_id INTEGER,
    created_day INTEGER NOT NULL DEFAULT 0,
    updated_day INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_latent_scope ON latent_entities(status,latent_kind,location_id,institution_actor_id);

-- v0.9: historical crystallization service audit / validation layer

CREATE TABLE IF NOT EXISTS crystallization_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latent_entity_id INTEGER REFERENCES latent_entities(id) ON DELETE SET NULL,
    target_kind TEXT NOT NULL DEFAULT 'actor' CHECK (target_kind IN ('actor','institution','possession','location')),
    requested_depth TEXT NOT NULL DEFAULT 'shallow' CHECK (requested_depth IN ('shallow','developed','deep')),
    trigger_kind TEXT NOT NULL DEFAULT 'engine',
    trigger_id INTEGER,
    status TEXT NOT NULL DEFAULT 'prepared' CHECK (status IN ('prepared','validated','rejected','applied','cancelled')),
    context_json TEXT NOT NULL DEFAULT '{}',
    proposal_json TEXT,
    validation_json TEXT NOT NULL DEFAULT '{}',
    crystallized_entity_kind TEXT,
    crystallized_entity_id INTEGER,
    created_day INTEGER NOT NULL DEFAULT 0,
    applied_day INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_crystallization_status ON crystallization_runs(status,created_day,id);
CREATE INDEX IF NOT EXISTS idx_crystallization_latent ON crystallization_runs(latent_entity_id,id);

CREATE TABLE IF NOT EXISTS crystallization_lineage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES crystallization_runs(id) ON DELETE CASCADE,
    fact_kind TEXT NOT NULL,
    fact_ref_kind TEXT,
    fact_ref_id INTEGER,
    produced_kind TEXT NOT NULL,
    produced_id INTEGER NOT NULL,
    summary TEXT,
    created_day INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_crystallization_lineage_run ON crystallization_lineage(run_id,id);

-- v0.10: persistent character embodiment, speech mediation, and commitment firewall

CREATE TABLE IF NOT EXISTS character_embodiment (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    voice_json TEXT NOT NULL DEFAULT '{}',
    temperament_json TEXT NOT NULL DEFAULT '{}',
    values_json TEXT NOT NULL DEFAULT '{}',
    habits_json TEXT NOT NULL DEFAULT '{}',
    social_json TEXT NOT NULL DEFAULT '{}',
    relationship_style_json TEXT NOT NULL DEFAULT '{}',
    expression_policy_json TEXT NOT NULL DEFAULT '{}',
    current_state_json TEXT NOT NULL DEFAULT '{}',
    development_json TEXT NOT NULL DEFAULT '{}',
    source_kind TEXT NOT NULL DEFAULT 'campaign' CHECK (source_kind IN ('campaign','canon','crystallization','admin','generated')),
    updated_day INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS embodiment_expressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    expression_kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.8 CHECK (confidence BETWEEN 0 AND 1),
    autonomy_result TEXT NOT NULL CHECK (autonomy_result IN ('allow','ask','block')),
    commitment_risk TEXT NOT NULL DEFAULT 'low' CHECK (commitment_risk IN ('low','medium','high')),
    related_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    source_kind TEXT NOT NULL DEFAULT 'narration',
    source_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_embodiment_expressions_actor ON embodiment_expressions(actor_id,day DESC,id DESC);

CREATE TABLE IF NOT EXISTS speech_mediations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    audience_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    input_mode TEXT NOT NULL CHECK (input_mode IN ('intent','guided','exact')),
    raw_input TEXT NOT NULL,
    intended_tone TEXT,
    social_objective TEXT,
    commitment_risk TEXT NOT NULL DEFAULT 'low' CHECK (commitment_risk IN ('low','medium','high')),
    mediation_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'prepared' CHECK (status IN ('prepared','rendered','cancelled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_speech_mediations_actor ON speech_mediations(actor_id,day DESC,id DESC);


-- v0.11: domain competence, professional readings, and advisor judgment separation

CREATE TABLE IF NOT EXISTS competence_domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    default_visibility TEXT NOT NULL DEFAULT 'private' CHECK (default_visibility IN ('public','limited','private','secret'))
);

CREATE TABLE IF NOT EXISTS actor_competence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    domain_id INTEGER NOT NULL REFERENCES competence_domains(id) ON DELETE CASCADE,
    score REAL NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100),
    specialty TEXT,
    specialty_key TEXT GENERATED ALWAYS AS (COALESCE(specialty,'')) STORED,
    experience_json TEXT NOT NULL DEFAULT '{}',
    training_json TEXT NOT NULL DEFAULT '{}',
    confidence_modifier REAL NOT NULL DEFAULT 0 CHECK (confidence_modifier BETWEEN -0.5 AND 0.5),
    source_kind TEXT NOT NULL DEFAULT 'campaign' CHECK (source_kind IN ('canon','campaign','career','crystallization','admin','generated')),
    updated_day INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    UNIQUE(actor_id,domain_id,specialty_key)
);

CREATE INDEX IF NOT EXISTS idx_actor_competence_actor ON actor_competence(actor_id,score DESC,domain_id);

CREATE TABLE IF NOT EXISTS professional_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    domain_key TEXT NOT NULL,
    specialty TEXT,
    situation_text TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    stakes INTEGER NOT NULL DEFAULT 2 CHECK (stakes BETWEEN 1 AND 5),
    uncertainty REAL NOT NULL DEFAULT 0.3 CHECK (uncertainty BETWEEN 0 AND 1),
    competence_score REAL NOT NULL DEFAULT 0 CHECK (competence_score BETWEEN 0 AND 100),
    competence_band TEXT NOT NULL,
    reading_confidence REAL NOT NULL DEFAULT 0.2 CHECK (reading_confidence BETWEEN 0 AND 1),
    status TEXT NOT NULL DEFAULT 'prepared' CHECK (status IN ('prepared','resolved','cancelled')),
    result_json TEXT NOT NULL DEFAULT '{}',
    provider TEXT,
    source_kind TEXT NOT NULL DEFAULT 'scene',
    source_id INTEGER,
    created_day INTEGER NOT NULL,
    resolved_day INTEGER
);

CREATE INDEX IF NOT EXISTS idx_professional_readings_actor ON professional_readings(actor_id,domain_key,created_day DESC,id DESC);

CREATE TABLE IF NOT EXISTS advisor_judgments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    advisor_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    domain_key TEXT NOT NULL,
    situation_key TEXT NOT NULL,
    judgment_text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.6 CHECK (confidence BETWEEN 0 AND 1),
    evidence_json TEXT NOT NULL DEFAULT '[]',
    assumptions_json TEXT NOT NULL DEFAULT '[]',
    bias_note TEXT,
    communicated INTEGER NOT NULL DEFAULT 1 CHECK (communicated IN (0,1)),
    source_kind TEXT NOT NULL DEFAULT 'conversation',
    source_id INTEGER,
    created_day INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_advisor_judgments_recipient ON advisor_judgments(recipient_actor_id,situation_key,domain_key,created_day DESC,id DESC);

-- v0.12: time-skip resolver, focus accumulation, and interruption-safe compressed progression

CREATE TABLE IF NOT EXISTS time_skip_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    start_day INTEGER NOT NULL,
    requested_end_day INTEGER NOT NULL,
    actual_end_day INTEGER,
    planned_days INTEGER NOT NULL CHECK (planned_days >= 1),
    status TEXT NOT NULL DEFAULT 'prepared' CHECK (status IN ('prepared','running','completed','interrupted','cancelled','error')),
    focus_json TEXT NOT NULL DEFAULT '[]',
    delegation_json TEXT NOT NULL DEFAULT '{}',
    interruption_policy TEXT NOT NULL DEFAULT 'meaningful' CHECK (interruption_policy IN ('all','meaningful','critical_only')),
    max_chunk_days INTEGER NOT NULL DEFAULT 30 CHECK (max_chunk_days BETWEEN 1 AND 365),
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time_skip_actor ON time_skip_runs(actor_id,status,start_day,id);

CREATE TABLE IF NOT EXISTS time_skip_focus_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES time_skip_runs(id) ON DELETE CASCADE,
    focus_key TEXT NOT NULL,
    description TEXT NOT NULL,
    domain_key TEXT,
    career_id INTEGER REFERENCES actor_careers(id) ON DELETE SET NULL,
    weight REAL NOT NULL DEFAULT 1.0 CHECK (weight > 0 AND weight <= 1.0),
    accumulated_days REAL NOT NULL DEFAULT 0 CHECK (accumulated_days >= 0),
    result_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(run_id,focus_key)
);

CREATE INDEX IF NOT EXISTS idx_time_skip_focus_run ON time_skip_focus_progress(run_id,id);

CREATE TABLE IF NOT EXISTS time_skip_interruptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES time_skip_runs(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('event','interaction','obligation','competence','system')),
    source_id INTEGER,
    reason TEXT NOT NULL,
    severity INTEGER NOT NULL DEFAULT 3 CHECK (severity BETWEEN 1 AND 5),
    requires_player INTEGER NOT NULL DEFAULT 1 CHECK (requires_player IN (0,1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time_skip_interrupt_run ON time_skip_interruptions(run_id,day,id);

-- v0.13: abstract battle and duel resolution, rank-sensitive battlefield views, and subordinate agency

CREATE TABLE IF NOT EXISTS combat_engagements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_kind TEXT NOT NULL CHECK (engagement_kind IN ('battle','duel')),
    title TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    player_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    objective_text TEXT,
    stakes INTEGER NOT NULL DEFAULT 3 CHECK (stakes BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'prepared' CHECK (status IN ('prepared','active','resolved','cancelled')),
    phase TEXT NOT NULL DEFAULT 'opening',
    round_index INTEGER NOT NULL DEFAULT 0 CHECK (round_index >= 0),
    day_started INTEGER NOT NULL,
    day_ended INTEGER,
    outcome_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_combat_engagement_status ON combat_engagements(status,engagement_kind,day_started,id);

CREATE TABLE IF NOT EXISTS battle_sides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    controller_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    objective_text TEXT,
    posture TEXT NOT NULL DEFAULT 'balanced' CHECK (posture IN ('cautious','balanced','assertive')),
    morale REAL NOT NULL DEFAULT 70 CHECK (morale BETWEEN 0 AND 100),
    cohesion REAL NOT NULL DEFAULT 70 CHECK (cohesion BETWEEN 0 AND 100),
    logistics REAL NOT NULL DEFAULT 70 CHECK (logistics BETWEEN 0 AND 100),
    information_quality REAL NOT NULL DEFAULT 50 CHECK (information_quality BETWEEN 0 AND 100),
    reserve_capacity REAL NOT NULL DEFAULT 50 CHECK (reserve_capacity BETWEEN 0 AND 100),
    momentum REAL NOT NULL DEFAULT 0 CHECK (momentum BETWEEN -100 AND 100),
    status TEXT NOT NULL DEFAULT 'engaged' CHECK (status IN ('engaged','withdrawing','withdrawn','broken','victorious')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(engagement_id,name)
);

CREATE INDEX IF NOT EXISTS idx_battle_sides_engagement ON battle_sides(engagement_id,status,id);

CREATE TABLE IF NOT EXISTS battle_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    side_id INTEGER NOT NULL REFERENCES battle_sides(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    commander_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    unit_role TEXT NOT NULL DEFAULT 'line' CHECK (unit_role IN ('line','support','reserve','specialist','command')),
    combat_capacity REAL NOT NULL DEFAULT 70 CHECK (combat_capacity BETWEEN 0 AND 100),
    morale REAL NOT NULL DEFAULT 70 CHECK (morale BETWEEN 0 AND 100),
    cohesion REAL NOT NULL DEFAULT 70 CHECK (cohesion BETWEEN 0 AND 100),
    fatigue REAL NOT NULL DEFAULT 10 CHECK (fatigue BETWEEN 0 AND 100),
    readiness REAL NOT NULL DEFAULT 70 CHECK (readiness BETWEEN 0 AND 100),
    commitment REAL NOT NULL DEFAULT 0 CHECK (commitment BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','engaged','strained','disengaged','broken')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(side_id,name)
);

CREATE INDEX IF NOT EXISTS idx_battle_units_side ON battle_units(side_id,status,id);
CREATE INDEX IF NOT EXISTS idx_battle_units_commander ON battle_units(commander_actor_id,side_id,id);

CREATE TABLE IF NOT EXISTS battle_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    side_id INTEGER NOT NULL REFERENCES battle_sides(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    unit_id INTEGER REFERENCES battle_units(id) ON DELETE CASCADE,
    round_index INTEGER NOT NULL,
    intent_key TEXT NOT NULL CHECK (intent_key IN ('hold','probe','press','reposition','reinforce','commit_reserve','recover','disengage')),
    risk_level TEXT NOT NULL DEFAULT 'balanced' CHECK (risk_level IN ('low','balanced','high')),
    commitment REAL NOT NULL DEFAULT 0.5 CHECK (commitment BETWEEN 0 AND 1),
    objective_text TEXT,
    source_kind TEXT NOT NULL DEFAULT 'player' CHECK (source_kind IN ('player','npc_rules','npc_model','delegated')),
    status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','resolved','cancelled')),
    result_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL,
    UNIQUE(engagement_id,actor_id,round_index,unit_id)
);

CREATE INDEX IF NOT EXISTS idx_battle_intents_round ON battle_intents(engagement_id,round_index,side_id,id);

CREATE TABLE IF NOT EXISTS battle_unit_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    side_id INTEGER NOT NULL REFERENCES battle_sides(id) ON DELETE CASCADE,
    unit_id INTEGER NOT NULL REFERENCES battle_units(id) ON DELETE CASCADE,
    commander_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    round_index INTEGER NOT NULL,
    action_key TEXT NOT NULL CHECK (action_key IN ('hold','probe','press','support','reposition','recover','commit','disengage')),
    autonomy_source TEXT NOT NULL CHECK (autonomy_source IN ('side_intent','unit_intent','commander_judgment','received_order','fallback')),
    competence_score REAL NOT NULL DEFAULT 0 CHECK (competence_score BETWEEN 0 AND 100),
    result_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_battle_unit_actions_round ON battle_unit_actions(engagement_id,round_index,side_id,id);

CREATE TABLE IF NOT EXISTS battle_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    round_index INTEGER NOT NULL,
    day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'resolved' CHECK (status IN ('resolved','cancelled')),
    summary_json TEXT NOT NULL DEFAULT '{}',
    seed INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(engagement_id,round_index)
);

CREATE TABLE IF NOT EXISTS duel_combatants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    readiness REAL NOT NULL DEFAULT 100 CHECK (readiness BETWEEN 0 AND 100),
    stamina REAL NOT NULL DEFAULT 100 CHECK (stamina BETWEEN 0 AND 100),
    composure REAL NOT NULL DEFAULT 75 CHECK (composure BETWEEN 0 AND 100),
    reserve REAL NOT NULL DEFAULT 100 CHECK (reserve BETWEEN 0 AND 100),
    momentum REAL NOT NULL DEFAULT 0 CHECK (momentum BETWEEN -100 AND 100),
    capability_override REAL CHECK (capability_override BETWEEN 0 AND 100 OR capability_override IS NULL),
    status TEXT NOT NULL DEFAULT 'engaged' CHECK (status IN ('engaged','disengaged','defeated','victorious')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(engagement_id,actor_id)
);

CREATE INDEX IF NOT EXISTS idx_duel_combatants_engagement ON duel_combatants(engagement_id,status,id);

CREATE TABLE IF NOT EXISTS duel_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    combatant_id INTEGER NOT NULL REFERENCES duel_combatants(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    round_index INTEGER NOT NULL,
    intent_key TEXT NOT NULL CHECK (intent_key IN ('measure','press','defend','conserve','commit','control','disengage')),
    risk_level TEXT NOT NULL DEFAULT 'balanced' CHECK (risk_level IN ('low','balanced','high')),
    reserve_commitment REAL NOT NULL DEFAULT 0.25 CHECK (reserve_commitment BETWEEN 0 AND 1),
    objective_text TEXT,
    source_kind TEXT NOT NULL DEFAULT 'player' CHECK (source_kind IN ('player','npc_rules','npc_model')),
    status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','resolved','cancelled')),
    result_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL,
    UNIQUE(engagement_id,actor_id,round_index)
);

CREATE INDEX IF NOT EXISTS idx_duel_intents_round ON duel_intents(engagement_id,round_index,id);

CREATE TABLE IF NOT EXISTS duel_exchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    round_index INTEGER NOT NULL,
    day INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(engagement_id,round_index)
);

-- v0.14: multi-front battle flow inspired by large-scale war fiction structure.
-- These tables remain abstract: they model command, information, fronts, morale and timing,
-- not real-world weapon technique or formation instructions.

CREATE TABLE IF NOT EXISTS battle_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 50 CHECK (importance BETWEEN 0 AND 100),
    pressure REAL NOT NULL DEFAULT 0 CHECK (pressure BETWEEN -100 AND 100),
    initiative_side_id INTEGER REFERENCES battle_sides(id) ON DELETE SET NULL,
    control_state TEXT NOT NULL DEFAULT 'contested' CHECK (control_state IN ('contested','leaning','decisive','abandoned')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','quiet','resolved','abandoned')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(engagement_id,name)
);

CREATE INDEX IF NOT EXISTS idx_battle_zones_engagement ON battle_zones(engagement_id,status,id);

CREATE TABLE IF NOT EXISTS battle_unit_zones (
    unit_id INTEGER PRIMARY KEY REFERENCES battle_units(id) ON DELETE CASCADE,
    zone_id INTEGER NOT NULL REFERENCES battle_zones(id) ON DELETE CASCADE,
    assigned_round INTEGER NOT NULL DEFAULT 0,
    assignment_kind TEXT NOT NULL DEFAULT 'primary' CHECK (assignment_kind IN ('primary','support','reserve')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_battle_unit_zones_zone ON battle_unit_zones(zone_id,assignment_kind,unit_id);

CREATE TABLE IF NOT EXISTS battle_command_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    side_id INTEGER NOT NULL REFERENCES battle_sides(id) ON DELETE CASCADE,
    senior_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    junior_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    junior_unit_id INTEGER REFERENCES battle_units(id) ON DELETE CASCADE,
    authority_scope TEXT NOT NULL DEFAULT 'unit' CHECK (authority_scope IN ('side','zone','unit')),
    communication_quality REAL NOT NULL DEFAULT 70 CHECK (communication_quality BETWEEN 0 AND 100),
    discretion REAL NOT NULL DEFAULT 60 CHECK (discretion BETWEEN 0 AND 100),
    trust REAL NOT NULL DEFAULT 60 CHECK (trust BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','severed','inactive')),
    UNIQUE(engagement_id,senior_actor_id,junior_actor_id,junior_unit_id)
);

CREATE INDEX IF NOT EXISTS idx_battle_command_links_side ON battle_command_links(engagement_id,side_id,status,id);

CREATE TABLE IF NOT EXISTS battle_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    side_id INTEGER NOT NULL REFERENCES battle_sides(id) ON DELETE CASCADE,
    issuer_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    recipient_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    unit_id INTEGER REFERENCES battle_units(id) ON DELETE CASCADE,
    zone_id INTEGER REFERENCES battle_zones(id) ON DELETE SET NULL,
    issued_round INTEGER NOT NULL,
    effective_round INTEGER NOT NULL,
    directive_key TEXT NOT NULL CHECK (directive_key IN ('hold','probe','press','support','reposition','recover','commit','disengage')),
    priority INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
    objective_text TEXT,
    status TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued','received','superseded','expired')),
    created_day INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_battle_orders_due ON battle_orders(engagement_id,effective_round,status,unit_id,id);

CREATE TABLE IF NOT EXISTS battle_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    side_id INTEGER REFERENCES battle_sides(id) ON DELETE CASCADE,
    recipient_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    source_unit_id INTEGER REFERENCES battle_units(id) ON DELETE SET NULL,
    zone_id INTEGER REFERENCES battle_zones(id) ON DELETE SET NULL,
    observed_round INTEGER NOT NULL,
    available_round INTEGER NOT NULL,
    confidence REAL NOT NULL DEFAULT 50 CHECK (confidence BETWEEN 0 AND 100),
    report_kind TEXT NOT NULL DEFAULT 'situation' CHECK (report_kind IN ('situation','morale','command','turning_point','objective')),
    summary_text TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_battle_reports_available ON battle_reports(engagement_id,recipient_actor_id,available_round,id);

CREATE TABLE IF NOT EXISTS battle_turning_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    round_index INTEGER NOT NULL,
    zone_id INTEGER REFERENCES battle_zones(id) ON DELETE SET NULL,
    side_id INTEGER REFERENCES battle_sides(id) ON DELETE SET NULL,
    turning_kind TEXT NOT NULL CHECK (turning_kind IN ('local_swing','local_crisis','command_shock','morale_surge','objective_shift')),
    significance INTEGER NOT NULL DEFAULT 2 CHECK (significance BETWEEN 1 AND 5),
    summary_text TEXT NOT NULL,
    effects_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_battle_turning_points_round ON battle_turning_points(engagement_id,round_index,significance,id);

CREATE TABLE IF NOT EXISTS battle_command_profiles (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    planning REAL NOT NULL DEFAULT 50 CHECK (planning BETWEEN 0 AND 100),
    adaptation REAL NOT NULL DEFAULT 50 CHECK (adaptation BETWEEN 0 AND 100),
    presence REAL NOT NULL DEFAULT 50 CHECK (presence BETWEEN 0 AND 100),
    delegation REAL NOT NULL DEFAULT 50 CHECK (delegation BETWEEN 0 AND 100),
    nerve REAL NOT NULL DEFAULT 50 CHECK (nerve BETWEEN 0 AND 100),
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- v0.15: abstract tactical grammar + Vein-aware battlefield layer.
-- This models high-level battlefield reasoning and fantasy cultivation effects only.
-- It intentionally does not encode real-world weapon drills, formation geometry, or actionable tactics.

CREATE TABLE IF NOT EXISTS battle_doctrines (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    pressure REAL NOT NULL DEFAULT 50 CHECK (pressure BETWEEN 0 AND 100),
    fixing REAL NOT NULL DEFAULT 50 CHECK (fixing BETWEEN 0 AND 100),
    misdirection REAL NOT NULL DEFAULT 50 CHECK (misdirection BETWEEN 0 AND 100),
    isolation REAL NOT NULL DEFAULT 50 CHECK (isolation BETWEEN 0 AND 100),
    depth REAL NOT NULL DEFAULT 50 CHECK (depth BETWEEN 0 AND 100),
    reserve_play REAL NOT NULL DEFAULT 50 CHECK (reserve_play BETWEEN 0 AND 100),
    mobility REAL NOT NULL DEFAULT 50 CHECK (mobility BETWEEN 0 AND 100),
    attrition REAL NOT NULL DEFAULT 50 CHECK (attrition BETWEEN 0 AND 100),
    disruption REAL NOT NULL DEFAULT 50 CHECK (disruption BETWEEN 0 AND 100),
    exploitation REAL NOT NULL DEFAULT 50 CHECK (exploitation BETWEEN 0 AND 100),
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS battle_tactical_choices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    side_id INTEGER NOT NULL REFERENCES battle_sides(id) ON DELETE CASCADE,
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    round_index INTEGER NOT NULL,
    family_key TEXT NOT NULL CHECK (family_key IN (
        'pressure','fixing','misdirection','isolation','depth','reserve_play','mobility','attrition','disruption','exploitation'
    )),
    focus_zone_id INTEGER REFERENCES battle_zones(id) ON DELETE SET NULL,
    commitment REAL NOT NULL DEFAULT 0.5 CHECK (commitment BETWEEN 0 AND 1),
    source_kind TEXT NOT NULL DEFAULT 'doctrine' CHECK (source_kind IN ('player','doctrine','npc_rules','npc_model','delegated')),
    status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','resolved','cancelled')),
    result_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL,
    UNIQUE(engagement_id,side_id,round_index)
);

CREATE INDEX IF NOT EXISTS idx_battle_tactical_choice_round ON battle_tactical_choices(engagement_id,round_index,side_id,id);

CREATE TABLE IF NOT EXISTS battle_zone_current (
    zone_id INTEGER PRIMARY KEY REFERENCES battle_zones(id) ON DELETE CASCADE,
    density REAL NOT NULL DEFAULT 50 CHECK (density BETWEEN 0 AND 100),
    stability REAL NOT NULL DEFAULT 50 CHECK (stability BETWEEN 0 AND 100),
    replenishment REAL NOT NULL DEFAULT 50 CHECK (replenishment BETWEEN 0 AND 100),
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS battle_vein_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    side_id INTEGER NOT NULL REFERENCES battle_sides(id) ON DELETE CASCADE,
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    unit_id INTEGER REFERENCES battle_units(id) ON DELETE SET NULL,
    zone_id INTEGER REFERENCES battle_zones(id) ON DELETE SET NULL,
    stage_key TEXT NOT NULL CHECK (stage_key IN ('First','Temper','Third','Breach','Fifth','Sixth')),
    battlefield_role TEXT NOT NULL DEFAULT 'flexible' CHECK (battlefield_role IN ('anchor','reserve','screen','support','hunter','flexible')),
    readiness REAL NOT NULL DEFAULT 100 CHECK (readiness BETWEEN 0 AND 100),
    reserve REAL NOT NULL DEFAULT 100 CHECK (reserve BETWEEN 0 AND 100),
    commitment REAL NOT NULL DEFAULT 0.5 CHECK (commitment BETWEEN 0 AND 1),
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','committed','strained','disengaged','defeated')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(engagement_id,actor_id)
);

CREATE INDEX IF NOT EXISTS idx_battle_vein_assets_zone ON battle_vein_assets(engagement_id,side_id,zone_id,status,id);

CREATE TABLE IF NOT EXISTS battle_tactical_effects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    round_index INTEGER NOT NULL,
    side_id INTEGER REFERENCES battle_sides(id) ON DELETE SET NULL,
    zone_id INTEGER REFERENCES battle_zones(id) ON DELETE SET NULL,
    effect_kind TEXT NOT NULL,
    magnitude REAL NOT NULL DEFAULT 0,
    summary_text TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_battle_tactical_effects_round ON battle_tactical_effects(engagement_id,round_index,side_id,zone_id,id);

CREATE TABLE IF NOT EXISTS battle_personal_consequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    round_index INTEGER NOT NULL,
    zone_id INTEGER REFERENCES battle_zones(id) ON DELETE SET NULL,
    winner_side_id INTEGER REFERENCES battle_sides(id) ON DELETE SET NULL,
    loser_side_id INTEGER REFERENCES battle_sides(id) ON DELETE SET NULL,
    winner_asset_id INTEGER REFERENCES battle_vein_assets(id) ON DELETE SET NULL,
    loser_asset_id INTEGER REFERENCES battle_vein_assets(id) ON DELETE SET NULL,
    consequence_scale TEXT NOT NULL CHECK (consequence_scale IN ('minor','local','operational','strategic')),
    summary_text TEXT NOT NULL,
    effects_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_battle_personal_consequence_round ON battle_personal_consequences(engagement_id,round_index,consequence_scale,id);


-- v0.15.1 audit hardening: explicit duel-to-battle linkage so personal combat
-- can feed its contextual consequence back into the battle automatically.
CREATE TABLE IF NOT EXISTS duel_battle_links (
    duel_engagement_id INTEGER PRIMARY KEY REFERENCES combat_engagements(id) ON DELETE CASCADE,
    battle_engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    zone_id INTEGER NOT NULL REFERENCES battle_zones(id) ON DELETE CASCADE,
    actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_a_asset_id INTEGER NOT NULL REFERENCES battle_vein_assets(id) ON DELETE CASCADE,
    actor_b_asset_id INTEGER NOT NULL REFERENCES battle_vein_assets(id) ON DELETE CASCADE,
    consequence_id INTEGER REFERENCES battle_personal_consequences(id) ON DELETE SET NULL,
    created_day INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_duel_battle_links_battle
ON duel_battle_links(battle_engagement_id,zone_id,duel_engagement_id);

-- v0.16: civilian simulation core. These systems model household, enterprise,
-- market, production, project, cultural-object, provenance, auction, and shadow-market
-- dynamics at an abstract simulation level.

CREATE TABLE IF NOT EXISTS households (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    head_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','declining','dissolved','historical')),
    wealth REAL NOT NULL DEFAULT 0,
    liquidity REAL NOT NULL DEFAULT 0,
    staff_capacity REAL NOT NULL DEFAULT 50 CHECK (staff_capacity BETWEEN 0 AND 100),
    cohesion REAL NOT NULL DEFAULT 70 CHECK (cohesion BETWEEN 0 AND 100),
    hospitality REAL NOT NULL DEFAULT 50 CHECK (hospitality BETWEEN 0 AND 100),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_households_location ON households(location_id,status,id);

CREATE TABLE IF NOT EXISTS household_members (
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    authority REAL NOT NULL DEFAULT 20 CHECK (authority BETWEEN 0 AND 100),
    dependency REAL NOT NULL DEFAULT 20 CHECK (dependency BETWEEN 0 AND 100),
    joined_day INTEGER,
    left_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','absent','former','deceased')),
    PRIMARY KEY(household_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_household_members_actor ON household_members(actor_id,status,household_id);

CREATE TABLE IF NOT EXISTS civilian_enterprises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    enterprise_kind TEXT NOT NULL CHECK (enterprise_kind IN ('merchant_house','workshop','estate','shop','studio','shipping','construction','service','other')),
    owner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    capital REAL NOT NULL DEFAULT 0,
    cash REAL NOT NULL DEFAULT 0,
    debt REAL NOT NULL DEFAULT 0,
    reputation REAL NOT NULL DEFAULT 50 CHECK (reputation BETWEEN 0 AND 100),
    admin_quality REAL NOT NULL DEFAULT 50 CHECK (admin_quality BETWEEN 0 AND 100),
    labor_capacity REAL NOT NULL DEFAULT 50 CHECK (labor_capacity BETWEEN 0 AND 100),
    risk_tolerance REAL NOT NULL DEFAULT 50 CHECK (risk_tolerance BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','insolvent','closed','historical')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL,
    UNIQUE(name,location_id)
);
CREATE INDEX IF NOT EXISTS idx_enterprises_location ON civilian_enterprises(location_id,status,id);

CREATE TABLE IF NOT EXISTS market_goods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    good_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    base_price REAL NOT NULL CHECK (base_price > 0),
    unit TEXT NOT NULL DEFAULT 'unit',
    perishability REAL NOT NULL DEFAULT 0 CHECK (perishability BETWEEN 0 AND 1),
    skill_intensity REAL NOT NULL DEFAULT 0.5 CHECK (skill_intensity BETWEEN 0 AND 1),
    luxury REAL NOT NULL DEFAULT 0 CHECK (luxury BETWEEN 0 AND 1),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS market_conditions (
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
    supply REAL NOT NULL DEFAULT 50 CHECK (supply >= 0),
    demand REAL NOT NULL DEFAULT 50 CHECK (demand >= 0),
    transport_pressure REAL NOT NULL DEFAULT 0 CHECK (transport_pressure BETWEEN 0 AND 100),
    risk_pressure REAL NOT NULL DEFAULT 0 CHECK (risk_pressure BETWEEN 0 AND 100),
    tax_pressure REAL NOT NULL DEFAULT 0 CHECK (tax_pressure BETWEEN 0 AND 100),
    current_price REAL NOT NULL CHECK (current_price > 0),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(location_id,good_id)
);
CREATE INDEX IF NOT EXISTS idx_market_due ON market_conditions(next_review_day,location_id,good_id);

CREATE TABLE IF NOT EXISTS production_sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
    capacity_per_30 REAL NOT NULL DEFAULT 10 CHECK (capacity_per_30 >= 0),
    efficiency REAL NOT NULL DEFAULT 50 CHECK (efficiency BETWEEN 0 AND 100),
    material_access REAL NOT NULL DEFAULT 50 CHECK (material_access BETWEEN 0 AND 100),
    skilled_labor REAL NOT NULL DEFAULT 50 CHECK (skilled_labor BETWEEN 0 AND 100),
    inventory REAL NOT NULL DEFAULT 0 CHECK (inventory >= 0),
    production_mode TEXT NOT NULL DEFAULT 'aggregate' CHECK (production_mode IN ('aggregate','tracked')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    last_resolved_day INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    UNIQUE(enterprise_id,good_id)
);
CREATE INDEX IF NOT EXISTS idx_production_enterprise ON production_sites(enterprise_id,active,id);

CREATE TABLE IF NOT EXISTS enterprise_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    account_kind TEXT NOT NULL CHECK (account_kind IN ('revenue','expense','credit','debt_payment','capital_injection','loss','asset_sale','purchase')),
    amount REAL NOT NULL CHECK (amount >= 0),
    description TEXT NOT NULL,
    related_good_id INTEGER REFERENCES market_goods(id) ON DELETE SET NULL,
    source_kind TEXT NOT NULL DEFAULT 'simulation',
    source_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_enterprise_accounts_day ON enterprise_accounts(enterprise_id,day,id);

CREATE TABLE IF NOT EXISTS civilian_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    project_kind TEXT NOT NULL CHECK (project_kind IN ('architecture','artwork','textile','manuscript','craft','public_work','household','business')),
    patron_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    creator_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    started_day INTEGER NOT NULL,
    target_day INTEGER,
    progress REAL NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    quality_potential REAL NOT NULL DEFAULT 50 CHECK (quality_potential BETWEEN 0 AND 100),
    funding REAL NOT NULL DEFAULT 50 CHECK (funding BETWEEN 0 AND 100),
    material_access REAL NOT NULL DEFAULT 50 CHECK (material_access BETWEEN 0 AND 100),
    skilled_labor REAL NOT NULL DEFAULT 50 CHECK (skilled_labor BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('planned','active','paused','completed','failed','abandoned')),
    last_resolved_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_civilian_projects_active ON civilian_projects(status,last_resolved_day,id);

CREATE TABLE IF NOT EXISTS cultural_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    object_kind TEXT NOT NULL CHECK (object_kind IN ('painting','sculpture','textile','garment','manuscript','book','jewelry','furniture','instrument','weapon','armor','architectural_element','other')),
    creator_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    workshop_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    created_day INTEGER,
    project_id INTEGER REFERENCES civilian_projects(id) ON DELETE SET NULL,
    current_owner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    current_household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    current_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    quality REAL NOT NULL DEFAULT 50 CHECK (quality BETWEEN 0 AND 100),
    condition REAL NOT NULL DEFAULT 100 CHECK (condition BETWEEN 0 AND 100),
    attribution_confidence REAL NOT NULL DEFAULT 1 CHECK (attribution_confidence BETWEEN 0 AND 1),
    cultural_reputation REAL NOT NULL DEFAULT 0 CHECK (cultural_reputation BETWEEN 0 AND 100),
    market_value REAL NOT NULL DEFAULT 0 CHECK (market_value >= 0),
    significance TEXT NOT NULL DEFAULT 'ordinary' CHECK (significance IN ('ordinary','personal','valuable','historical','institutional')),
    status TEXT NOT NULL DEFAULT 'extant' CHECK (status IN ('extant','damaged','lost','destroyed','disputed')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_cultural_owner ON cultural_objects(current_owner_actor_id,current_household_id,status,id);
CREATE INDEX IF NOT EXISTS idx_cultural_creator ON cultural_objects(creator_actor_id,created_day,id);

CREATE TABLE IF NOT EXISTS object_provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL REFERENCES cultural_objects(id) ON DELETE CASCADE,
    day INTEGER,
    provenance_kind TEXT NOT NULL CHECK (provenance_kind IN ('created','commissioned','sold','inherited','gifted','captured','restored','attributed','disputed','lost','recovered','catalogued')),
    from_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    to_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    record_text TEXT NOT NULL,
    reliability REAL NOT NULL DEFAULT 1 CHECK (reliability BETWEEN 0 AND 1),
    source_record_id INTEGER REFERENCES documentary_records(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_provenance_object ON object_provenance(object_id,day,id);

CREATE TABLE IF NOT EXISTS auctions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    scheduled_day INTEGER NOT NULL,
    resolved_day INTEGER,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','open','resolved','cancelled')),
    prestige REAL NOT NULL DEFAULT 50 CHECK (prestige BETWEEN 0 AND 100),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_auctions_due ON auctions(status,scheduled_day,id);

CREATE TABLE IF NOT EXISTS auction_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auction_id INTEGER NOT NULL REFERENCES auctions(id) ON DELETE CASCADE,
    object_id INTEGER NOT NULL REFERENCES cultural_objects(id) ON DELETE CASCADE,
    seller_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    reserve_price REAL NOT NULL DEFAULT 0 CHECK (reserve_price >= 0),
    estimate_low REAL NOT NULL DEFAULT 0 CHECK (estimate_low >= 0),
    estimate_high REAL NOT NULL DEFAULT 0 CHECK (estimate_high >= estimate_low),
    winning_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    hammer_price REAL CHECK (hammer_price IS NULL OR hammer_price >= 0),
    status TEXT NOT NULL DEFAULT 'listed' CHECK (status IN ('listed','sold','unsold','withdrawn')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_auction_lots_auction ON auction_lots(auction_id,status,id);

CREATE TABLE IF NOT EXISTS auction_interest (
    lot_id INTEGER NOT NULL REFERENCES auction_lots(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    interest REAL NOT NULL DEFAULT 50 CHECK (interest BETWEEN 0 AND 100),
    budget REAL NOT NULL DEFAULT 0 CHECK (budget >= 0),
    taste_fit REAL NOT NULL DEFAULT 50 CHECK (taste_fit BETWEEN 0 AND 100),
    status_motive REAL NOT NULL DEFAULT 0 CHECK (status_motive BETWEEN 0 AND 100),
    PRIMARY KEY(lot_id,actor_id)
);

CREATE TABLE IF NOT EXISTS shadow_market_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('enterprise','object','auction','actor')),
    subject_id INTEGER NOT NULL,
    link_kind TEXT NOT NULL CHECK (link_kind IN ('illicit_dealing','forgery_risk','fencing_risk','smuggling_risk','corrupt_access','disputed_provenance')),
    pressure REAL NOT NULL DEFAULT 0 CHECK (pressure BETWEEN 0 AND 100),
    exposure REAL NOT NULL DEFAULT 0 CHECK (exposure BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'latent' CHECK (status IN ('latent','active','exposed','resolved')),
    notes TEXT,
    created_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_subject ON shadow_market_links(subject_kind,subject_id,status,id);

-- v0.17 deeper civilian life: built environment, styles, succession, credit, partnerships,
-- and profession-specific institutional life.

CREATE TABLE IF NOT EXISTS buildings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    building_kind TEXT NOT NULL CHECK (building_kind IN ('residence','workshop','shop','warehouse','hall','temple','fortified_residence','public_building','bridge','garden','estate_improvement','other')),
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    owner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    project_id INTEGER REFERENCES civilian_projects(id) ON DELETE SET NULL,
    style_key TEXT,
    capacity REAL NOT NULL DEFAULT 50 CHECK (capacity BETWEEN 0 AND 100),
    condition REAL NOT NULL DEFAULT 100 CHECK (condition BETWEEN 0 AND 100),
    prestige REAL NOT NULL DEFAULT 50 CHECK (prestige BETWEEN 0 AND 100),
    utility REAL NOT NULL DEFAULT 50 CHECK (utility BETWEEN 0 AND 100),
    maintenance_burden REAL NOT NULL DEFAULT 10 CHECK (maintenance_burden >= 0),
    completed_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','derelict','destroyed','historical')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_day INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_buildings_location ON buildings(location_id,status,id);
CREATE INDEX IF NOT EXISTS idx_buildings_household ON buildings(household_id,status,id);
CREATE INDEX IF NOT EXISTS idx_buildings_institution ON buildings(institution_actor_id,status,id);

CREATE TABLE IF NOT EXISTS style_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    style_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    style_domain TEXT NOT NULL CHECK (style_domain IN ('dress','textile','architecture','interior','book','decorative')),
    origin_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    origin_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    prestige REAL NOT NULL DEFAULT 50 CHECK (prestige BETWEEN 0 AND 100),
    novelty REAL NOT NULL DEFAULT 50 CHECK (novelty BETWEEN 0 AND 100),
    accessibility REAL NOT NULL DEFAULT 50 CHECK (accessibility BETWEEN 0 AND 100),
    durability REAL NOT NULL DEFAULT 50 CHECK (durability BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'emerging' CHECK (status IN ('emerging','current','established','revival','declining','historical')),
    created_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_style_domain ON style_movements(style_domain,status,id);

CREATE TABLE IF NOT EXISTS style_adoption (
    style_id INTEGER NOT NULL REFERENCES style_movements(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    adoption REAL NOT NULL DEFAULT 0 CHECK (adoption BETWEEN 0 AND 100),
    elite_support REAL NOT NULL DEFAULT 0 CHECK (elite_support BETWEEN 0 AND 100),
    craft_capacity REAL NOT NULL DEFAULT 50 CHECK (craft_capacity BETWEEN 0 AND 100),
    resistance REAL NOT NULL DEFAULT 20 CHECK (resistance BETWEEN 0 AND 100),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(style_id,location_id)
);
CREATE INDEX IF NOT EXISTS idx_style_adoption_location ON style_adoption(location_id,adoption DESC,style_id);

CREATE TABLE IF NOT EXISTS object_style_links (
    object_id INTEGER NOT NULL REFERENCES cultural_objects(id) ON DELETE CASCADE,
    style_id INTEGER NOT NULL REFERENCES style_movements(id) ON DELETE CASCADE,
    strength REAL NOT NULL DEFAULT 100 CHECK (strength BETWEEN 0 AND 100),
    relation_kind TEXT NOT NULL DEFAULT 'made_in' CHECK (relation_kind IN ('made_in','influenced_by','revival_of','attributed_to')),
    PRIMARY KEY(object_id,style_id,relation_kind)
);

CREATE TABLE IF NOT EXISTS household_succession_plans (
    household_id INTEGER PRIMARY KEY REFERENCES households(id) ON DELETE CASCADE,
    designated_heir_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    succession_method TEXT NOT NULL DEFAULT 'designated' CHECK (succession_method IN ('designated','seniority','primogeniture','election','appointment','custom','unsettled')),
    certainty REAL NOT NULL DEFAULT 50 CHECK (certainty BETWEEN 0 AND 100),
    dispute_pressure REAL NOT NULL DEFAULT 0 CHECK (dispute_pressure BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','contested','resolved','obsolete')),
    notes TEXT,
    updated_day INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS inheritance_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    priority REAL NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
    legitimacy REAL NOT NULL DEFAULT 50 CHECK (legitimacy BETWEEN 0 AND 100),
    support REAL NOT NULL DEFAULT 0 CHECK (support BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'potential' CHECK (status IN ('potential','active','waived','satisfied','rejected')),
    notes TEXT,
    UNIQUE(household_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_inheritance_household ON inheritance_claims(household_id,status,priority DESC,id);

CREATE TABLE IF NOT EXISTS succession_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    former_head_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    new_head_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    resolution_kind TEXT NOT NULL CHECK (resolution_kind IN ('designated','claim_strength','manual','vacant')),
    disputed INTEGER NOT NULL DEFAULT 0 CHECK (disputed IN (0,1)),
    summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_succession_events_household ON succession_events(household_id,day,id);

CREATE TABLE IF NOT EXISTS credit_agreements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lender_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    lender_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    borrower_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    borrower_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    principal REAL NOT NULL CHECK (principal > 0),
    outstanding REAL NOT NULL CHECK (outstanding >= 0),
    interest_rate_per_30 REAL NOT NULL DEFAULT 0 CHECK (interest_rate_per_30 >= 0),
    opened_day INTEGER NOT NULL,
    due_day INTEGER,
    collateral_object_id INTEGER REFERENCES cultural_objects(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current','late','defaulted','repaid','written_off')),
    risk REAL NOT NULL DEFAULT 20 CHECK (risk BETWEEN 0 AND 100),
    last_review_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_credit_due ON credit_agreements(status,due_day,last_review_day,id);

CREATE TABLE IF NOT EXISTS enterprise_partners (
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    ownership_share REAL NOT NULL DEFAULT 0 CHECK (ownership_share BETWEEN 0 AND 100),
    governance_weight REAL NOT NULL DEFAULT 0 CHECK (governance_weight BETWEEN 0 AND 100),
    capital_committed REAL NOT NULL DEFAULT 0 CHECK (capital_committed >= 0),
    role TEXT NOT NULL DEFAULT 'partner',
    joined_day INTEGER NOT NULL,
    left_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','former')),
    PRIMARY KEY(enterprise_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_enterprise_partners_actor ON enterprise_partners(actor_id,status,enterprise_id);

CREATE TABLE IF NOT EXISTS professional_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    profession_domain TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    standing REAL NOT NULL DEFAULT 50 CHECK (standing BETWEEN 0 AND 100),
    seniority_days INTEGER NOT NULL DEFAULT 0 CHECK (seniority_days >= 0),
    influence REAL NOT NULL DEFAULT 10 CHECK (influence BETWEEN 0 AND 100),
    dues_per_30 REAL NOT NULL DEFAULT 0 CHECK (dues_per_30 >= 0),
    eligibility_state TEXT NOT NULL DEFAULT 'ordinary' CHECK (eligibility_state IN ('ordinary','eligible_for_review','under_review','restricted')),
    joined_day INTEGER NOT NULL,
    last_review_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','former','retired')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(actor_id,institution_actor_id,profession_domain,joined_day)
);
CREATE INDEX IF NOT EXISTS idx_prof_membership_institution ON professional_memberships(institution_actor_id,profession_domain,status,id);
CREATE INDEX IF NOT EXISTS idx_prof_membership_actor ON professional_memberships(actor_id,status,id);

CREATE TABLE IF NOT EXISTS professional_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    membership_id INTEGER NOT NULL REFERENCES professional_memberships(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    standing_before REAL NOT NULL,
    standing_after REAL NOT NULL,
    eligibility_before TEXT NOT NULL,
    eligibility_after TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prof_reviews_membership ON professional_reviews(membership_id,day,id);

-- v0.18 differentiated business ecology. The archetype catalog is engine vocabulary;
-- a campaign does not imply that every archetype exists in every settlement.
CREATE TABLE IF NOT EXISTS business_archetypes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archetype_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    sector TEXT NOT NULL,
    default_enterprise_kind TEXT NOT NULL,
    base_revenue_per_30 REAL NOT NULL DEFAULT 25 CHECK (base_revenue_per_30 >= 0),
    base_cost_ratio REAL NOT NULL DEFAULT 0.6 CHECK (base_cost_ratio BETWEEN 0 AND 2),
    demand_weights_json TEXT NOT NULL DEFAULT '{}',
    regulation_exposure REAL NOT NULL DEFAULT 0 CHECK (regulation_exposure BETWEEN 0 AND 1),
    skill_sensitive INTEGER NOT NULL DEFAULT 0 CHECK (skill_sensitive IN (0,1)),
    capital_sensitive INTEGER NOT NULL DEFAULT 0 CHECK (capital_sensitive IN (0,1)),
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_business_archetypes_sector ON business_archetypes(sector,archetype_key);

CREATE TABLE IF NOT EXISTS location_commercial_context (
    location_id INTEGER PRIMARY KEY REFERENCES locations(id) ON DELETE CASCADE,
    foot_traffic REAL NOT NULL DEFAULT 50 CHECK (foot_traffic BETWEEN 0 AND 100),
    traveler_flow REAL NOT NULL DEFAULT 50 CHECK (traveler_flow BETWEEN 0 AND 100),
    disposable_income REAL NOT NULL DEFAULT 50 CHECK (disposable_income BETWEEN 0 AND 100),
    trade_flow REAL NOT NULL DEFAULT 50 CHECK (trade_flow BETWEEN 0 AND 100),
    elite_patronage REAL NOT NULL DEFAULT 50 CHECK (elite_patronage BETWEEN 0 AND 100),
    cultural_activity REAL NOT NULL DEFAULT 50 CHECK (cultural_activity BETWEEN 0 AND 100),
    credit_demand REAL NOT NULL DEFAULT 50 CHECK (credit_demand BETWEEN 0 AND 100),
    military_demand REAL NOT NULL DEFAULT 50 CHECK (military_demand BETWEEN 0 AND 100),
    health_demand REAL NOT NULL DEFAULT 50 CHECK (health_demand BETWEEN 0 AND 100),
    craft_demand REAL NOT NULL DEFAULT 50 CHECK (craft_demand BETWEEN 0 AND 100),
    construction_demand REAL NOT NULL DEFAULT 50 CHECK (construction_demand BETWEEN 0 AND 100),
    regulation REAL NOT NULL DEFAULT 50 CHECK (regulation BETWEEN 0 AND 100),
    security REAL NOT NULL DEFAULT 50 CHECK (security BETWEEN 0 AND 100),
    event_activity REAL NOT NULL DEFAULT 50 CHECK (event_activity BETWEEN 0 AND 100),
    reputation_climate REAL NOT NULL DEFAULT 50 CHECK (reputation_climate BETWEEN 0 AND 100),
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS enterprise_business_profiles (
    enterprise_id INTEGER PRIMARY KEY REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    archetype_id INTEGER NOT NULL REFERENCES business_archetypes(id) ON DELETE RESTRICT,
    quality REAL NOT NULL DEFAULT 50 CHECK (quality BETWEEN 0 AND 100),
    price_position REAL NOT NULL DEFAULT 50 CHECK (price_position BETWEEN 0 AND 100),
    capacity REAL NOT NULL DEFAULT 50 CHECK (capacity > 0),
    utilization REAL NOT NULL DEFAULT 0 CHECK (utilization BETWEEN 0 AND 100),
    clientele_fit REAL NOT NULL DEFAULT 50 CHECK (clientele_fit BETWEEN 0 AND 100),
    service_reliability REAL NOT NULL DEFAULT 50 CHECK (service_reliability BETWEEN 0 AND 100),
    regulatory_pressure REAL NOT NULL DEFAULT 0 CHECK (regulatory_pressure BETWEEN 0 AND 100),
    last_resolved_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_business_profiles_due ON enterprise_business_profiles(next_review_day,enterprise_id);
CREATE INDEX IF NOT EXISTS idx_business_profiles_archetype ON enterprise_business_profiles(archetype_id,enterprise_id);

CREATE TABLE IF NOT EXISTS business_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    elapsed_days INTEGER NOT NULL CHECK (elapsed_days >= 0),
    demand_index REAL NOT NULL CHECK (demand_index BETWEEN 0 AND 100),
    utilization REAL NOT NULL CHECK (utilization BETWEEN 0 AND 100),
    gross_revenue REAL NOT NULL DEFAULT 0,
    operating_cost REAL NOT NULL DEFAULT 0,
    net_income REAL NOT NULL DEFAULT 0,
    context_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_business_cycles_enterprise ON business_cycles(enterprise_id,day,id);

-- v0.19 household, kinship, demographic, and life-course simulation.
CREATE TABLE IF NOT EXISTS actor_life_profiles (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    birth_day INTEGER,
    demographic_sex TEXT CHECK (demographic_sex IN ('female','male','unspecified') OR demographic_sex IS NULL),
    life_stage TEXT NOT NULL DEFAULT 'adult' CHECK (life_stage IN ('infant','child','youth','adult','elder')),
    origin_household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    current_household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    family_formation_eligible INTEGER NOT NULL DEFAULT 0 CHECK (family_formation_eligible IN (0,1)),
    life_status TEXT NOT NULL DEFAULT 'living' CHECK (life_status IN ('living','deceased')),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_life_profiles_household ON actor_life_profiles(current_household_id,life_status,actor_id);
CREATE INDEX IF NOT EXISTS idx_life_profiles_birth ON actor_life_profiles(birth_day,life_status,actor_id);


-- v0.43 sustained social context and structural trainee populations beneath the named registry.
CREATE TABLE IF NOT EXISTS social_contact_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    context_kind TEXT NOT NULL CHECK (context_kind IN ('institution','household','work','locality')),
    context_id INTEGER,
    affinity REAL NOT NULL DEFAULT 50 CHECK (affinity BETWEEN 0 AND 100),
    started_day INTEGER NOT NULL,
    last_review_day INTEGER NOT NULL,
    next_review_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','dormant','ended')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(actor_a_id,actor_b_id,context_kind,context_id),
    CHECK(actor_a_id < actor_b_id)
);
CREATE INDEX IF NOT EXISTS idx_social_contacts_due ON social_contact_links(status,next_review_day,actor_a_id,actor_b_id);

CREATE TABLE IF NOT EXISTS kinship_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    kin_kind TEXT NOT NULL CHECK (kin_kind IN ('parent','child','sibling','spouse','guardian','ward','adoptive_parent','adoptive_child','other')),
    legal_status TEXT NOT NULL DEFAULT 'recognized' CHECK (legal_status IN ('recognized','disputed','informal','former')),
    started_day INTEGER NOT NULL,
    ended_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(actor_a_id,actor_b_id,kin_kind,started_day),
    CHECK(actor_a_id <> actor_b_id)
);
CREATE INDEX IF NOT EXISTS idx_kinship_a ON kinship_links(actor_a_id,legal_status,kin_kind,actor_b_id);
CREATE INDEX IF NOT EXISTS idx_kinship_b ON kinship_links(actor_b_id,legal_status,kin_kind,actor_a_id);

CREATE TABLE IF NOT EXISTS household_unions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    union_kind TEXT NOT NULL DEFAULT 'marriage' CHECK (union_kind IN ('marriage','recognized_partnership')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','separated','dissolved','widowed')),
    started_day INTEGER NOT NULL,
    ended_day INTEGER,
    family_plan_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(actor_a_id <> actor_b_id)
);
CREATE INDEX IF NOT EXISTS idx_household_unions_household ON household_unions(household_id,status,id);
CREATE INDEX IF NOT EXISTS idx_household_unions_actor_a ON household_unions(actor_a_id,status,id);
CREATE INDEX IF NOT EXISTS idx_household_unions_actor_b ON household_unions(actor_b_id,status,id);

CREATE TABLE IF NOT EXISTS guardianships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guardian_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    ward_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    authority REAL NOT NULL DEFAULT 70 CHECK (authority BETWEEN 0 AND 100),
    support_level REAL NOT NULL DEFAULT 70 CHECK (support_level BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended')),
    started_day INTEGER NOT NULL,
    ended_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(guardian_actor_id <> ward_actor_id)
);
CREATE INDEX IF NOT EXISTS idx_guardianships_ward ON guardianships(ward_actor_id,status,id);

CREATE TABLE IF NOT EXISTS household_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    dependent_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    sponsor_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    dependency_kind TEXT NOT NULL CHECK (dependency_kind IN ('child','ward','elder','disabled','guest','client','other')),
    support_level REAL NOT NULL DEFAULT 50 CHECK (support_level BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended')),
    started_day INTEGER NOT NULL,
    ended_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_household_dependencies_household ON household_dependencies(household_id,status,id);

CREATE TABLE IF NOT EXISTS household_service_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    service_role TEXT NOT NULL CHECK (service_role IN ('servant','retainer','guard','steward','tutor','apprentice','clerk','other')),
    start_day INTEGER NOT NULL,
    review_day INTEGER NOT NULL,
    end_day INTEGER,
    loyalty REAL NOT NULL DEFAULT 50 CHECK (loyalty BETWEEN 0 AND 100),
    satisfaction REAL NOT NULL DEFAULT 50 CHECK (satisfaction BETWEEN 0 AND 100),
    renewal_bias REAL NOT NULL DEFAULT 50 CHECK (renewal_bias BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','former')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_household_service_due ON household_service_terms(status,review_day,id);

CREATE TABLE IF NOT EXISTS household_migration_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    planned_day INTEGER NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','in_transit','completed','cancelled')),
    created_day INTEGER NOT NULL,
    completed_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_household_migration_due ON household_migration_plans(status,planned_day,id);

CREATE TABLE IF NOT EXISTS life_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    event_kind TEXT NOT NULL CHECK (event_kind IN ('birth','union','separation','dissolution','adoption','guardianship','household_formation','household_split','migration','service_change','death','coming_of_age','other')),
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    related_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_life_events_day ON life_events(day,event_kind,id);
CREATE INDEX IF NOT EXISTS idx_life_events_actor ON life_events(actor_id,day,id);

CREATE TABLE IF NOT EXISTS demographic_cohorts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    cohort_key TEXT NOT NULL,
    age_band TEXT NOT NULL CHECK (age_band IN ('0_4','5_12','13_17','18_39','40_59','60_plus')),
    population REAL NOT NULL DEFAULT 0 CHECK (population >= 0),
    annual_birth_pressure REAL NOT NULL DEFAULT 0 CHECK (annual_birth_pressure >= 0),
    annual_migration_rate REAL NOT NULL DEFAULT 0,
    last_review_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(location_id,cohort_key,age_band)
);
CREATE INDEX IF NOT EXISTS idx_demographic_cohorts_location ON demographic_cohorts(location_id,age_band,id);


-- v0.20 health, aging, recovery, disability, medicine, and mortality.
CREATE TABLE IF NOT EXISTS actor_health_profiles (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    longevity_class TEXT NOT NULL DEFAULT 'ordinary' CHECK (longevity_class IN ('ordinary','first','temper','third','breach','fifth','sixth')),
    aging_phase TEXT NOT NULL DEFAULT 'prime' CHECK (aging_phase IN ('growth','prime','late_decline')),
    baseline_health REAL NOT NULL DEFAULT 80 CHECK (baseline_health BETWEEN 0 AND 100),
    functional_capacity REAL NOT NULL DEFAULT 100 CHECK (functional_capacity BETWEEN 0 AND 100),
    recovery_capacity REAL NOT NULL DEFAULT 100 CHECK (recovery_capacity BETWEEN 0 AND 100),
    injury_resilience REAL NOT NULL DEFAULT 100 CHECK (injury_resilience BETWEEN 0 AND 100),
    stamina_capacity REAL NOT NULL DEFAULT 100 CHECK (stamina_capacity BETWEEN 0 AND 100),
    mobility REAL NOT NULL DEFAULT 100 CHECK (mobility BETWEEN 0 AND 100),
    pain_burden REAL NOT NULL DEFAULT 0 CHECK (pain_burden BETWEEN 0 AND 100),
    chronic_burden REAL NOT NULL DEFAULT 0 CHECK (chronic_burden BETWEEN 0 AND 100),
    mortality_pressure REAL NOT NULL DEFAULT 0 CHECK (mortality_pressure BETWEEN 0 AND 100),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_health_profiles_due ON actor_health_profiles(next_review_day,actor_id);

CREATE TABLE IF NOT EXISTS health_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    condition_kind TEXT NOT NULL CHECK (condition_kind IN ('injury','illness','chronic','vein_channel','vein_core','rupture','fatigue','other')),
    label TEXT NOT NULL,
    body_system TEXT,
    severity REAL NOT NULL CHECK (severity BETWEEN 0 AND 100),
    capacity_impact REAL NOT NULL DEFAULT 0 CHECK (capacity_impact BETWEEN 0 AND 100),
    pain_impact REAL NOT NULL DEFAULT 0 CHECK (pain_impact BETWEEN 0 AND 100),
    recovery_rate_per_30 REAL NOT NULL DEFAULT 0,
    progression_rate_per_30 REAL NOT NULL DEFAULT 0,
    fatality_pressure REAL NOT NULL DEFAULT 0 CHECK (fatality_pressure BETWEEN 0 AND 100),
    specialist_requirement TEXT NOT NULL DEFAULT 'none' CHECK (specialist_requirement IN ('none','physician','vein_mender','legendary_vein_mender')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','recovering','resolved','chronic','fatal')),
    onset_day INTEGER NOT NULL,
    last_review_day INTEGER NOT NULL,
    next_review_day INTEGER NOT NULL,
    resolved_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_health_conditions_due ON health_conditions(status,next_review_day,actor_id);
CREATE INDEX IF NOT EXISTS idx_health_conditions_actor ON health_conditions(actor_id,status,id);

CREATE TABLE IF NOT EXISTS disabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    source_condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    mobility_impact REAL NOT NULL DEFAULT 0 CHECK (mobility_impact BETWEEN 0 AND 100),
    stamina_impact REAL NOT NULL DEFAULT 0 CHECK (stamina_impact BETWEEN 0 AND 100),
    capacity_impact REAL NOT NULL DEFAULT 0 CHECK (capacity_impact BETWEEN 0 AND 100),
    adaptation REAL NOT NULL DEFAULT 0 CHECK (adaptation BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','adapted','resolved')),
    started_day INTEGER NOT NULL,
    ended_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_disabilities_actor ON disabilities(actor_id,status,id);

CREATE TABLE IF NOT EXISTS medical_treatments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    condition_id INTEGER REFERENCES health_conditions(id) ON DELETE CASCADE,
    provider_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    treatment_kind TEXT NOT NULL CHECK (treatment_kind IN ('rest','ordinary_medicine','surgery','rehabilitation','vein_mending','guided_circulation','elixir_stabilization','other')),
    quality REAL NOT NULL DEFAULT 50 CHECK (quality BETWEEN 0 AND 100),
    adherence REAL NOT NULL DEFAULT 70 CHECK (adherence BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','stopped')),
    started_day INTEGER NOT NULL,
    end_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_medical_treatments_actor ON medical_treatments(actor_id,status,id);
CREATE INDEX IF NOT EXISTS idx_medical_treatments_condition ON medical_treatments(condition_id,status,id);

CREATE TABLE IF NOT EXISTS health_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL,
    event_kind TEXT NOT NULL CHECK (event_kind IN ('condition_onset','worsened','improved','resolved','disability','treatment','decline','death','other')),
    summary TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_health_events_actor ON health_events(actor_id,day,id);

CREATE TABLE IF NOT EXISTS demographic_health_state (
    cohort_id INTEGER PRIMARY KEY REFERENCES demographic_cohorts(id) ON DELETE CASCADE,
    annual_mortality_rate REAL NOT NULL DEFAULT 0 CHECK (annual_mortality_rate BETWEEN 0 AND 1),
    health_modifier REAL NOT NULL DEFAULT 1 CHECK (health_modifier >= 0),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- v0.21 religion and cultural institutions. Tradition rows are setting vocabulary;
-- observances, adherents, institutions, calendars and offices remain campaign state.
CREATE TABLE IF NOT EXISTS religious_traditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tradition_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    tradition_kind TEXT NOT NULL CHECK (tradition_kind IN ('household_rite','organized','revealed','local','other')),
    centralization REAL NOT NULL DEFAULT 0 CHECK (centralization BETWEEN 0 AND 100),
    exclusivity_claim REAL NOT NULL DEFAULT 0 CHECK (exclusivity_claim BETWEEN 0 AND 100),
    canon_status TEXT NOT NULL DEFAULT 'working' CHECK (canon_status IN ('settled','working','proposal','signoff_pending','open')),
    description TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS religious_affiliations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    tradition_id INTEGER NOT NULL REFERENCES religious_traditions(id) ON DELETE RESTRICT,
    affiliation_kind TEXT NOT NULL DEFAULT 'adherent' CHECK (affiliation_kind IN ('adherent','participant','sympathetic','raised_in','former')),
    practice_intensity REAL NOT NULL DEFAULT 50 CHECK (practice_intensity BETWEEN 0 AND 100),
    publicness REAL NOT NULL DEFAULT 50 CHECK (publicness BETWEEN 0 AND 100),
    joined_day INTEGER NOT NULL,
    left_day INTEGER,
    last_observance_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','former')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_relig_aff_active ON religious_affiliations(actor_id,tradition_id) WHERE status='active';

CREATE TABLE IF NOT EXISTS religious_institutions (
    institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    tradition_id INTEGER NOT NULL REFERENCES religious_traditions(id) ON DELETE RESTRICT,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    authority REAL NOT NULL DEFAULT 40 CHECK (authority BETWEEN 0 AND 100),
    ritual_capacity REAL NOT NULL DEFAULT 50 CHECK (ritual_capacity BETWEEN 0 AND 100),
    charity_commitment REAL NOT NULL DEFAULT 10 CHECK (charity_commitment BETWEEN 0 AND 100),
    treasury REAL NOT NULL DEFAULT 0 CHECK (treasury >= 0),
    reputation REAL NOT NULL DEFAULT 50 CHECK (reputation BETWEEN 0 AND 100),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','dormant','dissolved')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_relig_inst_due ON religious_institutions(next_review_day,status,institution_actor_id);

CREATE TABLE IF NOT EXISTS religious_offices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    standing REAL NOT NULL DEFAULT 50 CHECK (standing BETWEEN 0 AND 100),
    seniority_days INTEGER NOT NULL DEFAULT 0 CHECK (seniority_days >= 0),
    started_day INTEGER NOT NULL,
    last_review_day INTEGER NOT NULL DEFAULT 0,
    ended_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','former','vacant')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_relig_office_inst ON religious_offices(institution_actor_id,status,id);

CREATE TABLE IF NOT EXISTS religious_observances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tradition_id INTEGER NOT NULL REFERENCES religious_traditions(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    observance_kind TEXT NOT NULL DEFAULT 'seasonal',
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    recurrence_days INTEGER CHECK (recurrence_days IS NULL OR recurrence_days >= 1),
    next_due_day INTEGER NOT NULL,
    public_event INTEGER NOT NULL DEFAULT 1 CHECK (public_event IN (0,1)),
    significance REAL NOT NULL DEFAULT 50 CHECK (significance BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','ended')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_relig_observance_due ON religious_observances(status,next_due_day,id);

CREATE TABLE IF NOT EXISTS religious_observance_instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observance_id INTEGER NOT NULL REFERENCES religious_observances(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    UNIQUE(observance_id,day)
);

CREATE TABLE IF NOT EXISTS religious_attendance (
    instance_id INTEGER NOT NULL REFERENCES religious_observance_instances(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    participation_kind TEXT NOT NULL DEFAULT 'attended',
    PRIMARY KEY(instance_id,actor_id)
);

CREATE TABLE IF NOT EXISTS religious_obligations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
    household_id INTEGER REFERENCES households(id) ON DELETE CASCADE,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
    tradition_id INTEGER REFERENCES religious_traditions(id) ON DELETE SET NULL,
    obligation_kind TEXT NOT NULL,
    description TEXT NOT NULL,
    due_day INTEGER NOT NULL,
    recurrence_days INTEGER CHECK (recurrence_days IS NULL OR recurrence_days >= 1),
    reputation_stakes REAL NOT NULL DEFAULT 10 CHECK (reputation_stakes BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','overdue','fulfilled','waived','cancelled')),
    fulfilled_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_relig_obligation_due ON religious_obligations(status,due_day,id);

CREATE TABLE IF NOT EXISTS sacred_sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tradition_id INTEGER REFERENCES religious_traditions(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    building_id INTEGER REFERENCES buildings(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    site_kind TEXT NOT NULL DEFAULT 'shrine',
    sanctity_reputation REAL NOT NULL DEFAULT 50 CHECK (sanctity_reputation BETWEEN 0 AND 100),
    access_kind TEXT NOT NULL DEFAULT 'public' CHECK (access_kind IN ('public','limited','private','restricted')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','damaged','abandoned','destroyed','historical')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS cultural_institution_profiles (
    institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    cultural_domain TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    prestige REAL NOT NULL DEFAULT 50 CHECK (prestige BETWEEN 0 AND 100),
    resources REAL NOT NULL DEFAULT 0 CHECK (resources >= 0),
    public_reach REAL NOT NULL DEFAULT 50 CHECK (public_reach BETWEEN 0 AND 100),
    continuity REAL NOT NULL DEFAULT 50 CHECK (continuity BETWEEN 0 AND 100),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','dormant','dissolved')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_cultural_inst_due ON cultural_institution_profiles(next_review_day,status,institution_actor_id);

CREATE TABLE IF NOT EXISTS cultural_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    program_kind TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    style_id INTEGER REFERENCES style_movements(id) ON DELETE SET NULL,
    recurrence_days INTEGER CHECK (recurrence_days IS NULL OR recurrence_days >= 1),
    next_due_day INTEGER NOT NULL,
    prestige_effect REAL NOT NULL DEFAULT 1,
    reach REAL NOT NULL DEFAULT 50 CHECK (reach BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','ended')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_cultural_program_due ON cultural_programs(status,next_due_day,id);

CREATE TABLE IF NOT EXISTS cultural_program_instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER NOT NULL REFERENCES cultural_programs(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    UNIQUE(program_id,day)
);

CREATE TABLE IF NOT EXISTS institutional_patronage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_household_id INTEGER REFERENCES households(id) ON DELETE CASCADE,
    source_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    target_religious_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
    target_cultural_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
    amount REAL NOT NULL CHECK (amount > 0),
    recurrence_days INTEGER CHECK (recurrence_days IS NULL OR recurrence_days >= 1),
    next_due_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','ended')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_patronage_due ON institutional_patronage(status,next_due_day,id);

CREATE TABLE IF NOT EXISTS social_reputation (
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('actor','household','institution')),
    subject_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 50 CHECK (value BETWEEN 0 AND 100),
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(subject_kind,subject_id,domain)
);

-- v0.22 Ecology, seasons, travel, and environmental pressure
CREATE TABLE IF NOT EXISTS location_environment_profiles (
    location_id INTEGER PRIMARY KEY REFERENCES locations(id) ON DELETE CASCADE,
    climate_label TEXT,
    terrain_kind TEXT,
    year_length INTEGER NOT NULL DEFAULT 360 CHECK (year_length >= 30),
    phase_offset INTEGER NOT NULL DEFAULT 0,
    base_travel_factor REAL NOT NULL DEFAULT 1.0 CHECK (base_travel_factor > 0),
    base_production_factor REAL NOT NULL DEFAULT 1.0 CHECK (base_production_factor > 0),
    base_health_pressure REAL NOT NULL DEFAULT 0 CHECK (base_health_pressure BETWEEN 0 AND 100),
    current_density REAL NOT NULL DEFAULT 50 CHECK (current_density BETWEEN 0 AND 100),
    current_stability REAL NOT NULL DEFAULT 50 CHECK (current_stability BETWEEN 0 AND 100),
    current_replenishment REAL NOT NULL DEFAULT 50 CHECK (current_replenishment BETWEEN 0 AND 100),
    current_breadth REAL NOT NULL DEFAULT 50 CHECK (current_breadth BETWEEN 0 AND 100),
    current_concentration REAL NOT NULL DEFAULT 50 CHECK (current_concentration BETWEEN 0 AND 100),
    current_carrying_capacity REAL NOT NULL DEFAULT 100 CHECK (current_carrying_capacity >= 0),
    current_load REAL NOT NULL DEFAULT 0 CHECK (current_load >= 0),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','degraded','inactive')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_environment_due ON location_environment_profiles(status,next_review_day,location_id);

CREATE TABLE IF NOT EXISTS seasonal_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    start_day_of_year INTEGER NOT NULL CHECK (start_day_of_year >= 0),
    end_day_of_year INTEGER NOT NULL CHECK (end_day_of_year >= 0),
    travel_factor REAL NOT NULL DEFAULT 1.0 CHECK (travel_factor > 0),
    production_factor REAL NOT NULL DEFAULT 1.0 CHECK (production_factor > 0),
    health_pressure REAL NOT NULL DEFAULT 0 CHECK (health_pressure BETWEEN 0 AND 100),
    current_replenishment_factor REAL NOT NULL DEFAULT 1.0 CHECK (current_replenishment_factor >= 0),
    route_risk_delta REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','ended')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(location_id,name)
);
CREATE INDEX IF NOT EXISTS idx_seasonal_location ON seasonal_windows(location_id,status,id);

CREATE TABLE IF NOT EXISTS environmental_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    condition_kind TEXT NOT NULL,
    label TEXT NOT NULL,
    start_day INTEGER NOT NULL,
    end_day INTEGER,
    travel_factor REAL NOT NULL DEFAULT 1.0 CHECK (travel_factor > 0),
    production_factor REAL NOT NULL DEFAULT 1.0 CHECK (production_factor > 0),
    health_pressure REAL NOT NULL DEFAULT 0 CHECK (health_pressure BETWEEN 0 AND 100),
    current_replenishment_factor REAL NOT NULL DEFAULT 1.0 CHECK (current_replenishment_factor >= 0),
    route_risk_delta REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended','cancelled')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_environment_condition_active ON environmental_conditions(location_id,status,start_day,end_day,id);

CREATE TABLE IF NOT EXISTS travel_routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    to_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    route_kind TEXT NOT NULL DEFAULT 'road' CHECK (route_kind IN ('road','track','pass','river','sea','trail','other')),
    base_days REAL NOT NULL CHECK (base_days > 0),
    capacity REAL NOT NULL DEFAULT 50 CHECK (capacity BETWEEN 0 AND 100),
    reliability REAL NOT NULL DEFAULT 80 CHECK (reliability BETWEEN 0 AND 100),
    seasonal_sensitivity REAL NOT NULL DEFAULT 1.0 CHECK (seasonal_sensitivity >= 0),
    bidirectional INTEGER NOT NULL DEFAULT 1 CHECK (bidirectional IN (0,1)),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','restricted','closed','destroyed')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(from_location_id,to_location_id,route_kind)
);
CREATE INDEX IF NOT EXISTS idx_routes_from ON travel_routes(from_location_id,status,to_location_id,id);
CREATE INDEX IF NOT EXISTS idx_routes_to ON travel_routes(to_location_id,status,from_location_id,id);

CREATE TABLE IF NOT EXISTS route_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL REFERENCES travel_routes(id) ON DELETE CASCADE,
    condition_kind TEXT NOT NULL,
    label TEXT NOT NULL,
    start_day INTEGER NOT NULL,
    end_day INTEGER,
    accessibility REAL NOT NULL DEFAULT 100 CHECK (accessibility BETWEEN 0 AND 100),
    delay_factor REAL NOT NULL DEFAULT 1.0 CHECK (delay_factor > 0),
    hazard_pressure REAL NOT NULL DEFAULT 0 CHECK (hazard_pressure BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended','cancelled')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_route_condition_active ON route_conditions(route_id,status,start_day,end_day,id);

CREATE TABLE IF NOT EXISTS commercial_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(enterprise_id,location_id,good_id)
);
CREATE INDEX IF NOT EXISTS idx_commercial_stock_location ON commercial_stock(location_id,good_id,enterprise_id);

CREATE TABLE IF NOT EXISTS commercial_shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    source_production_site_id INTEGER REFERENCES production_sites(id) ON DELETE SET NULL,
    source_stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL,
    recipient_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    trade_contract_id INTEGER REFERENCES merchant_trade_contracts(id) ON DELETE SET NULL,
    carrier_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    freight_cost REAL NOT NULL DEFAULT 0 CHECK (freight_cost >= 0),
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK (quantity > 0),
    origin_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    current_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    current_route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
    segment_due_day INTEGER,
    next_review_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_transit' CHECK (status IN ('in_transit','stalled','delivered','cancelled','lost')),
    started_day INTEGER NOT NULL,
    arrived_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(origin_location_id <> destination_location_id)
);
CREATE INDEX IF NOT EXISTS idx_commercial_shipments_due ON commercial_shipments(status,next_review_day,id);
CREATE INDEX IF NOT EXISTS idx_commercial_shipments_enterprise ON commercial_shipments(enterprise_id,status,id);

CREATE TABLE IF NOT EXISTS travel_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('actor','household')),
    subject_id INTEGER NOT NULL,
    origin_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    current_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    current_route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
    started_day INTEGER NOT NULL,
    segment_started_day INTEGER,
    segment_due_day INTEGER,
    next_review_day INTEGER NOT NULL,
    exposure_pressure REAL NOT NULL DEFAULT 0 CHECK (exposure_pressure >= 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','stalled','arrived','cancelled')),
    arrived_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_travel_due ON travel_plans(status,next_review_day,id);

CREATE TABLE IF NOT EXISTS current_usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    source_kind TEXT NOT NULL DEFAULT 'simulation',
    source_id INTEGER,
    description TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_current_usage_location ON current_usage_events(location_id,day,id);


-- v0.23 politics, state transformation, and macro-history.
CREATE TABLE IF NOT EXISTS political_polities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_actor_id INTEGER NOT NULL UNIQUE REFERENCES actors(id) ON DELETE CASCADE,
    polity_kind TEXT NOT NULL,
    ruler_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    ruling_dynasty_id INTEGER,
    succession_method TEXT NOT NULL DEFAULT 'custom' CHECK (succession_method IN ('designated','hereditary','elective','appointment','custom','unsettled')),
    legitimacy REAL NOT NULL DEFAULT 50 CHECK (legitimacy BETWEEN 0 AND 100),
    stability REAL NOT NULL DEFAULT 50 CHECK (stability BETWEEN 0 AND 100),
    administrative_capacity REAL NOT NULL DEFAULT 50 CHECK (administrative_capacity BETWEEN 0 AND 100),
    military_capacity REAL NOT NULL DEFAULT 50 CHECK (military_capacity BETWEEN 0 AND 100),
    treasury_pressure REAL NOT NULL DEFAULT 0 CHECK (treasury_pressure BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','regency','succession_crisis','fragmenting','dissolved')),
    founded_day INTEGER,
    dissolved_day INTEGER,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    review_cadence_days INTEGER NOT NULL DEFAULT 30 CHECK (review_cadence_days>=1),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_political_polities_due ON political_polities(status,next_review_day,id);

CREATE TABLE IF NOT EXISTS political_dynasties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    home_polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    prestige REAL NOT NULL DEFAULT 50 CHECK (prestige BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','displaced','extinct','historical')),
    founded_day INTEGER,
    ended_day INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS political_dynasty_members (
    dynasty_id INTEGER NOT NULL REFERENCES political_dynasties(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    relation_label TEXT,
    seniority REAL NOT NULL DEFAULT 50 CHECK (seniority BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'member' CHECK (status IN ('member','head','former','deceased')),
    joined_day INTEGER,
    left_day INTEGER,
    PRIMARY KEY(dynasty_id,actor_id)
);

CREATE TABLE IF NOT EXISTS territorial_control (
    location_id INTEGER PRIMARY KEY REFERENCES locations(id) ON DELETE CASCADE,
    controller_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE RESTRICT,
    control_kind TEXT NOT NULL DEFAULT 'direct' CHECK (control_kind IN ('direct','vassal','occupied','disputed','chartered')),
    since_day INTEGER NOT NULL DEFAULT 0,
    legitimacy REAL NOT NULL DEFAULT 50 CHECK (legitimacy BETWEEN 0 AND 100),
    integration REAL NOT NULL DEFAULT 50 CHECK (integration BETWEEN 0 AND 100),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_territorial_controller ON territorial_control(controller_polity_id,location_id);

CREATE TABLE IF NOT EXISTS territorial_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claimant_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    claim_kind TEXT NOT NULL DEFAULT 'historical',
    legitimacy REAL NOT NULL DEFAULT 50 CHECK (legitimacy BETWEEN 0 AND 100),
    support REAL NOT NULL DEFAULT 0 CHECK (support BETWEEN 0 AND 100),
    pressure REAL NOT NULL DEFAULT 0 CHECK (pressure BETWEEN 0 AND 100),
    rate_per_30_days REAL NOT NULL DEFAULT 0,
    volatility REAL NOT NULL DEFAULT 0 CHECK (volatility BETWEEN 0 AND 1),
    threshold REAL NOT NULL DEFAULT 75 CHECK (threshold BETWEEN 1 AND 100),
    resolution_policy TEXT NOT NULL DEFAULT 'dispute' CHECK (resolution_policy IN ('none','dispute','recognize','transfer')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','pressed','recognized','fulfilled','renounced','failed')),
    created_day INTEGER NOT NULL DEFAULT 0,
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    review_cadence_days INTEGER NOT NULL DEFAULT 30 CHECK (review_cadence_days>=1),
    UNIQUE(claimant_polity_id,location_id,claim_kind,status)
);
CREATE INDEX IF NOT EXISTS idx_territorial_claims_due ON territorial_claims(status,next_review_day,id);

CREATE TABLE IF NOT EXISTS political_relations (
    polity_a_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    polity_b_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    relation_kind TEXT NOT NULL DEFAULT 'neutral' CHECK (relation_kind IN ('neutral','friendly','allied','rival','hostile','war','truce')),
    stance REAL NOT NULL DEFAULT 0 CHECK (stance BETWEEN -100 AND 100),
    trust REAL NOT NULL DEFAULT 0 CHECK (trust BETWEEN -100 AND 100),
    tension REAL NOT NULL DEFAULT 0 CHECK (tension BETWEEN 0 AND 100),
    updated_day INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    PRIMARY KEY(polity_a_id,polity_b_id),
    CHECK(polity_a_id < polity_b_id)
);

CREATE TABLE IF NOT EXISTS political_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    senior_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    junior_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    link_kind TEXT NOT NULL CHECK (link_kind IN ('vassalage','protectorate','federation','personal_union','tributary')),
    start_day INTEGER NOT NULL DEFAULT 0,
    end_day INTEGER,
    autonomy REAL NOT NULL DEFAULT 50 CHECK (autonomy BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended','broken')),
    terms_json TEXT NOT NULL DEFAULT '{}',
    CHECK(senior_polity_id <> junior_polity_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_political_link_active_unique ON political_links(senior_polity_id,junior_polity_id,link_kind,status);

CREATE TABLE IF NOT EXISTS political_succession_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    claimant_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    dynasty_id INTEGER REFERENCES political_dynasties(id) ON DELETE SET NULL,
    legitimacy REAL NOT NULL DEFAULT 50 CHECK (legitimacy BETWEEN 0 AND 100),
    support REAL NOT NULL DEFAULT 0 CHECK (support BETWEEN 0 AND 100),
    priority REAL NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','chosen','withdrawn','defeated','dead')),
    created_day INTEGER NOT NULL DEFAULT 0,
    resolved_day INTEGER,
    UNIQUE(polity_id,claimant_actor_id,status)
);
CREATE INDEX IF NOT EXISTS idx_succession_polity ON political_succession_claims(polity_id,status,id);

CREATE TABLE IF NOT EXISTS political_processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    process_type TEXT NOT NULL CHECK (process_type IN ('integration','separatism','legitimacy','stability','treasury','diplomacy')),
    location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE,
    target_polity_id INTEGER REFERENCES political_polities(id) ON DELETE CASCADE,
    rate_per_30_days REAL NOT NULL DEFAULT 0,
    volatility REAL NOT NULL DEFAULT 0 CHECK (volatility BETWEEN 0 AND 1),
    accumulator REAL NOT NULL DEFAULT 0,
    threshold REAL NOT NULL DEFAULT 10 CHECK (threshold>0),
    auto_action TEXT NOT NULL DEFAULT 'none' CHECK (auto_action IN ('none','mark_disputed','open_claim','fragment')),
    last_resolved_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    cadence_days INTEGER NOT NULL DEFAULT 30 CHECK (cadence_days>=1),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_political_process_due ON political_processes(active,next_review_day,id);

CREATE TABLE IF NOT EXISTS political_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    transition_type TEXT NOT NULL,
    polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    other_polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_political_history_day ON political_history(day,id);

-- v0.24 education, transmission, and institutional reproduction.
CREATE TABLE IF NOT EXISTS education_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
    program_key TEXT NOT NULL,
    name TEXT NOT NULL,
    domain_key TEXT NOT NULL,
    program_kind TEXT NOT NULL CHECK (program_kind IN ('apprenticeship','institutional_training','martial_foundation','advanced_instruction','professional_training','scholarly_training','medical_training','craft_training','tutoring','other')),
    duration_days INTEGER NOT NULL CHECK (duration_days>=1),
    capacity INTEGER NOT NULL DEFAULT 10 CHECK (capacity>=1),
    min_entry_score REAL NOT NULL DEFAULT 0 CHECK (min_entry_score BETWEEN 0 AND 100),
    min_teacher_score REAL NOT NULL DEFAULT 0 CHECK (min_teacher_score BETWEEN 0 AND 100),
    completion_gain REAL NOT NULL DEFAULT 5 CHECK (completion_gain BETWEEN 0 AND 100),
    max_score_from_program REAL NOT NULL DEFAULT 70 CHECK (max_score_from_program BETWEEN 0 AND 100),
    certificate_key TEXT,
    lineage_key TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','closed','historical')),
    created_day INTEGER NOT NULL DEFAULT 0,
    review_cadence_days INTEGER NOT NULL DEFAULT 30 CHECK (review_cadence_days>=1),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(institution_actor_id,program_key)
);
CREATE INDEX IF NOT EXISTS idx_education_program_domain ON education_programs(domain_key,status,id);

CREATE TABLE IF NOT EXISTS teaching_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    student_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    relation_kind TEXT NOT NULL CHECK (relation_kind IN ('instructor','mentor','personal_master','apprenticeship_supervisor','tutor','examiner','lineage_teacher')),
    domain_key TEXT NOT NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    responsibility REAL NOT NULL DEFAULT 50 CHECK (responsibility BETWEEN 0 AND 100),
    start_day INTEGER NOT NULL,
    end_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended','interrupted','repudiated')),
    notes TEXT,
    CHECK(teacher_actor_id<>student_actor_id)
);
CREATE INDEX IF NOT EXISTS idx_teaching_teacher ON teaching_relationships(teacher_actor_id,status,domain_key,id);
CREATE INDEX IF NOT EXISTS idx_teaching_student ON teaching_relationships(student_actor_id,status,domain_key,id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_teaching_active_unique ON teaching_relationships(teacher_actor_id,student_actor_id,relation_kind,domain_key) WHERE status='active';

CREATE TABLE IF NOT EXISTS education_enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    program_id INTEGER NOT NULL REFERENCES education_programs(id) ON DELETE CASCADE,
    primary_teacher_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    started_day INTEGER NOT NULL,
    progress_days REAL NOT NULL DEFAULT 0 CHECK (progress_days>=0),
    practice_quality REAL NOT NULL DEFAULT 1 CHECK (practice_quality BETWEEN 0 AND 1.5),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','completed','withdrawn','failed','deceased')),
    interruption_reason TEXT,
    completed_day INTEGER,
    last_review_day INTEGER NOT NULL,
    next_review_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_education_enrollment_due ON education_enrollments(status,next_review_day,id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_education_active_unique ON education_enrollments(actor_id,program_id) WHERE status IN ('active','paused');

CREATE TABLE IF NOT EXISTS knowledge_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    asset_kind TEXT NOT NULL CHECK (asset_kind IN ('manual','archive','curriculum','oral_lineage','formless_trace','demonstration_record','craft_pattern','medical_record','scholarly_work','other')),
    domain_key TEXT NOT NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    lineage_key TEXT,
    access_tier TEXT NOT NULL DEFAULT 'limited' CHECK (access_tier IN ('public','member','limited','inner','keeper','secret')),
    completeness REAL NOT NULL DEFAULT 1 CHECK (completeness BETWEEN 0 AND 1),
    teachability REAL NOT NULL DEFAULT 0.5 CHECK (teachability BETWEEN 0 AND 1),
    preservation_mode TEXT NOT NULL DEFAULT 'documented' CHECK (preservation_mode IN ('documented','mixed','oral','embodied','site_bound')),
    loss_threshold_days INTEGER CHECK (loss_threshold_days IS NULL OR loss_threshold_days>=1),
    status TEXT NOT NULL DEFAULT 'extant' CHECK (status IN ('extant','endangered','inaccessible','lost','destroyed','historical')),
    created_day INTEGER NOT NULL DEFAULT 0,
    last_review_day INTEGER NOT NULL DEFAULT 0,
    endangered_since_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_knowledge_asset_domain ON knowledge_assets(domain_key,status,id);

CREATE TABLE IF NOT EXISTS knowledge_custody (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES knowledge_assets(id) ON DELETE CASCADE,
    actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
    custody_kind TEXT NOT NULL CHECK (custody_kind IN ('owner','keeper','copy_holder','teacher','archive','site_custodian')),
    start_day INTEGER NOT NULL,
    end_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended','lost','destroyed')),
    notes TEXT,
    CHECK(actor_id IS NOT NULL OR institution_actor_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_custody_asset ON knowledge_custody(asset_id,status,id);

CREATE TABLE IF NOT EXISTS knowledge_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES knowledge_assets(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    access_level TEXT NOT NULL DEFAULT 'study' CHECK (access_level IN ('view','consult','study','practice','teach','keeper')),
    granted_by_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    granted_day INTEGER NOT NULL,
    revoked_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked','expired')),
    notes TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_access_active_unique ON knowledge_access(asset_id,actor_id) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_knowledge_access_actor ON knowledge_access(actor_id,status,asset_id);

CREATE TABLE IF NOT EXISTS program_knowledge_assets (
    program_id INTEGER NOT NULL REFERENCES education_programs(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES knowledge_assets(id) ON DELETE CASCADE,
    requirement_kind TEXT NOT NULL DEFAULT 'supporting' CHECK (requirement_kind IN ('supporting','required_access','required_teacher_access')),
    PRIMARY KEY(program_id,asset_id)
);

CREATE TABLE IF NOT EXISTS transmission_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    lineage_key TEXT NOT NULL,
    name TEXT NOT NULL,
    domain_key TEXT NOT NULL,
    parent_line_id INTEGER REFERENCES transmission_lines(id) ON DELETE SET NULL,
    founding_teacher_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    interpretation_summary TEXT,
    vitality REAL NOT NULL DEFAULT 70 CHECK (vitality BETWEEN 0 AND 100),
    fragility_per_year REAL NOT NULL DEFAULT 8 CHECK (fragility_per_year BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','fragile','dormant','historical','lost')),
    created_day INTEGER NOT NULL DEFAULT 0,
    last_review_day INTEGER NOT NULL DEFAULT 0,
    dormant_since_day INTEGER,
    UNIQUE(institution_actor_id,lineage_key)
);
CREATE INDEX IF NOT EXISTS idx_transmission_lines_domain ON transmission_lines(domain_key,status,id);

CREATE TABLE IF NOT EXISTS actor_transmissions (
    line_id INTEGER NOT NULL REFERENCES transmission_lines(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    relation_kind TEXT NOT NULL CHECK (relation_kind IN ('student','teacher','inheritor','keeper','former')),
    depth REAL NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 100),
    joined_day INTEGER NOT NULL,
    left_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','former','deceased','repudiated')),
    PRIMARY KEY(line_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_actor_transmission_actor ON actor_transmissions(actor_id,status,line_id);

CREATE TABLE IF NOT EXISTS professional_certifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    domain_key TEXT NOT NULL,
    certificate_key TEXT NOT NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    level REAL NOT NULL DEFAULT 50 CHECK (level BETWEEN 0 AND 100),
    granted_day INTEGER NOT NULL,
    expires_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','expired','revoked','historical')),
    notes TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_professional_cert_active ON professional_certifications(actor_id,certificate_key) WHERE status='active';

CREATE TABLE IF NOT EXISTS institution_reproduction_profiles (
    institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    recruitment_capacity REAL NOT NULL DEFAULT 50 CHECK (recruitment_capacity BETWEEN 0 AND 100),
    training_capacity REAL NOT NULL DEFAULT 50 CHECK (training_capacity BETWEEN 0 AND 100),
    instructor_depth REAL NOT NULL DEFAULT 50 CHECK (instructor_depth BETWEEN 0 AND 100),
    archival_resilience REAL NOT NULL DEFAULT 50 CHECK (archival_resilience BETWEEN 0 AND 100),
    pipeline_health REAL NOT NULL DEFAULT 50 CHECK (pipeline_health BETWEEN 0 AND 100),
    continuity_pressure REAL NOT NULL DEFAULT 0 CHECK (continuity_pressure BETWEEN 0 AND 100),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 90,
    review_cadence_days INTEGER NOT NULL DEFAULT 90 CHECK (review_cadence_days>=1),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_reproduction_due ON institution_reproduction_profiles(next_review_day,institution_actor_id);

CREATE TABLE IF NOT EXISTS institutional_successor_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    role_key TEXT NOT NULL,
    readiness REAL NOT NULL DEFAULT 0 CHECK (readiness BETWEEN 0 AND 100),
    legitimacy REAL NOT NULL DEFAULT 50 CHECK (legitimacy BETWEEN 0 AND 100),
    transmission_depth REAL NOT NULL DEFAULT 0 CHECK (transmission_depth BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','eligible','chosen','withdrawn','deceased','rejected')),
    created_day INTEGER NOT NULL DEFAULT 0,
    updated_day INTEGER NOT NULL DEFAULT 0,
    UNIQUE(institution_actor_id,actor_id,role_key)
);
CREATE INDEX IF NOT EXISTS idx_successor_candidates_inst ON institutional_successor_candidates(institution_actor_id,role_key,status,id);

CREATE TABLE IF NOT EXISTS education_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    event_kind TEXT NOT NULL,
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    teacher_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    program_id INTEGER REFERENCES education_programs(id) ON DELETE SET NULL,
    line_id INTEGER REFERENCES transmission_lines(id) ON DELETE SET NULL,
    asset_id INTEGER REFERENCES knowledge_assets(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_education_history_day ON education_history(day,id);

-- v0.25 long-run simulation, camera succession, and stress audit records
CREATE TABLE IF NOT EXISTS player_camera_successors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    successor_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    priority INTEGER NOT NULL DEFAULT 50,
    status TEXT NOT NULL DEFAULT 'designated' CHECK (status IN ('designated','used','revoked','unavailable')),
    designated_day INTEGER NOT NULL,
    resolved_day INTEGER,
    notes TEXT,
    UNIQUE(from_actor_id, successor_actor_id),
    CHECK(from_actor_id <> successor_actor_id)
);

CREATE TABLE IF NOT EXISTS player_camera_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    from_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    to_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    campaign_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_camera_history_day ON player_camera_history(day,id);

CREATE TABLE IF NOT EXISTS stress_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    scenario_kind TEXT NOT NULL,
    start_day INTEGER NOT NULL,
    target_day INTEGER NOT NULL,
    end_day INTEGER,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','passed','failed')),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    duration_seconds REAL,
    start_snapshot_json TEXT NOT NULL DEFAULT '{}',
    end_snapshot_json TEXT,
    summary_json TEXT,
    failure_text TEXT
);

CREATE TABLE IF NOT EXISTS stress_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES stress_runs(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    label TEXT,
    snapshot_json TEXT NOT NULL,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(run_id, day, label)
);

CREATE TABLE IF NOT EXISTS stress_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES stress_runs(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info','warning','error')),
    issue_key TEXT NOT NULL,
    detail TEXT NOT NULL
);

-- v0.26 / v1.0-preRC: migration history, production campaign bootstrap,
-- and explicit seed provenance. These tables are administrative metadata and
-- do not replace authoritative domain tables.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    migration_key TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaign_seed_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_id TEXT NOT NULL,
    seed_version INTEGER NOT NULL,
    source_name TEXT,
    source_hash TEXT,
    status TEXT NOT NULL DEFAULT 'applied' CHECK (status IN ('applying','applied','failed')),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(seed_id,seed_version)
);

CREATE TABLE IF NOT EXISTS campaign_seed_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_run_id INTEGER NOT NULL REFERENCES campaign_seed_runs(id) ON DELETE CASCADE,
    entity_kind TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    seed_key TEXT NOT NULL,
    source_status TEXT NOT NULL DEFAULT 'working' CHECK (source_status IN ('settled','working','proposal','open','campaign')),
    source_ref TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(seed_run_id,entity_kind,entity_id),
    UNIQUE(seed_run_id,seed_key)
);
CREATE INDEX IF NOT EXISTS idx_campaign_seed_entity ON campaign_seed_entities(entity_kind,entity_id);

CREATE TABLE IF NOT EXISTS campaign_setup_state (
    id INTEGER PRIMARY KEY CHECK (id=1),
    seed_id TEXT,
    seed_version INTEGER,
    bootstrap_complete INTEGER NOT NULL DEFAULT 0 CHECK (bootstrap_complete IN (0,1)),
    player_setup_complete INTEGER NOT NULL DEFAULT 0 CHECK (player_setup_complete IN (0,1)),
    setup_notes_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- v0.27: current-canon bridge, runtime coverage observability, institution membership,
-- and two-way resolution support for people and institutions.

CREATE TABLE IF NOT EXISTS source_identity_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_namespace TEXT NOT NULL,
    source_key TEXT NOT NULL,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN (
        'actor','institution','location','route','household','cohort','claim','process','enterprise','other'
    )),
    entity_id INTEGER NOT NULL,
    canon_status TEXT,
    provenance_json TEXT NOT NULL DEFAULT '[]',
    source_payload_json TEXT NOT NULL DEFAULT '{}',
    created_day INTEGER NOT NULL DEFAULT 0,
    updated_day INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source_namespace,source_key)
);
CREATE INDEX IF NOT EXISTS idx_source_identity_entity
ON source_identity_map(entity_kind,entity_id,source_namespace);

CREATE TABLE IF NOT EXISTS institution_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    member_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    membership_kind TEXT NOT NULL DEFAULT 'member',
    role_text TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','former','unknown')),
    joined_day INTEGER,
    left_day INTEGER,
    provenance_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(institution_actor_id,member_actor_id,membership_kind)
);
CREATE INDEX IF NOT EXISTS idx_institution_membership_member
ON institution_memberships(member_actor_id,status,institution_actor_id);
CREATE INDEX IF NOT EXISTS idx_institution_membership_institution
ON institution_memberships(institution_actor_id,status,member_actor_id);

CREATE TABLE IF NOT EXISTS coverage_registry (
    domain_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    bible_scope TEXT,
    owner_module TEXT,
    mechanism_status TEXT NOT NULL CHECK (mechanism_status IN (
        'RUNNABLE','PARTIAL','API_ONLY','MAJOR_GAP','SEMANTIC_ONLY'
    )),
    population_sql TEXT,
    eligibility_sql TEXT,
    required_for_ten_year INTEGER NOT NULL DEFAULT 1 CHECK (required_for_ten_year IN (0,1)),
    autonomous_initiation_required INTEGER NOT NULL DEFAULT 0 CHECK (autonomous_initiation_required IN (0,1)),
    population_policy TEXT NOT NULL DEFAULT 'opening_required',
    process_keys_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS coverage_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    start_day INTEGER NOT NULL,
    end_day INTEGER,
    source_seed_namespace TEXT,
    engine_version TEXT,
    schema_version INTEGER,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS coverage_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coverage_run_id INTEGER REFERENCES coverage_runs(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    domain_key TEXT NOT NULL REFERENCES coverage_registry(domain_key) ON DELETE CASCADE,
    phase TEXT NOT NULL DEFAULT 'snapshot',
    populated_count INTEGER,
    eligible_count INTEGER,
    due_count INTEGER,
    executed_count INTEGER NOT NULL DEFAULT 0,
    changed_count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0,
    blocked_reason TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_coverage_observation_run
ON coverage_observations(coverage_run_id,day,domain_key,id);

CREATE TABLE IF NOT EXISTS process_execution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coverage_run_id INTEGER REFERENCES coverage_runs(id) ON DELETE SET NULL,
    day INTEGER NOT NULL,
    process_key TEXT NOT NULL,
    due_count INTEGER,
    eligible_count INTEGER,
    executed_count INTEGER NOT NULL DEFAULT 0,
    changed_count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0,
    blocked_reason TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_process_execution_day
ON process_execution_log(day,process_key,id);

CREATE TABLE IF NOT EXISTS resolution_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN ('actor','institution','latent_person','latent_institution')),
    entity_id INTEGER NOT NULL,
    prior_level TEXT,
    proposed_level TEXT,
    applied_level TEXT,
    significance_score REAL NOT NULL DEFAULT 0,
    trigger_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT,
    action TEXT NOT NULL CHECK (action IN (
        'none','promote','demote','crystallize_person','crystallize_institution','defer'
    )),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_resolution_reviews_entity
ON resolution_reviews(entity_kind,entity_id,day,id);

CREATE TABLE IF NOT EXISTS autonomous_action_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    action_kind TEXT NOT NULL,
    domain_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('eligible','applied','refused','blocked','failed')),
    reason TEXT,
    input_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_autonomous_action_day
ON autonomous_action_attempts(day,domain_key,action_kind,status,id);

CREATE TABLE IF NOT EXISTS typed_relationship_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT,
    actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','former','historical','unknown')),
    provenance_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_key),
    CHECK(actor_a_id <> actor_b_id)
);
CREATE INDEX IF NOT EXISTS idx_typed_relationship_a ON typed_relationship_facts(actor_a_id,relation_type,status,id);
CREATE INDEX IF NOT EXISTS idx_typed_relationship_b ON typed_relationship_facts(actor_b_id,relation_type,status,id);

CREATE TABLE IF NOT EXISTS world_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,
    claim_type TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    confidence_label TEXT,
    canon_status TEXT,
    provenance_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','historical','discredited')),
    created_day INTEGER NOT NULL DEFAULT 0,
    updated_day INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS world_claim_subjects (
    claim_id INTEGER NOT NULL REFERENCES world_claims(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    PRIMARY KEY(claim_id,actor_id)
);
CREATE TABLE IF NOT EXISTS world_claim_locations (
    claim_id INTEGER NOT NULL REFERENCES world_claims(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    knowledge_state TEXT NOT NULL DEFAULT 'known_at_opening' CHECK (knowledge_state IN ('origin','known_at_opening')),
    PRIMARY KEY(claim_id,location_id,knowledge_state)
);

CREATE TABLE IF NOT EXISTS latent_population_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT UNIQUE,
    scope_kind TEXT NOT NULL CHECK (scope_kind IN ('institution','location','cohort','world')),
    scope_id INTEGER,
    archetype TEXT NOT NULL,
    population_estimate INTEGER CHECK (population_estimate IS NULL OR population_estimate >= 0),
    minimum_named_layer INTEGER,
    opening_named_count INTEGER,
    crystallization_rule TEXT NOT NULL,
    constraints_json TEXT NOT NULL DEFAULT '{}',
    historical_context_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','exhausted','retired')),
    created_day INTEGER NOT NULL DEFAULT 0,
    updated_day INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_latent_population_scope ON latent_population_scopes(scope_kind,scope_id,status,id);

CREATE TABLE IF NOT EXISTS emergent_institution_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_kind TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    founder_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    proposed_name TEXT,
    significance_score REAL NOT NULL DEFAULT 0,
    resources_json TEXT NOT NULL DEFAULT '{}',
    participants_json TEXT NOT NULL DEFAULT '[]',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'forming' CHECK (status IN ('forming','eligible','crystallized','abandoned','merged')),
    crystallized_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    created_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emergent_institution_status ON emergent_institution_candidates(status,candidate_kind,significance_score,id);

CREATE TABLE IF NOT EXISTS canon_process_anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,
    process_type TEXT NOT NULL,
    entity_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    facts_json TEXT NOT NULL DEFAULT '[]',
    cadence TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_canon_process_entity ON canon_process_anchors(entity_actor_id,process_type,status,id);


-- v0.32: causal cultivation and Realization
CREATE TABLE IF NOT EXISTS cultivation_profiles (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    core_state TEXT NOT NULL DEFAULT 'Unknown' CHECK (core_state IN ('Open-Core','Closed-Core','Damaged-Core','Destroyed-Core','Unknown')),
    current_stage TEXT CHECK (current_stage IN ('First','Temper','Third','Breach','Fifth','Sixth') OR current_stage IS NULL),
    active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0,1)),
    vessel_adaptation REAL NOT NULL DEFAULT 0 CHECK (vessel_adaptation BETWEEN 0 AND 100),
    realization_integration REAL NOT NULL DEFAULT 0 CHECK (realization_integration BETWEEN 0 AND 100),
    training_effort REAL NOT NULL DEFAULT 50 CHECK (training_effort BETWEEN 0 AND 100),
    resource_access REAL NOT NULL DEFAULT 50 CHECK (resource_access BETWEEN 0 AND 100),
    teacher_support REAL NOT NULL DEFAULT 0 CHECK (teacher_support BETWEEN 0 AND 100),
    injury_constraint REAL NOT NULL DEFAULT 0 CHECK (injury_constraint BETWEEN 0 AND 100),
    realization_aptitude REAL NOT NULL DEFAULT 1.0 CHECK (realization_aptitude BETWEEN 0.35 AND 1.75),
    vessel_aptitude REAL NOT NULL DEFAULT 1.0 CHECK (vessel_aptitude BETWEEN 0.35 AND 2.50),
    next_realization_check_day INTEGER NOT NULL DEFAULT 365 CHECK (next_realization_check_day>=0),
    observed_stage_days INTEGER NOT NULL DEFAULT 0 CHECK (observed_stage_days>=0),
    plateau_days INTEGER NOT NULL DEFAULT 0 CHECK (plateau_days>=0),
    last_realization_day INTEGER,
    last_breakthrough_attempt_day INTEGER,
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','retired','incapacitated','ended')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_cultivation_due ON cultivation_profiles(active,status,next_review_day,actor_id);
CREATE TABLE IF NOT EXISTS cultivation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    history_kind TEXT NOT NULL CHECK (history_kind IN ('opening_observation','practice_review','plateau','realization_opportunity','breakthrough_attempt','breakthrough_success','breakthrough_failure','rupture','retirement','resume')),
    stage_before TEXT,
    stage_after TEXT,
    summary TEXT NOT NULL,
    vessel_snapshot REAL,
    realization_snapshot REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_cultivation_history_actor ON cultivation_history(actor_id,day,id);
CREATE TABLE IF NOT EXISTS realization_anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    anchor_kind TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_id INTEGER,
    weight REAL NOT NULL DEFAULT 1 CHECK (weight>0),
    description TEXT,
    consumed_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_realization_actor ON realization_anchors(actor_id,consumed_day,day,id);


-- v0.33 elixir physiology: batch truth is separate from claims; fuel is separate from maturation/Realization.
CREATE TABLE IF NOT EXISTS elixir_supply_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    product_grade TEXT NOT NULL CHECK (product_grade IN ('refined','high_grade')),
    default_refinement_quality REAL NOT NULL CHECK (default_refinement_quality BETWEEN 0 AND 100),
    default_sediment_risk REAL NOT NULL CHECK (default_sediment_risk BETWEEN 0 AND 100),
    provenance_standard REAL NOT NULL DEFAULT 50 CHECK (provenance_standard BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','inactive')),
    source_basis TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(enterprise_id,product_grade)
);
CREATE TABLE IF NOT EXISTS elixir_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT, batch_key TEXT NOT NULL UNIQUE,
    product_grade TEXT NOT NULL CHECK (product_grade IN ('raw_root','refined','high_grade')),
    source_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    refiner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    producer_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    usable_current_per_unit REAL NOT NULL CHECK (usable_current_per_unit>0),
    refinement_quality REAL NOT NULL CHECK (refinement_quality BETWEEN 0 AND 100),
    sediment_risk REAL NOT NULL CHECK (sediment_risk BETWEEN 0 AND 100),
    remaining_units REAL NOT NULL CHECK (remaining_units>=0), created_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','depleted','seized','destroyed')),
    actual_provenance_json TEXT NOT NULL DEFAULT '{}', metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_elixir_batches_status ON elixir_batches(status,product_grade,id);
CREATE TABLE IF NOT EXISTS elixir_batch_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER NOT NULL REFERENCES elixir_batches(id) ON DELETE CASCADE,
    day INTEGER NOT NULL, claimant_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    claim_kind TEXT NOT NULL, claim_text TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 50 CHECK (confidence BETWEEN 0 AND 100),
    truth_status TEXT NOT NULL DEFAULT 'unknown' CHECK (truth_status IN ('unknown','supported','false','disputed')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_elixir_claims_batch ON elixir_batch_claims(batch_id,day,id);
CREATE TABLE IF NOT EXISTS elixir_exposures (
    id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER NOT NULL REFERENCES elixir_batches(id) ON DELETE RESTRICT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, day INTEGER NOT NULL,
    units_consumed REAL NOT NULL CHECK (units_consumed>0), assimilated_current REAL NOT NULL DEFAULT 0 CHECK (assimilated_current>=0),
    reserve_gain REAL NOT NULL DEFAULT 0 CHECK (reserve_gain>=0), vessel_gain REAL NOT NULL DEFAULT 0 CHECK (vessel_gain>=0),
    sediment_gain REAL NOT NULL DEFAULT 0 CHECK (sediment_gain>=0), rupture_condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_elixir_exposure_actor ON elixir_exposures(actor_id,day,id);

-- v0.35: consensual autonomous challenges and recurring tournament lifecycle
CREATE TABLE IF NOT EXISTS martial_challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposer_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    recipient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    interaction_id INTEGER REFERENCES interactions(id) ON DELETE SET NULL,
    duel_engagement_id INTEGER REFERENCES combat_engagements(id) ON DELETE SET NULL,
    terms_kind TEXT NOT NULL DEFAULT 'controlled' CHECK (terms_kind IN ('controlled','first_blood','submission','weapon_limited','lethal')),
    lethal INTEGER NOT NULL DEFAULT 0 CHECK (lethal IN (0,1)),
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','accepted','declined','active','resolved','cancelled')),
    created_day INTEGER NOT NULL,
    next_review_day INTEGER NOT NULL,
    resolved_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK (proposer_actor_id<>recipient_actor_id)
);
CREATE INDEX IF NOT EXISTS idx_martial_challenge_status ON martial_challenges(status,created_day,id);
CREATE TABLE IF NOT EXISTS tournament_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT, series_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL, recurrence_days INTEGER NOT NULL DEFAULT 365 CHECK (recurrence_days>0),
    next_registration_day INTEGER NOT NULL, registration_lead_days INTEGER NOT NULL DEFAULT 60 CHECK (registration_lead_days>=0),
    event_duration_days INTEGER NOT NULL DEFAULT 21 CHECK (event_duration_days>0), cycle_index INTEGER NOT NULL DEFAULT 0 CHECK (cycle_index>=0),
    convergence_every INTEGER NOT NULL DEFAULT 5 CHECK (convergence_every>=2), status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','ended')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tournament_series_due ON tournament_series(status,next_registration_day,id);
CREATE TABLE IF NOT EXISTS tournament_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, series_id INTEGER NOT NULL REFERENCES tournament_series(id) ON DELETE CASCADE,
    event_kind TEXT NOT NULL CHECK (event_kind IN ('annual','convergence','circuit','other')), name TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL, registration_day INTEGER NOT NULL, start_day INTEGER NOT NULL, end_day INTEGER NOT NULL,
    next_review_day INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'registration' CHECK (status IN ('registration','active','resolved','cancelled')),
    metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(series_id,start_day)
);
CREATE INDEX IF NOT EXISTS idx_tournament_events_due ON tournament_events(status,next_review_day,id);
CREATE TABLE IF NOT EXISTS tournament_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL REFERENCES tournament_events(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL CHECK (field_key IN ('open','rising','companies','grand_open','rising_court','company_contest','masters_invitation')),
    simulation_mode TEXT NOT NULL DEFAULT 'individual' CHECK (simulation_mode IN ('individual','structural')), capacity INTEGER NOT NULL DEFAULT 8 CHECK (capacity>=0),
    status TEXT NOT NULL DEFAULT 'registration' CHECK (status IN ('registration','active','resolved','structural','cancelled')),
    round_index INTEGER NOT NULL DEFAULT 0 CHECK (round_index>=0), champion_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(event_id,field_key)
);
CREATE TABLE IF NOT EXISTS tournament_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL REFERENCES tournament_events(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES tournament_fields(id) ON DELETE CASCADE, actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    origin_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL, seed_score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'registered' CHECK (status IN ('registered','arrived','active','eliminated','champion','withdrawn')),
    registered_day INTEGER NOT NULL, eliminated_day INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(event_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_tournament_entries_field ON tournament_entries(field_id,status,seed_score DESC,id);
CREATE TABLE IF NOT EXISTS tournament_bouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL REFERENCES tournament_events(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES tournament_fields(id) ON DELETE CASCADE, round_index INTEGER NOT NULL,
    actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    duel_engagement_id INTEGER REFERENCES combat_engagements(id) ON DELETE SET NULL, winner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','active','resolved','cancelled')),
    scheduled_day INTEGER NOT NULL, resolved_day INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}', CHECK(actor_a_id<>actor_b_id)
);
CREATE INDEX IF NOT EXISTS idx_tournament_bouts_status ON tournament_bouts(event_id,field_id,status,round_index,id);

-- v0.36: spectacle economy — aggregate betting books, structural Closed-Core prizefighting, and latent-career promotion
CREATE TABLE IF NOT EXISTS spectacle_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    book_kind TEXT NOT NULL CHECK (book_kind IN ('network_branch','independent_market')),
    legal_profile TEXT NOT NULL DEFAULT 'tolerated' CHECK (legal_profile IN ('licensed','tolerated','mixed')),
    reliability REAL NOT NULL DEFAULT 70 CHECK (reliability BETWEEN 0 AND 100),
    information_quality REAL NOT NULL DEFAULT 55 CHECK (information_quality BETWEEN 0 AND 100),
    margin_rate REAL NOT NULL DEFAULT 0.08 CHECK (margin_rate BETWEEN 0 AND 0.4),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','closed')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_spectacle_books_location ON spectacle_books(location_id,status,id);

CREATE TABLE IF NOT EXISTS prizefight_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    market_kind TEXT NOT NULL DEFAULT 'prize_hall' CHECK (market_kind IN ('prize_hall','back_room','pit','private_club')),
    legality TEXT NOT NULL DEFAULT 'licensed' CHECK (legality IN ('licensed','tolerated','unlicensed','criminal')),
    coercion_profile TEXT NOT NULL DEFAULT 'voluntary' CHECK (coercion_profile IN ('voluntary','mixed','coercive')),
    cadence_days INTEGER NOT NULL DEFAULT 30 CHECK (cadence_days>=7),
    next_card_day INTEGER NOT NULL,
    latent_pool_id INTEGER REFERENCES latent_entities(id) ON DELETE SET NULL,
    pool_size INTEGER NOT NULL DEFAULT 20 CHECK (pool_size>=4),
    public_form REAL NOT NULL DEFAULT 50 CHECK (public_form BETWEEN 0 AND 100),
    injury_load REAL NOT NULL DEFAULT 5 CHECK (injury_load BETWEEN 0 AND 100),
    champion_streak INTEGER NOT NULL DEFAULT 0 CHECK (champion_streak>=0),
    champion_profile_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','closed')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_prizefight_markets_due ON prizefight_markets(status,next_card_day,id);

CREATE TABLE IF NOT EXISTS prizefight_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id INTEGER NOT NULL REFERENCES prizefight_markets(id) ON DELETE CASCADE,
    scheduled_day INTEGER NOT NULL,
    resolved_day INTEGER,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','resolved','cancelled')),
    bout_count INTEGER NOT NULL DEFAULT 0 CHECK (bout_count>=0),
    attendance_index REAL NOT NULL DEFAULT 50 CHECK (attendance_index BETWEEN 0 AND 100),
    gross_purse REAL NOT NULL DEFAULT 0 CHECK (gross_purse>=0),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(market_id,scheduled_day)
);
CREATE INDEX IF NOT EXISTS idx_prizefight_cards_status ON prizefight_cards(status,scheduled_day,id);

CREATE TABLE IF NOT EXISTS prizefight_bouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES prizefight_cards(id) ON DELETE CASCADE,
    bout_index INTEGER NOT NULL,
    public_form_a REAL NOT NULL CHECK (public_form_a BETWEEN 0 AND 100),
    public_form_b REAL NOT NULL CHECK (public_form_b BETWEEN 0 AND 100),
    true_form_a REAL NOT NULL CHECK (true_form_a BETWEEN 0 AND 100),
    true_form_b REAL NOT NULL CHECK (true_form_b BETWEEN 0 AND 100),
    winner_side TEXT NOT NULL CHECK (winner_side IN ('A','B')),
    injury_a REAL NOT NULL DEFAULT 0 CHECK (injury_a BETWEEN 0 AND 100),
    injury_b REAL NOT NULL DEFAULT 0 CHECK (injury_b BETWEEN 0 AND 100),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(card_id,bout_index)
);

CREATE TABLE IF NOT EXISTS betting_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_key TEXT NOT NULL UNIQUE,
    book_id INTEGER NOT NULL REFERENCES spectacle_books(id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('tournament_bout','prizefight_card')),
    source_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    opened_day INTEGER NOT NULL,
    close_day INTEGER NOT NULL,
    settled_day INTEGER,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','settled','cancelled')),
    outcome_a_key TEXT NOT NULL,
    outcome_b_key TEXT NOT NULL,
    public_probability_a REAL NOT NULL CHECK (public_probability_a BETWEEN 0.02 AND 0.98),
    decimal_odds_a REAL NOT NULL CHECK (decimal_odds_a>=1.01),
    decimal_odds_b REAL NOT NULL CHECK (decimal_odds_b>=1.01),
    handle REAL NOT NULL DEFAULT 0 CHECK (handle>=0),
    stake_share_a REAL NOT NULL DEFAULT 0.5 CHECK (stake_share_a BETWEEN 0 AND 1),
    payout REAL NOT NULL DEFAULT 0 CHECK (payout>=0),
    book_result REAL NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_betting_markets_status ON betting_markets(status,source_kind,source_id,id);


-- v0.37: evidence-driven underworld ecology, conserved smuggling and local policing.
CREATE TABLE IF NOT EXISTS underworld_institution_profiles (
    institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    primary_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    operating_model TEXT NOT NULL,
    legal_fronts_json TEXT NOT NULL DEFAULT '[]',
    criminal_activities_json TEXT NOT NULL DEFAULT '[]',
    continuity_depth REAL NOT NULL DEFAULT 50 CHECK (continuity_depth BETWEEN 0 AND 100),
    hidden_exposure REAL NOT NULL DEFAULT 0 CHECK (hidden_exposure BETWEEN 0 AND 100),
    corrupt_access REAL NOT NULL DEFAULT 0 CHECK (corrupt_access BETWEEN 0 AND 100),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','dormant','ended')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_underworld_profiles_due ON underworld_institution_profiles(status,next_review_day,institution_actor_id);


-- v0.59/49: criminal organizational form is separate from scale or power.
-- A gang does not level into a Mafia family; each form can grow, shrink, federate, fragment, or remain small.
CREATE TABLE IF NOT EXISTS underworld_organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_key TEXT NOT NULL UNIQUE,
    organization_type TEXT NOT NULL CHECK (organization_type IN ('gang','mafia_family','criminal_dynasty','syndicate','criminal_enterprise','network','crew','other')),
    name TEXT,
    founder_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    anchor_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    primary_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    member_count_estimate REAL NOT NULL DEFAULT 1 CHECK (member_count_estimate>=0),
    command_depth INTEGER NOT NULL DEFAULT 1 CHECK (command_depth>=0),
    territorial_presence REAL NOT NULL DEFAULT 0 CHECK (territorial_presence BETWEEN 0 AND 100),
    racket_breadth REAL NOT NULL DEFAULT 0 CHECK (racket_breadth BETWEEN 0 AND 100),
    front_depth REAL NOT NULL DEFAULT 0 CHECK (front_depth BETWEEN 0 AND 100),
    corrupt_access REAL NOT NULL DEFAULT 0 CHECK (corrupt_access BETWEEN 0 AND 100),
    reputation_deterrence REAL NOT NULL DEFAULT 0 CHECK (reputation_deterrence BETWEEN 0 AND 100),
    violence_capacity REAL NOT NULL DEFAULT 0 CHECK (violence_capacity BETWEEN 0 AND 100),
    cohesion REAL NOT NULL DEFAULT 50 CHECK (cohesion BETWEEN 0 AND 100),
    membership_stability REAL NOT NULL DEFAULT 50 CHECK (membership_stability BETWEEN 0 AND 100),
    succession_depth REAL NOT NULL DEFAULT 0 CHECK (succession_depth BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','fragmented','dormant','destroyed','merged')),
    created_day INTEGER NOT NULL DEFAULT 0,
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK (NOT (organization_type='mafia_family' AND metadata_json LIKE '%auto_promoted_from_gang%'))
);
CREATE INDEX IF NOT EXISTS idx_underworld_org_actor ON underworld_organizations(founder_actor_id,status,id);
CREATE INDEX IF NOT EXISTS idx_underworld_org_enterprise ON underworld_organizations(anchor_enterprise_id,status,id);
CREATE INDEX IF NOT EXISTS idx_underworld_org_type ON underworld_organizations(organization_type,status,id);

-- v0.59 membership-flow layer: current headcount is a stock, not a growth counter.
-- Core members, ordinary active members, and peripheral associates turn over at different rates.
CREATE TABLE IF NOT EXISTS underworld_membership_profiles (
    organization_id INTEGER PRIMARY KEY REFERENCES underworld_organizations(id) ON DELETE CASCADE,
    core_members REAL NOT NULL DEFAULT 1 CHECK (core_members>=0),
    active_members REAL NOT NULL DEFAULT 0 CHECK (active_members>=0),
    peripheral_associates REAL NOT NULL DEFAULT 0 CHECK (peripheral_associates>=0),
    lifetime_entries REAL NOT NULL DEFAULT 0 CHECK (lifetime_entries>=0),
    lifetime_exits REAL NOT NULL DEFAULT 0 CHECK (lifetime_exits>=0),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS underworld_membership_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    flow_kind TEXT NOT NULL CHECK (flow_kind IN ('recruitment','desistance','defection','custody','death_or_incapacitation','relocation','associate_to_active','active_to_core','return_to_periphery')),
    count REAL NOT NULL CHECK (count>0),
    from_tier TEXT CHECK (from_tier IN ('core','active','peripheral')),
    to_tier TEXT CHECK (to_tier IN ('core','active','peripheral')),
    source_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_underworld_membership_flows_org ON underworld_membership_flows(organization_id,day,id);

CREATE TABLE IF NOT EXISTS underworld_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT, location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('enterprise','institution','smuggling_operation','actor','shadow_link')), subject_id INTEGER NOT NULL,
    evidence_kind TEXT NOT NULL, visibility TEXT NOT NULL DEFAULT 'hidden' CHECK (visibility IN ('hidden','local','public')),
    strength REAL NOT NULL DEFAULT 0 CHECK (strength BETWEEN 0 AND 100), source_kind TEXT NOT NULL, source_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','discredited','resolved')), created_day INTEGER NOT NULL, updated_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(source_kind,source_id,evidence_kind)
);
CREATE INDEX IF NOT EXISTS idx_underworld_evidence_subject ON underworld_evidence(subject_kind,subject_id,status,visibility,id);
CREATE INDEX IF NOT EXISTS idx_underworld_evidence_location ON underworld_evidence(location_id,status,visibility,id);

CREATE TABLE IF NOT EXISTS smuggling_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, operation_key TEXT UNIQUE, organizer_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE, destination_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE, quantity REAL NOT NULL CHECK (quantity>0),
    origin_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE, destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    current_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE, current_route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
    segment_due_day INTEGER, next_review_day INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'in_transit' CHECK (status IN ('in_transit','stalled','delivered','seized','cancelled')),
    violation_kind TEXT NOT NULL, concealment REAL NOT NULL DEFAULT 60 CHECK (concealment BETWEEN 0 AND 100), evidence_score REAL NOT NULL DEFAULT 0 CHECK (evidence_score BETWEEN 0 AND 100),
    detected_day INTEGER, detected_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL, started_day INTEGER NOT NULL, arrived_day INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_smuggling_due ON smuggling_operations(status,next_review_day,id);
CREATE INDEX IF NOT EXISTS idx_smuggling_organizer ON smuggling_operations(organizer_institution_actor_id,status,id);

CREATE TABLE IF NOT EXISTS law_enforcement_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, profile_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, authority_kind TEXT NOT NULL, capacity REAL NOT NULL DEFAULT 50 CHECK (capacity BETWEEN 0 AND 100),
    integrity REAL NOT NULL DEFAULT 60 CHECK (integrity BETWEEN 0 AND 100), corruption_pressure REAL NOT NULL DEFAULT 20 CHECK (corruption_pressure BETWEEN 0 AND 100),
    inspection_focus REAL NOT NULL DEFAULT 50 CHECK (inspection_focus BETWEEN 0 AND 100), last_review_day INTEGER NOT NULL DEFAULT 0, next_review_day INTEGER NOT NULL DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','inactive')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_law_profiles_due ON law_enforcement_profiles(status,next_review_day,location_id,id);

CREATE TABLE IF NOT EXISTS law_enforcement_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL REFERENCES law_enforcement_profiles(id) ON DELETE CASCADE,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('smuggling_operation','enterprise','institution','actor')), subject_id INTEGER NOT NULL, allegation_kind TEXT NOT NULL,
    evidence_score REAL NOT NULL DEFAULT 0 CHECK (evidence_score BETWEEN 0 AND 100), status TEXT NOT NULL DEFAULT 'monitoring' CHECK (status IN ('monitoring','open','actionable','referred','closed')),
    opened_day INTEGER NOT NULL, last_review_day INTEGER NOT NULL, next_review_day INTEGER NOT NULL, closed_day INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(profile_id,subject_kind,subject_id,allegation_kind)
);
CREATE INDEX IF NOT EXISTS idx_law_cases_due ON law_enforcement_cases(status,next_review_day,profile_id,id);

CREATE TABLE IF NOT EXISTS law_enforcement_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER NOT NULL REFERENCES law_enforcement_cases(id) ON DELETE CASCADE, day INTEGER NOT NULL,
    action_kind TEXT NOT NULL CHECK (action_kind IN ('inquiry','inspection','referral')), evidence_score REAL NOT NULL CHECK (evidence_score BETWEEN 0 AND 100),
    metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(case_id,action_kind)
);
CREATE INDEX IF NOT EXISTS idx_law_actions_case ON law_enforcement_actions(case_id,day,id);


-- v0.38 Hollow practice and Grand Coven succession.
CREATE TABLE IF NOT EXISTS hollow_practice_profiles (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    hollow_status TEXT NOT NULL CHECK (hollow_status IN ('formal_coven','independent','associated')),
    coven_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    accepts_extraction INTEGER NOT NULL DEFAULT 0 CHECK (accepts_extraction IN (0,1)),
    practiced_extraction INTEGER CHECK (practiced_extraction IN (0,1) OR practiced_extraction IS NULL),
    mantle_eligibility TEXT NOT NULL DEFAULT 'unknown' CHECK (mantle_eligibility IN ('eligible','ineligible','unknown')),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','former','deceased')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_hollow_profiles_coven ON hollow_practice_profiles(coven_institution_actor_id,status,actor_id);
CREATE TABLE IF NOT EXISTS hollow_extraction_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER NOT NULL,
    practitioner_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    source_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    context_kind TEXT NOT NULL DEFAULT 'practice' CHECK (context_kind IN ('practice','combat','rite','other')),
    requested_current REAL NOT NULL CHECK (requested_current>0), transferred_current REAL NOT NULL DEFAULT 0 CHECK (transferred_current>=0),
    source_reserve_before REAL NOT NULL DEFAULT 0 CHECK (source_reserve_before>=0), source_reserve_after REAL NOT NULL DEFAULT 0 CHECK (source_reserve_after>=0),
    recipient_reserve_before REAL NOT NULL DEFAULT 0 CHECK (recipient_reserve_before>=0), recipient_reserve_after REAL NOT NULL DEFAULT 0 CHECK (recipient_reserve_after>=0),
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed','partial','failed')), metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(practitioner_actor_id <> source_actor_id)
);
CREATE INDEX IF NOT EXISTS idx_hollow_extraction_actor ON hollow_extraction_events(practitioner_actor_id,day,id);
CREATE TABLE IF NOT EXISTS grand_coven_succession_state (
    institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    inheritor_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, foremost_heir_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    succession_status TEXT NOT NULL DEFAULT 'open' CHECK (succession_status IN ('open','contested','sealed','vacant')),
    mantle_sealed INTEGER NOT NULL DEFAULT 0 CHECK (mantle_sealed IN (0,1)), sealed_day INTEGER,
    transfer_available INTEGER NOT NULL DEFAULT 1 CHECK (transfer_available IN (0,1)),
    last_review_day INTEGER NOT NULL DEFAULT 0, next_review_day INTEGER NOT NULL DEFAULT 90, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_grand_coven_succession_due ON grand_coven_succession_state(next_review_day,succession_status,institution_actor_id);
CREATE TABLE IF NOT EXISTS grand_coven_heirs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    claim_kind TEXT NOT NULL CHECK (claim_kind IN ('recognized_heir','rival_heir','carrion_riser','other_exalted')),
    formal_status TEXT NOT NULL DEFAULT 'potential' CHECK (formal_status IN ('potential','recognized','pressed','withdrawn','settled','ineligible','deceased')),
    teaching_access REAL NOT NULL DEFAULT 0 CHECK (teaching_access BETWEEN 0 AND 100), authority_support REAL NOT NULL DEFAULT 0 CHECK (authority_support BETWEEN 0 AND 100),
    martial_credibility REAL NOT NULL DEFAULT 0 CHECK (martial_credibility BETWEEN 0 AND 100), political_support REAL NOT NULL DEFAULT 0 CHECK (political_support BETWEEN 0 AND 100),
    current_choice INTEGER NOT NULL DEFAULT 0 CHECK (current_choice IN (0,1)), created_day INTEGER NOT NULL DEFAULT 0, updated_day INTEGER NOT NULL DEFAULT 0,
    mantle_eligible INTEGER NOT NULL DEFAULT 1 CHECK (mantle_eligible IN (0,1)),
    metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(institution_actor_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_grand_coven_heirs ON grand_coven_heirs(institution_actor_id,formal_status,current_choice,id);
CREATE TABLE IF NOT EXISTS grand_coven_power_brokers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    role_kind TEXT NOT NULL CHECK (role_kind IN ('deep_court_elder','senior_power','hall_lord','order_command','keeper','family_line','other')),
    institutional_weight REAL NOT NULL DEFAULT 0 CHECK (institutional_weight BETWEEN 0 AND 100),
    stance TEXT NOT NULL DEFAULT 'uncommitted' CHECK (stance IN ('supports','opposes','uncommitted','fractured')),
    supported_heir_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    created_day INTEGER NOT NULL DEFAULT 0, updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(institution_actor_id,actor_id,role_kind)
);
CREATE INDEX IF NOT EXISTS idx_grand_coven_power_brokers ON grand_coven_power_brokers(institution_actor_id,role_kind,stance,id);
CREATE TABLE IF NOT EXISTS grand_coven_mantle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, day INTEGER NOT NULL,
    event_kind TEXT NOT NULL CHECK (event_kind IN ('recognition','claim_pressed','choice_changed','sealed','passing','accession','ascension','sudden_death_transition')),
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, other_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    current_transferred REAL NOT NULL DEFAULT 0 CHECK (current_transferred>=0), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_grand_coven_mantle_events ON grand_coven_mantle_events(institution_actor_id,day,id);


-- v0.39 addiction and psychological consequences. Internal state tracks causal impairment;
-- culture-specific interpretation remains narrative/semantic rather than a universal diagnosis vocabulary.
CREATE TABLE IF NOT EXISTS dependency_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    dependency_kind TEXT NOT NULL CHECK (dependency_kind IN ('chemical_medication','intoxicant','stimulant','gambling','elixir_performance','other')),
    status TEXT NOT NULL DEFAULT 'risk' CHECK (status IN ('risk','dependent','recovering','resolved')),
    exposure_count INTEGER NOT NULL DEFAULT 0 CHECK (exposure_count>=0),
    reinforcement_load REAL NOT NULL DEFAULT 0 CHECK (reinforcement_load>=0),
    urge_load REAL NOT NULL DEFAULT 0 CHECK (urge_load BETWEEN 0 AND 100),
    tolerance_load REAL NOT NULL DEFAULT 0 CHECK (tolerance_load BETWEEN 0 AND 100),
    functional_impairment REAL NOT NULL DEFAULT 0 CHECK (functional_impairment BETWEEN 0 AND 100),
    consequence_load REAL NOT NULL DEFAULT 0 CHECK (consequence_load BETWEEN 0 AND 100),
    last_exposure_day INTEGER,
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(actor_id,dependency_kind)
);
CREATE INDEX IF NOT EXISTS idx_dependency_profiles_due ON dependency_profiles(status,next_review_day,actor_id);

CREATE TABLE IF NOT EXISTS dependency_exposures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    dependency_kind TEXT NOT NULL CHECK (dependency_kind IN ('chemical_medication','intoxicant','stimulant','gambling','elixir_performance','other')),
    day INTEGER NOT NULL,
    source_kind TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount>0),
    reinforcing_value REAL NOT NULL DEFAULT 50 CHECK (reinforcing_value BETWEEN 0 AND 100),
    adverse_consequence REAL NOT NULL DEFAULT 0 CHECK (adverse_consequence BETWEEN 0 AND 100),
    source_ref_kind TEXT,
    source_ref_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(actor_id,source_ref_kind,source_ref_id,dependency_kind)
);
CREATE INDEX IF NOT EXISTS idx_dependency_exposures_actor ON dependency_exposures(actor_id,dependency_kind,day,id);

CREATE TABLE IF NOT EXISTS psychological_stressors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    stress_family TEXT NOT NULL CHECK (stress_family IN ('trauma','grief','anxiety','depression','nightmares','obsession','severe_mental_illness','other')),
    day INTEGER NOT NULL,
    burden REAL NOT NULL CHECK (burden BETWEEN 0 AND 100),
    source_kind TEXT NOT NULL,
    source_ref_kind TEXT,
    source_ref_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(actor_id,stress_family,source_ref_kind,source_ref_id)
);
CREATE INDEX IF NOT EXISTS idx_psychological_stressors_actor ON psychological_stressors(actor_id,stress_family,day,id);

CREATE TABLE IF NOT EXISTS psychological_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    condition_family TEXT NOT NULL CHECK (condition_family IN ('trauma','grief','anxiety','depression','nightmares','obsession','severe_mental_illness','other')),
    severity REAL NOT NULL CHECK (severity BETWEEN 0 AND 100),
    functional_impairment REAL NOT NULL DEFAULT 0 CHECK (functional_impairment BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','recovering','chronic','resolved')),
    onset_day INTEGER NOT NULL,
    last_review_day INTEGER NOT NULL,
    next_review_day INTEGER NOT NULL,
    resolved_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_psychological_conditions_due ON psychological_conditions(status,next_review_day,actor_id);

CREATE TABLE IF NOT EXISTS psychological_support (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    condition_id INTEGER REFERENCES psychological_conditions(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    support_kind TEXT NOT NULL,
    helpfulness REAL NOT NULL DEFAULT 50 CHECK (helpfulness BETWEEN -100 AND 100),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_psychological_support_actor ON psychological_support(actor_id,day,id);


-- v0.40 underworld medical access and exploitation integrity.
CREATE TABLE IF NOT EXISTS underworld_medical_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT, patient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL, provider_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    provider_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL, sponsor_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL, purpose_kind TEXT NOT NULL,
    consent_status TEXT NOT NULL DEFAULT 'voluntary' CHECK (consent_status IN ('voluntary','coerced','unknown')),
    confidentiality REAL NOT NULL DEFAULT 80 CHECK (confidentiality BETWEEN 0 AND 100), coercion REAL NOT NULL DEFAULT 0 CHECK (coercion BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended')), started_day INTEGER NOT NULL, last_review_day INTEGER NOT NULL, next_review_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}', CHECK (provider_actor_id IS NOT NULL OR provider_enterprise_id IS NOT NULL));
CREATE INDEX IF NOT EXISTS idx_underworld_medical_access_due ON underworld_medical_access(status,next_review_day,patient_actor_id);
CREATE TABLE IF NOT EXISTS medical_misconduct_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, access_id INTEGER NOT NULL REFERENCES underworld_medical_access(id) ON DELETE CASCADE, treatment_id INTEGER REFERENCES medical_treatments(id) ON DELETE SET NULL,
    condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL, day INTEGER NOT NULL, misconduct_kind TEXT NOT NULL,
    harm REAL NOT NULL DEFAULT 0 CHECK (harm BETWEEN 0 AND 100), financial_extraction REAL NOT NULL DEFAULT 0 CHECK (financial_extraction>=0),
    evidence_visibility TEXT NOT NULL DEFAULT 'hidden' CHECK (evidence_visibility IN ('hidden','local','public')), evidence_strength REAL NOT NULL DEFAULT 0 CHECK (evidence_strength BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','resolved')), metadata_json TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_medical_misconduct_access ON medical_misconduct_events(access_id,day,id);


-- v0.41: war logistics and aftermath
CREATE TABLE IF NOT EXISTS military_logistics_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, polity_id INTEGER NOT NULL UNIQUE REFERENCES political_polities(id) ON DELETE CASCADE,
    source_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL, food_fodder_capacity REAL NOT NULL DEFAULT 50 CHECK (food_fodder_capacity BETWEEN 0 AND 100),
    medical_capacity REAL NOT NULL DEFAULT 50 CHECK (medical_capacity BETWEEN 0 AND 100), equipment_capacity REAL NOT NULL DEFAULT 50 CHECK (equipment_capacity BETWEEN 0 AND 100),
    elixir_reserve_capacity REAL NOT NULL DEFAULT 25 CHECK (elixir_reserve_capacity BETWEEN 0 AND 100), transport_capacity REAL NOT NULL DEFAULT 50 CHECK (transport_capacity BETWEEN 0 AND 100),
    readiness REAL NOT NULL DEFAULT 50 CHECK (readiness BETWEEN 0 AND 100), status TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','mobilized','strained','recovering')),
    next_review_day INTEGER NOT NULL DEFAULT 30, metadata_json TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_military_logistics_profiles_due ON military_logistics_profiles(status,next_review_day,id);
CREATE TABLE IF NOT EXISTS military_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT, battle_engagement_id INTEGER NOT NULL UNIQUE REFERENCES combat_engagements(id) ON DELETE CASCADE, campaign_kind TEXT NOT NULL DEFAULT 'limited_campaign',
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL, status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','aftermath','closed','cancelled')),
    started_day INTEGER NOT NULL, ended_day INTEGER, next_review_day INTEGER NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_military_campaigns_due ON military_campaigns(status,next_review_day,id);
CREATE TABLE IF NOT EXISTS campaign_side_logistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER NOT NULL REFERENCES military_campaigns(id) ON DELETE CASCADE, battle_side_id INTEGER NOT NULL UNIQUE REFERENCES battle_sides(id) ON DELETE CASCADE,
    polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL, food_fodder REAL NOT NULL DEFAULT 70 CHECK (food_fodder BETWEEN 0 AND 100), medical REAL NOT NULL DEFAULT 70 CHECK (medical BETWEEN 0 AND 100),
    equipment REAL NOT NULL DEFAULT 70 CHECK (equipment BETWEEN 0 AND 100), elixir_reserve REAL NOT NULL DEFAULT 30 CHECK (elixir_reserve BETWEEN 0 AND 100), route_access REAL NOT NULL DEFAULT 100 CHECK (route_access BETWEEN 0 AND 100),
    current_ground_factor REAL NOT NULL DEFAULT 50 CHECK (current_ground_factor BETWEEN 0 AND 100), shortage_pressure REAL NOT NULL DEFAULT 0 CHECK (shortage_pressure BETWEEN 0 AND 100), aftermath_burden REAL NOT NULL DEFAULT 0 CHECK (aftermath_burden BETWEEN 0 AND 100),
    cultivated_share REAL NOT NULL DEFAULT 0 CHECK (cultivated_share BETWEEN 0 AND 1), last_review_day INTEGER NOT NULL, next_review_day INTEGER NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(campaign_id,battle_side_id));
CREATE INDEX IF NOT EXISTS idx_campaign_side_logistics_due ON campaign_side_logistics(campaign_id,next_review_day,id);
CREATE TABLE IF NOT EXISTS war_logistics_events (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER NOT NULL REFERENCES military_campaigns(id) ON DELETE CASCADE, side_logistics_id INTEGER REFERENCES campaign_side_logistics(id) ON DELETE SET NULL, day INTEGER NOT NULL, event_kind TEXT NOT NULL, magnitude REAL NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_war_logistics_events_campaign ON war_logistics_events(campaign_id,day,id);


CREATE TABLE IF NOT EXISTS structural_training_cohorts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER NOT NULL REFERENCES education_programs(id) ON DELETE CASCADE,
    cohort_index INTEGER NOT NULL,
    estimated_count INTEGER NOT NULL CHECK (estimated_count>=0),
    started_day INTEGER NOT NULL,
    expected_completion_day INTEGER NOT NULL,
    completed_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','cancelled')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(program_id,cohort_index)
);
CREATE INDEX IF NOT EXISTS idx_structural_training_active ON structural_training_cohorts(program_id,status,expected_completion_day,id);


CREATE TABLE IF NOT EXISTS latent_resolution_profiles (
    latent_entity_id INTEGER PRIMARY KEY REFERENCES latent_entities(id) ON DELETE CASCADE,
    resolution_level TEXT NOT NULL DEFAULT 'LATENT' CHECK (resolution_level IN ('LATENT','STRUCTURAL','TRACKED')),
    significance_score REAL NOT NULL DEFAULT 0 CHECK (significance_score BETWEEN 0 AND 100),
    previous_level TEXT CHECK (previous_level IN ('LATENT','STRUCTURAL','TRACKED') OR previous_level IS NULL),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 180,
    last_changed_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_latent_resolution_due ON latent_resolution_profiles(next_review_day,resolution_level,latent_entity_id);


-- v0.47: Groundbinding is permanent place-dependency, not a Stage boost or fuel meter.
CREATE TABLE IF NOT EXISTS groundbinding_profiles (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    bound_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    binding_status TEXT NOT NULL DEFAULT 'bound' CHECK (binding_status IN ('settling','bound','failed','ended')),
    dependency_state TEXT NOT NULL DEFAULT 'comfortable' CHECK (dependency_state IN ('comfortable','straining','failing','catastrophic')),
    binding_depth REAL NOT NULL DEFAULT 100 CHECK (binding_depth BETWEEN 0 AND 100),
    mismatch_burden REAL NOT NULL DEFAULT 0 CHECK (mismatch_burden BETWEEN 0 AND 100),
    last_inside_day INTEGER,
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 14,
    catastrophic_condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(actor_id,bound_location_id)
);
CREATE INDEX IF NOT EXISTS idx_groundbinding_due ON groundbinding_profiles(binding_status,next_review_day,actor_id);
CREATE TABLE IF NOT EXISTS groundbinding_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    state_before TEXT,
    state_after TEXT,
    burden_before REAL NOT NULL,
    burden_after REAL NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_groundbinding_history_actor ON groundbinding_history(actor_id,day,id);


-- v0.54 calibration patch: inverse age-Stage model.
-- This table stores WHEN a Stage was attained. Current age never implies expected Stage.
CREATE TABLE IF NOT EXISTS cultivation_stage_attainments (
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (stage IN ('First','Temper','Third','Breach','Fifth','Sixth')),
    attained_day INTEGER,
    attained_age_days INTEGER CHECK (attained_age_days IS NULL OR attained_age_days>=0),
    chronology_certainty TEXT NOT NULL DEFAULT 'unknown' CHECK (chronology_certainty IN ('known','bounded','unknown')),
    provenance TEXT NOT NULL CHECK (provenance IN ('runtime_breakthrough','source_explicit','opening_current_stage','opening_prior_stage')),
    source_history_id INTEGER REFERENCES cultivation_history(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(actor_id,stage)
);
CREATE INDEX IF NOT EXISTS idx_stage_attainment_stage_age
ON cultivation_stage_attainments(stage,chronology_certainty,attained_age_days,actor_id);


-- PRES-01: low-resolution presence shared across social/information/recruitment/etc.
CREATE TABLE IF NOT EXISTS actor_presence_profiles (
    actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    base_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    source_kind TEXT NOT NULL DEFAULT 'campaign',
    confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence BETWEEN 0 AND 1),
    effective_from_day INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS actor_presence_habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    habit_kind TEXT NOT NULL DEFAULT 'frequented',
    weight REAL NOT NULL DEFAULT 0.5 CHECK (weight BETWEEN 0 AND 1),
    cadence_days INTEGER NOT NULL DEFAULT 7 CHECK (cadence_days >= 1),
    time_window TEXT,
    basis_kind TEXT,
    basis_id INTEGER,
    source_kind TEXT NOT NULL DEFAULT 'campaign',
    confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence BETWEEN 0 AND 1),
    effective_from_day INTEGER NOT NULL,
    effective_to_day INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(actor_id,location_id,habit_kind,basis_kind,basis_id,effective_from_day)
);
CREATE INDEX IF NOT EXISTS idx_presence_habits_actor_day ON actor_presence_habits(actor_id,effective_from_day,effective_to_day,location_id);
CREATE INDEX IF NOT EXISTS idx_presence_habits_location_day ON actor_presence_habits(location_id,effective_from_day,effective_to_day,actor_id);

-- BELIEF-01: claims are propositions; evidence is actor-accessible provenance; beliefs are actor-relative stances.
CREATE TABLE IF NOT EXISTS information_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_key TEXT NOT NULL UNIQUE,
    proposition_text TEXT NOT NULL,
    subject_kind TEXT,
    subject_id INTEGER,
    authoritative_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    created_day INTEGER NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'simulation',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retracted','superseded'))
);

CREATE TABLE IF NOT EXISTS claim_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL REFERENCES information_claims(id) ON DELETE CASCADE,
    evidence_kind TEXT NOT NULL,
    source_id INTEGER,
    source_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    polarity TEXT NOT NULL DEFAULT 'supports' CHECK (polarity IN ('supports','contradicts','context')),
    reliability REAL NOT NULL DEFAULT 0.7 CHECK (reliability BETWEEN 0 AND 1),
    salience REAL NOT NULL DEFAULT 0.6 CHECK (salience BETWEEN 0 AND 1),
    domain_key TEXT,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    available_from_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim ON claim_evidence(claim_id,id);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_domain ON claim_evidence(domain_key,claim_id,id);

CREATE TABLE IF NOT EXISTS actor_evidence_access (
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    evidence_id INTEGER NOT NULL REFERENCES claim_evidence(id) ON DELETE CASCADE,
    received_day INTEGER NOT NULL,
    access_kind TEXT NOT NULL DEFAULT 'observed',
    weight REAL NOT NULL DEFAULT 1.0 CHECK (weight BETWEEN 0 AND 1),
    notes TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(actor_id,evidence_id)
);
CREATE INDEX IF NOT EXISTS idx_actor_evidence_access_actor ON actor_evidence_access(actor_id,received_day,evidence_id);

CREATE TABLE IF NOT EXISTS actor_beliefs (
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    claim_id INTEGER NOT NULL REFERENCES information_claims(id) ON DELETE CASCADE,
    stance TEXT NOT NULL DEFAULT 'uncertain' CHECK (stance IN ('unaware','uncertain','accepts','rejects')),
    confidence REAL NOT NULL DEFAULT 0.0 CHECK (confidence BETWEEN 0 AND 1),
    first_received_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL,
    correction_count INTEGER NOT NULL DEFAULT 0 CHECK (correction_count >= 0),
    basis_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY(actor_id,claim_id)
);
CREATE INDEX IF NOT EXISTS idx_actor_beliefs_actor ON actor_beliefs(actor_id,updated_day DESC,claim_id);

CREATE TABLE IF NOT EXISTS belief_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    claim_id INTEGER NOT NULL REFERENCES information_claims(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    old_stance TEXT NOT NULL,
    new_stance TEXT NOT NULL,
    old_confidence REAL NOT NULL,
    new_confidence REAL NOT NULL,
    reason TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_belief_revisions_actor_claim ON belief_revisions(actor_id,claim_id,day,id);


-- MERCHANT-01 cross-system commercial vertical slice
CREATE TABLE IF NOT EXISTS enterprise_staff (
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'factor',
    authority REAL NOT NULL DEFAULT 50 CHECK(authority BETWEEN 0 AND 100),
    specialty TEXT NOT NULL DEFAULT 'trade',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','former')),
    joined_day INTEGER NOT NULL,
    left_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(enterprise_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_enterprise_staff_actor ON enterprise_staff(actor_id,status,authority DESC,enterprise_id);

CREATE TABLE IF NOT EXISTS merchant_market_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    observer_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
    observed_day INTEGER NOT NULL,
    received_day INTEGER NOT NULL,
    observed_price REAL NOT NULL CHECK(observed_price>0),
    observed_supply REAL NOT NULL CHECK(observed_supply>=0),
    observed_demand REAL NOT NULL CHECK(observed_demand>=0),
    source_kind TEXT NOT NULL,
    source_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    reliability REAL NOT NULL DEFAULT .8 CHECK(reliability BETWEEN 0 AND 1),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_market_obs_enterprise ON merchant_market_observations(enterprise_id,received_day,location_id,good_id,observed_day DESC);

CREATE TABLE IF NOT EXISTS merchant_trade_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    stock_id INTEGER NOT NULL REFERENCES commercial_stock(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    quantity_available REAL NOT NULL CHECK(quantity_available>=0),
    unit_price REAL NOT NULL CHECK(unit_price>0),
    published_day INTEGER NOT NULL,
    expires_day INTEGER,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','filled','withdrawn','expired')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_trade_offers_market ON merchant_trade_offers(status,location_id,good_id,published_day,id);

CREATE TABLE IF NOT EXISTS merchant_offer_awareness (
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    offer_id INTEGER NOT NULL REFERENCES merchant_trade_offers(id) ON DELETE CASCADE,
    observed_day INTEGER NOT NULL,
    received_day INTEGER NOT NULL,
    PRIMARY KEY(enterprise_id,offer_id)
);

CREATE TABLE IF NOT EXISTS merchant_trade_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id INTEGER NOT NULL REFERENCES merchant_trade_offers(id) ON DELETE RESTRICT,
    buyer_enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE RESTRICT,
    seller_enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE RESTRICT,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity>0),
    unit_price REAL NOT NULL CHECK(unit_price>0),
    origin_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    settlement_kind TEXT NOT NULL CHECK(settlement_kind IN ('cash_on_delivery','seller_credit')),
    agreed_day INTEGER NOT NULL,
    due_day INTEGER NOT NULL,
    shipped_quantity REAL NOT NULL DEFAULT 0,
    delivered_quantity REAL NOT NULL DEFAULT 0,
    amount_paid REAL NOT NULL DEFAULT 0,
    shipment_id INTEGER REFERENCES commercial_shipments(id) ON DELETE SET NULL,
    fulfilled_day INTEGER,
    status TEXT NOT NULL DEFAULT 'accepted' CHECK(status IN ('accepted','in_transit','fulfilled','breached','cancelled')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_trade_contracts_due ON merchant_trade_contracts(status,due_day,id);

CREATE TABLE IF NOT EXISTS commercial_cash_transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    from_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    to_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    amount REAL NOT NULL CHECK(amount>0),
    transfer_kind TEXT NOT NULL,
    trade_contract_id INTEGER REFERENCES merchant_trade_contracts(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_cash_transfer_contract ON commercial_cash_transfers(trade_contract_id,day,id);

CREATE TABLE IF NOT EXISTS production_input_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_site_id INTEGER NOT NULL REFERENCES production_sites(id) ON DELETE CASCADE,
    input_good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
    units_per_output REAL NOT NULL DEFAULT 1 CHECK(units_per_output>0),
    substitution_group TEXT NOT NULL DEFAULT 'primary',
    preference_weight REAL NOT NULL DEFAULT 1 CHECK(preference_weight>0),
    current_share REAL NOT NULL DEFAULT .5 CHECK(current_share BETWEEN 0 AND 1),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    UNIQUE(production_site_id,input_good_id)
);
CREATE INDEX IF NOT EXISTS idx_input_options_due ON production_input_options(active,next_review_day,production_site_id);


-- CRAFT-01: tracked recipes, facilities, workers, orders and conserved input/output lots.
CREATE TABLE IF NOT EXISTS craft_recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    output_good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    output_quantity REAL NOT NULL DEFAULT 1 CHECK(output_quantity>0),
    base_duration_days REAL NOT NULL DEFAULT 1 CHECK(base_duration_days>0),
    skill_domain TEXT NOT NULL DEFAULT 'craft',
    min_skill REAL NOT NULL DEFAULT 0 CHECK(min_skill BETWEEN 0 AND 100),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_craft_recipe_output ON craft_recipes(output_good_id,active,id);

CREATE TABLE IF NOT EXISTS craft_recipe_inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES craft_recipes(id) ON DELETE CASCADE,
    group_key TEXT NOT NULL,
    input_good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    units_per_batch REAL NOT NULL CHECK(units_per_batch>0),
    preference_weight REAL NOT NULL DEFAULT 1 CHECK(preference_weight>0),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(recipe_id,group_key,input_good_id)
);
CREATE INDEX IF NOT EXISTS idx_craft_recipe_input_good ON craft_recipe_inputs(input_good_id,active,recipe_id);

CREATE TABLE IF NOT EXISTS craft_recipe_facility_requirements (
    recipe_id INTEGER NOT NULL REFERENCES craft_recipes(id) ON DELETE CASCADE,
    facility_kind TEXT NOT NULL,
    minimum_capacity REAL NOT NULL DEFAULT 1 CHECK(minimum_capacity>0),
    minimum_condition REAL NOT NULL DEFAULT 20 CHECK(minimum_condition BETWEEN 0 AND 100),
    PRIMARY KEY(recipe_id,facility_kind)
);

CREATE TABLE IF NOT EXISTS craft_facilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    facility_kind TEXT NOT NULL,
    name TEXT NOT NULL,
    capacity REAL NOT NULL DEFAULT 1 CHECK(capacity>0),
    condition REAL NOT NULL DEFAULT 100 CHECK(condition BETWEEN 0 AND 100),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_craft_facility_lookup ON craft_facilities(enterprise_id,location_id,facility_kind,active,id);

CREATE TABLE IF NOT EXISTS craft_site_recipes (
    production_site_id INTEGER NOT NULL REFERENCES production_sites(id) ON DELETE CASCADE,
    recipe_id INTEGER NOT NULL REFERENCES craft_recipes(id) ON DELETE CASCADE,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    PRIMARY KEY(production_site_id,recipe_id)
);

CREATE TABLE IF NOT EXISTS craft_site_workers (
    production_site_id INTEGER NOT NULL REFERENCES production_sites(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'craftsperson',
    capacity_share REAL NOT NULL DEFAULT 1 CHECK(capacity_share>0),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','former')),
    assigned_day INTEGER NOT NULL,
    PRIMARY KEY(production_site_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_craft_workers_actor ON craft_site_workers(actor_id,status,production_site_id);

CREATE TABLE IF NOT EXISTS craft_production_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_site_id INTEGER NOT NULL REFERENCES production_sites(id) ON DELETE CASCADE,
    recipe_id INTEGER NOT NULL REFERENCES craft_recipes(id) ON DELETE RESTRICT,
    requested_output_qty REAL NOT NULL CHECK(requested_output_qty>0),
    priority INTEGER NOT NULL DEFAULT 50 CHECK(priority BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','waiting_input','waiting_facility','waiting_labor','in_progress','completed','cancelled','blocked')),
    created_day INTEGER NOT NULL,
    due_day INTEGER,
    started_day INTEGER,
    completed_day INTEGER,
    next_review_day INTEGER NOT NULL,
    blocked_reason TEXT,
    blocked_detail_json TEXT NOT NULL DEFAULT '{}',
    selected_inputs_json TEXT NOT NULL DEFAULT '[]',
    quality REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_craft_orders_due ON craft_production_orders(status,next_review_day,priority DESC,id);
CREATE INDEX IF NOT EXISTS idx_craft_orders_site ON craft_production_orders(production_site_id,status,id);

CREATE TABLE IF NOT EXISTS craft_input_reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES craft_production_orders(id) ON DELETE CASCADE,
    recipe_input_id INTEGER NOT NULL REFERENCES craft_recipe_inputs(id) ON DELETE RESTRICT,
    stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    quantity_reserved REAL NOT NULL CHECK(quantity_reserved>0),
    quantity_consumed REAL NOT NULL DEFAULT 0 CHECK(quantity_consumed>=0),
    status TEXT NOT NULL DEFAULT 'reserved' CHECK(status IN ('reserved','consumed','released')),
    reserved_day INTEGER NOT NULL,
    consumed_day INTEGER,
    released_day INTEGER
);
CREATE INDEX IF NOT EXISTS idx_craft_reservation_order ON craft_input_reservations(order_id,status,id);

CREATE TABLE IF NOT EXISTS craft_output_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES craft_production_orders(id) ON DELETE CASCADE,
    stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity>0),
    quality REAL NOT NULL CHECK(quality BETWEEN 0 AND 100),
    produced_day INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_craft_output_order ON craft_output_lots(order_id,id);

CREATE TABLE IF NOT EXISTS craft_order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES craft_production_orders(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    event_kind TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_craft_event_order ON craft_order_events(order_id,day,id);

-- GROWTH-01: regional growth / state-capacity vertical slice.
-- These tables own conserved public finance, concrete public projects, delayed
-- administrative reports, and causal snapshots. There is intentionally no
-- authoritative prosperity/development score.
CREATE TABLE IF NOT EXISTS regional_public_treasuries (
    polity_id INTEGER PRIMARY KEY REFERENCES political_polities(id) ON DELETE CASCADE,
    cash REAL NOT NULL DEFAULT 0 CHECK(cash>=0),
    debt REAL NOT NULL DEFAULT 0 CHECK(debt>=0),
    tax_rate REAL NOT NULL DEFAULT .05 CHECK(tax_rate BETWEEN 0 AND .5),
    toll_rate REAL NOT NULL DEFAULT 0 CHECK(toll_rate BETWEEN 0 AND .5),
    debt_interest_rate_per_30 REAL NOT NULL DEFAULT .015 CHECK(debt_interest_rate_per_30>=0),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','strained','suspended')),
    last_collection_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    review_cadence_days INTEGER NOT NULL DEFAULT 30 CHECK(review_cadence_days>0),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_regional_treasury_due ON regional_public_treasuries(status,next_review_day,polity_id);

CREATE TABLE IF NOT EXISTS regional_fiscal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('inflow','outflow')),
    entry_kind TEXT NOT NULL,
    amount REAL NOT NULL CHECK(amount>0),
    counterparty_kind TEXT,
    counterparty_id INTEGER,
    source_kind TEXT,
    source_id INTEGER,
    description TEXT
);
CREATE INDEX IF NOT EXISTS idx_regional_fiscal_polity_day ON regional_fiscal_entries(polity_id,day,id);

CREATE TABLE IF NOT EXISTS regional_public_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
    project_kind TEXT NOT NULL CHECK(project_kind IN ('road_repair','security_post','market_warehouse','administrative_office')),
    title TEXT NOT NULL,
    required_cash REAL NOT NULL DEFAULT 0 CHECK(required_cash>=0),
    cash_spent REAL NOT NULL DEFAULT 0 CHECK(cash_spent>=0),
    required_labor_days REAL NOT NULL DEFAULT 0 CHECK(required_labor_days>=0),
    labor_days_used REAL NOT NULL DEFAULT 0 CHECK(labor_days_used>=0),
    material_good_id INTEGER REFERENCES market_goods(id) ON DELETE RESTRICT,
    required_material_quantity REAL NOT NULL DEFAULT 0 CHECK(required_material_quantity>=0),
    material_quantity_used REAL NOT NULL DEFAULT 0 CHECK(material_quantity_used>=0),
    started_day INTEGER NOT NULL,
    target_day INTEGER,
    completed_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','blocked','completed','cancelled')),
    blocked_reason TEXT,
    next_review_day INTEGER NOT NULL,
    effects_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_regional_project_due ON regional_public_projects(status,next_review_day,polity_id,id);
CREATE INDEX IF NOT EXISTS idx_regional_project_route ON regional_public_projects(route_id,status,id);

CREATE TABLE IF NOT EXISTS regional_project_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES regional_public_projects(id) ON DELETE CASCADE,
    supplier_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity>0),
    unit_price REAL NOT NULL CHECK(unit_price>=0),
    delivered_day INTEGER NOT NULL,
    paid_amount REAL NOT NULL CHECK(paid_amount>=0)
);
CREATE INDEX IF NOT EXISTS idx_regional_project_material ON regional_project_materials(project_id,good_id,id);

CREATE TABLE IF NOT EXISTS regional_project_labor (
    project_id INTEGER NOT NULL REFERENCES regional_public_projects(id) ON DELETE CASCADE,
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    labor_days_committed REAL NOT NULL CHECK(labor_days_committed>0),
    labor_days_used REAL NOT NULL DEFAULT 0 CHECK(labor_days_used>=0),
    wage_per_day REAL NOT NULL DEFAULT 0 CHECK(wage_per_day>=0),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','withdrawn')),
    PRIMARY KEY(project_id,household_id)
);

CREATE TABLE IF NOT EXISTS regional_security_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    route_id INTEGER REFERENCES travel_routes(id) ON DELETE CASCADE,
    location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE,
    monthly_cost REAL NOT NULL DEFAULT 0 CHECK(monthly_cost>=0),
    strength REAL NOT NULL DEFAULT 40 CHECK(strength BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','unfunded','ended','cancelled')),
    last_paid_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(route_id IS NOT NULL OR location_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_regional_security_due ON regional_security_assignments(status,next_review_day,polity_id,id);

CREATE TABLE IF NOT EXISTS regional_administrative_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    recipient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
    report_kind TEXT NOT NULL,
    observed_day INTEGER NOT NULL,
    received_day INTEGER NOT NULL,
    delivered_day INTEGER,
    reliability REAL NOT NULL DEFAULT .7 CHECK(reliability BETWEEN 0 AND 1),
    report_json TEXT NOT NULL DEFAULT '{}',
    claim_id INTEGER REFERENCES information_claims(id) ON DELETE SET NULL,
    evidence_id INTEGER REFERENCES claim_evidence(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','delivered','lost'))
);
CREATE INDEX IF NOT EXISTS idx_regional_report_due ON regional_administrative_reports(status,received_day,id);
CREATE INDEX IF NOT EXISTS idx_regional_report_recipient ON regional_administrative_reports(recipient_actor_id,delivered_day,id);

CREATE TABLE IF NOT EXISTS regional_migration_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    source_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    day INTEGER NOT NULL,
    appeal_gap REAL NOT NULL,
    migration_plan_id INTEGER REFERENCES household_migration_plans(id) ON DELETE SET NULL,
    reason_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_regional_migration_day ON regional_migration_responses(day,household_id,id);

CREATE TABLE IF NOT EXISTS regional_growth_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    population_estimate REAL NOT NULL DEFAULT 0,
    households INTEGER NOT NULL DEFAULT 0,
    active_enterprises INTEGER NOT NULL DEFAULT 0,
    enterprise_cash REAL NOT NULL DEFAULT 0,
    route_accessibility REAL NOT NULL DEFAULT 0,
    route_hazard REAL NOT NULL DEFAULT 0,
    average_route_days REAL,
    trade_contracts_365 INTEGER NOT NULL DEFAULT 0,
    food_stress REAL NOT NULL DEFAULT 0,
    treasury_cash REAL NOT NULL DEFAULT 0,
    public_debt REAL NOT NULL DEFAULT 0,
    net_public_flow_365 REAL NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_regional_snapshot_location_day ON regional_growth_snapshots(polity_id,location_id,day,id);


-- schema 67 / WAR-01

-- WAR-01: strategic campaign owner above individual engagements.
CREATE TABLE IF NOT EXISTS war_campaign_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    attacker_polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    defender_polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    commander_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    objective_kind TEXT NOT NULL DEFAULT 'limited' CHECK(objective_kind IN ('limited','territorial','raid','relief','defence','siege','other')),
    objective_text TEXT NOT NULL,
    origin_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    target_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'mobilizing' CHECK(status IN ('mobilizing','marching','engaged','aftermath','closed','cancelled','stalled')),
    started_day INTEGER NOT NULL,
    ended_day INTEGER,
    next_review_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(origin_location_id <> target_location_id)
);
CREATE INDEX IF NOT EXISTS idx_war_operation_due ON war_campaign_operations(status,next_review_day,id);

CREATE TABLE IF NOT EXISTS war_operation_engagements (
    operation_id INTEGER NOT NULL REFERENCES war_campaign_operations(id) ON DELETE CASCADE,
    engagement_id INTEGER NOT NULL UNIQUE REFERENCES combat_engagements(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL DEFAULT 1,
    linked_day INTEGER NOT NULL,
    PRIMARY KEY(operation_id,engagement_id)
);

CREATE TABLE IF NOT EXISTS war_campaign_forces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL REFERENCES war_campaign_operations(id) ON DELETE CASCADE,
    polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    battle_side_id INTEGER UNIQUE REFERENCES battle_sides(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'field_force' CHECK(role IN ('field_force','garrison','raiding_force','relief_force','escort','other')),
    personnel_initial INTEGER NOT NULL CHECK(personnel_initial>=0),
    personnel_available INTEGER NOT NULL CHECK(personnel_available>=0),
    aggregate_killed INTEGER NOT NULL DEFAULT 0 CHECK(aggregate_killed>=0),
    aggregate_wounded INTEGER NOT NULL DEFAULT 0 CHECK(aggregate_wounded>=0),
    aggregate_captured INTEGER NOT NULL DEFAULT 0 CHECK(aggregate_captured>=0),
    aggregate_deserted INTEGER NOT NULL DEFAULT 0 CHECK(aggregate_deserted>=0),
    current_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    current_route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
    segment_target_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    segment_due_day INTEGER,
    status TEXT NOT NULL DEFAULT 'mobilized' CHECK(status IN ('mobilized','marching','deployed','engaged','withdrawing','stalled','demobilized','destroyed')),
    last_review_day INTEGER NOT NULL,
    next_review_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(operation_id,name)
);
CREATE INDEX IF NOT EXISTS idx_war_force_due ON war_campaign_forces(status,next_review_day,operation_id,id);
CREATE INDEX IF NOT EXISTS idx_war_force_location ON war_campaign_forces(current_location_id,status,id);

CREATE TABLE IF NOT EXISTS war_force_members (
    force_id INTEGER NOT NULL REFERENCES war_campaign_forces(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    duty_kind TEXT NOT NULL DEFAULT 'soldier',
    exposure REAL NOT NULL DEFAULT 50 CHECK(exposure BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','wounded','killed','captured','missing','deserted','released','demobilized')),
    health_condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL,
    updated_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(force_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_war_force_member_actor ON war_force_members(actor_id,status,force_id);

CREATE TABLE IF NOT EXISTS war_force_supplies (
    force_id INTEGER NOT NULL REFERENCES war_campaign_forces(id) ON DELETE CASCADE,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    supply_kind TEXT NOT NULL CHECK(supply_kind IN ('food','fodder','equipment','medical','elixir','other')),
    source_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    source_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    on_hand REAL NOT NULL DEFAULT 0 CHECK(on_hand>=0),
    weekly_need REAL NOT NULL DEFAULT 0 CHECK(weekly_need>=0),
    max_on_hand REAL NOT NULL DEFAULT 0 CHECK(max_on_hand>=0),
    last_review_day INTEGER NOT NULL,
    PRIMARY KEY(force_id,good_id)
);

CREATE TABLE IF NOT EXISTS war_supply_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    force_id INTEGER NOT NULL REFERENCES war_campaign_forces(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    entry_kind TEXT NOT NULL CHECK(entry_kind IN ('mobilized','resupplied','consumed','lost','captured','returned')),
    quantity REAL NOT NULL CHECK(quantity>0),
    source_stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_war_supply_force_day ON war_supply_ledger(force_id,day,id);

CREATE TABLE IF NOT EXISTS war_battle_aftermath (
    engagement_id INTEGER PRIMARY KEY REFERENCES combat_engagements(id) ON DELETE CASCADE,
    operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL,
    applied_day INTEGER NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS war_damage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL,
    engagement_id INTEGER REFERENCES combat_engagements(id) ON DELETE SET NULL,
    day INTEGER NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    target_kind TEXT NOT NULL CHECK(target_kind IN ('route','building','stock','market','agriculture','other')),
    target_id INTEGER,
    magnitude REAL NOT NULL CHECK(magnitude BETWEEN 0 AND 100),
    effects_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_war_damage_location ON war_damage_events(location_id,day,id);

CREATE TABLE IF NOT EXISTS war_displacement_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL,
    engagement_id INTEGER REFERENCES combat_engagements(id) ON DELETE SET NULL,
    household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    source_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    destination_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    migration_plan_id INTEGER REFERENCES household_migration_plans(id) ON DELETE SET NULL,
    day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'displaced' CHECK(status IN ('displaced','planned','in_transit','resettled','stranded')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_war_displacement_day ON war_displacement_events(day,source_location_id,id);

CREATE TABLE IF NOT EXISTS war_battle_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    version_kind TEXT NOT NULL CHECK(version_kind IN ('official','eyewitness','rumour')),
    source_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    recipient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    observed_day INTEGER NOT NULL,
    received_day INTEGER NOT NULL,
    delivered_day INTEGER,
    reliability REAL NOT NULL DEFAULT .7 CHECK(reliability BETWEEN 0 AND 1),
    report_text TEXT NOT NULL,
    claim_id INTEGER REFERENCES information_claims(id) ON DELETE SET NULL,
    evidence_id INTEGER REFERENCES claim_evidence(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','delivered','lost')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_war_report_due ON war_battle_reports(status,received_day,id);
CREATE INDEX IF NOT EXISTS idx_war_report_recipient ON war_battle_reports(recipient_actor_id,delivered_day,id);



-- INTEGRATION-01 tables are installed authoritatively by migration 68; see engine/db.py _migration_68.

-- schema 77: shared institutional agency substrate.
CREATE TABLE IF NOT EXISTS organization_agency_profiles (
    institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
    institutional_inheritance_json TEXT NOT NULL DEFAULT '{}',
    culture_inertia REAL NOT NULL DEFAULT 0.75 CHECK(culture_inertia BETWEEN 0 AND 1),
    culture_drift_rate REAL NOT NULL DEFAULT 0.04 CHECK(culture_drift_rate BETWEEN 0 AND 1),
    governance_mode TEXT NOT NULL DEFAULT 'institutional',
    last_review_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS organization_regimes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    leader_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    regime_kind TEXT NOT NULL DEFAULT 'continuity',
    mandate_json TEXT NOT NULL DEFAULT '{}',
    worldview_json TEXT NOT NULL DEFAULT '{}',
    started_day INTEGER NOT NULL,
    ended_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ended','disputed')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_org_regime_one_active ON organization_regimes(institution_actor_id) WHERE status='active';

CREATE TABLE IF NOT EXISTS organization_factions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    faction_key TEXT NOT NULL,
    name TEXT,
    sponsor_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    influence REAL NOT NULL DEFAULT 0 CHECK(influence BETWEEN 0 AND 100),
    cohesion REAL NOT NULL DEFAULT 50 CHECK(cohesion BETWEEN 0 AND 100),
    positions_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','dormant','defeated','merged','dissolved')),
    created_day INTEGER NOT NULL DEFAULT 0,
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(institution_actor_id,faction_key)
);

CREATE TABLE IF NOT EXISTS organization_pressures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    pressure_key TEXT NOT NULL,
    domain TEXT NOT NULL,
    target_kind TEXT,
    target_id INTEGER,
    intensity REAL NOT NULL DEFAULT 0 CHECK(intensity>=0),
    urgency REAL NOT NULL DEFAULT 0 CHECK(urgency BETWEEN 0 AND 100),
    source_kind TEXT,
    source_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','resolved','expired')),
    created_day INTEGER NOT NULL DEFAULT 0,
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(institution_actor_id,pressure_key,status)
);
CREATE INDEX IF NOT EXISTS idx_org_pressures_active ON organization_pressures(institution_actor_id,status,intensity DESC,id);

CREATE TABLE IF NOT EXISTS organization_capabilities (
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    capability_key TEXT NOT NULL,
    domain TEXT NOT NULL,
    capacity REAL NOT NULL DEFAULT 0 CHECK(capacity BETWEEN 0 AND 100),
    readiness REAL NOT NULL DEFAULT 0 CHECK(readiness BETWEEN 0 AND 100),
    basis_json TEXT NOT NULL DEFAULT '{}',
    updated_day INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(institution_actor_id,capability_key)
);

CREATE TABLE IF NOT EXISTS organization_strategy_positions (
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    issue_key TEXT NOT NULL,
    domain TEXT NOT NULL,
    target_kind TEXT,
    target_id INTEGER,
    position_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL NOT NULL DEFAULT 0.5 CHECK(confidence BETWEEN 0 AND 1),
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(institution_actor_id,issue_key)
);

-- schema 79: relationship-specific polity agency.
CREATE TABLE IF NOT EXISTS polity_issue_states (
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    other_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    issue_key TEXT NOT NULL,
    issue_kind TEXT NOT NULL,
    interest REAL NOT NULL DEFAULT 50 CHECK(interest BETWEEN 0 AND 100),
    pressure REAL NOT NULL DEFAULT 0 CHECK(pressure BETWEEN 0 AND 100),
    restraint REAL NOT NULL DEFAULT 50 CHECK(restraint BETWEEN 0 AND 100),
    preferred_posture TEXT NOT NULL DEFAULT 'cautious' CHECK(preferred_posture IN ('cooperative','cautious','competitive','hardline','hostile')),
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(polity_id,other_polity_id,issue_key),
    CHECK(polity_id<>other_polity_id)
);
CREATE INDEX IF NOT EXISTS idx_polity_issue_pair ON polity_issue_states(polity_id,other_polity_id,pressure DESC,issue_key);

CREATE TABLE IF NOT EXISTS polity_government_actors (
    polity_id INTEGER PRIMARY KEY REFERENCES political_polities(id) ON DELETE CASCADE,
    decision_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    authority_kind TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- schema 80: causal conflict-origin layer.
CREATE TABLE IF NOT EXISTS conflict_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_key TEXT NOT NULL UNIQUE,
    polity_a_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    polity_b_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    issue_kind TEXT NOT NULL,
    location_a_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    location_b_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    base_pressure REAL NOT NULL DEFAULT 0 CHECK(base_pressure BETWEEN 0 AND 100),
    volatility REAL NOT NULL DEFAULT 0.2 CHECK(volatility BETWEEN 0 AND 1),
    restraint REAL NOT NULL DEFAULT 50 CHECK(restraint BETWEEN 0 AND 100),
    incident_threshold REAL NOT NULL DEFAULT 55 CHECK(incident_threshold BETWEEN 1 AND 100),
    accumulated_pressure REAL NOT NULL DEFAULT 0 CHECK(accumulated_pressure>=0),
    review_cadence_days INTEGER NOT NULL DEFAULT 30 CHECK(review_cadence_days>=1),
    last_review_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','dormant','resolved')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(polity_a_id<>polity_b_id)
);
CREATE INDEX IF NOT EXISTS idx_conflict_channels_due ON conflict_channels(status,next_review_day,id);

CREATE TABLE IF NOT EXISTS conflict_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER REFERENCES conflict_channels(id) ON DELETE SET NULL,
    day INTEGER NOT NULL,
    initiator_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    target_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    incident_kind TEXT NOT NULL,
    severity REAL NOT NULL CHECK(severity BETWEEN 0 AND 100),
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','responded','escalated','settled','expired')),
    response_state TEXT NOT NULL DEFAULT 'none' CHECK(response_state IN ('none','formal_demand','retaliation','settlement','campaign','other')),
    responded_day INTEGER,
    response_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(initiator_polity_id<>target_polity_id)
);
CREATE INDEX IF NOT EXISTS idx_conflict_incidents_target ON conflict_incidents(target_polity_id,status,day,id);

CREATE TABLE IF NOT EXISTS conflict_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES conflict_incidents(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    responding_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    response_kind TEXT NOT NULL,
    operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_conflict_one_formal_response ON conflict_responses(incident_id,responding_polity_id);


-- schema 105: WORLDHIST-01A / HARM-01 shared provenance-bearing harm projection.
CREATE TABLE IF NOT EXISTS harm_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL,
    source_ref_id INTEGER NOT NULL,
    harm_kind TEXT NOT NULL,
    intent_class TEXT NOT NULL CHECK(intent_class IN ('controlled','hostile','lethal','accidental')),
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    exposure REAL NOT NULL DEFAULT 50 CHECK(exposure BETWEEN 0 AND 100),
    raw_severity REAL NOT NULL CHECK(raw_severity BETWEEN 0 AND 100),
    resolved_severity REAL NOT NULL CHECK(resolved_severity BETWEEN 0 AND 100),
    outcome TEXT NOT NULL CHECK(outcome IN ('transient','persistent','fatal')),
    condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL,
    fatal INTEGER NOT NULL DEFAULT 0 CHECK(fatal IN (0,1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(actor_id,source_kind,source_ref_id,harm_kind)
);
CREATE INDEX IF NOT EXISTS idx_harm_actor_day ON harm_incidents(actor_id,day,id);
CREATE INDEX IF NOT EXISTS idx_harm_source ON harm_incidents(source_kind,source_ref_id,actor_id);
