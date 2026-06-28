"""Multi-sport config flow for Sports Live — v2.0 Competition Hub model.

Flow (primary):
  user → mode → competition → hub (sensors + teams) → done

Flow (edge cases):
  user → mode (all_today) → done
  user → mode (manual_team) → manual_team → done

Options flow (for any hub entry):
  init → saves scan_interval, recent_match_hours, enabled_sensors, team_names/ids
"""
from __future__ import annotations
import aiohttp

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .const import (
    _LOGGER, DOMAIN,
    CONF_MODE, CONF_SPORT, CONF_COMPETITION_CODE, CONF_COMPETITION_NAME,
    CONF_TEAM_ID, CONF_TEAM_NAME, CONF_TEAM_IDS, CONF_TEAM_NAMES, CONF_ENABLED_SENSORS,
    MODE_HUB, MODE_ALL_TODAY, MODE_MANUAL_TEAM,
    MODE_COMPETITION, MODE_TEAM, MODE_MULTI_TEAM, MODE_NEWS,
    SENSOR_MATCHES, SENSOR_STANDINGS, SENSOR_BRACKET, SENSOR_NEWS,
    OPT_SCAN_INTERVAL, OPT_RECENT_MATCH_HOURS,
)
from .sports import list_sports, get_profile
from .sports.registry import RUGBY_COMPETITIONS, TENNIS_COMPETITIONS

_ESPN_HEADERS = {"Accept-Language": "en"}
_TIMEOUT = aiohttp.ClientTimeout(total=10)


