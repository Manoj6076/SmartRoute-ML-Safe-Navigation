        )

        ml_risk = weighted_mean(
            "ml_risk"
        )

        # Estimated travel time.

        estimated_time = sum(
            (edge["length_m"] / 1000.0)
            / max(edge["speed_kmph"], 5.0)
            * 60.0
            * (
                1.0
                + edge["traffic_risk"] / 100.0 * 0.35
            )
            for edge in edge_rows
        )

        # Actual road-network coordinates.

        route_coordinates = [
            [
                node_coords[node][0],
                node_coords[node][1]
            ]
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

        raise ValueError(
            "No valid route candidates were generated."
        )

    # Apply the project's configured multi-factor weights.

    fastest_time = min(
        r["estimated_time_min"]
        for r in results
    )

    for route in results:

        travel_time_score = (
            100.0
            * fastest_time
            / max(route["estimated_time_min"], 1e-9)
        )

        traffic_score = (
            100.0 - route["traffic_risk_pct"]
        )

        ml_score = (
            100.0 - route["ml_risk_proxy_pct"]
        )

        route["overall_score"] = (

            0.25 * route["road_health_pct"]

            + 0.30 * route["selected_safety_pct"]

            + 0.20 * travel_time_score

            + 0.10 * traffic_score

            + 0.15 * ml_score

        )

    # Rank routes by overall score.

    results.sort(
        key=lambda item: item["overall_score"],
        reverse=True
    )

    for rank, route in enumerate(
        results,
        start=1
    ):

        route["rank"] = rank

        route["recommendation"] = (

            "Recommended route"
            if rank == 1
            else f"Alternative {rank}"

        )

    return results
