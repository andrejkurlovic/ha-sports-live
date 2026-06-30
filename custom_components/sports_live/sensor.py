"""Sensor platform for Sports Live.

Creates multiple CoordinatorEntity instances per config entry, each mapping
to one type of data (standings, matches, next_match, news, bracket, etc.).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.storage import Store

from .const import (
    _LOGGER, DOMAIN,
    CONF_MODE, CONF_SPORT, CONF_COMPETITION_CODE, CONF_TEAM_ID, CONF_TEAM_NAME,
    CONF_TEAM_IDS, CONF_TEAM_NAMES, CONF_ENABLED_SENSORS,
    MODE_HUB, MODE_COMPETITION, MODE_TEAM, MODE_MULTI_TEAM, MODE_ALL_TODAY, MODE_NEWS, MODE_MANUAL_TEAM,
    SENSOR_STANDINGS, SENSOR_MATCHES, SENSOR_NEXT_MATCH, SENSOR_SCHEDULE,
    SENSOR_SCHEDULE_ALL, SENSOR_NEWS, SENSOR_BRACKET, SENSOR_ALL_TODAY,
    EVENT_SCORE, EVENT_DISCIPLINE, EVENT_MATCH_FINISHED,
    EVENT_LEGACY_GOAL, EVENT_LEGACY_YELLOW, EVENT_LEGACY_RED, EVENT_LEGACY_FINISHED,
    OPT_RECENT_MATCH_HOURS,
)
from .coordinator import SportsLiveCoordinator
from .sports import get_profile
from .parsers.scoreboard import (
    process_scoreboard, process_news, is_within_recent_window, is_within_last_48_hours,
)
from .parsers.standings import process_standings
from .parsers.bracket import process_bracket
from .parsers.summary import process_summary
from .broadcast_rights import enrich_matches_with_uk_broadcast


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SportsLiveCoordinator = hass.data[DOMAIN][entry.entry_id]
    sport = entry.data.get(CONF_SPORT)
    profile = get_profile(sport)
    competition = entry.data.get(CONF_COMPETITION_CODE, "")
    team_id = entry.data.get(CONF_TEAM_ID)
    team_name = entry.data.get(CONF_TEAM_NAME)
    mode = entry.data.get(CONF_MODE)

    sport_slug = sport.replace("-", "_")
    comp_slug = str(competition).replace(".", "_").replace("-", "_").replace(" ", "_").lower()
    team_slug = (team_name or str(team_id) or "").replace(" ", "_").replace(".", "_").lower()

    entities: list[SportsLiveSensor] = []

    # Options-override: for hub mode, team_ids/enabled_sensors may have been updated via options flow
    opts = entry.options
    enabled_sensors: list = opts.get(
        CONF_ENABLED_SENSORS, entry.data.get(CONF_ENABLED_SENSORS, [SENSOR_MATCHES])
    )
    hub_team_ids: list = opts.get(CONF_TEAM_IDS, entry.data.get(CONF_TEAM_IDS, []))
    hub_team_names: list = opts.get(CONF_TEAM_NAMES, entry.data.get(CONF_TEAM_NAMES, []))

    if mode == MODE_HUB:
        enabled_set = set(enabled_sensors)

        # Competition-level sensors
        entities.append(SportsLiveSensor(
            coordinator, entry,
            sensor_type=SENSOR_MATCHES,
            unique_suffix=f"matches_{sport_slug}_{comp_slug}",
            sport_profile=profile,
            team_name=None,
            competition_code=competition,
        ))

        if SENSOR_STANDINGS in enabled_set and profile.capabilities.supports_standings:
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_STANDINGS,
                unique_suffix=f"standings_{sport_slug}_{comp_slug}",
                sport_profile=profile,
                team_name=None,
                competition_code=competition,
            ))

        if (SENSOR_BRACKET in enabled_set and profile.capabilities.supports_bracket
                and competition in profile.knockout_competitions):
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_BRACKET,
                unique_suffix=f"bracket_{sport_slug}_{comp_slug}",
                sport_profile=profile,
                team_name=None,
                competition_code=competition,
            ))

        if SENSOR_NEWS in enabled_set and profile.has_news_url():
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_NEWS,
                unique_suffix=f"news_{sport_slug}_{comp_slug}",
                sport_profile=profile,
                team_name=None,
                competition_code=competition,
            ))

        # Per-team sensors
        uid_prefix = f"{DOMAIN}_{entry.entry_id}"
        for team_id_i, team_name_i in zip(hub_team_ids, hub_team_names):
            t_slug = (team_name_i or str(team_id_i)).replace(" ", "_").replace(".", "_").replace("-", "_").lower()
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_NEXT_MATCH,
                unique_suffix=f"next_{sport_slug}_{comp_slug}_{t_slug}",
                sport_profile=profile,
                team_name=team_name_i,
                competition_code=competition,
                team_id=team_id_i,
                uid_override=f"{uid_prefix}_next_{sport_slug}_{comp_slug}_{t_slug}",
            ))
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_SCHEDULE,
                unique_suffix=f"schedule_{sport_slug}_{comp_slug}_{t_slug}",
                sport_profile=profile,
                team_name=team_name_i,
                competition_code=competition,
                team_id=team_id_i,
                uid_override=f"{uid_prefix}_schedule_{sport_slug}_{comp_slug}_{t_slug}",
            ))
            if profile.has_team_schedule_url() and team_id_i:
                entities.append(SportsLiveSensor(
                    coordinator, entry,
                    sensor_type=SENSOR_SCHEDULE_ALL,
                    unique_suffix=f"schedule_all_{sport_slug}_{t_slug}",
                    sport_profile=profile,
                    team_name=team_name_i,
                    competition_code=competition,
                    team_id=team_id_i,
                    uid_override=f"{uid_prefix}_schedule_all_{sport_slug}_{t_slug}",
                ))

    elif mode == MODE_NEWS:
        entities.append(SportsLiveSensor(
            coordinator, entry,
            sensor_type=SENSOR_NEWS,
            unique_suffix=f"news_{sport_slug}_{comp_slug}",
            sport_profile=profile,
            team_name=None,
            competition_code=competition,
        ))

    elif mode == MODE_ALL_TODAY:
        entities.append(SportsLiveSensor(
            coordinator, entry,
            sensor_type=SENSOR_ALL_TODAY,
            unique_suffix=f"today_{sport_slug}",
            sport_profile=profile,
            team_name=None,
            competition_code=competition,
        ))

    elif mode == MODE_COMPETITION:
        entities.append(SportsLiveSensor(
            coordinator, entry,
            sensor_type=SENSOR_MATCHES,
            unique_suffix=f"matches_{sport_slug}_{comp_slug}",
            sport_profile=profile,
            team_name=None,
            competition_code=competition,
        ))

        if profile.capabilities.supports_standings:
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_STANDINGS,
                unique_suffix=f"standings_{sport_slug}_{comp_slug}",
                sport_profile=profile,
                team_name=None,
                competition_code=competition,
            ))

        if (profile.capabilities.supports_news and profile.has_news_url()):
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_NEWS,
                unique_suffix=f"news_{sport_slug}_{comp_slug}",
                sport_profile=profile,
                team_name=None,
                competition_code=competition,
            ))

        if (profile.capabilities.supports_bracket
                and competition in profile.knockout_competitions):
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_BRACKET,
                unique_suffix=f"bracket_{sport_slug}_{comp_slug}",
                sport_profile=profile,
                team_name=None,
                competition_code=competition,
            ))

    elif mode in (MODE_TEAM, MODE_MANUAL_TEAM):
        entities.append(SportsLiveSensor(
            coordinator, entry,
            sensor_type=SENSOR_NEXT_MATCH,
            unique_suffix=f"next_{sport_slug}_{comp_slug}_{team_slug}",
            sport_profile=profile,
            team_name=team_name,
            competition_code=competition,
            team_id=team_id,
        ))
        entities.append(SportsLiveSensor(
            coordinator, entry,
            sensor_type=SENSOR_SCHEDULE,
            unique_suffix=f"schedule_{sport_slug}_{comp_slug}_{team_slug}",
            sport_profile=profile,
            team_name=team_name,
            competition_code=competition,
            team_id=team_id,
        ))
        if profile.has_team_schedule_url() and team_id:
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_SCHEDULE_ALL,
                unique_suffix=f"schedule_all_{sport_slug}_{team_slug}",
                sport_profile=profile,
                team_name=team_name,
                competition_code=competition,
                team_id=team_id,
            ))

    elif mode == MODE_MULTI_TEAM:
        team_ids = entry.data.get(CONF_TEAM_IDS, [])
        team_names_list = entry.data.get(CONF_TEAM_NAMES, [])
        for team_id_i, team_name_i in zip(team_ids, team_names_list):
            t_slug = (team_name_i or str(team_id_i)).replace(" ", "_").replace(".", "_").replace("-", "_").lower()
            uid_prefix = f"{DOMAIN}_{entry.entry_id}"
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_NEXT_MATCH,
                unique_suffix=f"next_{sport_slug}_{comp_slug}_{t_slug}",
                sport_profile=profile,
                team_name=team_name_i,
                competition_code=competition,
                team_id=team_id_i,
                uid_override=f"{uid_prefix}_next_{sport_slug}_{comp_slug}_{t_slug}",
            ))
            entities.append(SportsLiveSensor(
                coordinator, entry,
                sensor_type=SENSOR_SCHEDULE,
                unique_suffix=f"schedule_{sport_slug}_{comp_slug}_{t_slug}",
                sport_profile=profile,
                team_name=team_name_i,
                competition_code=competition,
                team_id=team_id_i,
                uid_override=f"{uid_prefix}_schedule_{sport_slug}_{comp_slug}_{t_slug}",
            ))
            if profile.has_team_schedule_url() and team_id_i:
                entities.append(SportsLiveSensor(
                    coordinator, entry,
                    sensor_type=SENSOR_SCHEDULE_ALL,
                    unique_suffix=f"schedule_all_{sport_slug}_{t_slug}",
                    sport_profile=profile,
                    team_name=team_name_i,
                    competition_code=competition,
                    team_id=team_id_i,
                    uid_override=f"{uid_prefix}_schedule_all_{sport_slug}_{t_slug}",
                ))

    async_add_entities(entities, True)


# ---------------------------------------------------------------------------
# Sensor class
# ---------------------------------------------------------------------------

class SportsLiveSensor(CoordinatorEntity, SensorEntity):
    """One entity backed by SportsLiveCoordinator data."""

    def __init__(self, coordinator: SportsLiveCoordinator, entry: ConfigEntry,
                 sensor_type: str, unique_suffix: str, sport_profile,
                 team_name: str | None, competition_code: str,
                 team_id: str | int | None = None,
                 recent_match_hours: int = 24,
                 uid_override: str | None = None):
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_type = sensor_type
        self._sport_profile = sport_profile
        self._team_name = team_name
        self._competition_code = competition_code
        self._team_id = team_id
        self._recent_match_hours = entry.options.get(OPT_RECENT_MATCH_HOURS, recent_match_hours)

        # Stable unique_suffix used for entity_id and unique_id
        self._unique_suffix = unique_suffix.replace("-", "_").lower()

        _SENSOR_LABELS = {
            SENSOR_STANDINGS: "Standings",
            SENSOR_MATCHES: "Matches",
            SENSOR_NEXT_MATCH: "Next Match",
            SENSOR_SCHEDULE: "Schedule",
            SENSOR_SCHEDULE_ALL: "Full Schedule",
            SENSOR_NEWS: "News",
            SENSOR_BRACKET: "Bracket",
            SENSOR_ALL_TODAY: "All Today",
        }
        _SENSOR_ICONS = {
            SENSOR_STANDINGS: "mdi:table-large",
            SENSOR_MATCHES: "mdi:scoreboard-outline",
            SENSOR_NEXT_MATCH: "mdi:calendar-clock",
            SENSOR_SCHEDULE: "mdi:calendar",
            SENSOR_SCHEDULE_ALL: "mdi:calendar-multiple",
            SENSOR_NEWS: "mdi:newspaper-variant-outline",
            SENSOR_BRACKET: "mdi:tournament",
            SENSOR_ALL_TODAY: "mdi:view-list",
        }

        label = _SENSOR_LABELS.get(sensor_type, sensor_type.replace("_", " ").title())
        # Multi-team entries put team_name in the friendly name so sensors are distinguishable
        if uid_override and team_name:
            self._attr_name = f"{entry.title} — {team_name} — {label}"
        else:
            self._attr_name = f"{entry.title} — {label}"
        self._attr_icon = _SENSOR_ICONS.get(sensor_type)
        self._attr_unique_id = uid_override or f"{DOMAIN}_{entry.entry_id}_{sensor_type}"
        self._attr_extra_state_attributes: dict = {}
        self._attr_native_value: str | None = None

        # Event dedup / state tracking
        self._previous_scores: dict = {}
        self._previous_match_details: dict = {}
        self._match_finished_dispatched: set = set()
        self._store: Store | None = None
        # Summary enrichment cache: {event_id: {"key": (...), "data": {...}}}
        self._summary_cache: dict = {}

    @property
    def name(self) -> str:
        return self._attr_name

    @property
    def unique_id(self) -> str:
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="ESPN",
            model=self._sport_profile.sport_id.replace("_", " ").title(),
            configuration_url="https://github.com/andrejkurlovic/ha-sports-live",
        )

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self) -> dict:
        return self._attr_extra_state_attributes

    # ------------------------------------------------------------------
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        key = f"sports_live_{self._unique_suffix}_finished"
        self._store = Store(self.hass, 1, key)
        stored = await self._store.async_load()
        if stored and "dispatched" in stored:
            self._match_finished_dispatched = set(stored["dispatched"])

    async def _save_finished_store(self):
        if self._store:
            await self._store.async_save({"dispatched": list(self._match_finished_dispatched)})

    # ------------------------------------------------------------------
    def _handle_coordinator_update(self):
        data = self.coordinator.data or {}
        self._process_update(data)
        self.async_write_ha_state()

    def _process_update(self, data: dict):
        stype = self._sensor_type

        if stype == SENSOR_NEWS:
            raw = data.get(SENSOR_NEWS) or {}
            articles = process_news(raw)
            self._attr_native_value = f"{len(articles)} articles" if articles else "No articles"
            self._attr_extra_state_attributes = {
                "articles": articles,
                "competition_code": self._competition_code,
                "sport": self._sport_profile.sport_id,
            }

        elif stype == SENSOR_STANDINGS:
            raw = data.get(SENSOR_STANDINGS) or {}
            standings = process_standings(raw)
            self._attr_native_value = "Standings"
            self._attr_extra_state_attributes = {
                **standings,
                "competition_code": self._competition_code,
                "sport": self._sport_profile.sport_id,
            }

        elif stype == SENSOR_BRACKET:
            # Bracket reuses the competition scoreboard (SENSOR_MATCHES) — same data,
            # no separate fetch needed. Using the full season-dated scoreboard also
            # fixes NFL (Jan playoffs) and MLB (Oct-Nov playoffs) which the old
            # hardcoded Feb-July bracket URL always missed.
            raw = data.get(SENSOR_MATCHES) or {}
            bracket = process_bracket(raw)
            rounds = bracket.get("rounds", [])
            if rounds:
                last = rounds[-1]
                self._attr_native_value = f"{last.get('name')} ({last.get('size')} teams)"
            else:
                self._attr_native_value = "Bracket unavailable"
            self._attr_extra_state_attributes = {
                "rounds": rounds,
                "ties_count": bracket.get("ties_count", 0),
                "competition_code": self._competition_code,
                "sport": self._sport_profile.sport_id,
            }

        elif stype in (SENSOR_MATCHES, SENSOR_ALL_TODAY):
            raw = data.get(stype) or {}
            self._attr_extra_state_attributes = self._build_scoreboard_attrs(
                raw, team_name=None, season_filtered=True,
                include_league_info=True, include_team_info=False, include_competition_code=True,
            )

        elif stype == SENSOR_SCHEDULE:
            raw = data.get(SENSOR_MATCHES) or {}
            self._attr_extra_state_attributes = self._build_scoreboard_attrs(
                raw, team_name=self._team_name, season_filtered=True,
                include_league_info=True, include_team_info=True, include_competition_code=True,
            )

        elif stype == SENSOR_SCHEDULE_ALL:
            # Multi-team mode stores data per-team: "schedule_all_{team_id}"
            per_team_key = f"schedule_all_{self._team_id}"
            key = per_team_key if per_team_key in data else SENSOR_SCHEDULE_ALL
            raw = data.get(key) or {}
            self._attr_extra_state_attributes = self._build_scoreboard_attrs(
                raw, team_name=self._team_name, season_filtered=False,
                include_league_info=False, include_team_info=True, include_competition_code=False,
            )

        elif stype == SENSOR_NEXT_MATCH:
            raw = data.get(SENSOR_MATCHES) or {}
            parsed = process_scoreboard(
                raw, self.hass,
                team_name=self._team_name,
                next_match_only=True,
                start_date=self.coordinator._season_start.strftime("%Y-%m-%d") if self.coordinator._season_start else None,
                end_date=self.coordinator._season_end.strftime("%Y-%m-%d") if self.coordinator._season_end else None,
                recent_match_hours=self._recent_match_hours,
            )
            next_match = parsed.get("next_match")
            matches = parsed.get("matches", [])
            enrich_matches_with_uk_broadcast(matches, self._competition_code or "")
            if next_match:
                enrich_matches_with_uk_broadcast([next_match], self._competition_code or "")

            if next_match:
                if next_match.get("state") == "in":
                    self._attr_native_value = (
                        f"{next_match.get('home_score','?')}-{next_match.get('away_score','?')}"
                        f" ({next_match.get('clock','')})"
                    )
                else:
                    self._attr_native_value = (
                        f"Next: {next_match.get('home_team','?')} vs {next_match.get('away_team','?')}"
                    )
            else:
                self._attr_native_value = "No upcoming match"

            computed = self._compute_next_match_attrs(next_match) if next_match else {}
            self._attr_extra_state_attributes = {
                **parsed,
                "matches": self._trim_matches_for_storage(matches, include_enrichment=True),
                **computed,
                "competition_code": self._competition_code,
                "sport": self._sport_profile.sport_id,
            }

            # Enrich next match with summary (lineup/events) if supported
            if (next_match and self._sport_profile.capabilities.supports_summary
                    and next_match.get("event_id")):
                self.hass.async_create_task(
                    self._enrich_with_summary(next_match, self._attr_extra_state_attributes)
                )

    def _build_scoreboard_attrs(self, raw: dict, *, team_name: str | None, season_filtered: bool,
                                 include_league_info: bool, include_team_info: bool,
                                 include_competition_code: bool) -> dict:
        """Shared by SENSOR_MATCHES/ALL_TODAY/SCHEDULE/SCHEDULE_ALL — they only
        differ in which attribute keys are present and whether the season's
        start/end date range narrows the fetch (schedule_all wants every
        match for the team, not just this season)."""
        season_start = self.coordinator._season_start if season_filtered else None
        season_end = self.coordinator._season_end if season_filtered else None
        parsed = process_scoreboard(
            raw, self.hass,
            team_name=team_name,
            start_date=season_start.strftime("%Y-%m-%d") if season_start else None,
            end_date=season_end.strftime("%Y-%m-%d") if season_end else None,
            recent_match_hours=self._recent_match_hours,
        )
        matches = parsed.get("matches", [])
        enrich_matches_with_uk_broadcast(matches, self._competition_code or "")
        # Stamp ESPN summary URL on penalty matches so the card can fetch kick data.
        if self._sport_profile.capabilities.supports_summary:
            espn_comp = getattr(self.coordinator, "_competition", None) or ""
            for m in matches:
                if m.get("decided_on_penalties") and m.get("event_id"):
                    m["espn_summary_url"] = self._sport_profile.summary_url(
                        espn_comp, str(m["event_id"])
                    )
        self._attr_native_value = self._describe_matches(matches)
        computed = self._compute_all_matches_attrs(matches)

        attrs: dict = {}
        if include_league_info:
            attrs["league_info"] = parsed.get("league_info", [])
        if include_team_info:
            attrs["team_name"] = self._team_name
            attrs["team_logo"] = parsed.get("team_logo")
        attrs["matches"] = self._trim_matches_for_storage(matches)
        attrs.update(computed)
        if include_competition_code:
            attrs["competition_code"] = self._competition_code
        attrs["sport"] = self._sport_profile.sport_id
        return attrs

    # ------------------------------------------------------------------
    # Summary enrichment
    # ------------------------------------------------------------------

    async def _enrich_with_summary(self, match: dict, attrs: dict):
        event_id = match.get("event_id")
        if not event_id:
            return
        # Refetch the summary only when the match identity/score changes; a
        # finished or static game reuses the cached parse every cycle.
        cache_key = (str(event_id), match.get("state"),
                     str(match.get("home_score")), str(match.get("away_score")))
        cached = self._summary_cache.get(str(event_id))
        if cached and cached["key"] == cache_key:
            summary_data = cached["data"]
        else:
            raw_summary = await self.coordinator.fetch_summary(str(event_id))
            if not raw_summary:
                return
            summary_data = await self.hass.async_add_executor_job(process_summary, raw_summary)
            # Single-entry cache — only the currently tracked match matters.
            self._summary_cache = {str(event_id): {"key": cache_key, "data": summary_data}}

        self._merge_summary(match, summary_data)
        # Re-apply the storage trim so the enriched fields reach
        # attributes["matches"] (the trimmed copies the cards actually read).
        attrs["matches"] = self._trim_matches_for_storage([match], include_enrichment=True)
        self.async_write_ha_state()

    @staticmethod
    def _merge_summary(match: dict, summary_data: dict):
        """Merge summary fields into a match dict without clobbering live
        scoreboard values (e.g. a win probability the predictor already set)."""
        for k, v in summary_data.items():
            if k == "summary_home_win_probability":
                if match.get("home_win_probability") in (None, ""):
                    match["home_win_probability"] = v
            elif k == "summary_away_win_probability":
                if match.get("away_win_probability") in (None, ""):
                    match["away_win_probability"] = v
            else:
                match[k] = v

    # ------------------------------------------------------------------
    # Event dispatching
    # ------------------------------------------------------------------

    def _compute_all_matches_attrs(self, matches: list) -> dict:
        # Dispatch events only for non-schedule-all sensors (avoid duplicate events)
        if self._sensor_type != SENSOR_SCHEDULE_ALL:
            self._detect_and_dispatch_scores(matches)
            self._detect_and_dispatch_discipline(matches)
            self._detect_and_dispatch_finished(matches)

        live = [m for m in matches if m.get("state") == "in"]
        upcoming = [m for m in matches if m.get("state") == "pre"]
        finished = [m for m in matches if m.get("state") == "post"]

        computed: dict = {
            "has_live_match": bool(live),
            "has_upcoming_match": bool(upcoming),
            "has_recent_match": False,
            "total_matches": len(matches),
            "live_matches_count": len(live),
            "upcoming_matches_count": len(upcoming),
            "finished_matches_count": len(finished),
        }
        if live:
            computed.update(self._live_match_attrs(live[0]))
        if upcoming:
            computed.update(self._compute_next_match_attrs(upcoming[0]))
        recent = [m for m in finished if is_within_last_48_hours(m.get("date_iso") or m.get("date"))]
        if recent:
            lm = recent[0]
            computed.update({
                "last_match_home_team": lm.get("home_team"),
                "last_match_away_team": lm.get("away_team"),
                "last_match_home_logo": lm.get("home_logo"),
                "last_match_away_logo": lm.get("away_logo"),
                "last_match_home_score": lm.get("home_score"),
                "last_match_away_score": lm.get("away_score"),
                "last_match_date": lm.get("date"),
                "last_match_venue": lm.get("venue"),
                "has_recent_match": True,
            })
        return computed

    def _compute_next_match_attrs(self, match: dict) -> dict:
        if not match:
            return {}
        dt = self._parse_match_dt(match.get("date"))
        return {
            "next_match_home_team": match.get("home_team"),
            "next_match_away_team": match.get("away_team"),
            "next_match_home_logo": match.get("home_logo"),
            "next_match_away_logo": match.get("away_logo"),
            "next_match_home_score": match.get("home_score"),
            "next_match_away_score": match.get("away_score"),
            "next_match_date": match.get("date"),
            "next_match_datetime_iso": dt.isoformat() if dt else "N/A",
            "next_match_minutes_until": self._minutes_until(dt),
            "next_match_status": match.get("state"),
            "next_match_description": match.get("status"),
            "next_match_venue": match.get("venue"),
            "next_match_period": match.get("period"),
            "next_match_clock": match.get("clock"),
            "next_match_home_form": match.get("home_form"),
            "next_match_away_form": match.get("away_form"),
            "next_match_season_info": match.get("season_info"),
        }

    def _live_match_attrs(self, match: dict) -> dict:
        return {
            "live_match_home_team": match.get("home_team"),
            "live_match_away_team": match.get("away_team"),
            "live_match_home_logo": match.get("home_logo"),
            "live_match_away_logo": match.get("away_logo"),
            "live_match_home_score": match.get("home_score"),
            "live_match_away_score": match.get("away_score"),
            "live_match_date": match.get("date"),
            "live_match_status": "in",
            "live_match_description": match.get("status"),
            "live_match_venue": match.get("venue"),
            "live_match_period": match.get("period"),
            "live_match_clock": match.get("clock"),
        }

    def _describe_matches(self, matches: list) -> str:
        live = [m for m in matches if m.get("state") == "in"]
        if live:
            lm = live[0]
            return (
                f"LIVE {lm.get('home_team','?')} {lm.get('home_score','?')}"
                f"-{lm.get('away_score','?')} {lm.get('away_team','?')}"
                f" ({lm.get('clock','')})"
            )
        upcoming = [m for m in matches if m.get("state") == "pre"]
        if upcoming:
            um = upcoming[0]
            return f"Next: {um.get('home_team','?')} vs {um.get('away_team','?')} ({um.get('date','?')})"
        finished = [m for m in matches if m.get("state") == "post"]
        if finished:
            fm = finished[-1]   # most recent finished match
            return (
                f"{fm.get('home_team','?')} {fm.get('home_score','?')}"
                f"-{fm.get('away_score','?')} {fm.get('away_team','?')}"
            )
        return f"{len(matches)} matches" if matches else "No matches"

    # ------------------------------------------------------------------
    # Event detection
    # ------------------------------------------------------------------

    def _detect_and_dispatch_scores(self, matches: list):
        for match in (m for m in matches if m.get("state") == "in"):
            mid = f"{match.get('home_team')}_{match.get('away_team')}"
            hs = self._safe_score(match.get("home_score"))
            as_ = self._safe_score(match.get("away_score"))
            prev = self._previous_scores.get(mid)
            if prev is None:
                self._previous_scores[mid] = {"home": hs, "away": as_,
                                               "details": match.get("match_details", [])}
                continue
            if hs > prev["home"]:
                self._fire_score_event(match, "home", hs - prev["home"], hs, as_,
                                       prev.get("details", []), match.get("match_details", []))
            if as_ > prev["away"]:
                self._fire_score_event(match, "away", as_ - prev["away"], hs, as_,
                                       prev.get("details", []), match.get("match_details", []))
            self._previous_scores[mid] = {"home": hs, "away": as_,
                                           "details": list(match.get("match_details", []))}

    def _fire_score_event(self, match, side, count, home_score, away_score,
                          prev_details, curr_details):
        score_label = self._sport_profile.score_event_label
        team = match.get(f"{side}_team", "N/A")
        opponent = match.get("away_team" if side == "home" else "home_team", "N/A")
        scorers = self._extract_scorers(prev_details, curr_details, count)

        first = scorers[0] if scorers else {}
        payload = {
            "sport": self._sport_profile.sport_id,
            "score_event_label": score_label,
            "team": team,
            "opponent": opponent,
            "count": count,
            "player": first.get("player", "N/A"),
            "minute": first.get("minute", "N/A"),
            "players": [g.get("player", g) if isinstance(g, dict) else g for g in scorers],
            "home_team": match.get("home_team", "N/A"),
            "away_team": match.get("away_team", "N/A"),
            "home_score": home_score,
            "away_score": away_score,
            "venue": match.get("venue", "N/A"),
            "competition_code": self._competition_code,
            "sensor_name": self._attr_name,
            "league_name": match.get("league_name", "N/A"),
        }
        self.hass.bus.fire(EVENT_SCORE, payload)
        # Legacy soccer alias
        if self._sport_profile.sport_id == "soccer":
            self.hass.bus.fire(EVENT_LEGACY_GOAL, {**payload, "goals_scored": count})

    def _detect_and_dispatch_discipline(self, matches: list):
        for match in (m for m in matches if m.get("state") == "in"):
            mid = f"{match.get('home_team')}_{match.get('away_team')}"
            curr = match.get("match_details", [])
            prev = self._previous_match_details.get(mid)
            if prev is None:
                self._previous_match_details[mid] = list(curr)
                continue
            for detail in curr:
                if detail not in prev:
                    self._fire_discipline_event(detail, match)
            self._previous_match_details[mid] = list(curr)

    def _fire_discipline_event(self, detail_str: str, match: dict):
        card_type = None
        if "Yellow Card" in detail_str:
            card_type = "yellow"
        elif "Red Card" in detail_str:
            card_type = "red"
        else:
            return

        parts = detail_str.split("': ")
        minute = parts[0].split(" - ")[-1] if " - " in parts[0] else "N/A"
        player = parts[1] if len(parts) > 1 else "N/A"

        payload = {
            "sport": self._sport_profile.sport_id,
            "discipline_type": card_type.upper(),
            "player": player,
            "minute": minute,
            "home_team": match.get("home_team", "N/A"),
            "away_team": match.get("away_team", "N/A"),
            "home_score": match.get("home_score", "N/A"),
            "away_score": match.get("away_score", "N/A"),
            "venue": match.get("venue", "N/A"),
            "competition_code": self._competition_code,
            "sensor_name": self._attr_name,
            "league_name": match.get("league_name", "N/A"),
        }
        self.hass.bus.fire(EVENT_DISCIPLINE, payload)
        if self._sport_profile.sport_id == "soccer":
            legacy = EVENT_LEGACY_YELLOW if card_type == "yellow" else EVENT_LEGACY_RED
            self.hass.bus.fire(legacy, {**payload, "card_type": card_type.upper()})

    def _detect_and_dispatch_finished(self, matches: list):
        for match in (m for m in matches if m.get("state") == "post"):
            mid = f"{match.get('home_team')}_{match.get('away_team')}"
            if mid not in self._match_finished_dispatched:
                self._fire_finished_event(match)
                self._match_finished_dispatched.add(mid)
                self.hass.async_create_task(self._save_finished_store())

    def _fire_finished_event(self, match: dict):
        payload = {
            "sport": self._sport_profile.sport_id,
            "home_team": match.get("home_team", "N/A"),
            "away_team": match.get("away_team", "N/A"),
            "home_score": match.get("home_score", "N/A"),
            "away_score": match.get("away_score", "N/A"),
            "final_status": match.get("status", "N/A"),
            "venue": match.get("venue", "N/A"),
            "date": match.get("date", "N/A"),
            "competition_code": self._competition_code,
            "league_name": match.get("league_name", "N/A"),
            "sensor_name": self._attr_name,
        }
        self.hass.bus.fire(EVENT_MATCH_FINISHED, payload)
        if self._sport_profile.sport_id == "soccer":
            self.hass.bus.fire(EVENT_LEGACY_FINISHED, payload)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    _MATCH_STORAGE_FIELDS = frozenset({
        "event_id", "date", "date_iso", "season_info", "league_name",
        "home_team", "home_abbrev", "home_color", "home_alt_color", "home_logo",
        "home_form", "home_score", "home_record",
        "away_team", "away_abbrev", "away_color", "away_alt_color", "away_logo",
        "away_form", "away_score", "away_record",
        "state", "status", "status_detail", "clock", "period",
        "venue", "venue_city", "venue_country", "attendance",
        "broadcast", "broadcast_uk", "match_details",
        # Penalty shootout fields (v2.0.7)
        "decided_on_penalties", "in_penalty_shootout",
        "penalty_home_score", "penalty_away_score", "shootout_details",
        "espn_summary_url",
        # Live situation & enrichment (v1.6.0)
        "event_url",
        "home_win_probability", "away_win_probability",
        "home_timeouts", "away_timeouts",
        "last_play", "down_distance_text",
        "balls", "strikes", "outs",
        "on_first", "on_second", "on_third",
        "odds_details", "over_under",
    })

    # Heavier per-match fields kept only for a single tracked match (next_match),
    # never for the bulk match lists — they would blow the 16 KB recorder cap.
    _MATCH_ENRICHMENT_FIELDS = frozenset({
        "scoring_plays", "stat_leaders",
        "key_events", "head_to_head",
        "lineup_home", "lineup_away", "formation_home", "formation_away",
        "home_top_scorer", "away_top_scorer",
        "home_statistics", "away_statistics",
    })

    @classmethod
    def _trim_matches_for_storage(cls, matches: list, *, include_enrichment: bool = False) -> list:
        """Keep live + upcoming + last 20 finished (by date) and strip heavy fields
        to stay under the 16 KB recorder cap. When include_enrichment is set (single
        tracked match), the summary-enrichment fields are retained as well."""
        live = [m for m in matches if m.get("state") == "in"]
        upcoming = [m for m in matches if m.get("state") == "pre"]
        finished = sorted(
            (m for m in matches if m.get("state") == "post"),
            key=lambda m: m.get("date_iso") or m.get("date") or "",
        )
        trimmed = live + upcoming + finished[-20:]
        allow = cls._MATCH_STORAGE_FIELDS | cls._MATCH_ENRICHMENT_FIELDS if include_enrichment \
            else cls._MATCH_STORAGE_FIELDS
        return [{k: v for k, v in m.items() if k in allow} for m in trimmed]

    @staticmethod
    def _safe_score(v) -> int:
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    def _extract_scorers(self, prev: list, curr: list, count: int) -> list:
        new_goals = []
        for detail in curr:
            if detail not in prev and "Goal" in detail:
                try:
                    parts = detail.split("': ")
                    if len(parts) == 2:
                        player = parts[1].strip()
                        minute = parts[0].split(" - ")[-1].strip() if " - " in parts[0] else "N/A"
                        new_goals.append({"player": player, "minute": minute})
                except Exception:
                    pass
        return new_goals[:count]

    def _parse_match_dt(self, date_str: str | None) -> datetime | None:
        try:
            if not date_str:
                return None
            tz = ZoneInfo(self.hass.config.time_zone)
            return datetime.strptime(date_str, "%d/%m/%Y %H:%M").replace(tzinfo=tz)
        except (ValueError, TypeError):
            return None

    def _minutes_until(self, dt: datetime | None) -> int | None:
        try:
            if not dt:
                return None
            tz = ZoneInfo(self.hass.config.time_zone)
            delta = dt - datetime.now(tz)
            return int(delta.total_seconds() / 60)
        except Exception:
            return None
