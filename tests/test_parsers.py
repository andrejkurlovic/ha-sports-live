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
            "homeassistant.helpers.aiohttp_client",
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


class TestRugbyStandings:
    def setup_method(self):
        from custom_components.sports_live.parsers.standings import process_standings
        self.parse = process_standings
        self.data = _load("rugby", "standings")

    def test_returns_standings_group(self):
        result = self.parse(self.data)
        assert "standings_groups" in result
        assert result["standings_groups"]

    def test_northampton_is_first(self):
        result = self.parse(self.data)
        standings = result["standings_groups"][0]["standings"]
        assert standings[0]["team_name"] == "Northampton Saints"
        assert standings[0]["rank"] == 1
        assert standings[0]["points"] == "74"

    def test_rugby_specific_stats_present(self):
        result = self.parse(self.data)
        entry = result["standings_groups"][0]["standings"][0]
        # Rugby exposes bonus points and tries
        assert entry["bonus_points"] != "N/A"
        assert entry["tries_for"] != "N/A"
        assert entry["tries_against"] != "N/A"

    def test_wins_draws_losses_resolved(self):
        result = self.parse(self.data)
        entry = result["standings_groups"][0]["standings"][0]
        # gamesWon / gamesDrawn / gamesLost aliases should resolve
        assert entry["wins"] != "N/A"
        assert entry["draws"] != "N/A"
        assert entry["losses"] != "N/A"


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

    def test_rugby_has_standings(self):
        from custom_components.sports_live.sports import get_profile
        p = get_profile("rugby")
        assert p.capabilities.supports_standings

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


# ---------------------------------------------------------------------------
# UK Broadcast Rights
# ---------------------------------------------------------------------------

class TestUKBroadcastRights:
    def test_known_competition_returns_channels(self):
        from custom_components.sports_live.broadcast_rights import get_uk_channels
        channels = get_uk_channels("eng.1")
        assert "Sky Sports" in channels

    def test_rugby_premiership_is_tnt(self):
        from custom_components.sports_live.broadcast_rights import get_uk_channels
        channels = get_uk_channels("267979")
        assert "TNT Sports" in channels

    def test_six_nations_is_bbc_itv(self):
        from custom_components.sports_live.broadcast_rights import get_uk_channels
        channels = get_uk_channels("180659")
        assert "BBC" in channels
        assert "ITV" in channels

    def test_nfl_includes_sky(self):
        from custom_components.sports_live.broadcast_rights import get_uk_channels
        channels = get_uk_channels("nfl")
        assert "Sky Sports" in channels

    def test_unknown_competition_returns_empty(self):
        from custom_components.sports_live.broadcast_rights import get_uk_channels
        assert get_uk_channels("unknown.competition") == []

    def test_enrich_adds_broadcast_uk_field(self):
        from custom_components.sports_live.broadcast_rights import enrich_matches_with_uk_broadcast
        matches = [{"home_team": "Arsenal", "broadcast": "NBC"}]
        enrich_matches_with_uk_broadcast(matches, "eng.1")
        assert "broadcast_uk" in matches[0]
        assert "Sky Sports" in matches[0]["broadcast_uk"]

    def test_enrich_preserves_existing_broadcast(self):
        from custom_components.sports_live.broadcast_rights import enrich_matches_with_uk_broadcast
        matches = [{"broadcast": "NBC"}]
        enrich_matches_with_uk_broadcast(matches, "eng.1")
        assert matches[0]["broadcast"] == "NBC"

    def test_enrich_unknown_competition_gives_empty_string(self):
        from custom_components.sports_live.broadcast_rights import enrich_matches_with_uk_broadcast
        matches = [{"broadcast": ""}]
        enrich_matches_with_uk_broadcast(matches, "unknown.xyz")
        assert matches[0]["broadcast_uk"] == ""


# ---------------------------------------------------------------------------
# Home/away resolution by homeAway field (not array index)
# ---------------------------------------------------------------------------

class TestHomeAwayResolution:
    def _event(self, competitors):
        return {
            "events": [{
                "id": "1",
                "date": "2026-06-14T18:00Z",
                "status": {"type": {"state": "post", "description": "Final"}},
                "competitions": [{"competitors": competitors}],
            }]
        }

    def test_away_listed_first_still_maps_correctly(self):
        from custom_components.sports_live.parsers.scoreboard import process_scoreboard
        # ESPN sometimes lists the away competitor at index 0.
        competitors = [
            {"homeAway": "away", "score": "1",
             "team": {"displayName": "Away FC"}},
            {"homeAway": "home", "score": "3",
             "team": {"displayName": "Home FC"}},
        ]
        result = process_scoreboard(self._event(competitors), _mock_hass())
        m = result["matches"][0]
        assert m["home_team"] == "Home FC"
        assert m["away_team"] == "Away FC"
        assert m["home_score"] == "3"
        assert m["away_score"] == "1"

    def test_index_fallback_when_homeaway_absent(self):
        from custom_components.sports_live.parsers.scoreboard import process_scoreboard
        competitors = [
            {"score": "2", "team": {"displayName": "First"}},
            {"score": "0", "team": {"displayName": "Second"}},
        ]
        result = process_scoreboard(self._event(competitors), _mock_hass())
        m = result["matches"][0]
        assert m["home_team"] == "First"
        assert m["away_team"] == "Second"


# ---------------------------------------------------------------------------
# Summary parser — scoring plays, win probability, stat leaders (all sports)
# ---------------------------------------------------------------------------

class TestSummaryParser:
    def test_parses_scoring_plays(self):
        from custom_components.sports_live.parsers.summary import process_summary
        data = {"plays": [
            {"scoringPlay": False, "text": "Jump ball"},
            {"scoringPlay": True, "text": "Brunson makes 3pt",
             "homeScore": 55, "awayScore": 48,
             "period": {"displayValue": "3rd Quarter"},
             "clock": {"displayValue": "7:12"}, "team": {"id": "18"},
             "scoreValue": 3},
        ]}
        out = process_summary(data)
        assert len(out["scoring_plays"]) == 1
        sp = out["scoring_plays"][0]
        assert sp["home_score"] == 55
        assert sp["period"] == "3rd Quarter"
        assert sp["team_id"] == "18"

    def test_win_probability_from_summary(self):
        from custom_components.sports_live.parsers.summary import process_summary
        data = {"winprobability": [
            {"homeWinPercentage": 0.4, "tiePercentage": 0.0},
            {"homeWinPercentage": 0.93, "tiePercentage": 0.0},
        ]}
        out = process_summary(data)
        assert out["summary_home_win_probability"] == 93.0
        assert out["summary_away_win_probability"] == 7.0

    def test_stat_leaders_parsed(self):
        from custom_components.sports_live.parsers.summary import process_summary
        data = {"leaders": [{
            "team": {"id": "5", "displayName": "Lakers"},
            "leaders": [
                {"name": "points", "displayName": "Points",
                 "leaders": [{"displayValue": "30",
                              "athlete": {"displayName": "Player A",
                                          "shortName": "A. Player"}}]},
            ],
        }]}
        out = process_summary(data)
        assert len(out["stat_leaders"]) == 1
        tl = out["stat_leaders"][0]
        assert tl["team_name"] == "Lakers"
        assert tl["categories"][0]["athlete"] == "Player A"
        assert tl["categories"][0]["value"] == "30"

    def test_empty_summary_safe(self):
        from custom_components.sports_live.parsers.summary import process_summary
        out = process_summary({})
        assert out["scoring_plays"] == []
        assert out["stat_leaders"] == []
        assert "summary_home_win_probability" not in out
