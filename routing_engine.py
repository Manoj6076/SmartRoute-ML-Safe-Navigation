
from pathlib import Path
import math

import networkx as nx
import numpy as np
import pandas as pd
from geopy.geocoders import Nominatim


# Bengaluru coverage boundary for this prototype.
LAT_MIN, LAT_MAX = 12.70, 13.25
LON_MIN, LON_MAX = 77.30, 77.85


def geocode_location(query):
    """Resolve a user-entered location within the Bengaluru coverage area."""
    query = str(query).strip()

    if not query:
        raise ValueError("Enter a source or destination.")

    geocoder = Nominatim(
        user_agent="SmartRouteSafeNavigation/1.0"
    )

    try:
        result = geocoder.geocode(
            f"{query}, Bengaluru, Karnataka, India",
            exactly_one=True,
            country_codes="in",
            viewbox=[
                (LAT_MAX, LON_MIN),
                (LAT_MIN, LON_MAX)
            ],
            bounded=True,
            timeout=15
        )
    except Exception as exc:
        raise RuntimeError(
            "Location search could not reach the geocoding service. "
            "Check your internet connection and try again later."
        ) from exc

    if result is None:
        raise ValueError(
            f"Could not find '{query}' within the supported Bengaluru area. "
            "Try a more specific locality or landmark."
        )

    lat = float(result.latitude)
    lon = float(result.longitude)

    if not (
        LAT_MIN <= lat <= LAT_MAX
        and LON_MIN <= lon <= LON_MAX
    ):
        raise ValueError(
            f"'{query}' resolved outside the supported Bengaluru area. "
            "Please enter a location within Bengaluru."
        )

    return {
        "query": query,
        "address": result.address,
        "lat": lat,
        "lon": lon
    }


