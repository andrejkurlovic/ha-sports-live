"""Generic ESPN scoreboard / event parser.

Works across soccer, NFL, and rugby because ESPN uses the same
events[]/competitions[]/competitors[] structure for all sports.
Sport-specific enrichment is handled in sensor.py via the sport profile.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil import parser as dateutil_parser

from ..const import _LOGGER


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def process_scoreboard(data: dict, hass, *, team_name: str | None = None,
                       next_match_only: bool = False,
                       start_date: str | None = None,
                       end_date: str | None = None,
                       recent_match_hours: int = 24) -> dict:
    """Parse ESPN scoreboard payload into normalised match dicts.

    Returns:
        {
            "league_info": [...],
            "team_name": str,
            "team_logo": str | None,
            "matches": [...],
            "next_match": dict | None,   # only when next_match_only=True
        }
    """
    try:
        matches_data = data.get("events", [])
        league_info = _parse_league_info(data, hass)
        team_logo: str | None = None

        start_dt = _to_utc_dt(start_date) if start_date else None
        end_dt = _to_utc_dt(end_date) if end_date else None

        matches: list[dict] = []
        for raw in matches_data:
            if team_name and team_name.lower() not in raw.get("name", "").lower():
                continue

            match_dt = _parse_iso_utc(raw.get("date", ""))
            if start_dt and match_dt and match_dt < start_dt:
                continue
            if end_dt and match_dt and match_dt > end_dt:
                continue

            parsed = _parse_event(raw, hass)
            if parsed is None:
                continue

            if team_name:
                ht, at = parsed.get("home_team", ""), parsed.get("away_team", "")
                if team_name.lower() in ht.lower():
                    team_logo = parsed.get("home_logo")
                elif team_name.lower() in at.lower():
                    team_logo = parsed.get("away_logo")

            matches.append(parsed)

        if next_match_only:
            selected = _select_next_match(matches, recent_match_hours)
            return {
                "league_info": league_info,
                "team_name": team_name or "All",
                "team_logo": team_logo,
                "matches": [selected] if selected else [],
                "next_match": selected,
            }

        return {
            "league_info": league_info,
            "team_name": team_name or "All",
            "team_logo": team_logo,
            "matches": matches,
            "next_match": None,
        }

    except Exception:
        _LOGGER.exception("Error in process_scoreboard")
        return {"league_info": [], "team_name": team_name or "All",
                "team_logo": None, "matches": [], "next_match": None}


def process_news(data: dict) -> list[dict]:
    """Parse ESPN news endpoint payload."""
    articles: list[dict] = []
    try:
        for a in data.get("articles", []):
            images = a.get("images", []) or []
            img = images[0].get("url", "") if images else ""
            categories = a.get("categories", []) or []
            cat_name = ""
            for c in categories:
                if c.get("type") == "league":
                    cat_name = (c.get("description", "")
                                or (c.get("league", {}) or {}).get("description", ""))
                    break
            articles.append({
                "headline": a.get("headline", ""),
                "description": a.get("description", ""),
                "published": a.get("published", ""),
                "image": img,
                "link": (a.get("links", {}) or {}).get("web", {}).get("href", "")
                         or a.get("link", ""),
                "category": cat_name,
                "type": a.get("type", ""),
            })
    except Exception:
        _LOGGER.exception("Error in process_news")
    return articles


def is_within_recent_window(date_str: str | None, hours: int = 24) -> bool:
    """True if match kickoff was within the last `hours`.

    Accepts either raw ISO 8601 UTC (date_iso field) or dd/mm/yyyy HH:MM (date field).
    """
    try:
        if not date_str:
            return False
        try:
            dt = dateutil_parser.isoparse(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - dt <= timedelta(hours=hours)
        except (ValueError, TypeError):
            # Fallback: local-formatted string — compare naive datetimes
            dt = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
            return datetime.now() - dt <= timedelta(hours=hours)
    except Exception:
        return False


def is_within_last_48_hours(date_str: str | None) -> bool:
    return is_within_recent_window(date_str, 48)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_event(raw: dict, hass) -> dict | None:
    """Convert a single ESPN event object into a normalised match dict."""
    try:
        comps = raw.get("competitions", [])
        if not comps:
            return None
        comp = comps[0]

        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            return None

        home = competitors[0]
        away = competitors[1]

        home_team_data = home.get("team", {})
        away_team_data = away.get("team", {})

        def _logo(c: dict) -> str:
            t = c.get("team", {})
            logo = t.get("logo")
            if not logo:
                logos = t.get("logos", [{}])
                logo = logos[0].get("href", "") if logos else ""
            return logo or ""

        status_type = raw.get("status", {}).get("type", {})
        venue_obj = comp.get("venue", {}) or {}
        venue_address = venue_obj.get("address", {}) or {}

        season_data = raw.get("season", {})
        season_info = season_data.get("slug") or season_data.get("displayName") or ""

        league_name = (comp.get("league", {}) or {}).get("displayName", "N/A")
        if league_name == "N/A":
            leagues = raw.get("leagues", []) or []
            if leagues:
                league_name = leagues[0].get("name", "N/A")

        details_raw = comp.get("details", [])
        match_details = _get_details(details_raw)

        # ESPN's displayClock for rugby is always stuck at "1'" regardless of
        # actual match time. Derive a better value from the latest event clock
        # in the details array, which does contain accurate per-event times.
        espn_clock = raw.get("status", {}).get("displayClock", "N/A")
        derived = _derive_clock_from_details(details_raw)
        if derived and (espn_clock in ("1'", "0:00", "N/A") or
                        _clock_minutes(derived) > _clock_minutes(espn_clock)):
            clock = derived
        else:
            clock = espn_clock

        return {
            "event_id": raw.get("id"),
            "date": _fmt_date(hass, raw.get("date")),
            "date_iso": raw.get("date", ""),   # raw UTC ISO for time calculations
            "season_info": season_info,
            "league_name": league_name,
            "home_team": home_team_data.get("displayName", "N/A"),
            "home_abbrev": home_team_data.get("abbreviation", ""),
            "home_color": home_team_data.get("color", ""),
            "home_logo": _logo(home),
            "home_form": home.get("form", ""),
            "home_score": home.get("score", "N/A"),
            "home_statistics": _get_statistics(home),
            "home_record": _get_record(home),
            "home_top_scorer": _get_top_scorer(home),
            "away_team": away_team_data.get("displayName", "N/A"),
            "away_abbrev": away_team_data.get("abbreviation", ""),
            "away_color": away_team_data.get("color", ""),
            "away_logo": _logo(away),
            "away_form": away.get("form", ""),
            "away_score": away.get("score", "N/A"),
            "away_statistics": _get_statistics(away),
            "away_record": _get_record(away),
            "away_top_scorer": _get_top_scorer(away),
            "state": status_type.get("state", "N/A"),
            "status": status_type.get("description", "N/A"),
            "status_detail": status_type.get("detail", "N/A"),
            "clock": clock,
            "period": raw.get("status", {}).get("period", "N/A"),
            "venue": venue_obj.get("fullName", "N/A"),
            "venue_city": venue_address.get("city", "N/A"),
            "venue_country": venue_address.get("country", "N/A"),
            "broadcast": _get_broadcast(comp),
            "attendance": comp.get("attendance", 0),
            "match_details": match_details,
        }
    except Exception:
        _LOGGER.exception("Error parsing event %s", raw.get("id"))
        return None


def _select_next_match(matches: list[dict], recent_match_hours: int) -> dict | None:
    live = [m for m in matches if m.get("state") == "in"]
    if live:
        return live[0]
    # Use date_iso for accurate recency check; fall back to formatted date string
    recent = [m for m in matches
              if m.get("state") == "post"
              and is_within_recent_window(
                  m.get("date_iso") or m.get("date"), recent_match_hours)]
    if recent:
        return recent[-1]   # most recent finished match
    upcoming = [m for m in matches if m.get("state") == "pre"]
    if upcoming:
        return upcoming[0]
    return None


def _parse_league_info(data: dict, hass) -> list[dict]:
    out = []
    for league in data.get("leagues", []):
        logos = league.get("logos", [])
        out.append({
            "abbreviation": league.get("abbreviation", ""),
            "startDate": _fmt_date(hass, league.get("season", {}).get("startDate"), time=False),
            "endDate": _fmt_date(hass, league.get("season", {}).get("endDate"), time=False),
            "logo_href": logos[0].get("href", "") if logos else "",
        })
    return out


def _to_utc_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _parse_iso_utc(s: str) -> datetime | None:
    try:
        return dateutil_parser.isoparse(s).astimezone(timezone.utc) if s else None
    except (ValueError, TypeError):
        return None


def _fmt_date(hass, date_str: str | None, *, time: bool = True) -> str:
    try:
        parsed = dateutil_parser.isoparse(date_str).replace(tzinfo=timezone.utc)
        tz = ZoneInfo(hass.config.time_zone)
        local = parsed.astimezone(tz)
        return local.strftime("%d/%m/%Y %H:%M") if time else local.strftime("%d/%m/%Y")
    except Exception:
        return "N/A"


def _get_statistics(competitor: dict) -> dict:
    return {s.get("name", "Unknown"): s.get("displayValue", "N/A")
            for s in competitor.get("statistics", [])}


def _get_record(competitor: dict) -> str:
    records = competitor.get("records", []) or []
    return records[0].get("summary", "") if records else ""


def _get_top_scorer(competitor: dict) -> dict | None:
    for ldr in competitor.get("leaders", []) or []:
        if ldr.get("name") == "goals":
            tops = ldr.get("leaders", []) or []
            if tops:
                t = tops[0]
                a = t.get("athlete", {}) or {}
                return {
                    "name": a.get("displayName", ""),
                    "short_name": a.get("shortName", ""),
                    "value": t.get("displayValue", ""),
                }
    return None


def _get_broadcast(competition: dict) -> str:
    gbs = competition.get("geoBroadcasts", []) or []
    if gbs:
        return (gbs[0].get("media", {}) or {}).get("shortName", "")
    return ""


def _get_details(details: list) -> list[str]:
    events = []
    for d in details:
        evt = d.get("type", {}).get("text", "Unknown")
        clock = d.get("clock", {}).get("displayValue", "N/A")
        athletes = [a.get("displayName", "") for a in d.get("athletesInvolved", [])]
        events.append(f"{evt} - {clock}: {', '.join(athletes) or 'N/A'}")
    return events


def _clock_minutes(clock_str: str) -> int:
    """Convert a clock string to total minutes for comparison purposes."""
    import re
    if not clock_str or clock_str == "N/A":
        return -1
    # N' rugby format
    m = re.match(r"^(\d+)'?$", str(clock_str).strip())
    if m:
        return int(m.group(1))
    # MM:SS soccer format
    m = re.match(r"^(\d+):(\d+)$", str(clock_str).strip())
    if m:
        return int(m.group(1))
    return -1


def _derive_clock_from_details(details: list) -> str | None:
    """Return the latest clock seen in match details.

    ESPN's displayClock for rugby is stuck at "1'" regardless of actual
    match time. The per-event clock inside details[] IS accurate, so we
    extract the highest minute value seen across all events.
    """
    import re
    max_min: int | None = None
    for d in details:
        val = str(d.get("clock", {}).get("displayValue", "")).strip()
        m = re.match(r"^(\d+)'?$", val)
        if m:
            mins = int(m.group(1))
            if max_min is None or mins > max_min:
                max_min = mins
    return f"{max_min}'" if max_min is not None else None
