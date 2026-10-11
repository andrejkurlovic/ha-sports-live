"""Self-maintaining season status — decides whether a competition is worth showing.

Pure functions (no HA imports) so they are trivially testable. Everything is derived
from the matches ESPN currently returns, so a new season/tournament "wakes up" on its
own and a finished one goes idle on its own — nothing to reconfigure.

status:
  live      a match is in progress
  recent    a match finished within the "keep finished match visible" window
  active    next match starts within ``idle_days``
  idle      nothing live/recent and the next match is further away than ``idle_days``
            (or there is no scheduled match at all) → cards may hide themselves
"""
from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_IDLE_DAYS = 180


def _parse(iso: str | None) -> datetime | None:
    try:
        if not iso:
            return None
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def compute_season_status(matches: list, *, idle_days: int = DEFAULT_IDLE_DAYS,
                          recent_hours: int = 24, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    next_dt = last_dt = None
    live = False
    for m in matches or []:
        state = m.get("state")
        dt = _parse(m.get("date_iso"))
        if state not in ("in", "pre", "post") and dt:
            # Team-schedule payloads carry no usable state ("N/A"); infer it from the date.
            state = "pre" if dt >= now else "post"
        if state == "in":
            live = True
        elif state == "pre" and dt and dt >= now and (next_dt is None or dt < next_dt):
            next_dt = dt
        elif state == "post" and dt and dt <= now and (last_dt is None or dt > last_dt):
            last_dt = dt

    days_until = round((next_dt - now).total_seconds() / 86400, 1) if next_dt else None
    hours_since = (now - last_dt).total_seconds() / 3600 if last_dt else None

    if live:
        status = "live"
    elif hours_since is not None and hours_since <= recent_hours:
        status = "recent"
    elif days_until is not None and days_until <= idle_days:
        status = "active"
    else:
        status = "idle"

    return {
        "season_status": status,
        "show_card": status != "idle",
        "days_until_next_match": days_until,
        "next_match_start_iso": next_dt.isoformat() if next_dt else None,
        "idle_hide_days": idle_days,
    }


def filter_events_to_season(raw: dict, season_start, season_end) -> dict:
    """Return a copy of an ESPN scoreboard payload keeping only events inside the season window.

    The scoreboard is fetched per calendar year, so it also contains the *previous* season's
    games (e.g. last May's Champions League knockouts). Anything that must not mix seasons
    (the bracket) goes through this. Events with no/invalid date are dropped; no window = no-op.
    """
    if not raw or not season_start or not season_end:
        return raw
    start = season_start if season_start.tzinfo else season_start.replace(tzinfo=timezone.utc)
    end = (season_end if season_end.tzinfo else season_end.replace(tzinfo=timezone.utc))
    out = dict(raw)
    kept = []
    for ev in raw.get("events") or []:
        dt = _parse(ev.get("date"))
        if dt and start <= dt <= end.replace(hour=23, minute=59, second=59):
            kept.append(ev)
    out["events"] = kept
    return out
