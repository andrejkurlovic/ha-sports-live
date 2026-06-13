"""Generic ESPN standings parser.

Works for soccer (v2 standings endpoint), NFL (site/v2 standings), and
Rugby (v2 standings endpoint — site.web.api.espn.com/apis/v2/sports/rugby/).

ESPN uses different stat names per sport:
  Soccer/NFL  : wins, ties, losses, pointDifferential
  Rugby       : gamesWon, gamesDrawn, gamesLost, pointsDifference
Both return pointsFor, pointsAgainst, gamesPlayed, points unchanged.
Rugby additionally exposes bonusPoints, triesFor, triesAgainst.
"""
from __future__ import annotations
from datetime import datetime

from dateutil import parser as dateutil_parser

from ..const import _LOGGER


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

        for child in data.get("children", []):
            standings_data = child.get("standings", {}).get("entries", [])
            standings = []

            for index, entry in enumerate(standings_data, start=1):
                team = entry.get("team", {})
                logos = team.get("logos", []) or []
                stats = {s["name"]: s["displayValue"] for s in entry.get("stats", [])}

                # Rank: prefer explicit rank stat, fall back to position in list
                rank = int(float(stats.get("rank", index))) if "rank" in stats else (
                    entry.get("note", {}).get("rank", index)
                )

                standings.append({
                    "rank": rank,
                    "team_id": team.get("id"),
                    "team_name": team.get("displayName"),
                    "team_logo": logos[0].get("href", "") if logos else "",
                    "points": stats.get("points", "N/A"),
                    "games_played": stats.get("gamesPlayed", "N/A"),
                    # Soccer/NFL use "wins"/"ties"/"losses"; rugby uses "gamesWon"/"gamesDrawn"/"gamesLost"
                    "wins": stats.get("wins") or stats.get("gamesWon", "N/A"),
                    "draws": stats.get("ties") or stats.get("gamesDrawn", "N/A"),
                    "losses": stats.get("losses") or stats.get("gamesLost", "N/A"),
                    "goals_for": stats.get("pointsFor", "N/A"),
                    "goals_against": stats.get("pointsAgainst", "N/A"),
                    # Soccer/NFL use "pointDifferential"; rugby uses "pointsDifference"
                    "goal_difference": (
                        stats.get("pointDifferential")
                        or stats.get("pointsDifference", "N/A")
                    ),
                    # Rugby-specific (will be "N/A" for other sports)
                    "bonus_points": stats.get("bonusPoints", "N/A"),
                    "tries_for": stats.get("triesFor", "N/A"),
                    "tries_against": stats.get("triesAgainst", "N/A"),
                })

            links = child.get("standings", {}).get("links", [])
            full_table_link = links[0].get("href", "") if links else ""

            standings_list.append({
                "name": child.get("name", "Unknown"),
                "standings": standings,
                "full_table_link": full_table_link,
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
