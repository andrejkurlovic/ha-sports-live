# Sports Live — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz)
[![Tests](https://github.com/andrejkurlovic/ha-sports-live/actions/workflows/tests.yml/badge.svg)](https://github.com/andrejkurlovic/ha-sports-live/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/andrejkurlovic/ha-sports-live)](https://github.com/andrejkurlovic/ha-sports-live/releases)

Live sports scores, standings, brackets, lineups, and news for [Home Assistant](https://www.home-assistant.io/) — powered by the ESPN public API.

Supports **Soccer/Football**, **NFL (American Football)**, and **Rugby Union**, with a sport-agnostic architecture that makes adding further sports straightforward.

> Built on top of [Bobsilvio/calcio-live](https://github.com/Bobsilvio/calcio-live) — the original soccer-only integration. Sports Live extends it to a multi-sport platform under a new domain (`sports_live`) with a redesigned config flow, DataUpdateCoordinator, and UK broadcast information.

---

## What you get

For each competition or team you configure you get a set of Home Assistant sensor entities:

| Sensor | What it shows |
|--------|---------------|
| **Matches** | Full scoreboard for a competition (state, score, clock, venue, broadcast) |
| **Standings** | League table or conference standings with form, goal difference, and — for rugby — bonus points and tries |
| **Next Match** | The next or currently live match for a team, with lineup and summary when available |
| **Schedule** | A team's full fixture list for the season |
| **Bracket** | Knockout/playoff bracket (soccer cup rounds, NFL playoffs) |
| **News** | Latest headlines for the sport or competition |
| **All Today** | Every match across all leagues today |

Every match dict in sensor attributes includes **`broadcast_uk`** — which UK channel to watch on — alongside the ESPN US broadcast field.

---

## Sport Support

| Feature | Soccer | NFL | Rugby |
|---------|:------:|:---:|:-----:|
| Scoreboard | ✅ | ✅ | ✅ |
| Standings | ✅ | ✅ | ✅ |
| Bracket / Playoffs | ✅ | ✅ | — |
| Lineup | ✅ | — | — |
| Match summary | ✅ | ✅ | — |
| Team mode | ✅ | ✅ | ✅ |
| All-today view | ✅ | ✅ | ✅ |
| UK broadcast info | ✅ | ✅ | ✅ |

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/andrejkurlovic/ha-sports-live` — category **Integration**
3. Find **Sports Live (ESPN)** and install it
4. Restart Home Assistant

### Manual

Copy the `custom_components/sports_live/` folder into your HA config's `custom_components/` directory, then restart.

---

## Configuration

**Settings → Devices & Services → Add Integration → Sports Live (ESPN)**

The setup walks you through four steps:

### 1. Choose Sport

| Option | Sport |
|--------|-------|
| Football / Soccer | Soccer, all leagues |
| American Football (NFL) | NFL (all conferences) |
| Rugby Union | All major rugby unions |

### 2. Choose Mode

| Mode | Best for |
|------|----------|
| **Competition** | Following a full league — gets scoreboard + standings + news |
| **Team** | Following a specific club — gets next match, schedule |
| **All Today** | Dashboard overview of everything on today |
| **News** | Latest headlines only |
| **Manual Team** | Enter team ID/competition directly for unsupported combos |

### 3. Select Competition

Dropdown loaded from ESPN. For rugby, a pre-loaded list of major competitions is used (ESPN rugby uses numeric IDs, not slugs):

| Competition | ESPN ID |
|-------------|---------|
| Gallagher Premiership | 267979 |
| Six Nations | 180659 |
| Super Rugby Pacific | 242041 |
| Rugby World Cup | 164205 |
| United Rugby Championship | 289234 |
| Heineken Champions Cup | 270559 |
| Top 14 (France) | 170645 |
| The Rugby Championship | 398 |

### 4. Select Team *(optional)*

Choose a team from the competition to narrow sensors to that club.

### Options (post-setup)

**Configure** on the integration card to change:

| Setting | Default | Range |
|---------|---------|-------|
| Scan interval | 5 min | 1 – 30 min |
| Recent match window | 12 h | 6 / 12 / 24 / 48 h |

---

## Entities & Attributes

Entity IDs follow the pattern `sensor.sports_live_<type>_<slug>`.

Every match object in the `matches` attribute includes:

```yaml
home_team: "Arsenal"
away_team: "Chelsea"
home_score: "2"
away_score: "1"
state: "post"          # pre | in | post
status: "Final"
clock: "90'"
venue: "Emirates Stadium"
venue_city: "London"
broadcast: "NBC"        # ESPN US-market data (may be empty outside NFL)
broadcast_uk: "Sky Sports / TNT Sports"   # UK channel(s), always populated
```

Rugby standings additionally include `bonus_points`, `tries_for`, and `tries_against`.

---

## UK Broadcast Information

ESPN's API only returns US broadcaster data. Sports Live ships a static **UK broadcast rights map** (`broadcast_rights.py`) so the `broadcast_uk` attribute is always populated for supported competitions. Example values:

| Competition | `broadcast_uk` |
|-------------|----------------|
| Premier League | Sky Sports / TNT Sports / Amazon Prime |
| Champions League | TNT Sports |
| Six Nations | BBC / ITV |
| Gallagher Premiership | TNT Sports |
| NFL | Sky Sports / DAZN |
| FA Cup | BBC / ITV |

> **Note:** broadcast rights change every season. The map is reviewed and updated with each release. If a channel is wrong or missing, please [open an issue](https://github.com/andrejkurlovic/ha-sports-live/issues).

---

## HA Events

The integration fires events you can use in automations:

| Event | Fired when | Key data |
|-------|-----------|----------|
| `sports_live_score` | Goal / score change | `sport`, `home_team`, `away_team`, `home_score`, `away_score`, `scorer` |
| `sports_live_discipline` | Yellow / red card | `sport`, `team`, `player`, `card_type` |
| `sports_live_match_finished` | Full time | `sport`, `home_team`, `away_team`, `home_score`, `away_score` |

Legacy `calcio_live_*` events are also fired so existing automations keep working.

### Example — Goal notification

```yaml
automation:
  - alias: "Announce goal"
    trigger:
      - platform: event
        event_type: sports_live_score
    action:
      - service: notify.mobile_app_my_phone
        data:
          title: "GOAL — {{ trigger.event.data.scorer }}"
          message: >
            {{ trigger.event.data.home_team }}
            {{ trigger.event.data.home_score }}–{{ trigger.event.data.away_score }}
            {{ trigger.event.data.away_team }}
```

---

## Architecture

```
custom_components/sports_live/
├── __init__.py           — integration setup
├── manifest.json
├── const.py              — all constants, domain, config keys, sensor types
├── config_flow.py        — 4-step config flow + options flow
├── coordinator.py        — DataUpdateCoordinator (one per entry, 3-retry fetch)
├── sensor.py             — CoordinatorEntity sensors + event dispatch
├── broadcast_rights.py   — static UK broadcaster map
├── sports/
│   ├── profile.py        — SportCapabilities + SportProfile dataclasses
│   └── registry.py       — SPORT_REGISTRY (soccer, nfl, rugby) + URL templates
└── parsers/
    ├── scoreboard.py     — generic match parser (soccer / NFL / rugby)
    ├── standings.py      — generic standings parser with sport-alias handling
    ├── bracket.py        — knockout bracket (two-legged ties + NFL single-game rounds)
    ├── summary.py        — lineup and key match events
    └── news.py
```

**Adding a new sport:** create one `SportProfile` entry in `sports/registry.py` with the ESPN sport slug, capability flags, and URL templates. Everything else — coordinator, config flow, sensors, events — reads from the registry automatically.

---

## Compatibility & Migration

This integration uses domain `sports_live`. It can run **alongside** the original `calcio_live` integration — no migration required. Existing `calcio_live` config entries are untouched.

Legacy `calcio_live_*` HA events are still fired by this integration so any automations you built against the old domain keep working.

---

## Upstream Attribution

Forked from [Bobsilvio/calcio-live](https://github.com/Bobsilvio/calcio-live) — original soccer-only HA integration. Original work copyright Bobsilvio, MIT licence.

---

## Licence

MIT — see [LICENSE](LICENSE).
