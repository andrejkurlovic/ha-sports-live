"""Tests for sport-agnostic parsers using saved ESPN fixtures."""
import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Allow importing the integration without a full HA install
sys.path.insert(0, str(Path(__file__).parent.parent))

# Stub out HA modules before importing integration code
for mod in ["homeassistant", "homeassistant.helpers",
            "homeassistant.helpers.update_coordinator",
            "homeassistant.helpers.entity",
            "homeassistant.helpers.storage",
            "homeassistant.components",
            "homeassistant.components.sensor",
            "homeassistant.config_entries",
            "homeassistant.core"]:
    sys.modules.setdefault(mod, MagicMock())

FIXTURES = Path(__file__).parent / "fixtures"


def _load(sport: str, name: str) -> dict:
    return json.loads((FIXTURES / sport / f"{name}.json").read_text())


def _mock_hass():
    hass = MagicMock()
    hass.config.time_zone = "UTC"
    return hass


# ---------------------------------------------------------------------------
# Scoreboard parser
# ---------------------------------------------------------------------------

class TestSoccerScoreboard:
    def setup_method(self):
        from custom_components.sports_live.parsers.scoreboard import process_scoreboard
        self.parse = process_scoreboard
        self.data = _load("soccer", "scoreboard")
        self.hass = _mock_hass()

    def test_returns_two_matches(self):
        result = self.parse(self.data, self.hass)
        assert len(result["matches"]) == 2

    def test_pre_match_state(self):
        result = self.parse(self.data, self.hass)
        pre = [m for m in result["matches"] if m["state"] == "pre"]
        assert pre, "Expected at least one pre-match"
        match = pre[0]
        assert "Internazionale" in match["home_team"]
        assert "AC Milan" in match["away_team"]

    def test_post_match_state(self):
        result = self.parse(self.data, self.hass)
        post = [m for m in result["matches"] if m["state"] == "post"]
        assert post
        match = post[0]
        assert match["home_score"] == "1"
        assert match["away_score"] == "1"

    def test_team_filter(self):
        result = self.parse(self.data, self.hass, team_name="Internazionale")
        assert all("Internazionale" in (m["home_team"] + m["away_team"]) for m in result["matches"])

    def test_next_match_only_returns_one(self):
        result = self.parse(self.data, self.hass, next_match_only=True)
        # Should prioritise live > recent_post > pre
        assert result["next_match"] is not None

    def test_match_details_parsed(self):
        result = self.parse(self.data, self.hass)
        post = [m for m in result["matches"] if m["state"] == "post"]
        assert post
        # The Juventus-Napoli match has 2 goals in details
        assert len(post[0]["match_details"]) == 2

    def test_league_info_extracted(self):
        result = self.parse(self.data, self.hass)
        assert result["league_info"]
        assert result["league_info"][0]["abbreviation"] == "ITA.1"

    def test_date_range_filter_excludes_out_of_range(self):
        # All events are in April 2025; filtering to 2024 should exclude them
        result = self.parse(
            self.data, self.hass,
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
        assert result["matches"] == []


class TestNFLScoreboard:
    def setup_method(self):
        from custom_components.sports_live.parsers.scoreboard import process_scoreboard
        self.parse = process_scoreboard
        self.data = _load("nfl", "scoreboard")
        self.hass = _mock_hass()

    def test_returns_one_match(self):
        result = self.parse(self.data, self.hass)
        assert len(result["matches"]) == 1

    def test_chiefs_won(self):
        result = self.parse(self.data, self.hass)
        m = result["matches"][0]
        assert m["home_score"] == "22"
        assert m["away_score"] == "19"
        assert m["state"] == "post"

    def test_venue_and_city(self):
        result = self.parse(self.data, self.hass)
        m = result["matches"][0]
        assert "Superdome" in m["venue"]
        assert m["venue_city"] == "New Orleans"

    def test_broadcasting(self):
        result = self.parse(self.data, self.hass)
        m = result["matches"][0]
        assert m["broadcast"] == "CBS"


class TestRugbyScoreboard:
    def setup_method(self):
        from custom_components.sports_live.parsers.scoreboard import process_scoreboard
        self.parse = process_scoreboard
        self.data = _load("rugby", "scoreboard")
        self.hass = _mock_hass()

    def test_returns_one_match(self):
        result = self.parse(self.data, self.hass)
        assert len(result["matches"]) == 1

    def test_pre_state(self):
        result = self.parse(self.data, self.hass)
        m = result["matches"][0]
        assert m["state"] == "pre"
        assert "Bath Rugby" in m["home_team"]
        assert "Harlequins" in m["away_team"]

    def test_records_parsed(self):
        result = self.parse(self.data, self.hass)
        m = result["matches"][0]
        assert m["home_record"] == "16-2-2"


# ---------------------------------------------------------------------------
# Standings parser
# ---------------------------------------------------------------------------

class TestSoccerStandings:
    def setup_method(self):
        from custom_components.sports_live.parsers.standings import process_standings
        self.parse = process_standings
        self.data = _load("soccer", "standings")

    def test_returns_standings_groups(self):
        result = self.parse(self.data)
        assert "standings_groups" in result
        assert result["standings_groups"]

    def test_inter_is_first(self):
        result = self.parse(self.data)
        group = result["standings_groups"][0]
        standings = group["standings"]
        assert standings[0]["team_name"] == "Internazionale"
        assert standings[0]["rank"] == 1
        assert standings[0]["points"] == "74"

    def test_goals_for_against(self):
        result = self.parse(self.data)
        group = result["standings_groups"][0]
        inter = group["standings"][0]
        assert inter["goals_for"] == "72"
        assert inter["goals_against"] == "24"
        assert inter["goal_difference"] == "+48"

    def test_season_dynamic(self):
        result = self.parse(self.data)
        # Should not hardcode 2024 — picks current year or nearby
        assert result["season"] != "N/A"


# ---------------------------------------------------------------------------
# Bracket parser
# ---------------------------------------------------------------------------

class TestBracketParser:
    def setup_method(self):
        from custom_components.sports_live.parsers.bracket import process_bracket
        self.parse = process_bracket

    def test_empty_data_returns_structure(self):
        result = self.parse({})
        assert result["rounds"] == []
        assert result["ties_count"] == 0

    def test_no_valid_events_empty_rounds(self):
        data = {
            "events": [
                {
                    "id": "x",
                    "date": "2025-03-05T20:00Z",
                    "status": {"type": {"state": "post"}},
                    "competitions": [
                        {
                            "notes": [],   # no note → not a KO game
                            "competitors": []
                        }
                    ]
                }
            ]
        }
        result = self.parse(data)
        assert result["rounds"] == []


# ---------------------------------------------------------------------------
# News parser
# ---------------------------------------------------------------------------

class TestNewsParser:
    def setup_method(self):
        from custom_components.sports_live.parsers.scoreboard import process_news
        self.parse = process_news

    def test_empty_returns_empty_list(self):
        assert self.parse({}) == []

    def test_parses_articles(self):
        data = {
            "articles": [
                {
                    "headline": "Napoli win title",
                    "description": "SSC Napoli won the Serie A title.",
                    "published": "2025-04-21T20:00Z",
                    "images": [{"url": "https://example.com/img.jpg"}],
                    "links": {"web": {"href": "https://espn.com/story/1"}},
                    "categories": [{"type": "league", "description": "Serie A"}],
                    "type": "Story",
                }
            ]
        }
        result = self.parse(data)
        assert len(result) == 1
        assert result[0]["headline"] == "Napoli win title"
        assert result[0]["category"] == "Serie A"
        assert result[0]["link"] == "https://espn.com/story/1"


# ---------------------------------------------------------------------------
# Sport registry
# ---------------------------------------------------------------------------

class TestSportRegistry:
    def test_all_sports_present(self):
        from custom_components.sports_live.sports.registry import SPORT_REGISTRY
        assert "soccer" in SPORT_REGISTRY
        assert "nfl" in SPORT_REGISTRY
        assert "rugby" in SPORT_REGISTRY

    def test_soccer_has_standings(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("soccer")
        assert p.capabilities.supports_standings

    def test_nfl_has_standings(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("nfl")
        assert p.capabilities.supports_standings

    def test_rugby_no_standings(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("rugby")
        assert not p.capabilities.supports_standings

    def test_soccer_has_lineup(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("soccer")
        assert p.capabilities.supports_lineup

    def test_nfl_no_lineup(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("nfl")
        assert not p.capabilities.supports_lineup

    def test_url_templates_build_correctly(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("soccer")
        url = p.scoreboard_url("ita.1", "20240817", "20250601")
        assert "ita.1" in url
        assert "20240817" in url
        assert "20250601" in url

    def test_rugby_numeric_competition_ids(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("rugby")
        assert p.numeric_competition_ids

    def test_nfl_knockout_competitions_include_nfl(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("nfl")
        assert "nfl" in p.knockout_competitions
