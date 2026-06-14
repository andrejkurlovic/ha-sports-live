"""Multi-sport config flow for Sports Live.

Flow:
  user → sport → mode → competition → [team] → done

Options flow exposes scan_interval and recent_match_hours.
"""
from __future__ import annotations
import aiohttp

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    _LOGGER, DOMAIN,
    CONF_MODE, CONF_SPORT, CONF_COMPETITION_CODE, CONF_COMPETITION_NAME,
    CONF_TEAM_ID, CONF_TEAM_NAME,
    MODE_COMPETITION, MODE_TEAM, MODE_ALL_TODAY, MODE_NEWS, MODE_MANUAL_TEAM,
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
                sport = self._data[CONF_SPORT]
                profile = get_profile(sport)
                self._data[CONF_COMPETITION_CODE] = "all"
                return self.async_create_entry(
                    title=f"All Matches Today ({profile.display_name})",
                    data=self._data,
                )

            if mode == MODE_MANUAL_TEAM:
                return await self.async_step_manual_team()

            return await self.async_step_competition()

        mode_options = {
            MODE_COMPETITION: "Competition / League",
            MODE_TEAM: "Specific Team",
            MODE_ALL_TODAY: "All Matches Today",
            MODE_NEWS: "News Feed",
            MODE_MANUAL_TEAM: "Manual Team ID",
        }
        return self.async_show_form(
            step_id="mode",
            data_schema=vol.Schema({
                vol.Required(CONF_MODE, default=MODE_COMPETITION): vol.In(mode_options),
            }),
            errors=self._errors,
        )

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
            mode = self._data.get(CONF_MODE)

            if mode == MODE_TEAM:
                await self._fetch_teams(profile, code)
                return await self.async_step_team()

            # competition or news modes
            prefix = "News" if mode == MODE_NEWS else profile.display_name
            return self.async_create_entry(
                title=f"{prefix} — {name}",
                data=self._data,
            )

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

    # ------------------------------------------------------------------ step_team
    async def async_step_team(self, user_input=None):
        """Step 4 (team mode): choose team."""
        self._errors = {}
        if user_input is not None:
            display_name = user_input.get(CONF_TEAM_NAME)
            selected = next((t for t in self._teams if t["displayName"] == display_name), None)
            team_id = selected["id"] if selected else None
            self._data[CONF_TEAM_NAME] = display_name
            self._data[CONF_TEAM_ID] = team_id

            profile = get_profile(self._data[CONF_SPORT])
            comp_name = self._data.get(CONF_COMPETITION_NAME, "")
            return self.async_create_entry(
                title=f"{profile.display_name} — {comp_name} — {display_name}",
                data=self._data,
            )

        if not self._teams:
            self._errors["base"] = "cannot_load_teams"

        team_opts = {t["displayName"]: t["displayName"]
                     for t in sorted(self._teams, key=lambda t: t["displayName"])}
        return self.async_show_form(
            step_id="team",
            data_schema=vol.Schema({
                vol.Required(CONF_TEAM_NAME): vol.In(team_opts) if team_opts else str,
            }),
            errors=self._errors,
        )

    # ------------------------------------------------------------------ step_manual_team
    async def async_step_manual_team(self, user_input=None):
        """Alternate team step: enter team ID manually + pick competition."""
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
        """Returns {code: name} dict for UI selector."""
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


class SportsLiveOptionsFlow(config_entries.OptionsFlow):

    def __init__(self, config_entry):
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        scan = self._config_entry.options.get("scan_interval", 3)
        hours = self._config_entry.options.get("recent_match_hours", 24)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("scan_interval", default=scan): vol.In([1, 2, 3, 5, 10, 15, 30]),
                vol.Optional("recent_match_hours", default=hours): vol.In([6, 12, 24, 48]),
            }),
        )
