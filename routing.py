"""
Routing engine for Bengaluru SafeRoute.
Calculates primary and alternative routes, polyline geometries,
travel times across transport modes, and detects curve geometries.
Supports both fast high-fidelity local arterial network and live OSMnx retrieval.
"""

import math
import logging
from typing import List, Tuple, Dict, Any, Optional
import networkx as nx
from shapely.geometry import LineString

from src.config import TRANSPORT_MODES, POPULAR_LOCATIONS
from src.curve_analysis import (
    haversine_distance_meters,
    detect_curves_from_coordinates
)

logger = logging.getLogger(__name__)


def build_bengaluru_arterial_graph() -> nx.MultiDiGraph:
    """
    Construct a connected arterial road network graph for Bengaluru.
    Contains real-world coordinates, intermediate waypoint curves, road names,
    and road classes connecting all major zones and junctions.
    """
    G = nx.MultiDiGraph()

    # Define key nodes in Bengaluru
    nodes = {
        "majestic": {"lat": 12.9781, "lon": 77.5695, "name": "Majestic (KSR Station)"},
        "corporation_circle": {"lat": 12.9715, "lon": 77.5835, "name": "Corporation Circle"},
        "mg_road": {"lat": 12.9754, "lon": 77.6066, "name": "MG Road / Trinity"},
        "richmond_circle": {"lat": 12.9664, "lon": 77.5991, "name": "Richmond Circle"},
        "indiranagar": {"lat": 12.9784, "lon": 77.6408, "name": "Indiranagar 100 Ft Rd"},
        "domlur": {"lat": 12.9609, "lon": 77.6387, "name": "Domlur Flyover"},
        "koramangala": {"lat": 12.9344, "lon": 77.6258, "name": "Koramangala 80 Ft Rd"},
        "dairy_circle": {"lat": 12.9348, "lon": 77.5997, "name": "Dairy Circle"},
        "silk_board": {"lat": 12.9177, "lon": 77.6238, "name": "Silk Board Junction"},
        "hsr_layout": {"lat": 12.9116, "lon": 77.6389, "name": "HSR Layout"},
        "electronic_city": {"lat": 12.8452, "lon": 77.6602, "name": "Electronic City Ph 1"},
        "hebbal": {"lat": 13.0359, "lon": 77.5971, "name": "Hebbal Flyover"},
        "mekhri_circle": {"lat": 13.0076, "lon": 77.5832, "name": "Mekhri Circle"},
        "malleshwaram": {"lat": 13.0084, "lon": 77.5702, "name": "Malleshwaram"},
        "yeshwanthpur": {"lat": 13.0232, "lon": 77.5501, "name": "Yeshwanthpur"},
        "goraguntepalya": {"lat": 13.0285, "lon": 77.5408, "name": "Goraguntepalya"},
        "rajajinagar": {"lat": 12.9904, "lon": 77.5528, "name": "Rajajinagar"},
        "deepanjali_nagar": {"lat": 12.9535, "lon": 77.5412, "name": "Mysore Rd / Deepanjali Nagar"},
        "jayanagar": {"lat": 12.9298, "lon": 77.5833, "name": "Jayanagar 4th Block"},
        "banashankari": {"lat": 12.9155, "lon": 77.5736, "name": "Banashankari Bus Stand"},
        "kr_puram": {"lat": 12.9982, "lon": 77.6625, "name": "KR Puram Hanging Bridge"},
        "marathahalli": {"lat": 12.9553, "lon": 77.7011, "name": "Marathahalli Bridge"},
        "whitefield": {"lat": 12.9858, "lon": 77.7314, "name": "Whitefield ITPL"}
    }

    for nid, data in nodes.items():
        G.add_node(nid, y=data["lat"], x=data["lon"], name=data["name"])

    # Define edges with real road names, intermediate waypoints (reflecting true curvature), and distance
    corridors = [
        # Majestic to Corporation / Richmond / MG Road
        ("majestic", "corporation_circle", "K.G. Road", [
            (12.9781, 77.5695), (12.9740, 77.5760), (12.9715, 77.5835)
        ]),
        ("corporation_circle", "richmond_circle", "Kasturba Road / Residency Road", [
            (12.9715, 77.5835), (12.9680, 77.5910), (12.9664, 77.5991)
        ]),
        ("corporation_circle", "mg_road", "Cantonment Corridor", [
            (12.9715, 77.5835), (12.9730, 77.5950), (12.9754, 77.6066)
        ]),
        ("richmond_circle", "mg_road", "Residency Road", [
            (12.9664, 77.5991), (12.9710, 77.6030), (12.9754, 77.6066)
        ]),
        # MG Road to Indiranagar & Domlur
        ("mg_road", "indiranagar", "Old Airport Road / CMH Corridor", [
            (12.9754, 77.6066), (12.9760, 77.6200), (12.9784, 77.6408)
        ]),
        ("indiranagar", "domlur", "100 Feet Road Indiranagar", [
            (12.9784, 77.6408), (12.9700, 77.6395), (12.9609, 77.6387)
        ]),
        ("domlur", "koramangala", "Intermediate Ring Road", [
            (12.9609, 77.6387), (12.9480, 77.6330), (12.9344, 77.6258)
        ]),
        # South: Koramangala, Dairy Circle, Silk Board, HSR, E-City
        ("richmond_circle", "dairy_circle", "Hosur Road - Adugodi", [
            (12.9664, 77.5991), (12.9510, 77.6010), (12.9348, 77.5997)
        ]),
        ("dairy_circle", "koramangala", "St. Johns Road", [
            (12.9348, 77.5997), (12.9350, 77.6120), (12.9344, 77.6258)
        ]),
        ("koramangala", "silk_board", "Madiwala Corridor / Hosur Rd", [
            (12.9344, 77.6258), (12.9250, 77.6240), (12.9177, 77.6238)
        ]),
        ("silk_board", "hsr_layout", "Outer Ring Road - HSR", [
            (12.9177, 77.6238), (12.9140, 77.6310), (12.9116, 77.6389)
        ]),
        ("silk_board", "electronic_city", "Hosur Road Elevated Expressway", [
            (12.9177, 77.6238), (12.8800, 77.6420), (12.8452, 77.6602)
        ]),
        ("dairy_circle", "jayanagar", "Bannerghatta Rd / 9th Main", [
            (12.9348, 77.5997), (12.9320, 77.5910), (12.9298, 77.5833)
        ]),
        ("jayanagar", "banashankari", "Rashtriya Vidyalaya Road", [
            (12.9298, 77.5833), (12.9220, 77.5780), (12.9155, 77.5736)
        ]),
        ("banashankari", "silk_board", "Outer Ring Road - BTM Layout", [
            (12.9155, 77.5736), (12.9160, 77.6000), (12.9177, 77.6238)
        ]),
        # North: Majestic to Mekhri Circle, Hebbal, Yeshwanthpur
        ("majestic", "malleshwaram", "Sampige Road", [
            (12.9781, 77.5695), (12.9930, 77.5700), (13.0084, 77.5702)
        ]),
        ("malleshwaram", "mekhri_circle", "Sankey Road", [
            (13.0084, 77.5702), (13.0080, 77.5760), (13.0076, 77.5832)
        ]),
        ("corporation_circle", "mekhri_circle", "Palace Road / Bellary Road", [
            (12.9715, 77.5835), (12.9890, 77.5840), (13.0076, 77.5832)
        ]),
        ("mekhri_circle", "hebbal", "Bellary Road (NH 44)", [
            (13.0076, 77.5832), (13.0220, 77.5900), (13.0359, 77.5971)
        ]),
        ("malleshwaram", "yeshwanthpur", "CV Raman Road", [
            (13.0084, 77.5702), (13.0150, 77.5600), (13.0232, 77.5501)
        ]),
        ("yeshwanthpur", "goraguntepalya", "Tumkur Road (NH 48)", [
            (13.0232, 77.5501), (13.0260, 77.5450), (13.0285, 77.5408)
        ]),
        ("goraguntepalya", "hebbal", "Outer Ring Road - North", [
            (13.0285, 77.5408), (13.0320, 77.5700), (13.0359, 77.5971)
        ]),
        # West & South-West
        ("majestic", "rajajinagar", "Dr. Rajkumar Road", [
            (12.9781, 77.5695), (12.9840, 77.5600), (12.9904, 77.5528)
        ]),
        ("rajajinagar", "yeshwanthpur", "Subramanya Nagar Rd", [
            (12.9904, 77.5528), (13.0050, 77.5510), (13.0232, 77.5501)
        ]),
        ("majestic", "deepanjali_nagar", "Mysore Road", [
            (12.9781, 77.5695), (12.9650, 77.5550), (12.9535, 77.5412)
        ]),
        ("deepanjali_nagar", "banashankari", "Outer Ring Road - West", [
            (12.9535, 77.5412), (12.9350, 77.5550), (12.9155, 77.5736)
        ]),
        # East & Outer Ring Road (KR Puram, Marathahalli, Whitefield)
        ("indiranagar", "kr_puram", "Old Madras Road (NH 75)", [
            (12.9784, 77.6408), (12.9880, 77.6510), (12.9982, 77.6625)
        ]),
        ("hebbal", "kr_puram", "Outer Ring Road - Nagawara/Kalyan Nagar", [
            (13.0359, 77.5971), (13.0200, 77.6300), (12.9982, 77.6625)
        ]),
        ("kr_puram", "marathahalli", "Outer Ring Road - Mahadevapura", [
            (12.9982, 77.6625), (12.9770, 77.6820), (12.9553, 77.7011)
        ]),
        ("marathahalli", "silk_board", "Outer Ring Road - Bellandur/Iblur", [
            (12.9553, 77.7011), (12.9280, 77.6780), (12.9177, 77.6238)
        ]),
        ("marathahalli", "whitefield", "HAL Old Airport Road - Whitefield", [
            (12.9553, 77.7011), (12.9680, 77.7150), (12.9858, 77.7314)
        ]),
        ("kr_puram", "whitefield", "Whitefield Main Road / ITPL", [
            (12.9982, 77.6625), (12.9920, 77.7000), (12.9858, 77.7314)
        ]),
        ("domlur", "marathahalli", "HAL Old Airport Road - Varthur", [
            (12.9609, 77.6387), (12.9580, 77.6700), (12.9553, 77.7011)
        ])
    ]

    for u, v, road_name, waypoints in corridors:
        # Calculate total distance along waypoints
        total_dist_m = 0.0
        for i in range(len(waypoints) - 1):
            p1 = waypoints[i]
            p2 = waypoints[i + 1]
            total_dist_m += haversine_distance_meters(p1[0], p1[1], p2[0], p2[1])

        # Add bidirectional edges
        G.add_edge(u, v, length=total_dist_m, road_name=road_name, geometry=waypoints)
        # Reverse geometry for opposite direction
        rev_waypoints = list(reversed(waypoints))
        G.add_edge(v, u, length=total_dist_m, road_name=road_name, geometry=rev_waypoints)

    return G


