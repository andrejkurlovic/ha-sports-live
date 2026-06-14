"""ESPN summary endpoint parser (lineup, formations, key events, head-to-head).

Gated behind sport profile's supports_summary capability flag.

Per-sport shape (verified against the live ESPN API 2026-06-14):
  * Soccer exposes ``keyEvents`` / ``rosters`` (lineups) / ``headToHeadGames``.
  * NBA/NHL/MLB/NFL expose ``plays`` (with ``scoringPlay`` flags),
    ``winprobability`` (per-play home win %), and ``leaders`` (stat leaders).
This parser reads whichever keys are present, so the same function enriches
every sport without sport-specific branching at the call site.
"""
from __future__ import annotations
from ..const import _LOGGER

H2H_MAX = 10
SCORING_PLAYS_MAX = 15   # keep recorder attribute payload bounded


def process_summary(data: dict) -> dict:
    """Extract lineup, key events, scoring plays, win probability and leaders."""
    out = {
        "lineup_home": [],
        "lineup_away": [],
        "formation_home": "",
        "formation_away": "",
        "key_events": [],
        "head_to_head": [],
        "scoring_plays": [],
        "stat_leaders": [],
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

        # Scoring plays — present for NBA/NHL/MLB/NFL (soccer uses keyEvents).
        # Keep only the most recent SCORING_PLAYS_MAX to bound the payload.
        scoring = [p for p in (data.get("plays") or []) if p.get("scoringPlay")]
        for p in scoring[-SCORING_PLAYS_MAX:]:
            period = p.get("period", {}) or {}
            out["scoring_plays"].append({
                "text": p.get("text", "") or p.get("shortDescription", ""),
                "short_text": p.get("shortDescription", ""),
                "home_score": p.get("homeScore"),
                "away_score": p.get("awayScore"),
                "period": period.get("displayValue", "") or period.get("number", ""),
                "clock": (p.get("clock", {}) or {}).get("displayValue", ""),
                "team_id": (p.get("team", {}) or {}).get("id", ""),
                "score_value": p.get("scoreValue"),
            })

        # Live win probability — last data point is the current state.
        # Only surfaced here; the sensor merges it without clobbering a value
        # the scoreboard predictor already provided.
        wp = data.get("winprobability") or []
        if wp:
            last = wp[-1] or {}
            home_pct = last.get("homeWinPercentage")
            tie_pct = last.get("tiePercentage") or 0
            if isinstance(home_pct, (int, float)):
                out["summary_home_win_probability"] = round(home_pct * 100, 1)
                out["summary_away_win_probability"] = round(
                    max(0.0, (1 - home_pct - tie_pct)) * 100, 1
                )

        # Stat leaders — generic per-sport (points/assists/rebounds, HR/RBI, …).
        for tl in data.get("leaders", []) or []:
            team = tl.get("team", {}) or {}
            cats = []
            for cat in tl.get("leaders", []) or []:
                tops = cat.get("leaders", []) or []
                if not tops:
                    continue
                top = tops[0]
                ath = top.get("athlete", {}) or {}
                cats.append({
                    "category": cat.get("name", ""),
                    "display_name": cat.get("displayName", "") or cat.get("name", ""),
                    "athlete": ath.get("displayName", ""),
                    "short_name": ath.get("shortName", ""),
                    "value": top.get("displayValue", ""),
                })
            if cats:
                out["stat_leaders"].append({
                    "team_id": team.get("id"),
                    "team_name": team.get("displayName", ""),
                    "categories": cats,
                })
    except Exception:
        _LOGGER.exception("Error in process_summary")
    return out