@config_entries.HANDLERS.register(DOMAIN)
class SportsLiveConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._data: dict = {}
        self._errors: dict = {}
        self._competitions: dict[str, str] = {}   # code → name
        self._teams: list[dict] = []

    # ------------------------------------------------------------------ step_user
    async def async_step_user(self, user_input=None):
        """Step 1: choose sport."""
        self._errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_mode()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_SPORT): vol.In(list_sports()),
            }),
            errors=self._errors,
        )

    # ------------------------------------------------------------------ step_mode
    async def async_step_mode(self, user_input=None):
        """Step 2: choose what to monitor."""
        self._errors = {}
        if user_input is not None:
            mode = user_input.get(CONF_MODE)
            self._data[CONF_MODE] = mode

            if mode == MODE_ALL_TODAY:
                profile = get_profile(self._data[CONF_SPORT])
                self._data[CONF_COMPETITION_CODE] = "all"
                return self.async_create_entry(
                    title=f"All {profile.display_name} Matches Today",
                    data=self._data,
                )
            if mode == MODE_MANUAL_TEAM:
                return await self.async_step_manual_team()

            # hub mode → choose competition next
            return await self.async_step_competition()

        sport = self._data[CONF_SPORT]
        profile = get_profile(sport)
        mode_opts = {
            MODE_HUB: (
                f"Follow a competition  "
                f"(standings, matches{', bracket' if profile.capabilities.supports_bracket else ''}"
                f"{', teams' if profile.capabilities.supports_next_match else ''})"
            ),
            MODE_ALL_TODAY: "All matches today (cross-competition snapshot)",
            MODE_MANUAL_TEAM: "Manual team by ESPN ID (advanced)",
        }
        return self.async_show_form(
            step_id="mode",
            data_schema=vol.Schema({
                vol.Required(CONF_MODE, default=MODE_HUB): vol.In(mode_opts),
            }),
            errors=self._errors,
            description_placeholders={
                "sport": profile.display_name,
                "features": self._capability_summary(sport),
            },
        )

    @staticmethod
    def _capability_summary(sport_id: str) -> str:
        caps = get_profile(sport_id).capabilities
        have = ["matches"]
        if caps.supports_standings:    have.append("standings")
        if caps.supports_bracket:      have.append("bracket")
        if caps.supports_news:         have.append("news")
        if caps.supports_summary:      have.append("live detail")
        if caps.supports_lineup:       have.append("lineups")
        return "Available: " + ", ".join(have) + "."

    # ------------------------------------------------------------------ step_competition
    async def async_step_competition(self, user_input=None):
        """Step 3: choose competition / league."""
        self._errors = {}
        sport = self._data.get(CONF_SPORT)
        profile = get_profile(sport)

        if user_input is not None:
            code = user_input.get(CONF_COMPETITION_CODE)
            name = self._competitions.get(code, code)
            self._data[CONF_COMPETITION_CODE] = code
            self._data[CONF_COMPETITION_NAME] = name
            # Fetch teams now (needed for hub step team picker)
            await self._fetch_teams(profile, code)
            return await self.async_step_hub()

        self._competitions = await self._fetch_competitions(profile)
        if not self._competitions:
            self._errors["base"] = "cannot_load_competitions"
            return self.async_show_form(
                step_id="competition",
                data_schema=vol.Schema({vol.Required(CONF_COMPETITION_CODE): str}),
                errors=self._errors,
            )

        sorted_comps = dict(sorted(self._competitions.items(), key=lambda x: x[1]))
        return self.async_show_form(
            step_id="competition",
            data_schema=vol.Schema({
                vol.Required(CONF_COMPETITION_CODE): vol.In(sorted_comps),
            }),
            errors=self._errors,
        )

    # ------------------------------------------------------------------ step_hub
    async def async_step_hub(self, user_input=None):
        """Step 4: configure which sensors to create + which teams to track."""
        self._errors = {}
        sport = self._data.get(CONF_SPORT)
        comp_code = self._data.get(CONF_COMPETITION_CODE, "")
        profile = get_profile(sport)
        caps = profile.capabilities

        if user_input is not None:
            enabled = user_input.get(CONF_ENABLED_SENSORS, [SENSOR_MATCHES])
            if not enabled:
                enabled = [SENSOR_MATCHES]
            self._data[CONF_ENABLED_SENSORS] = enabled

            team_names = user_input.get(CONF_TEAM_NAMES, [])
            team_ids = [
                next((t["id"] for t in self._teams if t["displayName"] == n), None)
                for n in team_names
            ]
            self._data[CONF_TEAM_NAMES] = team_names
            self._data[CONF_TEAM_IDS] = team_ids

            comp_name = self._data.get(CONF_COMPETITION_NAME, comp_code)
            title = f"{profile.display_name} — {comp_name}"
            if team_names:
                summary = ", ".join(team_names[:3])
                if len(team_names) > 3:
                    summary += f" +{len(team_names) - 3}"
                title += f"  [{summary}]"

            return self.async_create_entry(title=title, data=self._data)

        # Build sensor options (only include what this sport/competition supports)
        sensor_opts = [{"value": SENSOR_MATCHES, "label": "Matches & live scores"}]
        default_sensors = [SENSOR_MATCHES]

        if caps.supports_standings:
            sensor_opts.append({"value": SENSOR_STANDINGS, "label": "Standings / league table"})
            default_sensors.append(SENSOR_STANDINGS)

        if caps.supports_bracket and comp_code in profile.knockout_competitions:
            sensor_opts.append({"value": SENSOR_BRACKET, "label": "Bracket / playoff tree"})
            default_sensors.append(SENSOR_BRACKET)

        if caps.supports_news and profile.has_news_url():
            sensor_opts.append({"value": SENSOR_NEWS, "label": "News feed"})

        schema: dict = {
            vol.Required(CONF_ENABLED_SENSORS, default=default_sensors): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sensor_opts,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }

        # Team picker (only sports that have team schedule URLs)
        if profile.has_team_schedule_url() and self._teams:
            team_names_sorted = sorted(t["displayName"] for t in self._teams)
            schema[vol.Optional(CONF_TEAM_NAMES, default=[])] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=team_names_sorted,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )

        return self.async_show_form(
            step_id="hub",
            data_schema=vol.Schema(schema),
            errors=self._errors,
            description_placeholders={
                "competition": self._data.get(CONF_COMPETITION_NAME, comp_code),
                "sport": profile.display_name,
            },
        )

    # ------------------------------------------------------------------ step_manual_team
    async def async_step_manual_team(self, user_input=None):
        """Alternate: enter team ID manually + pick competition."""
        self._errors = {}
        sport = self._data.get(CONF_SPORT)
        profile = get_profile(sport)

        if user_input is not None:
            self._data[CONF_TEAM_ID] = user_input.get("manual_team_id")
            self._data[CONF_TEAM_NAME] = user_input.get("team_label", "Team")
            self._data[CONF_COMPETITION_CODE] = user_input.get(CONF_COMPETITION_CODE, "all")
            self._data[CONF_COMPETITION_NAME] = self._competitions.get(
                self._data[CONF_COMPETITION_CODE], self._data[CONF_COMPETITION_CODE]
            )
            return self.async_create_entry(
                title=f"Manual Team — {self._data[CONF_TEAM_NAME]}",
                data=self._data,
            )

        self._competitions = await self._fetch_competitions(profile)
        sorted_comps = dict(sorted(self._competitions.items(), key=lambda x: x[1]))
        return self.async_show_form(
            step_id="manual_team",
            data_schema=vol.Schema({
                vol.Required("manual_team_id"): str,
                vol.Optional("team_label", default="My Team"): str,
                vol.Required(CONF_COMPETITION_CODE): vol.In(sorted_comps) if sorted_comps else str,
            }),
            errors=self._errors,
        )

    # ------------------------------------------------------------------ options flow
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SportsLiveOptionsFlow(config_entry)

    # ------------------------------------------------------------------ helpers
    async def _fetch_competitions(self, profile) -> dict[str, str]:
        if profile.numeric_competition_ids:
            if profile.sport_id == "tennis":
                return dict(TENNIS_COMPETITIONS)
            return dict(RUGBY_COMPETITIONS)

        url = profile.competitions_url()
        if not url:
            return {}
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, headers=_ESPN_HEADERS, timeout=_TIMEOUT) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return {lg["slug"]: lg["name"] for lg in data.get("leagues", [])}
        except Exception as e:
            _LOGGER.error("Failed to load competitions for %s: %s", profile.sport_id, e)
            return {}

    async def _fetch_teams(self, profile, competition_code: str) -> None:
        url = profile.teams_url(competition_code)
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, headers=_ESPN_HEADERS, timeout=_TIMEOUT) as resp:
                resp.raise_for_status()
                data = await resp.json()
                sports = data.get("sports", [{}])
                leagues = sports[0].get("leagues", [{}]) if sports else []
                self._teams = [
                    {"id": t["team"]["id"], "displayName": t["team"]["displayName"]}
                    for lg in leagues for t in lg.get("teams", [])
                ]
        except Exception as e:
            _LOGGER.error("Failed to load teams: %s", e)
            self._teams = []


