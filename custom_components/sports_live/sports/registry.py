"""Sport registry: one SportProfile per supported sport.

ESPN base URLs used:
  Soccer:      https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/
  Football:    https://site.api.espn.com/apis/site/v2/sports/football/{league}/
  Rugby:       https://site.api.espn.com/apis/site/v2/sports/rugby/{league}/
  Basketball:  https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/
  Hockey:      https://site.api.espn.com/apis/site/v2/sports/hockey/{league}/
  Baseball:    https://site.api.espn.com/apis/site/v2/sports/baseball/{league}/
  Cricket:     https://site.api.espn.com/apis/site/v2/sports/cricket/{league}/
  Tennis:      https://site.api.espn.com/apis/site/v2/sports/tennis/{league}/
  MMA:         https://site.api.espn.com/apis/site/v2/sports/mma/{league}/

Rugby uses numeric league IDs; all other sports use text slugs.
"""
from __future__ import annotations
from .profile import SportCapabilities, SportProfile

_SOCCER = SportProfile(
    sport_id="soccer",
    display_name="Football / Soccer",
    espn_sport="soccer",
    icon="mdi:soccer",
    capabilities=SportCapabilities(
        supports_standings=True,
        supports_news=True,
        supports_next_match=True,
        supports_team_schedule=True,
        supports_summary=True,
        supports_bracket=True,
        supports_lineup=True,
    ),
    numeric_competition_ids=False,
    score_event_label="Goal",
    discipline_event_label="Card",
    knockout_competitions=frozenset({
        "uefa.champions",
        "uefa.europa",
        "uefa.europa.conf",
        "uefa.euro",
        "uefa.nations",
        "uefa.wchampions",
        "fifa.world",
        "fifa.wwc",
        "fifa.cwc",
        "concacaf.champions",
        "concacaf.gold",
        "concacaf.nations.league",
        "ita.coppa_italia",
        "eng.fa",
        "eng.league_cup",
        "esp.copa_del_rey",
        "ger.dfb_pokal",
        "fra.coupe_de_france",
    }),
    _competitions_url=(
        "https://site.api.espn.com/apis/site/v2/leagues/dropdown"
        "?lang=en&region=us&calendartype=whitelist&limit=200&sport=soccer"
    ),
    _teams_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/soccer/{competition}/teams"
    ),
    _scoreboard_url_tmpl=(
        "https://site.web.api.espn.com/apis/site/v2/sports/soccer/{competition}"
        "/scoreboard?limit=1000&dates={start}-{end}"
    ),
    _standings_url_tmpl=(
        "https://site.web.api.espn.com/apis/v2/sports/soccer/{competition}/standings"
    ),
    _news_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/soccer/{competition}/news?limit=15"
    ),
    _summary_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/soccer/{competition}/summary?event={event_id}"
    ),
    _team_schedule_url_tmpl=(
        "https://site.web.api.espn.com/apis/site/v2/sports/soccer/all/teams/{team_id}/schedule?fixture=true"
    ),
    _all_today_url="https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard",
)

_NFL = SportProfile(
    sport_id="nfl",
    display_name="American Football (NFL)",
    espn_sport="football",
    icon="mdi:football",
    capabilities=SportCapabilities(
        supports_standings=True,
        supports_news=True,
        supports_next_match=True,
        supports_team_schedule=True,
        supports_summary=False,
        supports_bracket=True,     # NFL playoffs
        supports_lineup=False,
    ),
    numeric_competition_ids=False,
    score_event_label="Touchdown / Score",
    discipline_event_label="Penalty",
    knockout_competitions=frozenset({"nfl"}),    # every NFL season has a playoff bracket
    # NFL: competitions are pre-defined; we only show a curated list
    _competitions_url=(
        "https://site.api.espn.com/apis/site/v2/leagues/dropdown"
        "?lang=en&region=us&calendartype=whitelist&limit=200&sport=football"
    ),
    _teams_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/football/{competition}/teams"
    ),
    _scoreboard_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/football/{competition}"
        "/scoreboard?limit=1000&dates={start}-{end}"
    ),
    _standings_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/football/{competition}/standings"
    ),
    _news_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/football/{competition}/news?limit=15"
    ),
    _summary_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/football/{competition}/summary?event={event_id}"
    ),
    _team_schedule_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule"
    ),
    _all_today_url="https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
)

# Rugby uses numeric league IDs — we provide a curated known list.
RUGBY_COMPETITIONS: dict[str, str] = {
    "267979": "Gallagher Premiership (England)",
    "180659": "Six Nations",
    "270557": "United Rugby Championship",
    "271937": "Heineken Champions Cup",
    "272073": "European Rugby Challenge Cup",
    "270559": "Top 14 (France)",
    "242041": "Super Rugby Pacific",
    "244293": "The Rugby Championship",
    "164205": "Rugby World Cup",
    "289237": "Women's Rugby World Cup",
    "268565": "British & Irish Lions Tour",
    "289262": "Major League Rugby",
    "17567": "Nations Championship",
    "289234": "International Test Match",
}

