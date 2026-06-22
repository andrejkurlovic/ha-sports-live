# ha-sports-live backend audit (2026-06-22)

Same review methodology used for lovelace-bin-collection-card's BIN_CARD_AUDIT.md:
dead code, naming, duplication, architecture risk, test gaps. Scope constraint
for this codebase (unlike the bin card): **entity_id/unique_id/event names are
a hard contract** — dashboards and automations key off them. Fixes below only
touch internals.

## File sizes

| File | Lines | Role |
|---|---|---|
| sensor.py | 770 → 700 | entity setup, attribute computation, event dispatch |
| registry.py | 453 | per-sport ESPN URL/capability profiles |
| config_flow.py | 291 | multi-step setup + options flow |
| parsers/scoreboard.py | 415 | shared scoreboard/event parsing |
| coordinator.py | 186 | fetch orchestration |
| parsers/bracket.py | 248 | knockout bracket parsing |
| parsers/summary.py | 146 | summary endpoint parsing |
| parsers/standings.py | 142 | standings parsing |
| broadcast_rights.py | 97 | static UK channel lookups |
| const.py | 56 | constants |

## Fixed this pass

1. **Dead import** — `import random` in `sensor.py` (never called). Removed.
2. **Dead constants wired up, not deleted** — `OPT_SCAN_INTERVAL`/
   `OPT_RECENT_MATCH_HOURS` existed in `const.py` but `__init__.py`,
   `config_flow.py`, and `sensor.py` all used raw string literals instead.
   Now imported and used everywhere, matching the existing `CONF_*` convention.
3. **Dead instance variable** — `self._recent_match_hours` was computed in
   `__init__` but never read; `_process_update` recomputed
   `entry.options.get("recent_match_hours", 24)` from scratch in 4 places
   instead. Confirmed safe to use the cached value: `__init__.py` registers
   `entry.add_update_listener` → `async_reload_entry`, so an options change
   always recreates the entity with a fresh `__init__` anyway.
4. **Encapsulation** — `sensor.py` reached into `profile._news_url_tmpl` /
   `profile._team_schedule_url_tmpl` (leading-underscore dataclass fields
   belonging to `SportProfile`) instead of going through the class's own
   API. Added `has_news_url()` / `has_team_schedule_url()` to
   `sports/profile.py`; `sensor.py` now calls those.
5. **80 lines of triplicated logic** — `SENSOR_MATCHES`/`SENSOR_ALL_TODAY`,
   `SENSOR_SCHEDULE`, and `SENSOR_SCHEDULE_ALL` each ran the identical
   sequence (`process_scoreboard` → `enrich_matches_with_uk_broadcast` →
   `_describe_matches` → `_compute_all_matches_attrs` → assemble an
   attributes dict), differing only in which keys end up in the dict and
   whether the fetch is season-filtered. Extracted `_build_scoreboard_attrs()`
   taking explicit `include_league_info`/`include_team_info`/
   `include_competition_code`/`season_filtered` flags — each branch is now a
   3-line call. Verified the exact attribute key set per branch is
   byte-for-byte unchanged (see verification below).
6. **Redundant wrapper** — `_next_match_attrs()` just called
   `_compute_next_match_attrs()` with the same signature. Removed; the one
   call site now calls `_compute_next_match_attrs()` directly.

## Verification

No HA test harness is installed in this environment (`homeassistant` package
absent), and the existing test suite only covers `parsers/` and
`config_flow.py` (sensor/coordinator/event logic has zero test coverage —
flagged below as a gap, not fixed this pass). Verified the refactor directly:

- `python3 -m pytest tests/ -q` — 66/66 pass, unchanged.
- Isolated `_build_scoreboard_attrs()` against a bare instance (HA base
  classes stubbed, matching the existing test suite's stubbing pattern) for
  all three call shapes — confirmed key sets exactly match what the
  pre-refactor inline code produced:
  - `MATCHES`/`ALL_TODAY`: `league_info`, `matches`, `competition_code`,
    `sport`, + computed keys. No `team_name`/`team_logo`.
  - `SCHEDULE`: same plus `team_name`/`team_logo`.
  - `SCHEDULE_ALL`: `team_name`/`team_logo`/`matches`/`sport` + computed
    keys only — no `league_info`, no `competition_code` (this asymmetry is
    original behavior, preserved exactly).

## Deferred (flagged, not done this pass)

- **`sensor.py` still mixes concerns** (entity setup + event dispatch +
  attribute computation in one `SportsLiveSensor` class, ~700 lines).
  Splitting this into entity/dispatcher/builder layers is the highest-value
  remaining structural improvement, but carries real risk of subtly changing
  `__init__`/`async_added_to_hass` ordering or unique_id derivation — given
  the "entity_id/unique_id must stay stable" constraint, this needs its own
  careful pass with explicit before/after entity-id diffing, not bundled
  into a cleanup pass. Recommend doing this only if/when a feature actually
  requires touching that class anyway.
- **Event payload assembly still repeated 3×** (`_fire_score_event`,
  `_fire_discipline_event`, `_fire_finished_event` each rebuild a similar
  but not identical payload dict). Lower value than the scoreboard dedup —
  the three payloads differ in real, non-mechanical ways (score events
  source `home_score`/`away_score` from fresh post-increment ints passed as
  parameters, not `match.get(...)` like the other two), so unifying them
  risks introducing a subtle behavior change in event payload content that
  automations consume. Left alone.
- **Sport-hardcoded legacy event checks** (`if sport_id == "soccer"` in 3
  places in `sensor.py`) — not generalized. These only matter if a future
  sport needs a legacy event alias, which none currently do.
- **No tests for `sensor.py`/`coordinator.py`** — would need a
  `pytest-homeassistant-custom-component`-style harness (not present).
  Flagged for a future pass; out of scope for an internals-only cleanup.

## Dependency hygiene

`manifest.json` lists only `python-dateutil>=2.8.2`, which is actively used.
The previously-proposed removal of `arrow`/`aiofiles`/`pytz` had already
happened before this pass — nothing further to do here.
