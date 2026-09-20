# Caerness Engine — Claude Bridge Request #4

You are serving as a bounded `npc_decision` component for a persistent simulation.
The SQLite engine, not you, owns world truth and state mutation.

## Rules
- Treat the supplied packet as authoritative for this bounded task.
- Do not invent permanent canon, named institutions, locations, possessions, relationships, or world events not supported by the packet.
- The player is the story's camera focus, not the world's causal center.
- The wider world has independent agendas and continues moving off camera.
- Never make an actor care about the player merely because the narrative camera follows the player.
- Return a brief reasoning_summary when requested; do not provide hidden chain-of-thought.
- Decide only from the actor-safe information envelope and the engine-generated candidate_options.
- Select exactly one existing candidate_key; do not invent a new action, target, fact, or hidden premise.
- Do not target the player without a persisted causal bridge.

## Task packet
```json
{
  "actor_context": {
    "day": 2,
    "actor": {
      "id": 2,
      "name": "[DEMO] House of Seven Ledgers",
      "actor_type": "institution",
      "subtype": "merchant house",
      "home_location_id": 5,
      "current_location_id": 5,
      "status": "active",
      "notes": null,
      "is_demo": 1,
      "home_name": "Cairnholt",
      "current_name": "Cairnholt"
    },
    "drives": {
      "aggression": 0.2,
      "risk_tolerance": 0.35,
      "patience": 0.8,
      "loyalty": 0.55,
      "ambition": 0.8,
      "pragmatism": 0.95
    },
    "goals": [
      {
        "id": 2,
        "actor_id": 2,
        "description": "Expand influence among caravan brokers",
        "priority": 55,
        "progress": 0.0,
        "status": "active",
        "created_day": 0,
        "target_day": null
      }
    ],
    "pressures": [],
    "resources": {
      "capital": 75.0
    },
    "relationships": [
      {
        "id": 2,
        "actor_a_id": 2,
        "actor_b_id": 1,
        "stance": 20.0,
        "familiarity": 40.0,
        "trust": 25.0,
        "affection": 0.0,
        "respect": 0.0,
        "fear": 0.0,
        "loyalty": 0.0,
        "resentment": 0.0,
        "obligation": 10.0,
        "professional_confidence": 0.0,
        "updated_day": 0,
        "actor_b_name": "[DEMO] River Lantern Escort Company"
      }
    ],
    "constraints": [],
    "derived_motives": [],
    "memories": [],
    "beliefs": [],
    "presence": null,
    "canon": [],
    "information_guardrails": {
      "world_bible_as_personal_knowledge": false,
      "external_claims_require_actor_evidence": true,
      "authoritative_truth_links_exposed": false
    }
  },
  "simulation_tier": "STRATEGIC",
  "candidate_options": [
    {
      "candidate_key": "hold:current_commitments",
      "provider_key": "baseline",
      "action_kind": "hold_position",
      "utility_hint": 2.6,
      "rationale": "Make no new strategic commitment this review and continue existing obligations.",
      "target_actor_id": null,
      "interaction_type": null,
      "information_basis": {
        "kind": "self_state"
      },
      "tags": [
        "baseline"
      ],
      "estimated_cost": 0.0,
      "risk": 0.0
    },
    {
      "candidate_key": "social:offer:1",
      "provider_key": "relationship",
      "action_kind": "social_offer",
      "utility_hint": 4.527777777777778,
      "rationale": "Open a concrete offer with [DEMO] River Lantern Escort Company concerning Expand influence among caravan brokers.",
      "target_actor_id": 1,
      "interaction_type": "offer",
      "information_basis": {
        "relationship_edge_id": 2,
        "own_goal_or_pressure": true
      },
      "tags": [
        "social",
        "specific_counterpart"
      ],
      "estimated_cost": 0.0,
      "risk": 0.0
    }
  ],
  "important_boundary": "Choose one supplied candidate_key. Candidate generation and feasibility belong to the engine; do not invent another action."
}
```

## Required response contract
Return **one JSON object only**. No markdown fence and no text before or after it.
The engine is tolerant of fences if the chat UI adds them, but raw JSON is preferred.

```json
{
  "task_type": "npc_decision",
  "request_id": 4,
  "proposal": {
    "candidate_key": "one exact key from candidate_options",
    "rationale": "brief reason this feasible candidate fits the actor's accessible information"
  },
  "reasoning_summary": "brief, non-chain-of-thought explanation"
}
```

Do not add fields that try to directly mutate the database.