_RUGBY = SportProfile(
    sport_id="rugby",
    display_name="Rugby Union",
    espn_sport="rugby",
    icon="mdi:rugby",
    capabilities=SportCapabilities(
        supports_standings=True,
        supports_news=True,
        supports_next_match=True,
        supports_team_schedule=True,
        supports_summary=False,
        supports_bracket=False,
        supports_lineup=False,
    ),
    numeric_competition_ids=True,
    score_event_label="Try / Score",
    discipline_event_label="Card",
    knockout_competitions=frozenset(),
    _competitions_url="",           # not used; registry provides RUGBY_COMPETITIONS directly
    _teams_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/rugby/{competition}/teams"
    ),
    _scoreboard_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/rugby/{competition}"
        "/scoreboard?limit=1000&dates={start}-{end}"
    ),
    _standings_url_tmpl=(
        "https://site.web.api.espn.com/apis/v2/sports/rugby/{competition}/standings"
    ),
    _news_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/rugby/{competition}/news?limit=15"
    ),
    _summary_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/rugby/{competition}/summary?event={event_id}"
    ),
    _team_schedule_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/rugby/{competition}/teams/{team_id}/schedule"
    ),
    _all_today_url="https://site.api.espn.com/apis/site/v2/sports/rugby/all/scoreboard",
)

_NBA = SportProfile(
    sport_id="nba",
    display_name="Basketball (NBA)",
    espn_sport="basketball",
    icon="mdi:basketball",
    capabilities=SportCapabilities(
        supports_standings=True,
        supports_news=True,
        supports_next_match=True,
        supports_team_schedule=True,
        supports_summary=False,
        supports_bracket=True,
        supports_lineup=False,
    ),
    numeric_competition_ids=False,
    score_event_label="Score",
    discipline_event_label="Foul",
    knockout_competitions=frozenset({"nba"}),
    _competitions_url=(
        "https://site.api.espn.com/apis/site/v2/leagues/dropdown"
        "?lang=en&region=us&calendartype=whitelist&limit=200&sport=basketball"
    ),
    _teams_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/basketball/{competition}/teams"
    ),
    _scoreboard_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/basketball/{competition}"
        "/scoreboard?limit=1000&dates={start}-{end}"
    ),
    _standings_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/basketball/{competition}/standings"
    ),
    _news_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/basketball/{competition}/news?limit=15"
    ),
    _summary_url_tmpl="",
    _team_schedule_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/basketball/{competition}/teams/{team_id}/schedule"
    ),
    _all_today_url="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
)

_NHL = SportProfile(
    sport_id="nhl",
    display_name="Ice Hockey (NHL)",
    espn_sport="hockey",
    icon="mdi:hockey-puck",
    capabilities=SportCapabilities(
        supports_standings=True,
        supports_news=True,
        supports_next_match=True,
        supports_team_schedule=True,
        supports_summary=False,
        supports_bracket=True,
        supports_lineup=False,
    ),
    numeric_competition_ids=False,
    score_event_label="Goal",
    discipline_event_label="Penalty",
    knockout_competitions=frozenset({"nhl"}),
    _competitions_url=(
        "https://site.api.espn.com/apis/site/v2/leagues/dropdown"
        "?lang=en&region=us&calendartype=whitelist&limit=200&sport=hockey"
    ),
    _teams_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/hockey/{competition}/teams"
    ),
    _scoreboard_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/hockey/{competition}"
        "/scoreboard?limit=1000&dates={start}-{end}"
    ),
    _standings_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/hockey/{competition}/standings"
    ),
    _news_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/hockey/{competition}/news?limit=15"
    ),
    _summary_url_tmpl="",
    _team_schedule_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/hockey/{competition}/teams/{team_id}/schedule"
    ),
    _all_today_url="https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
)

_MLB = SportProfile(
    sport_id="mlb",
    display_name="Baseball (MLB)",
    espn_sport="baseball",
    icon="mdi:baseball",
    capabilities=SportCapabilities(
        supports_standings=True,
        supports_news=True,
        supports_next_match=True,
        supports_team_schedule=True,
        supports_summary=False,
        supports_bracket=True,
        supports_lineup=False,
    ),
    numeric_competition_ids=False,
    score_event_label="Run",
    discipline_event_label="Ejection",
    knockout_competitions=frozenset({"mlb"}),
    _competitions_url=(
        "https://site.api.espn.com/apis/site/v2/leagues/dropdown"
        "?lang=en&region=us&calendartype=whitelist&limit=200&sport=baseball"
    ),
    _teams_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/baseball/{competition}/teams"
    ),
    _scoreboard_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/baseball/{competition}"
        "/scoreboard?limit=1000&dates={start}-{end}"
    ),
    _standings_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/baseball/{competition}/standings"
    ),
    _news_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/baseball/{competition}/news?limit=15"
    ),
    _summary_url_tmpl="",
    _team_schedule_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/baseball/{competition}/teams/{team_id}/schedule"
    ),
    _all_today_url="https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
)

