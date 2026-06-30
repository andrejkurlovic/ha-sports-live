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

            # Season slug from the event (e.g. "round-of-32", "quarterfinals", "final").
            # ESPN uses this instead of competition notes for some tournaments (FIFA WC 2026+).
            season_slug = e.get("season", {}).get("slug", "").lower()

            # Single-game eliminations: NFL playoffs, single-leg soccer knockouts
            # (FIFA World Cup, Copa America, African Cup, etc.). Two-legged ties carry
            # "1st Leg"/"2nd Leg" in notes; those are caught above and won't reach here.
            is_single = (not is_first_leg and not is_second_leg) and (
                # Note-based detection (UEFA, NFL, MLB, NBA…)
                "Final" in note_text or "Playoff" in note_text or
                "Wild Card" in note_text or "Divisional" in note_text or
                "Conference" in note_text or "Championship" in note_text or
                "Round of" in note_text or "Quarterfinal" in note_text or
                "Semifinal" in note_text or "Third Place" in note_text or
                "3rd Place" in note_text or
                "Super Bowl" in note_text or
                "World Series" in note_text or
                "Division Series" in note_text or
                "penalt" in note_text.lower() or  # penalty shootout result note
                # Season-slug detection (FIFA WC 2026+, some CONCACAF events)
                any(kw in season_slug for kw in (
                    "round-of", "quarterfinal", "semifinal", "final", "playoff", "knockout",
                    "3rd-place",
                ))
            )
            if not (is_first_leg or is_second_leg or is_single):
                continue

            # Synthesize the round label from season_slug when available.
            # This is used as the display label (note_for_display) and for grouping,
            # but the original note_text is kept for winner-detection (penalty parsing).
            _SLUG_MAP = {
                "round-of-64": "Round of 64", "round-of-32": "Round of 32",
                "round-of-16": "Round of 16", "quarterfinal": "Quarterfinal",
                "semifinal": "Semifinal", "3rd-place": "Third Place", "final": "Final",
            }
            note_for_display = note_text  # default: use ESPN note as display label
            for _k, _v in _SLUG_MAP.items():
                if _k in season_slug:
                    note_for_display = _v  # slug label overrides result descriptions
                    break

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
                    "decided_on_penalties": False,
                    "penalty_score": None,
                    "penalty_details": [],
                }
            tie = ties[tie_key]

            status_obj = (e.get("status") or {})
            status_type = (status_obj.get("type") or {})
            venue_obj = c.get("venue") or {}
            venue_city = (venue_obj.get("address") or {}).get("city", "")
            venue_name = venue_obj.get("fullName", "")
            venue_str = f"{venue_name}, {venue_city}".strip(", ") if venue_name else venue_city

            detail_str = status_type.get("detail", "") or ""
            leg = {
                "home_team": home_t.get("displayName", ""),
                "home_score": _safe_int(home.get("score")),
                "away_team": away_t.get("displayName", ""),
                "away_score": _safe_int(away.get("score")),
                "date": e.get("date", ""),
                "state": status_type.get("state", ""),
                "status_detail": detail_str,
                "clock": status_obj.get("displayClock", ""),
                "venue": venue_str,
                "note": note_for_display,
                "in_penalty_shootout": (
                    "penalt" in detail_str.lower() or "shootout" in detail_str.lower()
                ),
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
                        # Draw after 90/120 mins — try to extract penalty winner from note
                        pen_info = _parse_penalty_info(note_text)
                        if pen_info:
                            tie["winner_team"] = pen_info["winner"]
                            tie["decided_on_penalties"] = True
                            tie["penalty_score"] = pen_info.get("score")
                            pen_details = _parse_penalty_details_from_comp(c)
                            if pen_details:
                                tie["penalty_details"] = pen_details
                        else:
                            tie["tied"] = True

        sorted_ties = sorted(
            ties.values(),
            key=lambda t: t.get("first_leg_date") or "",
        )

        # Group single-leg ties by their synthesized note (round name) so rounds like
        # R32→R16→QF stay separate even when scheduled within 7 days of each other.
        # Two-legged ties (no "single" leg) fall back to the 7-day date-proximity rule
        # so leg1 and leg2 of the same round are kept together.
        groups: list[list] = []
        single_groups: dict[str, list] = {}   # note_text → [ties]
        twolegged_current: list = []
        prev_date: datetime | None = None

        for tie in sorted_ties:
            if tie.get("single") is not None:
                note = tie["single"].get("note") or "Unknown Round"
                single_groups.setdefault(note, []).append(tie)
            else:
                # Two-legged tie — group by date proximity
                d = _parse_date(tie.get("first_leg_date") or "")
                if prev_date is None or d is None or abs((d - prev_date).days) <= 7:
                    twolegged_current.append(tie)
                else:
                    if twolegged_current:
                        groups.append(twolegged_current)
                    twolegged_current = [tie]
                if d is not None:
                    prev_date = d

        if twolegged_current:
            groups.append(twolegged_current)

        # Interleave single-leg rounds (ordered by earliest match date) with two-legged groups.
        # Build a unified list ordered by earliest date in each group.
        all_groups: list[tuple[str, list]] = []
        for g in groups:
            earliest = min((t.get("first_leg_date") or "" for t in g), default="")
            all_groups.append((earliest, g))
        for note_key, note_ties in single_groups.items():
            earliest = min((t.get("first_leg_date") or "" for t in note_ties), default="")
            all_groups.append((earliest, note_ties))

        all_groups.sort(key=lambda x: x[0])
        groups = [g for _, g in all_groups]

        sized_rounds = []
        for g in groups:
            size = 1
            while size < len(g):
                size *= 2
            # Prefer the synthesized note as the explicit round label (single-leg groups).
            # For two-legged groups the note comes from the competition note text.
            explicit_label = None
            first_single = g[0].get("single") if g else None
            if first_single:
                explicit_label = first_single.get("note") or None
            sized_rounds.append({"size": size, "ties": g, "explicit_label": explicit_label})

        n = len(sized_rounds)
        labels = [None] * n
        if n > 0:
            expected = sized_rounds[-1]["size"]
            for idx in range(n - 1, -1, -1):
                sr = sized_rounds[idx]
                if sr.get("explicit_label"):
                    # Use the label embedded from season_slug / competition note
                    labels[idx] = sr["explicit_label"]
                else:
                    actual = sr["size"]
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


def _parse_penalty_info(note_text: str) -> dict | None:
    """Extract winner and shootout score from a penalty note.

    Matches ESPN patterns like 'Paris Saint-Germain win 4-3 on penalties'.
    Returns {"winner": str, "score": "4-3"} or None.
    """
    m = re.search(
        r'^(.+?)\s+(?:win(?:s)?|advance[sd]?)\s+(\d+)[-–]\s*(\d+)\s+on\s+penalt',
        note_text, re.IGNORECASE,
    )
    if m:
        return {"winner": m.group(1).strip(), "score": f"{m.group(2)}-{m.group(3)}"}
    # Fallback: winner without score (rare ESPN format)
    m2 = re.search(
        r'^(.+?)\s+(?:win(?:s)?|advance[sd]?)\s+on\s+penalt', note_text, re.IGNORECASE,
    )
    if m2:
        return {"winner": m2.group(1).strip(), "score": None}
    return None


def _parse_penalty_details_from_comp(comp: dict) -> list[dict]:
    """Extract penalty shootout kicks from competition details.

    ESPN marks shootout events with period >= 5 (soccer) or a clock
    value matching the 'P<n>' format used for shootout rounds.
    """
    events = []
    for d in (comp.get("details") or []):
        evt_type = ((d.get("type") or {}).get("text") or "").lower()
        if "penalty" not in evt_type:
            continue
        period = d.get("period")
        period_num = 0
        if isinstance(period, dict):
            period_num = int(period.get("number", 0) or 0)
        elif isinstance(period, (int, float)):
            period_num = int(period)
        clock_val = ((d.get("clock") or {}).get("displayValue") or "")
        is_shootout = period_num >= 5 or bool(re.match(r'^P\d', clock_val, re.IGNORECASE))
        if not is_shootout:
            continue
        athletes = [a.get("displayName", "") for a in (d.get("athletesInvolved") or [])]
        team = ((d.get("team") or {}).get("displayName") or "")
        scored = "missed" not in evt_type
        events.append({
            "team": team,
            "player": athletes[0] if athletes else "",
            "scored": scored,
        })
    return events


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
