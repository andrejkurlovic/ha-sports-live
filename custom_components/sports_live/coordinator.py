"""DataUpdateCoordinator for Sports Live.

One coordinator per config entry. All sensors in an entry share one
coordinator instance so ESPN is hit once per update cycle, not once per sensor.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime, timedelta

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    _LOGGER, DOMAIN,
    CONF_MODE, CONF_SPORT, CONF_COMPETITION_CODE, CONF_TEAM_ID,
    CONF_TEAM_IDS, CONF_TEAM_NAMES, CONF_ENABLED_SENSORS,
    MODE_HUB, MODE_COMPETITION, MODE_TEAM, MODE_MULTI_TEAM, MODE_ALL_TODAY, MODE_NEWS, MODE_MANUAL_TEAM,
    SENSOR_STANDINGS, SENSOR_MATCHES, SENSOR_NEXT_MATCH, SENSOR_SCHEDULE,
    SENSOR_SCHEDULE_ALL, SENSOR_NEWS, SENSOR_BRACKET, SENSOR_ALL_TODAY,
)
from .sports import get_profile

_ESPN_HEADERS = {"Accept-Language": "en"}
_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Module-level season-dates cache: (espn_sport, competition) → (start, end, resolved_at)
# Shared across all coordinators so N entries in the same competition only fetch dates once.
_SEASON_DATES_CACHE: dict[tuple, tuple] = {}


class SportsLiveCoordinator(DataUpdateCoordinator):
    """Fetch and cache all ESPN data needed by this config entry's sensors."""

    def __init__(self, hass, entry, update_interval: timedelta):
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=update_interval,
        )
        self._entry = entry
        self._mode = entry.data.get(CONF_MODE)
        self._sport_id = entry.data.get(CONF_SPORT)
        self._competition = entry.data.get(CONF_COMPETITION_CODE)
        self._team_id = entry.data.get(CONF_TEAM_ID)
        # Options-override: allow editing teams/sensors after setup via options flow
        opts = entry.options
        self._team_ids: list = opts.get(CONF_TEAM_IDS, entry.data.get(CONF_TEAM_IDS, []))
        self._team_names: list = opts.get(CONF_TEAM_NAMES, entry.data.get(CONF_TEAM_NAMES, []))
        self._enabled_sensors: list = opts.get(
            CONF_ENABLED_SENSORS, entry.data.get(CONF_ENABLED_SENSORS, [SENSOR_MATCHES])
        )
        self._profile = get_profile(self._sport_id)

        # Dynamically resolved season dates (per-coordinator; refreshed at most daily)
        self._season_start: datetime | None = None
        self._season_end: datetime | None = None
        self._season_resolved_at: datetime | None = None

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """Fetch all data relevant to this config entry."""
        mode = self._mode
        result: dict = {}

        try:
            if mode == MODE_HUB:
                await self._resolve_season_dates()
                start, end = self._date_range_strs()
                enabled = set(self._enabled_sensors)

                scoreboard_url = self._profile.scoreboard_url(self._competition, start, end)
                result[SENSOR_MATCHES] = await self._fetch(scoreboard_url)

                if SENSOR_STANDINGS in enabled and self._profile.capabilities.supports_standings:
                    result[SENSOR_STANDINGS] = await self._fetch(
                        self._profile.standings_url(self._competition)
                    )

                if SENSOR_NEWS in enabled and self._profile._news_url_tmpl:
                    result[SENSOR_NEWS] = await self._fetch(
                        self._profile.news_url(self._competition)
                    )

                # Per-team schedule fetch (one request per team; no batch API)
                for team_id in self._team_ids:
                    if team_id and self._profile._team_schedule_url_tmpl:
                        result[f"schedule_all_{team_id}"] = await self._fetch(
                            self._profile.team_schedule_url(
                                str(team_id), competition=self._competition or ""
                            )
                        )

            elif mode == MODE_NEWS:
                url = self._profile.news_url(self._competition)
                result[SENSOR_NEWS] = await self._fetch(url)

            elif mode == MODE_ALL_TODAY:
                url = self._profile.all_today_url()
                result[SENSOR_ALL_TODAY] = await self._fetch(url)

            elif mode in (MODE_COMPETITION,):
                # Resolve season dates first
                await self._resolve_season_dates()
                start, end = self._date_range_strs()

                scoreboard_url = self._profile.scoreboard_url(self._competition, start, end)
                result[SENSOR_MATCHES] = await self._fetch(scoreboard_url)

                if self._profile.capabilities.supports_standings:
                    standings_url = self._profile.standings_url(self._competition)
                    result[SENSOR_STANDINGS] = await self._fetch(standings_url)

                if (self._profile.capabilities.supports_news
                        and self._profile._news_url_tmpl):
                    news_url = self._profile.news_url(self._competition)
                    result[SENSOR_NEWS] = await self._fetch(news_url)

            elif mode in (MODE_TEAM, MODE_MANUAL_TEAM):
                await self._resolve_season_dates()
                start, end = self._date_range_strs()

                # Competition scoreboard filtered to team in Python — one call covers all
                scoreboard_url = self._profile.scoreboard_url(self._competition, start, end)
                result[SENSOR_MATCHES] = await self._fetch(scoreboard_url)

                # Cross-competition team schedule (per-team, ESPN has no batch endpoint)
                if (self._team_id and self._profile._team_schedule_url_tmpl):
                    schedule_url = self._profile.team_schedule_url(
                        str(self._team_id), competition=self._competition or ""
                    )
                    result[SENSOR_SCHEDULE_ALL] = await self._fetch(schedule_url)

            elif mode == MODE_MULTI_TEAM:
                # One scoreboard covers all teams; team_schedule still per-team (no batch API).
                await self._resolve_season_dates()
                start, end = self._date_range_strs()

                scoreboard_url = self._profile.scoreboard_url(self._competition, start, end)
                result[SENSOR_MATCHES] = await self._fetch(scoreboard_url)

                for team_id in self._team_ids:
                    if team_id and self._profile._team_schedule_url_tmpl:
                        schedule_url = self._profile.team_schedule_url(
                            str(team_id), competition=self._competition or ""
                        )
                        result[f"schedule_all_{team_id}"] = await self._fetch(schedule_url)

        except Exception as exc:
            raise UpdateFailed(f"ESPN fetch failed: {exc}") from exc

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _fetch(self, url: str) -> dict:
        if not url:
            return {}
        # Reuse Home Assistant's shared aiohttp session instead of building one
        # per request (HA best practice; avoids session churn each cycle).
        session = async_get_clientsession(self.hass)
        retries = 0
        while retries < 3:
            try:
                async with session.get(url, headers=_ESPN_HEADERS, timeout=_TIMEOUT) as resp:
                    if resp.status == 200:
                        raw = await resp.read()
                        return await self.hass.async_add_executor_job(json.loads, raw)
                    if resp.status in (404, 500):
                        _LOGGER.warning("ESPN %s returned %s", url, resp.status)
                        return {}
                    await asyncio.sleep(5)
                    retries += 1
            except (aiohttp.ClientError, asyncio.TimeoutError):
                await asyncio.sleep(5)
                retries += 1
        return {}

    async def _resolve_season_dates(self):
        """Fetch ESPN scoreboard once to extract calendarStartDate/EndDate.

        Two-level cache:
        1. Per-coordinator (24h TTL) — fast path, avoids even the dict lookup.
        2. Module-level keyed by (sport, competition) — shared across all coordinators
           for the same competition so N entries only hit ESPN once per day.
        """
        if self._competition in ("", None):
            return
        now = datetime.now()

        # Fast path: this coordinator already has fresh dates
        if (self._season_start and self._season_end and self._season_resolved_at
                and (now - self._season_resolved_at) < timedelta(hours=24)):
            return

        # Cross-coordinator cache: another entry for same sport+competition resolved already
        cache_key = (self._profile.espn_sport, self._competition)
        cached = _SEASON_DATES_CACHE.get(cache_key)
        if cached:
            start, end, resolved_at = cached
            if (now - resolved_at) < timedelta(hours=24):
                self._season_start = start
                self._season_end = end
                self._season_resolved_at = resolved_at
                return

        url = self._profile.scoreboard_url_plain(self._competition)
        try:
            data = await self._fetch(url)
            leagues = data.get("leagues") or []
            l0 = leagues[0] if leagues else {}
            start = data.get("calendarStartDate") or l0.get("calendarStartDate")
            end = data.get("calendarEndDate") or l0.get("calendarEndDate")
            if start and end:
                self._season_start = datetime.strptime(start[:10], "%Y-%m-%d")
                self._season_end = datetime.strptime(end[:10], "%Y-%m-%d")
        except Exception as e:
            _LOGGER.debug("Could not resolve season dates: %s", e)

        if not self._season_start or not self._season_end:
            self._season_start = now - timedelta(days=240)
            self._season_end = now + timedelta(days=240)

        self._season_resolved_at = now
        _SEASON_DATES_CACHE[cache_key] = (self._season_start, self._season_end, self._season_resolved_at)

    def _date_range_strs(self) -> tuple[str, str]:
        s = (self._season_start or datetime.now() - timedelta(days=240)).strftime("%Y%m%d")
        e = (self._season_end or datetime.now() + timedelta(days=240)).strftime("%Y%m%d")
        return s, e

    async def fetch_summary(self, event_id: str) -> dict:
        """One-off summary fetch for a specific event (used by next_match enrichment)."""
        url = self._profile.summary_url(self._competition, event_id)
        return await self._fetch(url)