def load_routing_data(data_dir):
    """
    Load compact routing files and build a directed graph.

    Parallel edges between the same pair of nodes are reduced to the
    shortest usable edge to keep the in-memory graph manageable.
    """
    data_dir = Path(data_dir)
    nodes_path = data_dir / "nodes.csv.gz"
    edges_path = data_dir / "edges.csv.gz"

    if not nodes_path.exists() or not edges_path.exists():
        raise FileNotFoundError(
            "Compact routing files are missing. Run Section 12.5."
        )

    nodes = pd.read_csv(nodes_path)

    required_node_columns = {"node_id", "lat", "lon"}
    if not required_node_columns.issubset(nodes.columns):
        raise ValueError("The node file has an invalid schema.")

    nodes["node_id"] = nodes["node_id"].astype(str)
    nodes["lat"] = pd.to_numeric(nodes["lat"], errors="coerce")
    nodes["lon"] = pd.to_numeric(nodes["lon"], errors="coerce")
    nodes = nodes.dropna(subset=["node_id", "lat", "lon"])

    node_coords = {
        row.node_id: (float(row.lat), float(row.lon))
        for row in nodes.itertuples(index=False)
    }

    # Arrays accelerate nearest-road-node lookup.
    node_ids = np.asarray(list(node_coords.keys()), dtype=object)
    node_lats = np.asarray(
        [node_coords[n][0] for n in node_ids], dtype=float
    )
    node_lons = np.asarray(
        [node_coords[n][1] for n in node_ids], dtype=float
    )

    node_index = {
        "ids": node_ids,
        "lats": node_lats,
        "lons": node_lons
    }

    graph = nx.DiGraph()

    # Add nodes first so isolated or currently unusable edges do not
    # remove their coordinate records.
    graph.add_nodes_from(node_coords.keys())

    usecols = [
        "u", "v", "length_m",
        "road_health_feature",
        "day_safety_feature",
        "night_safety_feature",
        "road_health_risk",
        "day_safety_risk",
        "traffic_risk_component",
        "time_risk_component",
        "peak_speed_feature_kmph",
        "risk_proxy_score"
    ]

    # Read chunks to avoid holding the complete CSV in memory.
    for chunk in pd.read_csv(
        edges_path,
        compression="gzip",
        usecols=lambda c: c in usecols,
        chunksize=40000
    ):
        for col in usecols:
            if col not in chunk.columns:
                if col in ("u", "v"):
                    raise ValueError(f"Edge file is missing {col}.")
                chunk[col] = np.nan

        for col in usecols[2:]:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

        chunk = chunk.dropna(subset=["u", "v", "length_m"])
        chunk = chunk[chunk["length_m"] > 0]

        for row in chunk.itertuples(index=False, name=None):
            (
                u, v, length_m,
                health, day_safety, night_safety,
                health_risk, day_safety_risk,
                traffic_risk, time_risk,
                speed, ml_risk
            ) = row

            u, v = str(u), str(v)

            if u not in node_coords or v not in node_coords:
                continue

            length_m = float(length_m)

            health = float(health) if pd.notna(health) else 50.0
            day_safety = (
                float(day_safety) if pd.notna(day_safety) else 50.0
            )
            night_safety = (
                float(night_safety) if pd.notna(night_safety) else 50.0
            )
            health_risk = (
                float(health_risk)
                if pd.notna(health_risk) else 100.0 - health
            )
            traffic_risk = (
                float(traffic_risk)
                if pd.notna(traffic_risk) else 50.0
            )
            time_risk = float(time_risk) if pd.notna(time_risk) else 50.0
            ml_risk = float(ml_risk) if pd.notna(ml_risk) else 50.0
            speed = float(speed) if pd.notna(speed) else 20.0

            health = float(np.clip(health, 0, 100))
            day_safety = float(np.clip(day_safety, 0, 100))
            night_safety = float(np.clip(night_safety, 0, 100))
            health_risk = float(np.clip(health_risk, 0, 100))
            traffic_risk = float(np.clip(traffic_risk, 0, 100))
            time_risk = float(np.clip(time_risk, 0, 100))
            ml_risk = float(np.clip(ml_risk, 0, 100))
            speed = float(np.clip(speed, 5, 100))

            # Keep the shortest parallel edge for this directed node pair.
            if graph.has_edge(u, v):
                if graph[u][v]["length_m"] <= length_m:
                    continue

            # Distance, balanced-risk, and safety-oriented route costs.
            balanced_factor = (
                1.0
                + 0.25 * health_risk / 100
                + 0.30 * (100 - day_safety) / 100
                + 0.20 * time_risk / 100
                + 0.10 * traffic_risk / 100
                + 0.15 * ml_risk / 100
            )

            safety_factor = (
                1.0
                + 0.15 * health_risk / 100
                + 0.50 * (100 - day_safety) / 100
                + 0.10 * time_risk / 100
                + 0.10 * traffic_risk / 100
                + 0.15 * ml_risk / 100
            )

            graph.add_edge(
                u, v,
                length_m=length_m,
                road_health=health,
                day_safety=day_safety,
                night_safety=night_safety,
                health_risk=health_risk,
                traffic_risk=traffic_risk,
                time_risk=time_risk,
                ml_risk=ml_risk,
                speed_kmph=speed,
                distance_cost=length_m,
                balanced_cost=length_m * balanced_factor,
                safety_cost=length_m * safety_factor
            )

    if graph.number_of_edges() == 0:
        raise ValueError("No usable routing edges were loaded.")

    return graph, node_coords, node_index


def nearest_node(lat, lon, node_index):
    """Find the nearest road-network node using vectorized coordinates."""
    lat = float(lat)
    lon = float(lon)

    lats = node_index["lats"]
    lons = node_index["lons"]

    # Approximate local distance in kilometres.
    dy = (lats - lat) * 111.0
    dx = (lons - lon) * 111.0 * math.cos(math.radians(lat))
    distances_sq = dx * dx + dy * dy

    index = int(np.argmin(distances_sq))
    return str(node_index["ids"][index]), float(
        math.sqrt(distances_sq[index])
    )


