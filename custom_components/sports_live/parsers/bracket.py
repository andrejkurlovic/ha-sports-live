"""Generic knockout bracket parser.

Adapted from the upstream soccer bracket parser. Works for soccer (1st Leg / 2nd Leg
two-legged ties) and NFL (single-game playoff rounds). The sport profile's
knockout_competitions set controls when the bracket sensor is auto-created.

NFL playoffs are single-game eliminations — those events don't have "1st Leg" / "2nd Leg"
notes. Instead we fall through to a single-game bracket mode.
"""
from __future__ import annotations
import re
from datetime import datetime

from ..const import _LOGGER


ROUND_NAMES = {
    1: "Final",
    2: "Semifinals",
    4: "Quarterfinals",
    8: "Round of 16",
    16: "Round of 32",
    32: "Round of 64",
}


def process_bracket(data: dict) -> dict:
    """Parse scoreboard data into a bracket structure.

    Returns {rounds: [{name, size, ties: [...]}], ties_count: int}
    """
    out: dict = {"rounds": [], "ties_count": 0}
    try:
        events = data.get("events", []) or []
        ties: dict = {}

        for e in events:
            comps = e.get("competitions", []) or []
            if not comps:
                continue
            c = comps[0]
            notes = c.get("notes", []) or []
            note_text = ""
            if notes:
                note_text = notes[0].get("headline", "") or notes[0].get("text", "") or ""

            is_first_leg = "1st Leg" in note_text
            is_second_leg = "2nd Leg" in note_text
            # Single-game eliminations: NFL playoffs, and single-leg soccer knockouts
            # (FIFA World Cup, Copa America, African Cup, etc.). Two-legged ties always
            # carry "1st Leg"/"2nd Leg" in their notes, so those are caught above first
            # and will never reach the is_single check.
            is_single = (not is_first_leg and not is_second_leg) and (
                "Final" in note_text or "Playoff" in note_text or
                "Wild Card" in note_text or "Divisional" in note_text or
                "Conference" in note_text or "Championship" in note_text or
                "Round of" in note_text or "Quarterfinal" in note_text or
                "Semifinal" in note_text or "Third Place" in note_text or
                "3rd Place" in note_text or
                "Super Bowl" in note_text or          # NFL championship game
                "World Series" in note_text or        # MLB championship series
                "Division Series" in note_text        # MLB ALDS / NLDS
            )
            if not (is_first_leg or is_second_leg or is_single):
                continue

            competitors = c.get("competitors", []) or []
            home = next((x for x in competitors if x.get("homeAway") == "home"), None)
            away = next((x for x in competitors if x.get("homeAway") == "away"), None)
            if not home or not away:
                continue

            home_t = home.get("team") or {}
            away_t = away.get("team") or {}
            home_id, away_id = home_t.get("id", ""), away_t.get("id", "")

            tie_key = frozenset([home_id, away_id])
            if tie_key not in ties:
                ties[tie_key] = {
                    "team_a": {"name": "", "logo": "", "abbrev": "", "id": ""},
                    "team_b": {"name": "", "logo": "", "abbrev": "", "id": ""},
                    "leg1": None, "leg2": None, "single": None,
                    "first_leg_date": None,
                    "winner_team": None, "aggregate": None,
                    "tied": False, "completed": False,
                }
            tie = ties[tie_key]

            leg = {
                "home_team": home_t.get("displayName", ""),
                "home_score": _safe_int(home.get("score")),
                "away_team": away_t.get("displayName", ""),
                "away_score": _safe_int(away.get("score")),
                "date": e.get("date", ""),
                "state": ((e.get("status") or {}).get("type") or {}).get("state", ""),
                "note": note_text,
            }

            if is_first_leg:
                tie["leg1"] = leg
                tie["first_leg_date"] = e.get("date", "")
                if not tie["team_a"]["name"]:
                    tie["team_a"] = {
                        "name": home_t.get("displayName", ""),
                        "logo": home_t.get("logo", ""),
                        "abbrev": home_t.get("abbreviation", ""),
                        "id": home_id,
                    }
                    tie["team_b"] = {
                        "name": away_t.get("displayName", ""),
                        "logo": away_t.get("logo", ""),
                        "abbrev": away_t.get("abbreviation", ""),
                        "id": away_id,
                    }
            elif is_second_leg:
                tie["leg2"] = leg
                agg = _parse_aggregate(note_text)
                if agg:
                    tie["winner_team"] = agg.get("winner_team")
                    agg_for = agg.get("agg_for")
                    agg_against = agg.get("agg_against")
                    tie["aggregate"] = (
                        f"{agg_for}-{agg_against}" if agg_for is not None else None
                    )
                    tie["tied"] = agg.get("tied", False)
                    tie["completed"] = leg["state"] == "post"
                if not tie["team_a"]["name"]:
                    tie["team_a"] = {
                        "name": away_t.get("displayName", ""),
                        "logo": away_t.get("logo", ""),
                        "abbrev": away_t.get("abbreviation", ""),
                        "id": away_id,
                    }
                    tie["team_b"] = {
                        "name": home_t.get("displayName", ""),
                        "logo": home_t.get("logo", ""),
                        "abbrev": home_t.get("abbreviation", ""),
                        "id": home_id,
                    }
            elif is_single:
                tie["single"] = leg
                tie["first_leg_date"] = e.get("date", "")
                if not tie["team_a"]["name"]:
                    tie["team_a"] = {
                        "name": home_t.get("displayName", ""),
                        "logo": home_t.get("logo", ""),
                        "abbrev": home_t.get("abbreviation", ""),
                        "id": home_id,
                    }
                    tie["team_b"] = {
                        "name": away_t.get("displayName", ""),
                        "logo": away_t.get("logo", ""),
                        "abbrev": away_t.get("abbreviation", ""),
                        "id": away_id,
                    }
                hs, as_ = leg["home_score"], leg["away_score"]
                if leg["state"] == "post" and hs is not None and as_ is not None:
                    tie["completed"] = True
                    if hs > as_:
                        tie["winner_team"] = home_t.get("displayName", "")
                    elif as_ > hs:
                        tie["winner_team"] = away_t.get("displayName", "")
                    else:
                        tie["tied"] = True

        sorted_ties = sorted(
            ties.values(),
            key=lambda t: t.get("first_leg_date") or "",
        )

        groups: list[list] = []
        current: list = []
        prev_date: datetime | None = None

        for tie in sorted_ties:
            d = _parse_date(tie.get("first_leg_date") or "")
            if prev_date is None or d is None or abs((d - prev_date).days) <= 7:
                current.append(tie)
            else:
                groups.append(current)
                current = [tie]
            if d is not None:
                prev_date = d
        if current:
            groups.append(current)

        sized_rounds = []
        for g in groups:
            size = 1
            while size < len(g):
                size *= 2
            sized_rounds.append({"size": size, "ties": g})

        n = len(sized_rounds)
        labels = [None] * n
        if n > 0:
            expected = sized_rounds[-1]["size"]
            for idx in range(n - 1, -1, -1):
                actual = sized_rounds[idx]["size"]
                if actual == expected:
                    labels[idx] = ROUND_NAMES.get(actual, f"Round of {actual * 2}")
                    expected = actual * 2
                elif idx + 1 < n and actual == sized_rounds[idx + 1]["size"]:
                    labels[idx] = "Knockout Playoffs" if actual == 8 else (
                        ROUND_NAMES.get(actual, f"Round of {actual * 2}"))
                    expected = actual * 2
                else:
                    labels[idx] = ROUND_NAMES.get(actual, f"Round of {actual * 2}")
                    expected = actual * 2

        for idx, sr in enumerate(sized_rounds):
            for tie in sr["ties"]:
                tie.get("team_a", {}).pop("id", None)
                tie.get("team_b", {}).pop("id", None)
            out["rounds"].append({
                "name": labels[idx],
                "size": sr["size"],
                "ties": sr["ties"],
            })

        out["ties_count"] = sum(len(sr["ties"]) for sr in sized_rounds)
    except Exception:
        _LOGGER.exception("Error in process_bracket")
    return out


def _parse_aggregate(note_text: str) -> dict | None:
    if not note_text:
        return None
    if "Tied on aggregate" in note_text:
        return {"winner_team": None, "agg_for": None, "agg_against": None, "tied": True}
    m = re.search(
        r"2nd Leg\s*-\s*(.+?)\s+(?:advance|lead)\s+(\d+)\s*-\s*(\d+)\s+on aggregate",
        note_text,
    )
    if m:
        return {
            "winner_team": m.group(1).strip(),
            "agg_for": int(m.group(2)),
            "agg_against": int(m.group(3)),
            "tied": False,
        }
    return None


def _safe_int(v) -> int | None:
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d") if s else None
    except Exception:
        return None
