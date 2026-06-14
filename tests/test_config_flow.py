"""Config flow tests (unit-level, no live HA required).

Tests the data-transformation logic in config_flow.py using mocked
aiohttp responses rather than real ESPN calls.
"""
import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Stub HA modules before importing integration code
_MOCK_MODULES = [
    "homeassistant",
    "homeassistant.helpers",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.storage",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.config_entries",
    "homeassistant.core",
    "voluptuous",
]
for mod in _MOCK_MODULES:
    sys.modules.setdefault(mod, MagicMock())

# Make config_entries.ConfigFlow a real base class that accepts domain= kwarg
import homeassistant.config_entries as _ce


class _MockConfigFlow:
    """Minimal ConfigFlow stub that accepts domain= in class definition."""
    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def __init__(self):
        self._errors = {}
        self._data = {}
        self._competitions = {}
        self._teams = []


class _MockOptionsFlow:
    pass


_ce.ConfigFlow = _MockConfigFlow
_ce.OptionsFlow = _MockOptionsFlow
# HANDLERS.register is a class decorator — must return the class unchanged
_ce.HANDLERS = MagicMock()
_ce.HANDLERS.register = lambda domain: (lambda cls: cls)
_ce.callback = lambda fn: fn

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Sample ESPN responses
# ---------------------------------------------------------------------------

SAMPLE_COMPETITIONS = {
    "leagues": [
        {"slug": "ita.1", "name": "Serie A"},
        {"slug": "eng.1", "name": "Premier League"},
        {"slug": "esp.1", "name": "LaLiga"},
    ]
}

SAMPLE_TEAMS = {
    "sports": [
        {
            "leagues": [
                {
                    "teams": [
                        {"team": {"id": "109", "displayName": "Internazionale"}},
                        {"team": {"id": "103", "displayName": "AC Milan"}},
                    ]
                }
            ]
        }
    ]
}


def _make_aiohttp_mock(response_data: dict):
    """Return a properly chained aiohttp mock that returns response_data."""
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=response_data)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_get = MagicMock(return_value=mock_resp)

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    return mock_session


# ---------------------------------------------------------------------------
# Test competition fetching
# ---------------------------------------------------------------------------

class TestFetchCompetitions:

    async def test_returns_dict_for_soccer(self):
        from custom_components.sports_live.config_flow import SportsLiveConfigFlow
        from custom_components.sports_live.sports import get_profile

        flow = SportsLiveConfigFlow()
        flow.hass = MagicMock()
        mock_session = _make_aiohttp_mock(SAMPLE_COMPETITIONS)

        with patch("custom_components.sports_live.config_flow.async_get_clientsession",
                   return_value=mock_session):
            profile = get_profile("soccer")
            comps = await flow._fetch_competitions(profile)

        assert "ita.1" in comps
        assert comps["ita.1"] == "Serie A"
        assert len(comps) == 3

    async def test_returns_rugby_competitions_without_api(self):
        from custom_components.sports_live.config_flow import SportsLiveConfigFlow
        from custom_components.sports_live.sports import get_profile

        flow = SportsLiveConfigFlow()
        profile = get_profile("rugby")
        # Rugby uses hardcoded list — no HTTP call needed
        comps = await flow._fetch_competitions(profile)

        assert "267979" in comps  # Gallagher Premiership
        assert "180659" in comps  # Six Nations
        assert len(comps) >= 5

    async def test_returns_empty_on_network_error(self):
        from custom_components.sports_live.config_flow import SportsLiveConfigFlow
        from custom_components.sports_live.sports import get_profile

        flow = SportsLiveConfigFlow()
        with patch("aiohttp.ClientSession", side_effect=Exception("network error")):
            profile = get_profile("soccer")
            comps = await flow._fetch_competitions(profile)

        assert comps == {}


class TestFetchTeams:

    async def test_populates_teams_list(self):
        from custom_components.sports_live.config_flow import SportsLiveConfigFlow
        from custom_components.sports_live.sports import get_profile

        flow = SportsLiveConfigFlow()
        flow.hass = MagicMock()
        mock_session = _make_aiohttp_mock(SAMPLE_TEAMS)

        with patch("custom_components.sports_live.config_flow.async_get_clientsession",
                   return_value=mock_session):
            profile = get_profile("soccer")
            await flow._fetch_teams(profile, "ita.1")

        assert len(flow._teams) == 2
        names = [t["displayName"] for t in flow._teams]
        assert "Internazionale" in names
        assert "AC Milan" in names

    async def test_empty_teams_on_error(self):
        from custom_components.sports_live.config_flow import SportsLiveConfigFlow
        from custom_components.sports_live.sports import get_profile

        flow = SportsLiveConfigFlow()
        with patch("aiohttp.ClientSession", side_effect=Exception("timeout")):
            profile = get_profile("soccer")
            await flow._fetch_teams(profile, "ita.1")

        assert flow._teams == []


# ---------------------------------------------------------------------------
# Test sport profile URL generation (synchronous)
# ---------------------------------------------------------------------------

class TestProfileURLs:
    def test_soccer_scoreboard_url_contains_dates(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("soccer")
        url = p.scoreboard_url("ita.1", "20240817", "20250601")
        assert "ita.1" in url
        assert "dates=20240817-20250601" in url

    def test_nfl_teams_url(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("nfl")
        url = p.teams_url("nfl")
        assert "football" in url
        assert "nfl" in url
        assert "teams" in url

    def test_rugby_news_url(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("rugby")
        url = p.news_url("267979")
        assert "rugby" in url
        assert "267979" in url
        assert "news" in url

    def test_soccer_standings_url(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("soccer")
        url = p.standings_url("ita.1")
        assert "standings" in url
        assert "ita.1" in url

    def test_nfl_standings_url(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("nfl")
        url = p.standings_url("nfl")
        assert "standings" in url

    def test_soccer_summary_url(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("soccer")
        url = p.summary_url("ita.1", "701234")
        assert "summary" in url
        assert "701234" in url