# Cricket uses numeric competition IDs dynamically discovered from the ESPN API.
_CRICKET = SportProfile(
    sport_id="cricket",
    display_name="Cricket",
    espn_sport="cricket",
    icon="mdi:cricket",
    capabilities=SportCapabilities(
        supports_standings=False,
        supports_news=True,
        supports_next_match=True,
        supports_team_schedule=False,
        supports_summary=False,
        supports_bracket=False,
        supports_lineup=False,
    ),
    numeric_competition_ids=False,   # slugs happen to be numbers; fetched dynamically
    score_event_label="Wicket",
    discipline_event_label="Dismissal",
    knockout_competitions=frozenset(),
    _competitions_url=(
        "https://site.api.espn.com/apis/site/v2/leagues/dropdown"
        "?lang=en&region=us&calendartype=whitelist&limit=200&sport=cricket"
    ),
    _teams_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/cricket/{competition}/teams"
    ),
    _scoreboard_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/cricket/{competition}"
        "/scoreboard?limit=1000&dates={start}-{end}"
    ),
    _standings_url_tmpl="",
    _news_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/cricket/{competition}/news?limit=15"
    ),
    _summary_url_tmpl="",
    _team_schedule_url_tmpl="",
    _all_today_url="https://site.api.espn.com/apis/site/v2/sports/cricket/all/scoreboard",
)

# Tennis: ATP and WTA are the two top-level tour competitions.
TENNIS_COMPETITIONS: dict[str, str] = {
    "atp": "ATP (Men's)",
    "wta": "WTA (Women's)",
}

_TENNIS = SportProfile(
    sport_id="tennis",
    display_name="Tennis",
    espn_sport="tennis",
    icon="mdi:tennis",
    capabilities=SportCapabilities(
        supports_standings=False,
        supports_news=True,
        supports_next_match=True,
        supports_team_schedule=False,
        supports_summary=False,
        supports_bracket=False,
        supports_lineup=False,
    ),
    numeric_competition_ids=True,    # use TENNIS_COMPETITIONS static list
    score_event_label="Set",
    discipline_event_label="Warning",
    knockout_competitions=frozenset(),
    _competitions_url="",
    _teams_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/tennis/{competition}/teams"
    ),
    _scoreboard_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/tennis/{competition}"
        "/scoreboard?limit=1000&dates={start}-{end}"
    ),
    _standings_url_tmpl="",
    _news_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/tennis/{competition}/news?limit=15"
    ),
    _summary_url_tmpl="",
    _team_schedule_url_tmpl="",
    _all_today_url="https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard",
)

_MMA = SportProfile(
    sport_id="mma",
    display_name="MMA / UFC",
    espn_sport="mma",
    icon="mdi:karate",
    capabilities=SportCapabilities(
        supports_standings=False,
        supports_news=True,
        supports_next_match=True,
        supports_team_schedule=False,
        supports_summary=False,
        supports_bracket=False,
        supports_lineup=False,
    ),
    numeric_competition_ids=False,
    score_event_label="KO / Decision",
    discipline_event_label="Disqualification",
    knockout_competitions=frozenset(),
    _competitions_url=(
        "https://site.api.espn.com/apis/site/v2/leagues/dropdown"
        "?lang=en&region=us&calendartype=whitelist&limit=200&sport=mma"
    ),
    _teams_url_tmpl="",
    _scoreboard_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/mma/{competition}"
        "/scoreboard?limit=1000&dates={start}-{end}"
    ),
    _standings_url_tmpl="",
    _news_url_tmpl=(
        "https://site.api.espn.com/apis/site/v2/sports/mma/{competition}/news?limit=15"
    ),
    _summary_url_tmpl="",
    _team_schedule_url_tmpl="",
    _all_today_url="https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard",
)

SPORT_REGISTRY: dict[str, SportProfile] = {
    "soccer": _SOCCER,
    "nfl": _NFL,
    "rugby": _RUGBY,
    "nba": _NBA,
    "nhl": _NHL,
    "mlb": _MLB,
    "cricket": _CRICKET,
    "tennis": _TENNIS,
    "mma": _MMA,
}


def get_profile(sport_id: str) -> SportProfile:
    return SPORT_REGISTRY[sport_id]


def list_sports() -> dict[str, str]:
    """Returns {sport_id: display_name} for UI selectors."""
    return {k: v.display_name for k, v in SPORT_REGISTRY.items()}
