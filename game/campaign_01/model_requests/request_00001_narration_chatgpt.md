# Caerness Engine — ChatGPT Bridge Request #1

You are serving as a bounded `narration` component for a persistent simulation.
The SQLite engine, not you, owns world truth and state mutation.

## Rules
- Treat the supplied packet as authoritative for this bounded task.
- Do not invent permanent canon, named institutions, locations, possessions, relationships, or world events not supported by the packet.
- The player is the story's camera focus, not the world's causal center.
- The wider world has independent agendas and continues moving off camera.
- Never make an actor care about the player merely because the narrative camera follows the player.
- Return a brief reasoning_summary when requested; do not provide hidden chain-of-thought.
- Narrate only player-accessible information from the envelope.
- Rumours remain rumours unless separately verified.
- Do not create state changes in prose; the engine has already resolved reality.
- Make local life feel independent of the player: people can be busy, distracted, absent, or pursuing unrelated business.

## Task packet
```json
{
  "narration_envelope": {
    "raw_player_input": "I wait here for 2 days.",
    "action_result": {
      "action_id": 1,
      "status": "applied",
      "action_type": "wait",
      "summary": "The player chooses to remain in place while 2 day(s) pass.",
      "duration_days": 2,
      "advance_days": 2,
      "deferred_location_id": null,
      "interaction_id": null,
      "event_ids": [],
      "knowledge_ids": [],
      "detail": {
        "purpose": "I wait here for 2 days."
      }
    },
    "scene_before": {
      "world": {
        "name": "Caerness",
        "day": 0,
        "campaign": "Demo Campaign"
      },
      "player": {
        "actor_id": 5,
        "name": "[DEMO] Player Wanderer",
        "actor_type": "character",
        "subtype": "Long Road wanderer",
        "goals": [],
        "pressures": [],
        "resources": [],
        "relationships": []
      },
      "location": {
        "id": 6,
        "name": "Toll's Reach",
        "kind": "free city",
        "political_owner": null,
        "notes": null
      },
      "present_actors": [
        {
          "id": 1,
          "name": "[DEMO] River Lantern Escort Company",
          "actor_type": "institution",
          "subtype": "escort company",
          "status": "active"
        }
      ],
      "known_events": [],
      "known_rumours": [],
      "beliefs": [],
      "pending_player_interactions": [],
      "embodiment": {
        "profile": {
          "actor_id": 5,
          "actor_name": "[DEMO] Player Wanderer",
          "subtype": "Long Road wanderer",
          "voice": {
            "register": "natural",
            "verbosity": "contextual",
            "directness": "contextual"
          },
          "temperament": {},
          "values": {},
          "habits": {},
          "social": {
            "formality": "contextual",
            "social_confidence": "unknown"
          },
          "relationship_style": {},
          "expression_policy": {
            "autonomous_expression_min_confidence": 0.8,
            "ask_below_confidence": 0.7,
            "max_autonomous_stakes": 2,
            "allow_low_stakes_expression": true,
            "major_commitments_require_player": true,
            "avoid_caricature": true,
            "prefer_small_expression_over_irreversible_action": true
          },
          "current_state": {},
          "development": {
            "behavioral_inertia": true,
            "change_requires_evidence": true
          },
          "source_kind": "campaign",
          "updated_day": 0,
          "notes": null,
          "recent_expressions": []
        },
        "present_relationship_context": [],
        "current_player_wording": "I wait here for 2 days.",
        "rendering_rules": [
          "Treat player wording as intent/content/tone unless the player explicitly marks exact dialogue.",
          "Render speech through the protagonist's established voice, culture, status, competence, relationship, and current state.",
          "Do not infer simplicity, bluntness, awkwardness, or eloquence merely from the player's typing style.",
          "The protagonist remains a character between direct commands; small consistent gestures or habitual expression may be inferred.",
          "Do not infer major irreversible commitments, betrayals, oaths, marriage choices, declarations of war, executions, permanent allegiances, or life-changing disclosures.",
          "Prefer small expressive behavior over consequential autonomous decisions.",
          "Established personality creates expectations, not caricature. Context and relationships can produce exceptions.",
          "Do not invent hidden self-knowledge or major internal commitments for the player character."
        ]
      },
      "attention_cues": [],
      "competence_outcomes": [],
      "professional_context": {
        "relevant_domains": [],
        "all_domains": [],
        "rules": [
          "Character expertise may interpret accessible evidence but may not reveal hidden world state.",
          "Separate direct observation, reports, professional inference, advisor judgment, and player choice.",
          "Higher competence deepens interpretation; it never makes the character omniscient.",
          "Surface material uncertainty and missing evidence rather than inventing certainty.",
          "Offer actionable professional options when the character has enough competence to frame them.",
          "Do not silently override a deliberate player decision merely because the character is expert."
        ]
      },
      "health_context": {
        "aging_phase": "prime",
        "longevity_class": "ordinary",
        "functional_capacity": 100.0,
        "recovery_capacity": 100.0,
        "stamina_capacity": 100.0,
        "mobility": 100.0,
        "pain_burden": 0.0,
        "conditions": [],
        "disabilities": [],
        "rule": "Health changes capacity and trajectory; it does not toggle characters between combat-ready and dead."
      },
      "religious_context": {
        "affiliations": [],
        "obligations": [],
        "local_religious_institutions": [],
        "upcoming_observances": [],
        "guardrails": [
          "religion_is_lived_social_reality_not_a_faction_alignment",
          "no_unwritten_feast_day_or_doctrine_becomes_canon_automatically",
          "hearth_rites_vigil_and_other_practices_may_overlap_socially",
          "true_faith_exact_historical_furniture_remains_author_signoff_pending"
        ]
      },
      "cultural_context": {
        "local_cultural_institutions": [],
        "upcoming_programs": [],
        "guardrails": [
          "culture_has_inherited_depth_before_player_arrival",
          "cultural_institutions_have_agendas_not_player_service"
        ]
      },
      "environment_context": {
        "profile": null,
        "effects": {
          "travel_factor": 1.0,
          "production_factor": 1.0,
          "health_pressure": 0.0,
          "current_replenishment_factor": 1.0,
          "route_risk_delta": 0.0,
          "season_name": null
        },
        "current": {
          "capacity": 0.0,
          "load": 0.0,
          "available": 0.0,
          "load_ratio": 0.0
        },
        "routes": []
      },
      "political_context": {
        "polities": 0,
        "dissolved_polities": 0,
        "territories": 0,
        "active_claims": 0,
        "active_links": 0,
        "succession_crises": 0,
        "history_entries": 0,
        "principle": "Political maps are campaign state: they may expand, contract, split, federate, or disappear without protagonist protection."
      },
      "education_context": {
        "enrollments": [],
        "teachers": [],
        "certifications": [],
        "transmission_lines": [],
        "knowledge_access": []
      },
      "matters": {
        "intentions": [],
        "obligations": []
      },
      "canon": [
        {
          "chunk_id": 340,
          "heading": "Part Twenty — Hearth Geography, Cities, and Travel > Travel times",
          "text": "Travel times\nQinggong changes travel without making roads, horses, inns and rivers obsolete. Cultivators can sustain bursts of exceptional speed, difficult terrain movement and long efficient days; they do not sprint at combat acceleration from city to city without rest. The following times are working route calibrations under ordinary conditions.\nRoute | Caravan / ordinary road | Courier / fast mounted | Cultivated light travel\nAldergate → Cairnholt | 4–6 days | 2–3 days | ~2 days\nCairnholt → Waymeet | 2–3 days | 1–2 days | ~1 day\nWaymeet → Amber Court | 2–3 days | ~1 day | under 1–2 days\nCairnholt → White Laurel foothills | 4–6 days | 2–3 days | ~2 days + ascent\nCairnholt → Aldenmoor | 5–7 days | ~3 days | 2–3 days\nCairnholt → Lysmere | 5–7 days | 3–4 days | 2–3 days\nCairnholt → northern Fellmarch | 6–9 days | 3–5 days | 3–4 days\nCairnholt → Toll’s Reach | 12–16 days | 6–9 days | ~5–7 days\nToll’s Reach → Saltmere | 4–7 days by road; often ship | — | ~2–4 days light travel / fast passage\nCairnholt → Grand Coven | 10–14 days | 6–8 days | 5–6 days\nCairnholt → Silent Peak outer approach | 8–12 days + mountain | 4–6 days + ascent | faster approach, but ascent and local terrain remain decisive\nWeather, injury, baggage, border inspection, ferries, river levels, company size and road condition can move these numbers substantially. The point is relative scale: the Hearth is large enough that institutions do not all sit within a morning’s ride, but connected enough for circuits, politics and repeated travel to function.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 526,
          "heading": "Part Twenty-Four — The Living Registry and Simulation Anchors > The Long Road seed population > Breach-stage Road figures",
          "text": "Breach-stage Road figures\nName | Age | Stage | Role / training provenance\nSenna Vosk | 39 | Breach | Famous independent who repeatedly refused institutional recruitment.\nJoss Fenner | 46 | Breach | Reliable bounty and contract professional.\nCaleb North | 43 | Breach | Challenge-circuit regular.\nGordon Gage | 48 | Breach | Former free-company officer.\nNolan Drake | 41 | Breach | Saber fighter on central and southern roads.\nEzra Baines | 44 | Breach | Travelling instructor.\nLeon Pace | 42 | Breach | Contract fighter with merchant ties.\nQuentin Dale | 45 | Breach | Waymeet regular and formal challenger.\nMoira Stone | 40 | Breach | Strong eastern-Hearth wanderer.\nLester Kersey | 39 | Breach | Former household disciple, now Road-aligned.\nFreya Bellamy | 37 | Breach | Southern Road fighter with rising reputation.\nTheo Barr | 43 | Breach | Former company lieutenant.\nCassian Groves | 35 | Breach | Young Breach attracting attention.\nEthan Vale | 49 | Breach | Late-reaching master still improving.\nDora Whitlock | 46 | Breach | Escort captain with working reputation.\nAvery Clarke | 38 | Breach | Former household disciple.\nSimeon Mays | 52 | Breach | Mature steady fighter.\nSabine Kells | 36 | Breach | Younger eastern-circuit wanderer.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 525,
          "heading": "Part Twenty-Four — The Living Registry and Simulation Anchors > The Long Road seed population > Summit and Fifth-stage Road figures",
          "text": "Summit and Fifth-stage Road figures\nName | Age | Stage | Role / training provenance\nBarrow | 78 | Sixth | Born Corren Rannick; former clan heir, now famous Long Roader.\nMarek Cole | 90 | Sixth | Veteran contract and bounty-circuit master.\nHalric Sten | 97 | Sixth | Old independent master.\nGalen Thorpe | 85 | Sixth | Famous wandering master.\nVera Morrow | 102 | Sixth | Elder wandering sword master.\nRufus Crane | 111 | Sixth | Old hermit-like Road figure.\nBlake Merrin | 34 | Sixth | Historical freak; Sixth at thirty-four.\nPetra Wilde | 79 | Fifth | Reclusive senior wanderer.\nFelix Ward | 62 | Fifth | Veteran spear fighter and challenge master.\nBruno Webb | 64 | Fifth | Free-company captain and master.\nJulian Beck | 58 | Fifth | Former institutional disciple.\nHugo Kent | 60 | Fifth | Senior escort and caravan-route master.\nColin Blythe | 55 | Fifth | Highly respected independent duelist.\nStefan Lowe | 57 | Fifth | Wandering teacher.\nAda March | 53 | Fifth | Veteran western-road fighter.\nRafe Larkin | 59 | Fifth | Former mercenary captain.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 527,
          "heading": "Part Twenty-Four — The Living Registry and Simulation Anchors > The Long Road seed population > Third-stage Road figures",
          "text": "Third-stage Road figures\nName | Age | Stage | Role / training provenance\nCedric Nash | 34 | Third | Waymeet-known working duelist.\nSamuel Ford | 39 | Third | Escort specialist.\nJasper Hill | 27 | Third | Fast-developing challenge regular.\nRoman Wood | 36 | Third | Travelling teacher with small circle.\nArthur Dean | 40 | Third | Former retainer.\nLevi Brook | 32 | Third | River-route wanderer.\nGideon Ross | 37 | Third | Bounty fighter.\nIris Keene | 28 | Third | Young independent duelist.\nEliza Rowe | 31 | Third | Escort fighter and company hand.\nNina Fox | 29 | Third | Talked-about Toll’s Reach fighter.\nCormac Dyer | 33 | Third | Self-made with irregular training history.\nPhoebe Oakley | 23 | Third | Genuine Road prodigy.\nBram Foster | 42 | Third | Competent veteran.\nLyle Benton | 35 | Third | Former minor-sect disciple.\nMorgan Heath | 38 | Third | Company fighter and instructor.\nWes Glover | 30 | Third | Solid Road professional.\nPerry Sloan | 41 | Third | Mature travelling swordsman.\nJoel Harland | 26 | Third | Young practitioner drawing attention.\nGemma Moran | 34 | Third | Western escort master.\nKieran Foyle | 29 | Third | Ambitious challenge fighter.\nDexter Hall | 44 | Third | Older Third with strong combat reputation.\nMabel Keen | 36 | Third | Travelling healer-fighter.\nBrennan Hodge | 31 | Third | Former clan retainer.\nRupert Snow | 39 | Third | Experienced mercenary, likely command path.\nElsa Vardon | 30 | Third | Young master and travelling teacher.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 428,
          "heading": "Part Twenty-Two — The Underworld and Vice > Hearth underworld geography > Toll’s Reach",
          "text": "Toll’s Reach\nToll’s Reach has the broadest visible overlap between legitimate nightlife and the underworld: dock taverns, foreign sailors, mercenaries, cheap brothels, expensive houses, gaming rooms, auction visitors, smugglers, performers, fences, killers, illicit cargo and transient martial people. The Red Yard, warehouse districts, River and Sea Quays, and auction economy constantly bring strangers with money into proximity with people who know how to separate them from it.\nGreyhook and the Cormorants fit naturally here, but neither owns the city. Toll’s Reach should remain the place where dozens of specialist networks intersect because the port is useful, not because one criminal superstructure controls all vice.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 70,
          "heading": "Part Three — The Hearth and the Churn > The Four Currents and the Long Road",
          "text": "The Four Currents and the Long Road\nThe two-axis model. The Four Currents are exhaustive as a person’s present Churn position, and the Long Road is a second, independent axis describing how some martial artists live. Current answers where you stand in the Churn’s institutional and social order, Concord, Undertow, Unsworn, or Hollow; the Long Road answers how you live, and it can overlap any Current. So “independent” or “Long Road” is not a fifth Current. Every Churn martial artist has, socially, a Current position, and separately may or may not be of the Road. A Grey Bell tournament traveller is Concord and Long Road; a Kellbrook wanderer is Undertow and Long Road; a Grand Coven emissary who spends years moving between cities is Hollow and Long Road; a settled Rannick fighter is simply Undertow. Where a registry lists a person under “Long Road,” it is grouping them by their most relevant sphere for simulation, not giving a complete taxonomy: Barrow, having left Rannick and become genuinely independent, is Unsworn in Current position and Long Road in way of life. A person may spend a season or a lifetime on the Road without ceasing to belong to their clan or sect, or, if they belong to none, without ceasing to be Unsworn.",
          "source": "world_bible_current.docx"
        }
      ],
      "request": "I wait here for 2 days.",
      "camera_principle": "The player is the story's camera focus, not the world's protagonist or causal center.",
      "narrator_rules": [
        "The player is the camera focus, not the world's causal center.",
        "Narrate only from the player's accessible knowledge plus retrieved canon.",
        "Treat rumours as beliefs, not verified truth, unless the same fact is separately known.",
        "Use the beliefs envelope as actor-relative claims grounded in accessible evidence; confidence is not objective truth, and hidden authoritative truth links are not exposed here.",
        "Do not reveal other actors' hidden goals, pressures, drives, resources, or private relationships.",
        "Do not invent permanent state changes in prose; resolve them through the simulation/state layer first.",
        "The wider world continues moving off-screen at the resolution appropriate to each actor's tier.",
        "Do not make unrelated actors or events converge on the player simply because the player is present.",
        "Local people should visibly have agendas, work, relationships and routines that do not exist for the player's benefit.",
        "The Character Competence Layer handles obvious follow-through. Do not make the player restate routine actions already resolved by competence_outcomes.",
        "Use professional_context to mediate expertise: interpret accessible evidence at the character's domain level, distinguish observation from inference, and never reveal hidden world state.",
        "Character professional reading, reports, advisor judgment, and player choice are separate layers; do not merge an advisor's opinion into objective truth or the protagonist's own expertise.",
        "Use health_context as authoritative capacity state. Injury, illness, aging and disability constrain what the character can sustain without dictating their choices or personality.",
        "Use religious_context as lived social context. Do not infer private belief from faction, office, ancestry, or public observance, and do not invent feast days or doctrine not already established in campaign state or retrieved canon.",
        "Use cultural_context for local institutions and scheduled public cultural life. Cultural institutions exist for their own continuity, patrons and audiences rather than to generate content for the player.",
        "Use environment_context for current route, season, production, exposure, and local-current constraints. Do not invent weather events, route closures, or seasonal customs that are not in campaign state or canon.",
        "Use political_context as authoritative macro-state. Do not preserve states, borders, rulers, or alliances merely because they were important at campaign start, and do not invent political transformations that have not been resolved by the simulation.",
        "Use education_context as authoritative training and transmission state. Access to a manual is not mastery; teachers, time, competence gates, and living transmission matter. Do not invent completed training, certifications, or master-disciple bonds that the engine has not resolved.",
        "Do not end with generic game prompts such as 'What do you do?' or 'What happens next?'. End naturally at the agency handoff.",
        "A narration response may span multiple scenes, transitions, or days if no meaningful player intervention was required in between.",
        "Use the embodiment packet to keep the protagonist consistent between direct commands.",
        "Player wording is intent/content/tone unless explicitly marked as exact dialogue.",
        "Small low-stakes expression may be inferred when strongly supported; major commitments always return to player agency.",
        "Do not turn persistent personality into caricature or invent major hidden self-knowledge for the player character."
      ],
      "scene_packet_id": 1
    },
    "scene_after": {
      "world": {
        "name": "Caerness",
        "day": 2,
        "campaign": "Demo Campaign"
      },
      "player": {
        "actor_id": 5,
        "name": "[DEMO] Player Wanderer",
        "actor_type": "character",
        "subtype": "Long Road wanderer",
        "goals": [],
        "pressures": [],
        "resources": [],
        "relationships": []
      },
      "location": {
        "id": 6,
        "name": "Toll's Reach",
        "kind": "free city",
        "political_owner": null,
        "notes": null
      },
      "present_actors": [
        {
          "id": 1,
          "name": "[DEMO] River Lantern Escort Company",
          "actor_type": "institution",
          "subtype": "escort company",
          "status": "active"
        }
      ],
      "known_events": [],
      "known_rumours": [],
      "beliefs": [],
      "pending_player_interactions": [],
      "embodiment": {
        "profile": {
          "actor_id": 5,
          "actor_name": "[DEMO] Player Wanderer",
          "subtype": "Long Road wanderer",
          "voice": {
            "register": "natural",
            "verbosity": "contextual",
            "directness": "contextual"
          },
          "temperament": {},
          "values": {},
          "habits": {},
          "social": {
            "formality": "contextual",
            "social_confidence": "unknown"
          },
          "relationship_style": {},
          "expression_policy": {
            "autonomous_expression_min_confidence": 0.8,
            "ask_below_confidence": 0.7,
            "max_autonomous_stakes": 2,
            "allow_low_stakes_expression": true,
            "major_commitments_require_player": true,
            "avoid_caricature": true,
            "prefer_small_expression_over_irreversible_action": true
          },
          "current_state": {},
          "development": {
            "behavioral_inertia": true,
            "change_requires_evidence": true
          },
          "source_kind": "campaign",
          "updated_day": 0,
          "notes": null,
          "recent_expressions": []
        },
        "present_relationship_context": [],
        "current_player_wording": "I wait here for 2 days.",
        "rendering_rules": [
          "Treat player wording as intent/content/tone unless the player explicitly marks exact dialogue.",
          "Render speech through the protagonist's established voice, culture, status, competence, relationship, and current state.",
          "Do not infer simplicity, bluntness, awkwardness, or eloquence merely from the player's typing style.",
          "The protagonist remains a character between direct commands; small consistent gestures or habitual expression may be inferred.",
          "Do not infer major irreversible commitments, betrayals, oaths, marriage choices, declarations of war, executions, permanent allegiances, or life-changing disclosures.",
          "Prefer small expressive behavior over consequential autonomous decisions.",
          "Established personality creates expectations, not caricature. Context and relationships can produce exceptions.",
          "Do not invent hidden self-knowledge or major internal commitments for the player character."
        ]
      },
      "attention_cues": [],
      "competence_outcomes": [],
      "professional_context": {
        "relevant_domains": [],
        "all_domains": [],
        "rules": [
          "Character expertise may interpret accessible evidence but may not reveal hidden world state.",
          "Separate direct observation, reports, professional inference, advisor judgment, and player choice.",
          "Higher competence deepens interpretation; it never makes the character omniscient.",
          "Surface material uncertainty and missing evidence rather than inventing certainty.",
          "Offer actionable professional options when the character has enough competence to frame them.",
          "Do not silently override a deliberate player decision merely because the character is expert."
        ]
      },
      "health_context": {
        "aging_phase": "prime",
        "longevity_class": "ordinary",
        "functional_capacity": 100.0,
        "recovery_capacity": 100.0,
        "stamina_capacity": 100.0,
        "mobility": 100.0,
        "pain_burden": 0.0,
        "conditions": [],
        "disabilities": [],
        "rule": "Health changes capacity and trajectory; it does not toggle characters between combat-ready and dead."
      },
      "religious_context": {
        "affiliations": [],
        "obligations": [],
        "local_religious_institutions": [],
        "upcoming_observances": [],
        "guardrails": [
          "religion_is_lived_social_reality_not_a_faction_alignment",
          "no_unwritten_feast_day_or_doctrine_becomes_canon_automatically",
          "hearth_rites_vigil_and_other_practices_may_overlap_socially",
          "true_faith_exact_historical_furniture_remains_author_signoff_pending"
        ]
      },
      "cultural_context": {
        "local_cultural_institutions": [],
        "upcoming_programs": [],
        "guardrails": [
          "culture_has_inherited_depth_before_player_arrival",
          "cultural_institutions_have_agendas_not_player_service"
        ]
      },
      "environment_context": {
        "profile": null,
        "effects": {
          "travel_factor": 1.0,
          "production_factor": 1.0,
          "health_pressure": 0.0,
          "current_replenishment_factor": 1.0,
          "route_risk_delta": 0.0,
          "season_name": null
        },
        "current": {
          "capacity": 0.0,
          "load": 0.0,
          "available": 0.0,
          "load_ratio": 0.0
        },
        "routes": []
      },
      "political_context": {
        "polities": 0,
        "dissolved_polities": 0,
        "territories": 0,
        "active_claims": 0,
        "active_links": 0,
        "succession_crises": 0,
        "history_entries": 0,
        "principle": "Political maps are campaign state: they may expand, contract, split, federate, or disappear without protagonist protection."
      },
      "education_context": {
        "enrollments": [],
        "teachers": [],
        "certifications": [],
        "transmission_lines": [],
        "knowledge_access": []
      },
      "matters": {
        "intentions": [],
        "obligations": []
      },
      "canon": [
        {
          "chunk_id": 340,
          "heading": "Part Twenty — Hearth Geography, Cities, and Travel > Travel times",
          "text": "Travel times\nQinggong changes travel without making roads, horses, inns and rivers obsolete. Cultivators can sustain bursts of exceptional speed, difficult terrain movement and long efficient days; they do not sprint at combat acceleration from city to city without rest. The following times are working route calibrations under ordinary conditions.\nRoute | Caravan / ordinary road | Courier / fast mounted | Cultivated light travel\nAldergate → Cairnholt | 4–6 days | 2–3 days | ~2 days\nCairnholt → Waymeet | 2–3 days | 1–2 days | ~1 day\nWaymeet → Amber Court | 2–3 days | ~1 day | under 1–2 days\nCairnholt → White Laurel foothills | 4–6 days | 2–3 days | ~2 days + ascent\nCairnholt → Aldenmoor | 5–7 days | ~3 days | 2–3 days\nCairnholt → Lysmere | 5–7 days | 3–4 days | 2–3 days\nCairnholt → northern Fellmarch | 6–9 days | 3–5 days | 3–4 days\nCairnholt → Toll’s Reach | 12–16 days | 6–9 days | ~5–7 days\nToll’s Reach → Saltmere | 4–7 days by road; often ship | — | ~2–4 days light travel / fast passage\nCairnholt → Grand Coven | 10–14 days | 6–8 days | 5–6 days\nCairnholt → Silent Peak outer approach | 8–12 days + mountain | 4–6 days + ascent | faster approach, but ascent and local terrain remain decisive\nWeather, injury, baggage, border inspection, ferries, river levels, company size and road condition can move these numbers substantially. The point is relative scale: the Hearth is large enough that institutions do not all sit within a morning’s ride, but connected enough for circuits, politics and repeated travel to function.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 526,
          "heading": "Part Twenty-Four — The Living Registry and Simulation Anchors > The Long Road seed population > Breach-stage Road figures",
          "text": "Breach-stage Road figures\nName | Age | Stage | Role / training provenance\nSenna Vosk | 39 | Breach | Famous independent who repeatedly refused institutional recruitment.\nJoss Fenner | 46 | Breach | Reliable bounty and contract professional.\nCaleb North | 43 | Breach | Challenge-circuit regular.\nGordon Gage | 48 | Breach | Former free-company officer.\nNolan Drake | 41 | Breach | Saber fighter on central and southern roads.\nEzra Baines | 44 | Breach | Travelling instructor.\nLeon Pace | 42 | Breach | Contract fighter with merchant ties.\nQuentin Dale | 45 | Breach | Waymeet regular and formal challenger.\nMoira Stone | 40 | Breach | Strong eastern-Hearth wanderer.\nLester Kersey | 39 | Breach | Former household disciple, now Road-aligned.\nFreya Bellamy | 37 | Breach | Southern Road fighter with rising reputation.\nTheo Barr | 43 | Breach | Former company lieutenant.\nCassian Groves | 35 | Breach | Young Breach attracting attention.\nEthan Vale | 49 | Breach | Late-reaching master still improving.\nDora Whitlock | 46 | Breach | Escort captain with working reputation.\nAvery Clarke | 38 | Breach | Former household disciple.\nSimeon Mays | 52 | Breach | Mature steady fighter.\nSabine Kells | 36 | Breach | Younger eastern-circuit wanderer.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 525,
          "heading": "Part Twenty-Four — The Living Registry and Simulation Anchors > The Long Road seed population > Summit and Fifth-stage Road figures",
          "text": "Summit and Fifth-stage Road figures\nName | Age | Stage | Role / training provenance\nBarrow | 78 | Sixth | Born Corren Rannick; former clan heir, now famous Long Roader.\nMarek Cole | 90 | Sixth | Veteran contract and bounty-circuit master.\nHalric Sten | 97 | Sixth | Old independent master.\nGalen Thorpe | 85 | Sixth | Famous wandering master.\nVera Morrow | 102 | Sixth | Elder wandering sword master.\nRufus Crane | 111 | Sixth | Old hermit-like Road figure.\nBlake Merrin | 34 | Sixth | Historical freak; Sixth at thirty-four.\nPetra Wilde | 79 | Fifth | Reclusive senior wanderer.\nFelix Ward | 62 | Fifth | Veteran spear fighter and challenge master.\nBruno Webb | 64 | Fifth | Free-company captain and master.\nJulian Beck | 58 | Fifth | Former institutional disciple.\nHugo Kent | 60 | Fifth | Senior escort and caravan-route master.\nColin Blythe | 55 | Fifth | Highly respected independent duelist.\nStefan Lowe | 57 | Fifth | Wandering teacher.\nAda March | 53 | Fifth | Veteran western-road fighter.\nRafe Larkin | 59 | Fifth | Former mercenary captain.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 527,
          "heading": "Part Twenty-Four — The Living Registry and Simulation Anchors > The Long Road seed population > Third-stage Road figures",
          "text": "Third-stage Road figures\nName | Age | Stage | Role / training provenance\nCedric Nash | 34 | Third | Waymeet-known working duelist.\nSamuel Ford | 39 | Third | Escort specialist.\nJasper Hill | 27 | Third | Fast-developing challenge regular.\nRoman Wood | 36 | Third | Travelling teacher with small circle.\nArthur Dean | 40 | Third | Former retainer.\nLevi Brook | 32 | Third | River-route wanderer.\nGideon Ross | 37 | Third | Bounty fighter.\nIris Keene | 28 | Third | Young independent duelist.\nEliza Rowe | 31 | Third | Escort fighter and company hand.\nNina Fox | 29 | Third | Talked-about Toll’s Reach fighter.\nCormac Dyer | 33 | Third | Self-made with irregular training history.\nPhoebe Oakley | 23 | Third | Genuine Road prodigy.\nBram Foster | 42 | Third | Competent veteran.\nLyle Benton | 35 | Third | Former minor-sect disciple.\nMorgan Heath | 38 | Third | Company fighter and instructor.\nWes Glover | 30 | Third | Solid Road professional.\nPerry Sloan | 41 | Third | Mature travelling swordsman.\nJoel Harland | 26 | Third | Young practitioner drawing attention.\nGemma Moran | 34 | Third | Western escort master.\nKieran Foyle | 29 | Third | Ambitious challenge fighter.\nDexter Hall | 44 | Third | Older Third with strong combat reputation.\nMabel Keen | 36 | Third | Travelling healer-fighter.\nBrennan Hodge | 31 | Third | Former clan retainer.\nRupert Snow | 39 | Third | Experienced mercenary, likely command path.\nElsa Vardon | 30 | Third | Young master and travelling teacher.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 428,
          "heading": "Part Twenty-Two — The Underworld and Vice > Hearth underworld geography > Toll’s Reach",
          "text": "Toll’s Reach\nToll’s Reach has the broadest visible overlap between legitimate nightlife and the underworld: dock taverns, foreign sailors, mercenaries, cheap brothels, expensive houses, gaming rooms, auction visitors, smugglers, performers, fences, killers, illicit cargo and transient martial people. The Red Yard, warehouse districts, River and Sea Quays, and auction economy constantly bring strangers with money into proximity with people who know how to separate them from it.\nGreyhook and the Cormorants fit naturally here, but neither owns the city. Toll’s Reach should remain the place where dozens of specialist networks intersect because the port is useful, not because one criminal superstructure controls all vice.",
          "source": "world_bible_current.docx"
        },
        {
          "chunk_id": 70,
          "heading": "Part Three — The Hearth and the Churn > The Four Currents and the Long Road",
          "text": "The Four Currents and the Long Road\nThe two-axis model. The Four Currents are exhaustive as a person’s present Churn position, and the Long Road is a second, independent axis describing how some martial artists live. Current answers where you stand in the Churn’s institutional and social order, Concord, Undertow, Unsworn, or Hollow; the Long Road answers how you live, and it can overlap any Current. So “independent” or “Long Road” is not a fifth Current. Every Churn martial artist has, socially, a Current position, and separately may or may not be of the Road. A Grey Bell tournament traveller is Concord and Long Road; a Kellbrook wanderer is Undertow and Long Road; a Grand Coven emissary who spends years moving between cities is Hollow and Long Road; a settled Rannick fighter is simply Undertow. Where a registry lists a person under “Long Road,” it is grouping them by their most relevant sphere for simulation, not giving a complete taxonomy: Barrow, having left Rannick and become genuinely independent, is Unsworn in Current position and Long Road in way of life. A person may spend a season or a lifetime on the Road without ceasing to belong to their clan or sect, or, if they belong to none, without ceasing to be Unsworn.",
          "source": "world_bible_current.docx"
        }
      ],
      "request": "I wait here for 2 days.",
      "camera_principle": "The player is the story's camera focus, not the world's protagonist or causal center.",
      "narrator_rules": [
        "The player is the camera focus, not the world's causal center.",
        "Narrate only from the player's accessible knowledge plus retrieved canon.",
        "Treat rumours as beliefs, not verified truth, unless the same fact is separately known.",
        "Use the beliefs envelope as actor-relative claims grounded in accessible evidence; confidence is not objective truth, and hidden authoritative truth links are not exposed here.",
        "Do not reveal other actors' hidden goals, pressures, drives, resources, or private relationships.",
        "Do not invent permanent state changes in prose; resolve them through the simulation/state layer first.",
        "The wider world continues moving off-screen at the resolution appropriate to each actor's tier.",
        "Do not make unrelated actors or events converge on the player simply because the player is present.",
        "Local people should visibly have agendas, work, relationships and routines that do not exist for the player's benefit.",
        "The Character Competence Layer handles obvious follow-through. Do not make the player restate routine actions already resolved by competence_outcomes.",
        "Use professional_context to mediate expertise: interpret accessible evidence at the character's domain level, distinguish observation from inference, and never reveal hidden world state.",
        "Character professional reading, reports, advisor judgment, and player choice are separate layers; do not merge an advisor's opinion into objective truth or the protagonist's own expertise.",
        "Use health_context as authoritative capacity state. Injury, illness, aging and disability constrain what the character can sustain without dictating their choices or personality.",
        "Use religious_context as lived social context. Do not infer private belief from faction, office, ancestry, or public observance, and do not invent feast days or doctrine not already established in campaign state or retrieved canon.",
        "Use cultural_context for local institutions and scheduled public cultural life. Cultural institutions exist for their own continuity, patrons and audiences rather than to generate content for the player.",
        "Use environment_context for current route, season, production, exposure, and local-current constraints. Do not invent weather events, route closures, or seasonal customs that are not in campaign state or canon.",
        "Use political_context as authoritative macro-state. Do not preserve states, borders, rulers, or alliances merely because they were important at campaign start, and do not invent political transformations that have not been resolved by the simulation.",
        "Use education_context as authoritative training and transmission state. Access to a manual is not mastery; teachers, time, competence gates, and living transmission matter. Do not invent completed training, certifications, or master-disciple bonds that the engine has not resolved.",
        "Do not end with generic game prompts such as 'What do you do?' or 'What happens next?'. End naturally at the agency handoff.",
        "A narration response may span multiple scenes, transitions, or days if no meaningful player intervention was required in between.",
        "Use the embodiment packet to keep the protagonist consistent between direct commands.",
        "Player wording is intent/content/tone unless explicitly marked as exact dialogue.",
        "Small low-stakes expression may be inferred when strongly supported; major commitments always return to player agency.",
        "Do not turn persistent personality into caricature or invent major hidden self-knowledge for the player character."
      ],
      "scene_packet_id": 2
    },
    "protagonist_embodiment": {
      "profile": {
        "actor_id": 5,
        "actor_name": "[DEMO] Player Wanderer",
        "subtype": "Long Road wanderer",
        "voice": {
          "register": "natural",
          "verbosity": "contextual",
          "directness": "contextual"
        },
        "temperament": {},
        "values": {},
        "habits": {},
        "social": {
          "formality": "contextual",
          "social_confidence": "unknown"
        },
        "relationship_style": {},
        "expression_policy": {
          "autonomous_expression_min_confidence": 0.8,
          "ask_below_confidence": 0.7,
          "max_autonomous_stakes": 2,
          "allow_low_stakes_expression": true,
          "major_commitments_require_player": true,
          "avoid_caricature": true,
          "prefer_small_expression_over_irreversible_action": true
        },
        "current_state": {},
        "development": {
          "behavioral_inertia": true,
          "change_requires_evidence": true
        },
        "source_kind": "campaign",
        "updated_day": 0,
        "notes": null,
        "recent_expressions": []
      },
      "present_relationship_context": [],
      "current_player_wording": "I wait here for 2 days.",
      "rendering_rules": [
        "Treat player wording as intent/content/tone unless the player explicitly marks exact dialogue.",
        "Render speech through the protagonist's established voice, culture, status, competence, relationship, and current state.",
        "Do not infer simplicity, bluntness, awkwardness, or eloquence merely from the player's typing style.",
        "The protagonist remains a character between direct commands; small consistent gestures or habitual expression may be inferred.",
        "Do not infer major irreversible commitments, betrayals, oaths, marriage choices, declarations of war, executions, permanent allegiances, or life-changing disclosures.",
        "Prefer small expressive behavior over consequential autonomous decisions.",
        "Established personality creates expectations, not caricature. Context and relationships can produce exceptions.",
        "Do not invent hidden self-knowledge or major internal commitments for the player character."
      ]
    },
    "professional_context": {
      "relevant_domains": [],
      "all_domains": [],
      "rules": [
        "Character expertise may interpret accessible evidence but may not reveal hidden world state.",
        "Separate direct observation, reports, professional inference, advisor judgment, and player choice.",
        "Higher competence deepens interpretation; it never makes the character omniscient.",
        "Surface material uncertainty and missing evidence rather than inventing certainty.",
        "Offer actionable professional options when the character has enough competence to frame them.",
        "Do not silently override a deliberate player decision merely because the character is expert."
      ]
    },
    "agency_handoff": {
      "handoff_type": "none",
      "reason": "No unresolved meaningful choice or sufficiently rich intervention opportunity has appeared yet.",
      "richness_score": 10.0,
      "can_auto_continue": true
    },
    "segment_outline": [
      {
        "kind": "downtime",
        "beat": "ordinary passage of time and character routine",
        "weight": 0.45
      },
      {
        "kind": "aftermath",
        "beat": "only consequences or information that actually became accessible",
        "weight": 0.35
      },
      {
        "kind": "scene",
        "beat": "the present moment after the elapsed time",
        "weight": 0.2
      }
    ],
    "narration_rules": [
      "The player is the camera focus, not the world's causal center.",
      "Narrate only information available in scene_after plus the explicit resolved player action.",
      "Do not reveal off-screen events merely because the engine simulated them.",
      "Do not make NPCs care about the player unless persisted relationships, goals, events, or direct circumstances justify it.",
      "Do not create permanent state in prose. The database has already decided what changed.",
      "Allow evidence of a world already in motion: arrivals, departures, rumours, business, feuds, consequences, and unrelated agendas.",
      "Do not frame unrelated world events as foreshadowing for the player unless state actually connects them.",
      "Character competence has already handled obvious follow-through. Do not ask the player to repeat routine actions.",
      "Use professional_context to express what the protagonist can professionally infer from accessible evidence; expertise does not grant omniscience.",
      "Keep character professional reading distinct from reports, advisor opinions, and the player's final decision.",
      "The prose may span multiple scenes, transitions, or days when no unresolved agency point exists between them.",
      "Never end with generic prompts such as 'What do you do?', 'What happens next?', or a forced menu of choices.",
      "When a handoff exists, end naturally in the situation itself; the persistent input field signals that the player may act.",
      "Do not manufacture a request or question from an NPC merely to justify returning control.",
      "Keep the protagonist's voice and incidental behavior consistent with protagonist_embodiment.",
      "Treat the player's wording as intent/content/tone unless they explicitly request exact dialogue.",
      "Do not autonomously make major commitments for the protagonist; stop at the agency boundary instead."
    ]
  },
  "style": {
    "mode": "immersive, grounded, long-form when appropriate",
    "camera": "limited to player-accessible state",
    "world_rule": "Caerness is already alive; do not make the scene orbit the player unnecessarily",
    "handoff_rule": "Never end with 'What do you do?'. End naturally where player agency becomes useful.",
    "continuity_rule": "One response may cover several scenes or time transitions if no meaningful intervention point exists between them."
  }
}
```

## Required response contract
Return **one JSON object only**. No markdown fence and no text before or after it.
The engine is tolerant of fences if the chat UI adds them, but raw JSON is preferred.

```json
{
  "task_type": "narration",
  "request_id": 1,
  "narration": "player-facing prose only; no hidden-state exposition"
}
```

Do not add fields that try to directly mutate the database.