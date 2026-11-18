# Bengaluru SafeRoute

> **Route-safety awareness for people driving or riding on unfamiliar roads in Bengaluru, Karnataka.**
>
> ⚠ **Disclaimer:** Safety information may be incomplete or outdated. Follow road signs, traffic rules, and on-road conditions.

---

## Purpose

Bengaluru SafeRoute is a **read-only awareness dashboard**, not a navigation app and not an emergency advisory service.  
It helps users understand known safety hazards — blackspots, accident clusters, speed limits, and road curves — along or near a chosen route.

---

## Screenshots / Features

| Feature | Detail |
|---|---|
| Interactive Leaflet map | Zoom, pan, click markers for details |
| Up to 3 route alternatives | Scored and ranked by safety |
| Colour-coded safety markers | Red=blackspot · Orange=accident · Blue=speed · Purple=curve |
| Transparent risk score | Every score component is shown individually |
| Demo mode | No API key, no live data needed |
| Admin import | Upload CSV / GeoJSON to extend the database |

---

## Windows Setup

### 1. Prerequisites

- Python 3.10 or later (from [python.org](https://www.python.org/downloads/))
- Git (optional, for cloning)

### 2. Create and activate a virtual environment

```bat
cd bengaluru-saferoute
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```bat
pip install -r requirements.txt
```

### 4. Configure environment (optional)

Copy `.env.example` to `.env` and edit as needed:

```bat
copy .env.example .env
```

Default settings work immediately without editing.

### 5. Run the application

```bat
python app.py
```

Open your browser at **http://127.0.0.1:8050**

The app seeds the database with demo data automatically on first run.

### 6. Run tests

```bat
python -m pytest tests/ -v
```

---

## Project Structure

```
bengaluru-saferoute/
├── app.py                  ← Main Dash application entry point
├── requirements.txt        ← Python dependencies
├── README.md
├── .env.example            ← Environment variable template
├── data_sources.yaml       ← Source registry (data provenance)
├── assets/
│   └── custom.css          ← UI styling
├── data/
│   ├── demo_accidents.csv       ← 16 demo accident records
│   ├── demo_blackspots.geojson  ← 8 demo blackspots
│   ├── demo_speed_limits.csv    ← 14 demo speed-limit entries
│   ├── demo_curves.geojson      ← 10 demo road curves
│   └── sources.csv              ← Data source registry (CSV)
├── src/
│   ├── config.py           ← App configuration and constants
│   ├── database.py         ← SQLAlchemy engine, session, and seed logic
│   ├── models.py           ← SQLAlchemy ORM + Pydantic schemas
│   ├── importers.py        ← CSV / GeoJSON import with validation
│   ├── routing.py          ← Bengaluru arterial road graph + route calculation
│   ├── hazard_analysis.py  ← Corridor creation, hazard intersect, risk scoring
│   ├── curve_analysis.py   ← Road geometry curve detection
│   ├── map_components.py   ← Leaflet marker/polyline builders
│   └── validation.py       ← Input and policy validation helpers
└── tests/
    ├── test_importers.py         ← Import and schema validation tests
    ├── test_hazard_analysis.py   ← Corridor matching and risk-score tests
    └── test_curve_analysis.py    ← Curve detection and bearing tests
```

---

## Demo Data

All demo records are labelled **[DEMO DATA]** in the UI.  
They are synthetic and do not reflect actual crash records.  
Every demo record is linked to `SRC_DEMO_BENCHMARK` (verification_status = `demo`).

| Dataset | Records | File |
|---|---|---|
| Accidents | 16 | `data/demo_accidents.csv` |
| Blackspots | 8 | `data/demo_blackspots.geojson` |
| Speed limits | 14 | `data/demo_speed_limits.csv` |
| Road curves | 10 | `data/demo_curves.geojson` |

---

## Admin / Data Import Schemas

### Accidents CSV

| Column | Type | Notes |
|---|---|---|
| `accident_id` | string | Unique ID, e.g. `ACC_001` |
| `date` | YYYY-MM-DD | Incident date |
| `latitude` | float | 12.5–13.5 (Bengaluru bbox) |
| `longitude` | float | 77.2–78.0 |
| `road_name` | string | Road or corridor name |
| `ward` | string | Optional. Bengaluru ward |
| `severity` | Fatal \| Grievous \| Minor | Required |
| `vehicle_type` | string | Optional |
| `cause` | string | Optional |
| `source_id` | string | Must exist in `sources` registry |
| `confidence_level` | string | e.g. `verified_official`, `demo` |

### Blackspots GeoJSON

GeoJSON FeatureCollection. Each Feature must be a `Point` geometry.  
Properties per Feature:

| Property | Type | Notes |
|---|---|---|
| `blackspot_id` | string | Unique ID |
| `name` | string | Human-readable name |
| `road_name` | string | |
| `latitude` / `longitude` | float | Coordinates |
| `radius_meters` | float | 10–1000. Zone of influence |
| `accident_count` | int | ≥ 0 |
| `fatal_count` | int | ≥ 0 |
| `risk_score` | float | 0.0–100.0 |
| `status` | string | `verified_official`, `verified_admin`, `demo` |
| `source_id` | string | Must exist in sources registry |
| `verified_date` | YYYY-MM-DD | |

> **Policy:** Records from `media_report` / `news_archive` sources may never be imported as `verified_official` or `verified_admin` blackspots.

### Speed Limits CSV

| Column | Type | Notes |
|---|---|---|
| `speed_limit_id` | string | Unique ID |
| `road_name` | string | |
| `latitude` / `longitude` | float | Bengaluru bbox |
| `speed_kmph` | int | 10–120 |
| `direction` | string | `Both`, `North`, `South`, `East`, `West` |
| `source_id` | string | Must exist |
| `verified_date` | YYYY-MM-DD | |
| `confidence_level` | string | |

### Road Curves GeoJSON

GeoJSON FeatureCollection. Each Feature must be a `LineString` geometry.  
Properties per Feature:

| Property | Type | Notes |
|---|---|---|
| `curve_id` | string | Unique ID |
| `road_name` | string | |
| `curve_severity` | `sharp` \| `moderate` \| `gentle` | Required |
| `estimated_radius_meters` | float | Optional. Leave null if not measured |
| `warning_text` | string | Precautionary text |
| `source_id` | string | Must exist |
| `confidence_level` | string | e.g. `geometry-derived`, `verified_field_survey` |

---

## Risk Score Methodology

The route safety score (0–100) is computed transparently from weighted hazard counts:

| Component | Base Weight |
|---|---|
| Verified blackspot near corridor | 25 pts each |
| Fatal accident record | 18 pts each |
| Grievous accident | 10 pts each |
| Minor accident | 4 pts each |
| Sharp curve | 12 pts each |
| Moderate curve | 6 pts each |
| Unknown speed limit section | 5 pts |

All weights are multiplied by a **vulnerability multiplier** based on transport mode:

| Mode | Multiplier |
|---|---|
| Car / Four-wheeler | 1.0× |
| Motorcycle / Two-wheeler | 1.3× |
| Bicycle | 1.6× |
| Pedestrian | 2.0× |

The final score is capped at 100. All component weights and multipliers are shown in the UI.  
**This score is for awareness only. It is not a prediction or guarantee of safety.**

---

## Data Sources & Licences

| Source | Type | Licence |
|---|---|---|
| OpenStreetMap | Road geometry, speed tags | ODbL 1.0 |
| Bengaluru Traffic Police Annual Report | Official accident data | Public Government Document |
| MoRTH / Karnataka Police Blackspot Audit | Blackspot records | OGDL India |
| BBMP Road Safety Portal | Municipal infrastructure | Municipal Public Notice |
| Demo Benchmark Dataset | Synthetic demonstration | Educational Use Only |

Full provenance is viewable in the **Data Sources** tab of the app.

---

## Legal & Usage Notes

- OpenStreetMap data © OpenStreetMap contributors, ODbL 1.0
- This application does **not** scrape Google Maps or any restricted source
- Overpass API access respects stated rate limits (2-second delay between requests)
- No personal, emergency, or real-time data is collected or transmitted
- Demo data is synthetic and must not be used for actual road safety decisions

---

## Licence

MIT License – see `LICENSE` file (create as appropriate for your deployment).
