-- Optional planning protocol schema v1. Installed transactionally on first use;
-- legacy Schema 108 tables and packaged opening are never rewritten.
CREATE TABLE IF NOT EXISTS ai_sessions (
 id INTEGER PRIMARY KEY, owner_actor_id INTEGER NOT NULL REFERENCES actors(id),
 created_day INTEGER NOT NULL, messages_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS ai_plans (
 id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES ai_sessions(id),
 owner_actor_id INTEGER NOT NULL REFERENCES actors(id), revision INTEGER NOT NULL DEFAULT 1,
 source_text TEXT NOT NULL, spec_json TEXT NOT NULL, digest TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft', created_day INTEGER NOT NULL,
 approved_digest TEXT, updated_day INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_plan_steps (
 plan_id INTEGER NOT NULL REFERENCES ai_plans(id), step_key TEXT NOT NULL,
 spec_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 result_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(plan_id,step_key)
);
CREATE TABLE IF NOT EXISTS ai_plan_events (
 id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL REFERENCES ai_plans(id),
 day INTEGER NOT NULL, kind TEXT NOT NULL, detail_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_resource_allocations (
 id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL REFERENCES ai_plans(id),
 institution_actor_id INTEGER NOT NULL REFERENCES actors(id),
 resources_json TEXT NOT NULL, spent_json TEXT NOT NULL DEFAULT '{}',
 status TEXT NOT NULL DEFAULT 'reserved'
);
CREATE TABLE IF NOT EXISTS ai_work_links (
 project_id INTEGER PRIMARY KEY REFERENCES civilian_projects(id),
 plan_id INTEGER NOT NULL REFERENCES ai_plans(id), site_id INTEGER NOT NULL REFERENCES strategic_assets(id),
 offering_id INTEGER NOT NULL REFERENCES seekable_offerings(id),
 service_engagement_id INTEGER NOT NULL REFERENCES service_engagements(id)
);
CREATE INDEX IF NOT EXISTS ai_plans_owner ON ai_plans(owner_actor_id,status);
CREATE INDEX IF NOT EXISTS ai_work_site ON ai_work_links(site_id);
