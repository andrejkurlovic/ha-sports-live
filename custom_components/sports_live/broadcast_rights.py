"""Static UK broadcast rights lookup.

ESPN's geoBroadcasts API only returns US market data. This module provides a
best-effort static map of UK broadcasters per competition code so the
'broadcast_uk' field on match entities is useful for UK users.

Rights change every few seasons — treat this as indicative, not authoritative.
Last reviewed: 2025.
"""
from __future__ import annotations

# Map of competition_code → list of UK broadcaster names.
# Soccer uses text slugs; rugby uses numeric IDs (as strings).
_UK_RIGHTS: dict[str, list[str]] = {
    # ── Soccer / Football ────────────────────────────────────────────────────
    "eng.1":              ["Sky Sports", "TNT Sports", "Amazon Prime"],   # Premier League
    "eng.2":              ["Sky Sports"],                                  # Championship
    "eng.3":              ["Sky Sports"],                                  # League One
    "eng.4":              ["Sky Sports"],                                  # League Two
    "eng.fa":             ["BBC", "ITV"],                                  # FA Cup
    "eng.league_cup":     ["Sky Sports"],                                  # Carabao Cup
    "ita.1":              ["TNT Sports"],                                   # Serie A
    "esp.1":              ["Premier Sports", "LaLigaTV"],                  # La Liga
    "ger.1":              ["Sky Sports", "TNT Sports"],                    # Bundesliga
    "fra.1":              ["Sky Sports"],                                   # Ligue 1
    "ned.1":              ["Viaplay"],                                     # Eredivisie
    "por.1":              ["Viaplay"],                                     # Primeira Liga
    "sco.1":              ["Sky Sports"],                                   # Scottish Premiership
    "uefa.champions":     ["TNT Sports"],                                  # Champions League
    "uefa.europa":        ["TNT Sports"],                                   # Europa League
    "uefa.europa.conf":   ["TNT Sports"],                                   # Conference League
    "uefa.wchampions":    ["TNT Sports", "DAZN"],                          # Women's Champions League
    "uefa.euro":          ["BBC", "ITV"],                                  # European Championship
    "uefa.nations":       ["Channel 4", "Sky Sports"],                    # Nations League
    "fifa.world":         ["BBC", "ITV"],                                  # World Cup (men)
    "fifa.wwc":           ["BBC", "ITV"],                                  # World Cup (women)
    "fifa.cwc":           ["DAZN"],                                        # Club World Cup
    "concacaf.champions": ["TNT Sports"],                                  # CONCACAF Champions Cup
    "concacaf.gold":      ["Sky Sports"],                                  # CONCACAF Gold Cup

    # ── American Football (NFL) ───────────────────────────────────────────────
    "nfl":                ["Sky Sports", "DAZN"],

    # ── Rugby Union ──────────────────────────────────────────────────────────
    "267979":             ["TNT Sports"],                  # Gallagher Premiership
    "180659":             ["BBC", "ITV"],                  # Six Nations
    "242041":             ["Sky Sports"],                  # Super Rugby Pacific
    "164205":             ["ITV"],                         # Rugby World Cup
    "289234":             ["TNT Sports"],                  # United Rugby Championship
    "170645":             ["Premier Sports"],              # Top 14 (France)
    "270559":             ["TNT Sports"],                  # Heineken Champions Cup
    "289235":             ["TNT Sports"],                  # EPCR Challenge Cup
    "398":                ["Sky Sports"],                  # The Rugby Championship
    "244293":             ["Sky Sports"],                  # The Rugby Championship (alt ID)
}


def get_uk_channels(competition_code: str) -> list[str]:
    """Return list of UK broadcaster names for a competition, or [] if unknown."""
    return _UK_RIGHTS.get(competition_code, [])


def enrich_matches_with_uk_broadcast(matches: list[dict], competition_code: str) -> None:
    """Add 'broadcast_uk' field to each match dict in-place.

    Sets 'broadcast_uk' to a comma-joined channel string (or "" if unknown).
    The existing 'broadcast' field (ESPN US data) is left untouched.
    """
    channels = get_uk_channels(competition_code)
    channel_str = " / ".join(channels)
    for match in matches:
        match["broadcast_uk"] = channel_str