# ------------------------------------------------------------------
class SportsLiveOptionsFlow(config_entries.OptionsFlow):
    """Options flow: edit scan interval, match window, tracked teams, and enabled sensors."""

    def __init__(self, config_entry):
        super().__init__()
        self._config_entry = config_entry
        self._teams: list[dict] = []
        self._team_id_map: dict[str, str] = {}  # displayName → id

    async def async_step_init(self, user_input=None):
        mode = self._config_entry.data.get(CONF_MODE)

        if user_input is not None:
            opts: dict = {
                OPT_SCAN_INTERVAL: int(user_input.get(OPT_SCAN_INTERVAL, 3)),
                OPT_RECENT_MATCH_HOURS: int(user_input.get(OPT_RECENT_MATCH_HOURS, 24)),
            }
            if mode == MODE_HUB:
                enabled = user_input.get(CONF_ENABLED_SENSORS, [SENSOR_MATCHES])
                opts[CONF_ENABLED_SENSORS] = enabled if enabled else [SENSOR_MATCHES]
                team_names = user_input.get(CONF_TEAM_NAMES, [])
                opts[CONF_TEAM_NAMES] = team_names
                opts[CONF_TEAM_IDS] = [self._team_id_map.get(n) for n in team_names]
            return self.async_create_entry(title="", data=opts)

        # For hub mode, fetch teams so the multi-select can show them
        if mode == MODE_HUB:
            sport = self._config_entry.data.get(CONF_SPORT)
            comp_code = self._config_entry.data.get(CONF_COMPETITION_CODE, "")
            profile = get_profile(sport)
            await self._fetch_teams(profile, comp_code)
            self._team_id_map = {t["displayName"]: t["id"] for t in self._teams}

        return self._build_schema(mode)

    def _build_schema(self, mode: str):
        opts = self._config_entry.options
        data = self._config_entry.data

        scan = opts.get(OPT_SCAN_INTERVAL, 3)
        hours = opts.get(OPT_RECENT_MATCH_HOURS, 24)

        schema_dict: dict = {
            vol.Optional(OPT_SCAN_INTERVAL, default=scan): vol.In([1, 2, 3, 5, 10, 15, 30]),
            vol.Optional(OPT_RECENT_MATCH_HOURS, default=hours): vol.In([6, 12, 24, 48]),
        }

        if mode == MODE_HUB:
            sport = data.get(CONF_SPORT)
            comp_code = data.get(CONF_COMPETITION_CODE, "")
            profile = get_profile(sport)
            caps = profile.capabilities

            # Sensor options (sport/competition filtered)
            sensor_opts = [{"value": SENSOR_MATCHES, "label": "Matches & live scores"}]
            if caps.supports_standings:
                sensor_opts.append({"value": SENSOR_STANDINGS, "label": "Standings / league table"})
            if caps.supports_bracket and comp_code in profile.knockout_competitions:
                sensor_opts.append({"value": SENSOR_BRACKET, "label": "Bracket / playoff tree"})
            if caps.supports_news and profile.has_news_url():
                sensor_opts.append({"value": SENSOR_NEWS, "label": "News feed"})

            current_enabled = opts.get(
                CONF_ENABLED_SENSORS,
                data.get(CONF_ENABLED_SENSORS, [o["value"] for o in sensor_opts])
            )
            schema_dict[vol.Optional(CONF_ENABLED_SENSORS, default=current_enabled)] = (
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=sensor_opts, multiple=True, mode=selector.SelectSelectorMode.LIST,
                ))
            )

            # Team picker
            if self._teams:
                team_names_sorted = sorted(t["displayName"] for t in self._teams)
                current_teams = opts.get(CONF_TEAM_NAMES, data.get(CONF_TEAM_NAMES, []))
                schema_dict[vol.Optional(CONF_TEAM_NAMES, default=current_teams)] = (
                    selector.SelectSelector(selector.SelectSelectorConfig(
                        options=team_names_sorted, multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    ))
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )

    async def _fetch_teams(self, profile, competition_code: str) -> None:
        url = profile.teams_url(competition_code)
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, headers=_ESPN_HEADERS, timeout=_TIMEOUT) as resp:
                resp.raise_for_status()
                data = await resp.json()
                sports = data.get("sports", [{}])
                leagues = sports[0].get("leagues", [{}]) if sports else []
                self._teams = [
                    {"id": t["team"]["id"], "displayName": t["team"]["displayName"]}
                    for lg in leagues for t in lg.get("teams", [])
                ]
        except Exception as e:
            _LOGGER.error("Failed to load teams for options: %s", e)
            self._teams = []
