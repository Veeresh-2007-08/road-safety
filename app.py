"""
Bengaluru SafeRoute – Main Application Entry Point
Route-safety awareness web dashboard for Bengaluru, Karnataka.

Purpose: Raise safety awareness for people driving or riding on unfamiliar roads.
         NOT a navigation app. NOT an emergency advisory service.

Data policy:
  - All data records carry source, verification status, and confidence labels.
  - Demo data is clearly marked [DEMO DATA] throughout.
  - Media / news-only records are stored as reference and never promoted to verified blackspots.
  - Unknown speed limits are shown as UNKNOWN, never guessed.

Disclaimer (shown prominently in UI):
  "Safety information may be incomplete or outdated.
   Follow road signs, traffic rules, and on-road conditions."
"""

import sys
import logging
from pathlib import Path

# ── Make src/ importable ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

import dash
from dash import html, dcc, Input, Output, State, callback, ctx
import dash_bootstrap_components as dbc
import dash_leaflet as dl

from src.config import (
    APP_HOST, APP_PORT, DEBUG,
    BENGALURU_CENTER, DEFAULT_ZOOM,
    POPULAR_LOCATIONS, TRANSPORT_MODES,
    SAFETY_DISCLAIMER, CORRIDOR_BUFFER_METERS
)
from src.database import init_and_seed_db, SessionLocal
from src.routing import calculate_routes
from src.hazard_analysis import create_safety_corridor, analyze_corridor_hazards
from src.map_components import build_all_map_elements
from src.importers import parse_dash_upload
from src.validation import validate_route_inputs

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s – %(message)s")
logger = logging.getLogger(__name__)

# ── Database bootstrap ────────────────────────────────────────────────────────
logger.info("Initialising database and seeding demo data...")
seed_counts = init_and_seed_db()
logger.info(f"Seed counts: {seed_counts}")

# ── Dash App ──────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="Bengaluru SafeRoute",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
)
server = app.server

# ── Helper components ─────────────────────────────────────────────────────────

def disclaimer_banner():
    return html.Div(
        f"⚠  {SAFETY_DISCLAIMER}",
        className="disclaimer-banner"
    )


def header():
    return html.Div([
        html.H1("🗺 Bengaluru SafeRoute", style={"margin": 0}),
        html.Div("Route-safety awareness for Bengaluru roads • For awareness only",
                 className="tagline")
    ], className="saferoute-header")


def map_legend():
    items = [
        ("#DC2626", "Verified Blackspot"),
        ("#EA580C", "Accident Record"),
        ("#2563EB", "Known Speed Limit"),
        ("#7C3AED", "Sharp / Moderate Curve"),
        ("#6B7280", "Demo / Unverified Data"),
        ("#16A34A", "Selected Route"),
    ]
    return html.Div([
        html.B("Legend", style={"display": "block", "marginBottom": 4}),
        *[html.Div([
            html.Span(style={
                "display": "inline-block", "width": 11, "height": 11,
                "borderRadius": "50%", "background": c,
                "marginRight": 6, "verticalAlign": "middle"
            }),
            label
        ], style={"lineHeight": "1.9"}) for c, label in items]
    ], className="map-legend")


def location_dropdown(id_prefix: str, label: str):
    options = [{"label": f"{name} — {info['desc']}", "value": name}
               for name, info in POPULAR_LOCATIONS.items()]
    return html.Div([
        dbc.Label(label, style={"fontWeight": 600, "fontSize": "0.87rem"}),
        dcc.Dropdown(
            id=f"{id_prefix}-dropdown",
            options=options,
            placeholder="Select a location…",
            clearable=True,
            style={"fontSize": "0.85rem"}
        ),
        html.Small("Or enter coordinates below:", style={"color": "#94a3b8", "marginTop": 2}),
        dbc.Row([
            dbc.Col(dbc.Input(id=f"{id_prefix}-lat", placeholder="Latitude", type="number",
                              min=12.5, max=13.5, step=0.0001, size="sm", style={"marginTop": 4}), width=6),
            dbc.Col(dbc.Input(id=f"{id_prefix}-lon", placeholder="Longitude", type="number",
                              min=77.2, max=78.0, step=0.0001, size="sm", style={"marginTop": 4}), width=6),
        ], className="g-1")
    ])


