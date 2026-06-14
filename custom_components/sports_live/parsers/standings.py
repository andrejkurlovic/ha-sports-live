"""Generic ESPN standings parser.

All sports use the ``site.web.api.espn.com/apis/v2/sports/{sport}/{league}/standings``
endpoint. ESPN names the same concepts differently per sport, so each output
field is resolved from a list of candidate ESPN stat names:

  Wins/Losses/Draws : wins / gamesWon, losses / gamesLost, ties / gamesDrawn
  Difference        : pointDifferential (soccer/US) / pointsDifference (rugby)
  US-league extras  : winPercent, gamesBehind, streak, playoffSeed,
                      divisionRecord, OT losses, overall record
  Rugby extras      : bonusPoints, triesFor, triesAgainst

The output dict carries every field; the card decides which columns to show
based on the entry's sport. League tables (soccer/rugby) return one group;
US leagues return one group per conference (Eastern/Western, AL/NL, AFC/NFC),
sometimes with divisions nested a level deeper — handled by walking children
recursively.
"""
from __future__ import annotations
from datetime import datetime

from dateutil import parser as dateutil_parser

from ..const import _LOGGER


def _stat(stats: dict, *names: str, default: str = "N/A"):
    """Return the first present, non-empty ESPN stat among ``names``."""
    for n in names:
        v = stats.get(n)
        if v not in (None, ""):
            return v
    return default


def _iter_groups(node: dict):
    """Yield (name, entries, links) for every standings group in the tree.

    A conference node may hold team entries directly, or nest division
    sub-nodes that hold the entries; recurse so both shapes are flattened
    into one group per table the user would expect to see.
    """
    children = node.get("children") or []
    standings = node.get("standings") or {}
    entries = standings.get("entries") or []

    if entries:
        yield (node.get("name", "Standings"), entries, standings.get("links") or [])
        return

    if children:
        for child in children:
            yield from _iter_groups(child)


def process_standings(data: dict) -> dict:
    """Parse ESPN standings payload.

    Returns:
        {
            "season": str,
            "season_start": str | None,
            "season_end": str | None,
            "standings_groups": [
                {"name": str, "standings": [...], "full_table_link": str}
            ]
        }
    """
    try:
        standings_list = []

        for name, entries, links in _iter_groups(data):
            standings = []
            for index, entry in enumerate(entries, start=1):
                team = entry.get("team", {})
                logos = [l for l in (team.get("logos", []) or []) if l]
                stats = {s["name"]: s.get("displayValue", "") for s in entry.get("stats", [])}

                rank = int(float(stats.get("rank", index))) if "rank" in stats else (
                    entry.get("note", {}).get("rank", index)
                )

                standings.append({
                    "rank": rank,
                    "team_id": team.get("id"),
                    "team_name": team.get("displayName"),
                    "team_abbrev": team.get("abbreviation", ""),
                    "team_logo": logos[0].get("href", "") if logos else "",
                    "points": _stat(stats, "points"),
                    "games_played": _stat(stats, "gamesPlayed"),
                    "wins": _stat(stats, "wins", "gamesWon"),
                    "draws": _stat(stats, "ties", "gamesDrawn"),
                    "losses": _stat(stats, "losses", "gamesLost"),
                    "goals_for": _stat(stats, "pointsFor"),
                    "goals_against": _stat(stats, "pointsAgainst"),
                    "goal_difference": _stat(stats, "pointDifferential", "pointsDifference"),
                    # Rugby-specific
                    "bonus_points": _stat(stats, "bonusPoints"),
                    "tries_for": _stat(stats, "triesFor"),
                    "tries_against": _stat(stats, "triesAgainst"),
                    # US-league standings (NBA/NHL/MLB/NFL)
                    "win_pct": _stat(stats, "winPercent"),
                    "games_behind": _stat(stats, "gamesBehind"),
                    "streak": _stat(stats, "streak"),
                    "playoff_seed": _stat(stats, "playoffSeed"),
                    "division_record": _stat(stats, "divisionRecord"),
                    "ot_losses": _stat(stats, "otLosses", "OTLosses", "overtimeLosses"),
                    "overall_record": _stat(stats, "overall", default=""),
                })

            standings_list.append({
                "name": name,
                "standings": standings,
                "full_table_link": links[0].get("href", "") if links else "",
            })

        # Determine current season dynamically — no hardcoded year
        seasons_data = data.get("seasons", [])
        current_year = datetime.now().year
        current_season = (
            next((s for s in seasons_data if s.get("year") == current_year), None)
            or next((s for s in seasons_data if s.get("year") == current_year - 1), None)
            or (seasons_data[0] if seasons_data else None)
        )

        return {
            "season": current_season.get("displayName", "N/A") if current_season else "N/A",
            "season_start": _parse_date(current_season.get("startDate")) if current_season else None,
            "season_end": _parse_date(current_season.get("endDate")) if current_season else None,
            "standings_groups": standings_list,
        }

    except Exception:
        _LOGGER.exception("Error in process_standings")
        return {"season": "N/A", "season_start": None, "season_end": None, "standings_groups": []}


def _parse_date(date_str: str | None) -> str | None:
    try:
        return dateutil_parser.isoparse(date_str).strftime("%d-%m-%Y") if date_str else None
    except (ValueError, TypeError):
        return None
