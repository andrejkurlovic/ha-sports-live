"""ESPN summary endpoint parser (lineup, formations, key events, head-to-head).

Gated behind sport profile's supports_summary capability flag.
Soccer supports full lineups; NFL/rugby do not.
"""
from __future__ import annotations
from ..const import _LOGGER

H2H_MAX = 10


def process_summary(data: dict) -> dict:
    """Extract lineup, formations, key events and head-to-head from summary endpoint."""
    out = {
        "lineup_home": [],
        "lineup_away": [],
        "formation_home": "",
        "formation_away": "",
        "key_events": [],
        "head_to_head": [],
    }
    try:
        for r in data.get("rosters", []) or []:
            home_away = r.get("homeAway", "")
            formation = r.get("formation", "")
            players = []
            for p in r.get("roster", []) or []:
                a = p.get("athlete", {}) or {}
                players.append({
                    "name": a.get("displayName", ""),
                    "short_name": a.get("shortName", ""),
                    "jersey": p.get("jersey", ""),
                    "position": (p.get("position", {}) or {}).get("abbreviation", ""),
                    "starter": p.get("starter", False),
                    "headshot": (a.get("headshot", {}) or {}).get("href", ""),
                })
            if home_away == "home":
                out["lineup_home"] = players
                out["formation_home"] = formation
            elif home_away == "away":
                out["lineup_away"] = players
                out["formation_away"] = formation

        for ev in data.get("keyEvents", []) or []:
            t = ev.get("type", {}) or {}
            clock = (ev.get("clock", {}) or {}).get("displayValue", "")
            team = (ev.get("team", {}) or {}).get("displayName", "")
            athletes = [
                (p.get("athlete", {}) or {}).get("displayName", "")
                for p in ev.get("participants", []) or []
            ]
            out["key_events"].append({
                "type": t.get("type", ""),
                "type_text": t.get("text", ""),
                "short_text": ev.get("shortText", ""),
                "clock": clock,
                "team": team,
                "athletes": athletes,
                "scoring_play": ev.get("scoringPlay", False),
            })

        for game in (data.get("headToHeadGames", []) or []):
            if len(out["head_to_head"]) >= H2H_MAX:
                break
            for e in game.get("events", []) or []:
                if len(out["head_to_head"]) >= H2H_MAX:
                    break
                comp = (e.get("competitions", []) or [{}])[0]
                competitors = comp.get("competitors", []) or []
                if len(competitors) < 2:
                    continue
                home_c = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                away_c = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                out["head_to_head"].append({
                    "date": e.get("date", ""),
                    "home_team": (home_c.get("team", {}) or {}).get("displayName", ""),
                    "home_score": home_c.get("score", ""),
                    "away_team": (away_c.get("team", {}) or {}).get("displayName", ""),
                    "away_score": away_c.get("score", ""),
                })
    except Exception:
        _LOGGER.exception("Error in process_summary")
    return out
