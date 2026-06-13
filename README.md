# Sports Live — Home Assistant Integration

Multi-sport live scores and standings for [Home Assistant](https://www.home-assistant.io/), powered by the ESPN public API.

Supports **Soccer/Football**, **NFL (American Football)**, and **Rugby** with a sport-agnostic architecture designed to add more sports without changing the core.

Forked from [Bobsilvio/calcio-live](https://github.com/Bobsilvio/calcio-live) — original soccer-only integration. This project extends it to a full multi-sport platform with a new domain (`sports_live`), config-flow redesign, and DataUpdateCoordinator.

---

## Features

| Feature | Soccer | NFL | Rugby |
|---------|:------:|:---:|:-----:|
| Live scoreboard | ✅ | ✅ | ✅ |
| Standings | ✅ | ✅ | — |
| News feed | ✅ | ✅ | ✅ |
| Bracket/Playoff tree | ✅ | ✅ | — |
| Lineup (pre-match) | ✅ | — | — |
| Match summary | ✅ | ✅ | — |
| Team mode | ✅ | ✅ | ✅ |
| All-today view | ✅ | ✅ | ✅ |

---

## Installation

### Via HACS (recommended)

1. Add this repo as a custom HACS repository:
   - **HACS → Integrations → ⋮ → Custom repositories**
   - URL: `https://github.com/andrejkurlovic/ha-sports-live`
   - Category: **Integration**
2. Install **Sports Live (ESPN)**
3. Restart Home Assistant

### Manual

Copy `custom_components/sports_live/` into your HA config's `custom_components/` directory, then restart.

---

## Configuration

Go to **Settings → Devices & Services → Add Integration → Sports Live**.

The config flow has four steps:

### Step 1 — Choose Sport

| Value | Sport |
|-------|-------|
| `soccer` | Soccer / Football |
| `nfl` | American Football (NFL) |
| `rugby` | Rugby Union |

### Step 2 — Choose Mode

| Mode | Description |
|------|-------------|
| **Competition** | Track a league/cup: scoreboard + standings + news |
| **Team** | Track a specific team: next match, schedule |
| **All Today** | All matches across all leagues today |
| **News** | Latest headlines for the sport |
| **Manual Team** | Enter team ID and competition manually |

### Step 3 — Select Competition

Dropdown populated from ESPN. For rugby, pre-loaded list:

| Rugby Competition | ESPN ID |
|-------------------|---------|
| Gallagher Premiership | 267979 |
| Six Nations | 180659 |
| Super Rugby Pacific | 242041 |
| Rugby World Cup | 164205 |
| United Rugby Championship | 270559 |
| The Rugby Championship | 244293 |
| Heineken Champions Cup | 271937 |

### Step 4 — Select Team *(optional)*

Dropdown of teams in the chosen competition. Leave blank to track the whole competition.

### Options

After setup, go to **Configure** on the integration entry:

| Option | Default | Range |
|--------|---------|-------|
| Scan interval | 5 min | 1–30 min |
| Recent match window | 12 h | 6/12/24/48 h |

---

## Entities Created

Entity names follow the pattern `sensor.sports_live_<type>_<slug>`.

| Sensor type | Mode | Description |
|-------------|------|-------------|
| `matches` | Competition | All matches for the competition |
| `standings` | Competition (soccer/NFL) | League table or conference standings |
| `news` | Competition / News | Latest articles |
| `bracket` | Competition + knockout | Knockout bracket/playoff tree |
| `next_match` | Team | Upcoming or live match |
| `schedule` | Team | Full team schedule |
| `all_today` | All Today | Every match today across all leagues |

---

## Events

The integration fires HA events for real-time automation:

| Event | Trigger | Fields |
|-------|---------|--------|
| `sports_live_score` | Goal / score change | `sport`, `competition`, `home_team`, `away_team`, `home_score`, `away_score`, `scorer` |
| `sports_live_discipline` | Yellow/red card | `sport`, `competition`, `team`, `player`, `card_type` |
| `sports_live_match_finished` | Full-time | `sport`, `competition`, `home_team`, `away_team`, `home_score`, `away_score` |

Legacy soccer events (`calcio_live_goal`, `calcio_live_card`, `calcio_live_match_finished`) are also fired for backward compatibility.

### Example Automation

```yaml
automation:
  - alias: "Announce Goal"
    trigger:
      - platform: event
        event_type: sports_live_score
    action:
      - service: notify.mobile_app
        data:
          title: "GOAL! {{ trigger.event.data.scorer }}"
          message: >
            {{ trigger.event.data.home_team }} {{ trigger.event.data.home_score }}
            – {{ trigger.event.data.away_score }} {{ trigger.event.data.away_team }}
```

---

## Architecture

```
custom_components/sports_live/
├── __init__.py              # Integration setup
├── manifest.json
├── const.py                 # All constants
├── config_flow.py           # Multi-step config flow + options flow
├── coordinator.py           # DataUpdateCoordinator (one per config entry)
├── sensor.py                # CoordinatorEntity sensors + event dispatch
├── sports/
│   ├── profile.py           # SportCapabilities + SportProfile dataclasses
│   └── registry.py          # SPORT_REGISTRY (soccer, nfl, rugby)
├── parsers/
│   ├── scoreboard.py        # Generic match/event parser
│   ├── standings.py         # Generic standings parser (dynamic season)
│   ├── bracket.py           # Knockout/playoff bracket parser
│   ├── summary.py           # Lineup + key events
│   └── news.py              # News article parser
└── translations/
    ├── strings.json
    └── en.json
```

### Adding a New Sport

1. Add a `SportProfile` entry to `sports/registry.py` with the correct ESPN sport slug and capabilities flags
2. If the sport uses numeric competition IDs, set `numeric_competition_ids=True` and provide a hardcoded competition map
3. That's it — the coordinator, sensor, and config flow all read from the registry

---

## Upstream Attribution

This project builds on [calcio-live](https://github.com/Bobsilvio/calcio-live) by [@Bobsilvio](https://github.com/Bobsilvio).  
Original license: MIT — see [LICENSE](LICENSE).

---

## License

MIT
