# Caerness Engine v0.22 — Ecology, Seasons, Travel & Environmental Pressure

v0.22 adds an authoritative environmental layer without silently inventing a fixed Caernessian calendar, road map, climate map, or weather history.

## Canon boundary

The current World Bible establishes that ambient current behaves environmentally, varying with geology, water, elevation, basins, caverns, long-stable terrain, and slow continental patterns. It also defines site properties such as density, stability, replenishment, breadth and concentration, and says valuable sites have carrying capacity and recover after heavy use. The engine therefore models those properties directly.

The World Bible also explicitly leaves a detailed Hearth travel map for later placement. v0.22 therefore seeds **no routes, seasons, route closures, weather events, or local climate labels**. These become campaign facts only when configured or crystallized.

## Location environments

`location_environment_profiles` persist per-location environmental state:

- climate label and terrain kind;
- configurable year length and calendar phase offset;
- baseline travel and production factors;
- health/exposure pressure;
- current density;
- current stability;
- current replenishment;
- current breadth;
- current concentration;
- current carrying capacity and current load.

No location receives a profile automatically.

## Seasons and temporary conditions

`seasonal_windows` are campaign-defined recurring environmental periods. They can alter travel, production, exposure pressure, current replenishment and route risk. Windows may wrap across the configured year boundary.

`environmental_conditions` are temporary pressures with start/end dates. They can represent any established local condition without forcing the engine to canonize its cause. Expired conditions stop affecting state automatically.

Seasonal and temporary modifiers affect actual simulation systems rather than only narration:

- ordinary production receives environmental production modifiers;
- market transport friction receives environmental transport pressure;
- travel duration and exposure depend on current route/environment state;
- local-current recovery depends on current replenishment conditions.

## Current ecology

`current_usage_events` record actual local use. Usage increases `current_load`; available carrying capacity is bounded at zero rather than going negative. Story-time reviews reduce load according to site carrying capacity, intrinsic replenishment and the active environmental replenishment factor.

This is a sustainability model, not a universal magical fuel meter. It does not grant capabilities a cultivator lacks.

## Routes and travel

`travel_routes` define campaign route geography between locations. Supported route grammar is deliberately broad: road, track, pass, river, sea, trail and other.

Routes persist:

- base travel time;
- capacity;
- reliability;
- seasonal sensitivity;
- directionality;
- open/restricted/closed/destroyed state.

`route_conditions` add temporary accessibility, delay and hazard pressure.

`find_route_path()` performs shortest-path selection using the currently traversable route graph and environmental costs. `travel_plans` resolve one segment at a time through authoritative story time. At each intermediate location the next route is recalculated, so a later closure can stall or reroute a traveller instead of being ignored.

Actors and households can travel. Household travel moves active members together. Travel arrival is an authoritative world event.

## Household migration integration

The v0.19 migration system previously moved a household directly to its destination on the planned day. v0.22 hardens this boundary:

- if crystallized route geography exists, scheduled household migration starts a real travel plan and remains `in_transit` until arrival;
- if relevant route geography exists but no traversable route currently exists, migration waits rather than teleporting through a closure;
- if the geography has not been crystallized at all, the older structural relocation path remains available so latent geography does not have to be invented merely to process a low-resolution migration.

This preserves the principle: **latent means undescribed, not nonexistent** while ensuring established geography constrains movement.

## Health boundary

Ecology can accumulate abstract travel exposure. Severe accumulated exposure may create a generic `Travel exposure` fatigue condition. v0.22 does not resolve that condition; the v0.20 health system remains the authoritative owner of recovery and bodily consequences.

## Player-facing context

Scene packets now include `environment_context`, containing established local environment, current sustainability and usable routes. Narration is explicitly told not to invent weather events, route closures or seasonal customs absent from campaign state or canon.

## Deliberate limits

v0.22 does not yet hard-code:

- named Caernessian seasons;
- a universal 360-day canon calendar;
- exact climate zones;
- daily stochastic weather;
- a fixed road/river map;
- crop calendars not already established in campaign state;
- arbitrary disasters for dramatic pacing.

The layer provides causal environmental machinery while leaving open setting material open.
