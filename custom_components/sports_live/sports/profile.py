"""Sport profile dataclass — defines per-sport ESPN URL patterns and capability flags."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class SportCapabilities:
    supports_standings: bool = False
    supports_news: bool = True
    supports_next_match: bool = True
    supports_team_schedule: bool = True
    supports_summary: bool = False
    supports_bracket: bool = False
    supports_lineup: bool = False


@dataclass(frozen=True)
class SportProfile:
    """All ESPN API configuration and capability metadata for one sport."""

    sport_id: str                     # internal key: "soccer" | "nfl" | "rugby"
    display_name: str                  # shown in UI
    espn_sport: str                    # ESPN sport path segment: "soccer", "football", "rugby"
    icon: str                          # mdi icon
    capabilities: SportCapabilities

    # Whether competition codes are numeric IDs (rugby) or text slugs (soccer/football)
    numeric_competition_ids: bool = False

    # How scoring is described for events
    score_event_label: str = "Score"
    discipline_event_label: str = "Discipline"

    # Competitions that have a knockout bracket
    knockout_competitions: frozenset = field(default_factory=frozenset)

    # --- URL builder callables ---
    # Each receives (competition_code: str) or just the base and returns the URL string.
    # These are provided by the registry, not user-configurable.
    _competitions_url: str = ""        # competitions discovery URL
    _teams_url_tmpl: str = ""          # .format(competition=code)
    _scoreboard_url_tmpl: str = ""     # .format(competition=code, start=YYYYMMDD, end=YYYYMMDD)
    _standings_url_tmpl: str = ""      # .format(competition=code)
    _news_url_tmpl: str = ""           # .format(competition=code)
    _summary_url_tmpl: str = ""        # .format(competition=code, event_id=id)
    _team_schedule_url_tmpl: str = ""  # .format(team_id=id)
    _all_today_url: str = ""           # no parameters

    def competitions_url(self) -> str:
        return self._competitions_url

    def teams_url(self, competition: str) -> str:
        return self._teams_url_tmpl.format(competition=competition)

    def scoreboard_url(self, competition: str, start: str, end: str) -> str:
        return self._scoreboard_url_tmpl.format(competition=competition, start=start, end=end)

    def scoreboard_url_plain(self, competition: str) -> str:
        """Scoreboard without date range — used for calendar/season discovery."""
        return f"https://site.api.espn.com/apis/site/v2/sports/{self.espn_sport}/{competition}/scoreboard"

    def standings_url(self, competition: str) -> str:
        return self._standings_url_tmpl.format(competition=competition)

    def news_url(self, competition: str) -> str:
        return self._news_url_tmpl.format(competition=competition)

    def summary_url(self, competition: str, event_id: str) -> str:
        return self._summary_url_tmpl.format(competition=competition, event_id=event_id)

    def team_schedule_url(self, team_id: str, competition: str = "") -> str:
        return self._team_schedule_url_tmpl.format(team_id=team_id, competition=competition)

    def all_today_url(self) -> str:
        return self._all_today_url
