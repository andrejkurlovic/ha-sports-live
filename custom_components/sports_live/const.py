import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "sports_live"

# Config entry data keys
CONF_MODE = "mode"
CONF_SPORT = "sport"
CONF_COMPETITION_CODE = "competition_code"
CONF_COMPETITION_NAME = "competition_name"
CONF_TEAM_ID = "team_id"
CONF_TEAM_NAME = "team_name"

# Modes
MODE_COMPETITION = "competition"
MODE_TEAM = "team"
MODE_ALL_TODAY = "all_today"
MODE_NEWS = "news"
MODE_MANUAL_TEAM = "manual_team"

# Sports
SPORT_SOCCER = "soccer"
SPORT_NFL = "nfl"
SPORT_RUGBY = "rugby"
SPORT_NBA = "nba"
SPORT_NHL = "nhl"
SPORT_MLB = "mlb"
SPORT_CRICKET = "cricket"
SPORT_TENNIS = "tennis"
SPORT_MMA = "mma"

# Options keys
OPT_SCAN_INTERVAL = "scan_interval"
OPT_RECENT_MATCH_HOURS = "recent_match_hours"

# HA event names
EVENT_SCORE = "sports_live_score"
EVENT_DISCIPLINE = "sports_live_discipline"
EVENT_MATCH_FINISHED = "sports_live_match_finished"

# Legacy event aliases (emitted alongside new events for backward compat during transition)
EVENT_LEGACY_GOAL = "calcio_live_goal"
EVENT_LEGACY_YELLOW = "calcio_live_yellow_card"
EVENT_LEGACY_RED = "calcio_live_red_card"
EVENT_LEGACY_FINISHED = "calcio_live_match_finished"

# Sensor type identifiers
SENSOR_STANDINGS = "standings"
SENSOR_MATCHES = "matches"
SENSOR_NEXT_MATCH = "next_match"
SENSOR_SCHEDULE = "schedule"
SENSOR_SCHEDULE_ALL = "schedule_all"
SENSOR_NEWS = "news"
SENSOR_BRACKET = "bracket"
SENSOR_ALL_TODAY = "all_today"