def route_tab_content():
    return dbc.Row([
        # ── Left sidebar ──────────────────────────────────────────────────────
        dbc.Col([
            html.Div([
                html.H5("Plan Your Route"),
                location_dropdown("start", "🟢 Start Location"),
                html.Div(style={"height": 12}),
                location_dropdown("dest", "🔴 Destination"),
                html.Div(style={"height": 12}),
                dbc.Label("Transport Mode", style={"fontWeight": 600, "fontSize": "0.87rem"}),
                dbc.RadioItems(
                    id="mode-selector",
                    options=[{"label": info["label"], "value": k}
                             for k, info in TRANSPORT_MODES.items()],
                    value="car",
                    inline=False,
                    style={"fontSize": "0.84rem"}
                ),
                html.Div(style={"height": 14}),
                dbc.Button(
                    "🔍 Find Routes & Analyse Safety",
                    id="analyse-btn",
                    color="success",
                    size="lg",
                    className="w-100"
                ),
                dbc.Button(
                    "📍 Use Common Example Routes",
                    id="example-btn",
                    color="outline-secondary",
                    size="sm",
                    className="w-100 mt-2"
                ),
                html.Div(id="input-error", style={"color": "#dc2626", "fontSize": "0.82rem", "marginTop": 6}),
            ], className="sidebar-panel"),

            html.Div([
                html.H5("Route Alternatives"),
                html.Div(id="route-cards-container",
                         children=[html.Small("Calculate a route to see alternatives.",
                                              style={"color": "#94a3b8"})]),
            ], className="sidebar-panel"),

            html.Div([
                html.H5("Route Safety Summary"),
                html.Div(id="safety-summary-panel",
                         children=[html.Small("No route selected.", style={"color": "#94a3b8"})]),
            ], className="sidebar-panel"),

            html.Div([
                html.H5("⚠ Safety Precautions"),
                html.Div(id="precautions-panel",
                         children=[html.Small("No route selected.", style={"color": "#94a3b8"})]),
            ], className="sidebar-panel"),

        ], md=4, style={"overflowY": "auto", "maxHeight": "calc(100vh - 120px)"}),

        # ── Map ───────────────────────────────────────────────────────────────
        dbc.Col([
            html.Div([
                dl.Map(
                    id="main-map",
                    center=BENGALURU_CENTER,
                    zoom=DEFAULT_ZOOM,
                    style={"height": "calc(100vh - 160px)", "width": "100%"},
                    children=[
                        dl.TileLayer(
                            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                            attribution='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                        ),
                        dl.LayerGroup(id="map-layers"),
                    ]
                )
            ], className="map-container"),
            html.Div(map_legend(), style={"marginTop": 10}),
        ], md=8),
    ], style={"marginTop": 10})


def admin_tab_content():
    return html.Div([
        html.H4("Admin / Data Import", style={"marginBottom": 16}),
        html.P(
            "Upload verified CSV or GeoJSON files to extend the local safety database. "
            "All imports are validated against the data schema before saving. "
            "Media/news-only sources cannot be imported as verified blackspots.",
            style={"fontSize": "0.9rem", "color": "#475569"}
        ),
        dbc.Row([
            dbc.Col([
                html.H6("Import Accidents (CSV)"),
                dcc.Upload(
                    id="upload-accidents",
                    children=html.Div(["📁 Drag & drop or ", html.A("select file")]),
                    className="upload-box",
                    accept=".csv"
                ),
                html.Div(id="upload-accidents-result", style={"marginTop": 8, "fontSize": "0.82rem"}),
            ], md=6),
            dbc.Col([
                html.H6("Import Blackspots (GeoJSON)"),
                dcc.Upload(
                    id="upload-blackspots",
                    children=html.Div(["📁 Drag & drop or ", html.A("select file")]),
                    className="upload-box",
                    accept=".geojson,.json"
                ),
                html.Div(id="upload-blackspots-result", style={"marginTop": 8, "fontSize": "0.82rem"}),
            ], md=6),
        ], className="g-3"),
        dbc.Row([
            dbc.Col([
                html.H6("Import Speed Limits (CSV)"),
                dcc.Upload(
                    id="upload-speeds",
                    children=html.Div(["📁 Drag & drop or ", html.A("select file")]),
                    className="upload-box",
                    accept=".csv"
                ),
                html.Div(id="upload-speeds-result", style={"marginTop": 8, "fontSize": "0.82rem"}),
            ], md=6),
            dbc.Col([
                html.H6("Import Road Curves (GeoJSON)"),
                dcc.Upload(
                    id="upload-curves",
                    children=html.Div(["📁 Drag & drop or ", html.A("select file")]),
                    className="upload-box",
                    accept=".geojson,.json"
                ),
                html.Div(id="upload-curves-result", style={"marginTop": 8, "fontSize": "0.82rem"}),
            ], md=6),
        ], className="g-3 mt-3"),

        html.Hr(style={"marginTop": 28}),
        html.H5("CSV / GeoJSON Schema Reference"),
        dbc.Accordion([
            dbc.AccordionItem([
                html.Pre(
                    "accident_id, date, latitude, longitude, road_name, ward,\n"
                    "severity (Fatal|Grievous|Minor), vehicle_type, cause,\n"
                    "source_id, confidence_level",
                    style={"background": "#f8fafc", "padding": 10, "borderRadius": 6, "fontSize": "0.78rem"}
                )
            ], title="Accidents CSV"),
            dbc.AccordionItem([
                html.Pre(
                    "GeoJSON FeatureCollection. Each Feature properties:\n"
                    "  blackspot_id, name, road_name, latitude, longitude,\n"
                    "  radius_meters, accident_count, fatal_count, risk_score (0–100),\n"
                    "  status, source_id, verified_date",
                    style={"background": "#f8fafc", "padding": 10, "borderRadius": 6, "fontSize": "0.78rem"}
                )
            ], title="Blackspots GeoJSON"),
            dbc.AccordionItem([
                html.Pre(
                    "speed_limit_id, road_name, latitude, longitude,\n"
                    "speed_kmph (10–120), direction (Both|North|South|East|West),\n"
                    "source_id, verified_date, confidence_level",
                    style={"background": "#f8fafc", "padding": 10, "borderRadius": 6, "fontSize": "0.78rem"}
                )
            ], title="Speed Limits CSV"),
            dbc.AccordionItem([
                html.Pre(
                    "GeoJSON FeatureCollection. Each Feature geometry: LineString.\n"
                    "Properties: curve_id, road_name, curve_severity (sharp|moderate|gentle),\n"
                    "estimated_radius_meters (optional), warning_text,\n"
                    "source_id, confidence_level",
                    style={"background": "#f8fafc", "padding": 10, "borderRadius": 6, "fontSize": "0.78rem"}
                )
            ], title="Road Curves GeoJSON"),
        ], start_collapsed=True)
    ], style={"padding": 20})


def sources_tab_content():
    with SessionLocal() as db:
        from src.models import SourceModel
        sources = db.query(SourceModel).all()

    rows = []
    for src in sources:
        status_class = {
            "verified_official": "source-tag-verified",
            "verified_admin": "source-tag-verified",
            "demo": "source-tag-demo",
            "community_verified": "source-tag-verified",
        }.get(src.verification_status, "source-tag-unverified")
        rows.append(html.Tr([
            html.Td(src.source_id, style={"fontSize": "0.75rem", "fontFamily": "monospace"}),
            html.Td(src.source_name, style={"fontSize": "0.82rem"}),
            html.Td(src.source_type, style={"fontSize": "0.78rem"}),
            html.Td(html.Span(src.verification_status, className=status_class), style={"fontSize": "0.78rem"}),
            html.Td(src.last_updated, style={"fontSize": "0.78rem"}),
            html.Td(html.Small(src.licence_or_usage_note, style={"color": "#64748b"})),
        ]))

    return html.Div([
        html.H4("Data Sources & Provenance"),
        html.P(
            "Every safety record in the database is linked to a registered source. "
            "Records marked 'demo' are synthetic demonstration data. "
            "Media/news records are stored as reference only and are never shown as verified blackspots.",
            style={"fontSize": "0.9rem", "color": "#475569"}
        ),
        dbc.Table(
            [html.Thead(html.Tr([
                html.Th("Source ID"), html.Th("Name"), html.Th("Type"),
                html.Th("Status"), html.Th("Updated"), html.Th("Licence / Usage")
            ]))] + [html.Tbody(rows)],
            bordered=True, hover=True, responsive=True, size="sm",
            style={"fontSize": "0.8rem"}
        )
    ], style={"padding": 20})


# ── App Layout ────────────────────────────────────────────────────────────────
app.layout = html.Div([
    # Hidden stores
    dcc.Store(id="routes-store", data=[]),
    dcc.Store(id="selected-route-idx", data=0),
    dcc.Store(id="hazard-store", data={}),

    header(),
    disclaimer_banner(),

    dbc.Container([
        dbc.Tabs([
            dbc.Tab(route_tab_content(), label="🗺 Route Planner", tab_id="tab-route"),
            dbc.Tab(admin_tab_content(), label="📂 Admin / Import", tab_id="tab-admin"),
            dbc.Tab(sources_tab_content(), label="📋 Data Sources", tab_id="tab-sources"),
        ], id="main-tabs", active_tab="tab-route", style={"marginTop": 10}),
    ], fluid=True, style={"paddingLeft": 10, "paddingRight": 10}),
])


# ── Callbacks ─────────────────────────────────────────────────────────────────

def _get_coords(dropdown_value, lat_input, lon_input):
    """Resolve selected dropdown location OR manual lat/lon inputs."""
    if dropdown_value and dropdown_value in POPULAR_LOCATIONS:
        info = POPULAR_LOCATIONS[dropdown_value]
        return info["lat"], info["lon"]
    if lat_input is not None and lon_input is not None:
        return float(lat_input), float(lon_input)
    return None, None


@app.callback(
    Output("start-lat", "value"),
    Output("start-lon", "value"),
    Input("start-dropdown", "value"),
    prevent_initial_call=True
)
def fill_start_coords(name):
    if name and name in POPULAR_LOCATIONS:
        info = POPULAR_LOCATIONS[name]
        return info["lat"], info["lon"]
    return dash.no_update, dash.no_update


@app.callback(
    Output("dest-lat", "value"),
    Output("dest-lon", "value"),
    Input("dest-dropdown", "value"),
    prevent_initial_call=True
)
def fill_dest_coords(name):
    if name and name in POPULAR_LOCATIONS:
        info = POPULAR_LOCATIONS[name]
        return info["lat"], info["lon"]
    return dash.no_update, dash.no_update


@app.callback(
    Output("start-dropdown", "value"),
    Output("dest-dropdown", "value"),
    Output("start-lat", "value", allow_duplicate=True),
    Output("start-lon", "value", allow_duplicate=True),
    Output("dest-lat", "value", allow_duplicate=True),
    Output("dest-lon", "value", allow_duplicate=True),
    Input("example-btn", "n_clicks"),
    prevent_initial_call=True
)
def load_example_route(n):
    """Load an example route: Majestic to Electronic City."""
    return (
        "Majestic (KSR Railway Station)",
        "Electronic City (Phase 1)",
        12.9781, 77.5695,
        12.8452, 77.6602
    )


@app.callback(
    Output("routes-store", "data"),
    Output("selected-route-idx", "data"),
    Output("route-cards-container", "children"),
    Output("input-error", "children"),
    Input("analyse-btn", "n_clicks"),
    State("start-lat", "value"),
    State("start-lon", "value"),
    State("dest-lat", "value"),
    State("dest-lon", "value"),
    State("mode-selector", "value"),
    prevent_initial_call=True
)
def compute_routes(n_clicks, start_lat, start_lon, dest_lat, dest_lon, mode):
    """Calculate route alternatives and populate the route-cards sidebar."""
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update, ""

    if any(v is None for v in [start_lat, start_lon, dest_lat, dest_lon]):
        return [], 0, [html.Small("Please fill in both start and destination locations.", style={"color": "#dc2626"})], ""

    start_lat, start_lon = float(start_lat), float(start_lon)
    dest_lat, dest_lon = float(dest_lat), float(dest_lon)

    # Validation
    ok, err_msg = validate_route_inputs(start_lat, start_lon, dest_lat, dest_lon, mode, CORRIDOR_BUFFER_METERS)
    if not ok:
        return [], 0, [html.Small(err_msg, style={"color": "#dc2626"})], err_msg

    # Calculate routes
    routes = calculate_routes(start_lat, start_lon, dest_lat, dest_lon, mode=mode, max_alternatives=3)

    # Compute hazard score for each route (quick preview)
    with SessionLocal() as db:
        scored_routes = []
        for r in routes:
            coords = r["coordinates"]
            _, corridor_utm, _ = create_safety_corridor(coords, CORRIDOR_BUFFER_METERS)
            from shapely.geometry import LineString as SLS
            route_line = SLS([(lon, lat) for lat, lon in coords])
            hazards = analyze_corridor_hazards(
                db, corridor_utm, route_line,
                buffer_meters=CORRIDOR_BUFFER_METERS,
                mode=mode,
                geometry_curves=r.get("detected_curves", [])
            )
            r["risk_score"] = hazards["final_risk_score"]
            r["safety_level"] = hazards["safety_level"]
            r["safety_badge_color"] = hazards["safety_badge_color"]
            scored_routes.append(r)

    # Build route cards
    cards = []
    for idx, r in enumerate(scored_routes):
        score = r["risk_score"]
        badge_color = r["safety_badge_color"]
        cards.append(
            html.Div([
                html.Div(r["title"], className="route-card-title"),
                html.Div(f"📍 {r['distance_km']} km · ⏱ {r['estimated_minutes']} min", className="route-card-meta"),
                dbc.Badge(
                    f"Risk Score: {score}/100 – {r['safety_level']}",
                    color=badge_color,
                    className="route-card-score"
                ),
                html.Small(
                    f"Via: {', '.join(r['primary_corridors'][:2])}",
                    style={"color": "#64748b", "display": "block", "marginTop": 4, "fontSize": "0.74rem"}
                )
            ],
                id={"type": "route-card", "index": idx},
                className="route-card selected" if idx == 0 else "route-card",
                n_clicks=0
            )
        )

    return scored_routes, 0, cards, ""


@app.callback(
    Output("selected-route-idx", "data", allow_duplicate=True),
    Output("map-layers", "children"),
    Output("safety-summary-panel", "children"),
    Output("precautions-panel", "children"),
    Output("hazard-store", "data"),
    Input("routes-store", "data"),
    Input("selected-route-idx", "data"),
    State("mode-selector", "value"),
    prevent_initial_call=True
)
def render_selected_route(routes_data, selected_idx, mode):
    """Render map layers and safety summary for the selected route."""
    if not routes_data or selected_idx is None:
        return selected_idx, [], dash.no_update, dash.no_update, {}

    selected_idx = int(selected_idx)
    if selected_idx >= len(routes_data):
        selected_idx = 0
    route = routes_data[selected_idx]
    coords = route["coordinates"]

    # Run full hazard analysis
    with SessionLocal() as db:
        _, corridor_utm, _ = create_safety_corridor(coords, CORRIDOR_BUFFER_METERS)
        from shapely.geometry import LineString as SLS
        route_line = SLS([(lon, lat) for lat, lon in coords])
        hazards = analyze_corridor_hazards(
            db, corridor_utm, route_line,
            buffer_meters=CORRIDOR_BUFFER_METERS,
            mode=mode,
            geometry_curves=route.get("detected_curves", [])
        )

    mh = hazards["matched_hazards"]
    map_elements = build_all_map_elements(
        coords,
        mh["blackspots"],
        mh["accidents"],
        mh["speed_limits"],
        mh["curves"],
        route_title=route["title"]
    )

    # Safety summary panel
    sc = hazards["score_components"]
    cnt = hazards["counts"]
    score = hazards["final_risk_score"]
    badge_color = hazards["safety_badge_color"]

    summary_panel = html.Div([
        dbc.Row([
            dbc.Col([
                html.Div(f"{score}", className="score-display",
                         style={"color": {"success": "#16a34a", "warning": "#d97706",
                                          "danger": "#dc2626", "dark": "#1e3a5f"}.get(badge_color, "#1e3a5f")}),
                dbc.Badge(hazards["safety_level"], color=badge_color, className="mt-1"),
                html.Div(f"Mode: {hazards['mode_label']}", style={"fontSize": "0.75rem", "color": "#64748b", "marginTop": 4})
            ], width=5),
            dbc.Col([
                dbc.Row([
                    dbc.Col(html.Div([html.Div(str(cnt["blackspots"]), className="stat-number"), "Blackspots"], className="stat-badge"), width=6),
                    dbc.Col(html.Div([html.Div(str(cnt["total_accidents"]), className="stat-number"), "Incidents"], className="stat-badge"), width=6),
                ], className="g-1"),
                dbc.Row([
                    dbc.Col(html.Div([html.Div(str(cnt["sharp_curves"] + cnt["moderate_curves"]), className="stat-number"), "Curves"], className="stat-badge"), width=6),
                    dbc.Col(html.Div([html.Div(str(cnt["speed_limits"]), className="stat-number"), "Speed Signs"], className="stat-badge"), width=6),
                ], className="g-1 mt-1"),
            ], width=7),
        ]),
        html.Hr(style={"margin": "12px 0"}),
        html.B("Score Breakdown:", style={"fontSize": "0.82rem"}),
        html.Div([
            html.Div([
                html.Span(label, style={"color": "#64748b"}),
                html.Span(f"+{val}", style={"fontWeight": 700, "color": "#dc2626" if val > 0 else "#16a34a"})
            ], className="score-breakdown-row")
            for label, val in [
                ("Blackspot zones", sc["blackspot_penalty"]),
                ("Fatal accidents", sc["fatal_accident_penalty"]),
                ("Grievous accidents", sc["grievous_accident_penalty"]),
                ("Minor accidents", sc["minor_accident_penalty"]),
                ("Sharp curves", sc["sharp_curve_penalty"]),
                ("Moderate curves", sc["moderate_curve_penalty"]),
                ("Unknown speed limit", sc["unknown_speed_penalty"]),
            ]
        ]),
        html.Div([
            html.Span("Total (raw)", style={"color": "#64748b"}),
            html.Span(f"{sc['raw_total']}", style={"fontWeight": 700})
        ], className="score-breakdown-row"),
        html.Small(
            f"Vulnerability multiplier: ×{hazards['vulnerability_multiplier']} ({hazards['mode_label']})",
            style={"color": "#94a3b8", "display": "block", "marginTop": 4}
        ),
        html.Hr(style={"margin": "10px 0"}),
        html.Div([
            html.B("Route: "), route["title"], html.Br(),
            html.B("Distance: "), f"{route['distance_km']} km", html.Br(),
            html.B("Est. Time: "), f"{route['estimated_minutes']} min", html.Br(),
            html.B("Speed Limits: "), hazards["speed_limit_status"],
        ], style={"fontSize": "0.82rem"}),
        html.Small("⚠ This score is for awareness only. It is not a guarantee of safety.",
                   style={"color": "#94a3b8", "display": "block", "marginTop": 6}),
    ])

    # Precautions panel
    prec_items = []
    for p in hazards["precautions"]:
        is_disc = "Safety information may be incomplete" in p
        prec_items.append(html.Div(p, className="precaution-item disclaimer" if is_disc else "precaution-item"))

    return selected_idx, map_elements, summary_panel, html.Div(prec_items), hazards


# Route card click handler
@app.callback(
    Output("selected-route-idx", "data", allow_duplicate=True),
    Input({"type": "route-card", "index": dash.ALL}, "n_clicks"),
    State("routes-store", "data"),
    prevent_initial_call=True
)
def select_route_card(n_clicks_list, routes_data):
    triggered = ctx.triggered_id
    if triggered and isinstance(triggered, dict):
        idx = triggered.get("index", 0)
        return idx
    return dash.no_update


# Admin upload callbacks
def _make_upload_callback(upload_id, result_id, data_type):
    @app.callback(
        Output(result_id, "children"),
        Input(upload_id, "contents"),
        State(upload_id, "filename"),
        prevent_initial_call=True
    )
    def handle_upload(contents, filename):
        if not contents or not filename:
            return ""
        with SessionLocal() as db:
            result = parse_dash_upload(contents, filename, data_type, db)
        imported = result["imported"]
        errors = result["errors"]
        parts = [dbc.Alert(f"✅ {imported} record(s) imported from '{filename}'.",
                           color="success", dismissable=True, style={"fontSize": "0.82rem"})]
        for err in errors[:5]:
            parts.append(dbc.Alert(f"❌ {err}", color="danger", dismissable=True, style={"fontSize": "0.78rem"}))
        if len(errors) > 5:
            parts.append(html.Small(f"…and {len(errors)-5} more errors.", style={"color": "#dc2626"}))
        return parts


_make_upload_callback("upload-accidents", "upload-accidents-result", "accidents")
_make_upload_callback("upload-blackspots", "upload-blackspots-result", "blackspots")
_make_upload_callback("upload-speeds", "upload-speeds-result", "speed_limits")
_make_upload_callback("upload-curves", "upload-curves-result", "curves")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info(f"Starting Bengaluru SafeRoute at http://{APP_HOST}:{APP_PORT}")
    app.run(host=APP_HOST, port=APP_PORT, debug=DEBUG)