def find_route_candidates(
    graph,
    node_coords,
    node_index,
    source,
    destination,
    period="Daytime",
    max_routes=3
):
    """
    Calculate alternative routes from source/destination coordinate dicts.

    Each location dict must contain 'lat' and 'lon'.
    Route paths are generated using different edge-cost strategies.
    """
    if period not in ("Daytime", "Nighttime"):
        raise ValueError("period must be Daytime or Nighttime.")

    source_node, source_offset_km = nearest_node(
        source["lat"], source["lon"], node_index
    )
    destination_node, destination_offset_km = nearest_node(
        destination["lat"], destination["lon"], node_index
    )

    if source_node == destination_node:
        raise ValueError(
            "Source and destination resolve to the same nearby road node. "
            "Please choose more distinct locations."
        )

    strategies = [
        ("Shortest distance", "distance_cost"),
        ("Balanced risk", "balanced_cost"),
        ("Safety-oriented", "safety_cost")
    ]

    selected_safety_key = (
        "day_safety" if period == "Daytime" else "night_safety"
    )

    # Safety-oriented route cost must reflect the selected time period.
    if period == "Nighttime":
        for _, _, data in graph.edges(data=True):
            safety_risk = 100.0 - data["night_safety"]
            data["safety_cost"] = data["length_m"] * (
                1.0
                + 0.15 * data["health_risk"] / 100
                + 0.50 * safety_risk / 100
                + 0.10 * data["time_risk"] / 100
                + 0.10 * data["traffic_risk"] / 100
                + 0.15 * data["ml_risk"] / 100
            )

    candidate_paths = []
    seen_paths = set()

    for label, weight in strategies:
        try:
            path = nx.shortest_path(
                graph,
                source=source_node,
                target=destination_node,
                weight=weight,
                method="dijkstra"
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

        path_key = tuple(path)

        if path_key in seen_paths:
            continue

        seen_paths.add(path_key)
        candidate_paths.append((label, path))

        if len(candidate_paths) >= max_routes:
            break

    if not candidate_paths:
        raise ValueError(
            "No connected road route was found between these locations."
        )

    results = []

    for index, (strategy, path) in enumerate(candidate_paths, start=1):
        edge_rows = []

        for u, v in zip(path[:-1], path[1:]):
            edge_rows.append(graph[u][v])

        if not edge_rows:
            continue

        lengths = np.asarray(
            [edge["length_m"] for edge in edge_rows], dtype=float
        )
        total_length = float(lengths.sum())
        weights = lengths / max(total_length, 1e-9)

        def weighted_mean(key):
            values = np.asarray(
                [edge[key] for edge in edge_rows], dtype=float
            )
            return float(np.average(values, weights=weights))

        road_health = weighted_mean("road_health")
        safety = weighted_mean(selected_safety_key)
        traffic_risk = weighted_mean("traffic_risk")
        ml_risk = weighted_mean("ml_risk")

        estimated_time = sum(
            (edge["length_m"] / 1000.0)
            / max(edge["speed_kmph"], 5.0)
            * 60.0
            * (1.0 + edge["traffic_risk"] / 100.0 * 0.35)
            for edge in edge_rows
        )

        route_coordinates = [
            [node_coords[node][0], node_coords[node][1]]
            for node in path
            if node in node_coords
        ]

        results.append({
            "route_id": f"dynamic_{index}",
            "route_number": index,
            "strategy": strategy,
            "distance_km": total_length / 1000.0,
            "estimated_time_min": float(estimated_time),
            "road_health_pct": road_health,
            "day_safety_pct": weighted_mean("day_safety"),
            "night_safety_pct": weighted_mean("night_safety"),
            "selected_safety_pct": safety,
            "traffic_risk_pct": traffic_risk,
            "ml_risk_proxy_pct": ml_risk,
            "segment_count": len(edge_rows),
            "coordinates": route_coordinates,
            "source_node": source_node,
            "destination_node": destination_node,
            "source_snap_distance_km": source_offset_km,
            "destination_snap_distance_km": destination_offset_km
        })

    if not results:
        raise ValueError("No valid route candidates were generated.")

    # Apply the project's configured multi-factor weights.
    fastest_time = min(r["estimated_time_min"] for r in results)

    for route in results:
        travel_time_score = (
            100.0 * fastest_time / max(route["estimated_time_min"], 1e-9)
        )
        traffic_score = 100.0 - route["traffic_risk_pct"]
        ml_score = 100.0 - route["ml_risk_proxy_pct"]

        route["overall_score"] = (
            0.25 * route["road_health_pct"]
            + 0.30 * route["selected_safety_pct"]
            + 0.20 * travel_time_score
            + 0.10 * traffic_score
            + 0.15 * ml_score
        )

    results.sort(key=lambda item: item["overall_score"], reverse=True)

    for rank, route in enumerate(results, start=1):
        route["rank"] = rank
        route["recommendation"] = (
            "Recommended route" if rank == 1 else f"Alternative {rank}"
        )

    return results