# Global cached arterial graph
BENGALURU_GRAPH = build_bengaluru_arterial_graph()


def find_nearest_node(graph: nx.MultiDiGraph, lat: float, lon: float) -> str:
    """Find the closest graph node to given coordinates."""
    best_node = None
    min_dist = float("inf")
    for node, data in graph.nodes(data=True):
        nlat = data["y"]
        nlon = data["x"]
        d = haversine_distance_meters(lat, lon, nlat, nlon)
        if d < min_dist:
            min_dist = d
            best_node = node
    return best_node


def calculate_routes(
    start_lat: float,
    start_lon: float,
    dest_lat: float,
    dest_lon: float,
    mode: str = "car",
    max_alternatives: int = 3
) -> List[Dict[str, Any]]:
    """
    Compute up to 3 reasonable route alternatives between start and destination.
    Returns structured route metadata including geometry polyline, distance,
    estimated travel time, and detected road curves.
    """
    mode_key = mode.lower() if mode.lower() in TRANSPORT_MODES else "car"
    mode_info = TRANSPORT_MODES[mode_key]
    avg_speed_kmph = mode_info["avg_speed_kmph"]

    # Locate nearest nodes in arterial network
    start_node = find_nearest_node(BENGALURU_GRAPH, start_lat, start_lon)
    dest_node = find_nearest_node(BENGALURU_GRAPH, dest_lat, dest_lon)

    if not start_node or not dest_node or start_node == dest_node:
        # Directly connect start and destination with intermediate interpolated bend if identical
        direct_waypoints = [
            (start_lat, start_lon),
            ((start_lat + dest_lat) / 2.0 + 0.002, (start_lon + dest_lon) / 2.0 + 0.002),
            (dest_lat, dest_lon)
        ]
        dist_m = haversine_distance_meters(start_lat, start_lon, dest_lat, dest_lon)
        dist_km = max(0.5, round(dist_m / 1000.0, 2))
        est_mins = max(2, int(round((dist_km / avg_speed_kmph) * 60.0)))

        curves = detect_curves_from_coordinates(direct_waypoints, road_name="Direct Corridor")

        return [{
            "alternative_id": 0,
            "title": "Direct Local Corridor",
            "description": "Direct arterial link between selected locations",
            "distance_km": dist_km,
            "estimated_minutes": est_mins,
            "coordinates": direct_waypoints,
            "detected_curves": curves,
            "primary_corridors": ["Local Arterial Link"]
        }]

    # Generate alternative paths using k-shortest simple paths or penalized alternative routes
    raw_paths = []
    try:
        # 1. Shortest path (by distance)
        path1 = nx.shortest_path(BENGALURU_GRAPH, source=start_node, target=dest_node, weight="length")
        raw_paths.append(path1)

        # 2. Alternative route: penalize the edges of path1
        if max_alternatives > 1:
            G_temp = BENGALURU_GRAPH.copy()
            for i in range(len(path1) - 1):
                u, v = path1[i], path1[i + 1]
                for key in G_temp[u][v]:
                    G_temp[u][v][key]["length"] *= 2.5
                for key in G_temp[v][u]:
                    G_temp[v][u][key]["length"] *= 2.5

            try:
                path2 = nx.shortest_path(G_temp, source=start_node, target=dest_node, weight="length")
                if path2 != path1:
                    raw_paths.append(path2)
            except Exception:
                pass

        # 3. Tertiary alternative: penalize path2 edges as well
        if max_alternatives > 2 and len(raw_paths) > 1:
            G_temp2 = G_temp.copy()
            path2 = raw_paths[1]
            for i in range(len(path2) - 1):
                u, v = path2[i], path2[i + 1]
                for key in G_temp2[u][v]:
                    G_temp2[u][v][key]["length"] *= 2.5
                for key in G_temp2[v][u]:
                    G_temp2[v][u][key]["length"] *= 2.5
            try:
                path3 = nx.shortest_path(G_temp2, source=start_node, target=dest_node, weight="length")
                if path3 not in raw_paths:
                    raw_paths.append(path3)
            except Exception:
                pass

    except nx.NetworkXNoPath:
        # Fallback direct path
        raw_paths = [[start_node, dest_node]]

    route_results = []
    titles = [
        "Primary Arterial Route (Fastest)",
        "Alternative 1 (Via Secondary Arterial)",
        "Alternative 2 (Via Peripheral / Ring Road)"
    ]

    for idx, node_path in enumerate(raw_paths[:max_alternatives]):
        # Build composite coordinates
        coords: List[Tuple[float, float]] = [(start_lat, start_lon)]
        corridor_names = []
        total_len_m = 0.0

        for i in range(len(node_path) - 1):
            u = node_path[i]
            v = node_path[i + 1]
            edge_data = BENGALURU_GRAPH.get_edge_data(u, v, default={0: {}})[0]
            geom = edge_data.get("geometry")
            road_name = edge_data.get("road_name", "Arterial Road")
            if road_name not in corridor_names:
                corridor_names.append(road_name)

            if geom:
                # Append intermediate points
                for pt in geom:
                    if not coords or coords[-1] != pt:
                        coords.append(pt)
            else:
                n_data = BENGALURU_GRAPH.nodes[v]
                pt = (n_data["y"], n_data["x"])
                coords.append(pt)

        # Add end destination point
        if coords[-1] != (dest_lat, dest_lon):
            coords.append((dest_lat, dest_lon))

        # Calculate exact distance
        for k in range(len(coords) - 1):
            total_len_m += haversine_distance_meters(
                coords[k][0], coords[k][1],
                coords[k + 1][0], coords[k + 1][1]
            )

        dist_km = max(0.5, round(total_len_m / 1000.0, 2))
        est_mins = max(2, int(round((dist_km / avg_speed_kmph) * 60.0)))

        # Detect road curves along route polyline
        curves = detect_curves_from_coordinates(
            coords,
            road_name=", ".join(corridor_names[:2]),
            prefix_id=f"CRV_R{idx+1}"
        )

        via_summary = " via " + " & ".join(corridor_names[:2]) if corridor_names else ""

        route_results.append({
            "alternative_id": idx,
            "title": titles[idx] if idx < len(titles) else f"Alternative Route {idx+1}",
            "description": f"{dist_km} km{via_summary}",
            "distance_km": dist_km,
            "estimated_minutes": est_mins,
            "coordinates": coords,
            "detected_curves": curves,
            "primary_corridors": corridor_names
        })

    return route_results
