from pathlib import Path
import json
import math

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from routing_engine import (
    geocode_location,
    load_routing_data,
    find_route_candidates,
)

# ============================================================================
# CONFIGURATION
# ============================================================================

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
ROUTES_PATH = DATA_DIR / "routes.json"

st.set_page_config(
    page_title="SmartRoute | Safe Route Recommendation",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# STYLE
# ============================================================================

st.markdown("""
<style>
.main-title {
    font-size: 2.35rem;
    font-weight: 800;
    margin-bottom: 0.1rem;
}
.subtitle {
    color: #8b949e;
    font-size: 1rem;
    margin-bottom: 1rem;
}
.metric-card {
    padding: 14px;
    border: 1px solid rgba(128,128,128,.35);
    border-radius: 12px;
    min-height: 105px;
}
.route-card {
    padding: 15px;
    border: 1px solid rgba(128,128,128,.35);
    border-radius: 12px;
    margin-bottom: 12px;
}
.small-note {
    color: #8b949e;
    font-size: .83rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="main-title">🛣️ SmartRoute</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="subtitle">'
    'Machine Learning-Based Multi-Factor Safe Route Recommendation'
    '</div>',
    unsafe_allow_html=True,
)

st.caption(
    "Bengaluru road routing prototype | Distance, road health, "
    "time-aware safety and risk-based recommendations"
)
st.divider()

# ============================================================================
# LOAD ROUTING NETWORK ONCE PER APP PROCESS
# ============================================================================

@st.cache_resource(show_spinner="Loading Bengaluru road network...")
def get_routing_network(data_directory):
    return load_routing_data(Path(data_directory))


# ============================================================================
# HELPERS
# ============================================================================

def format_number(value, decimals=1):
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def format_pct(value):
    return f"{format_number(value)}%"


def load_example_routes():
    """Load existing route examples without requiring them for dynamic routing."""
    if not ROUTES_PATH.exists():
        return []

    try:
        with open(ROUTES_PATH, encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            routes = data.get("routes", [])
            return routes if isinstance(routes, list) else []

    except (OSError, ValueError):
        return []

    return []


def make_route_map(routes, source, destination):
    """Build an interactive Folium map using actual calculated route paths."""
    center = [
        (source["lat"] + destination["lat"]) / 2,
        (source["lon"] + destination["lon"]) / 2,
    ]

    fmap = folium.Map(
        location=center,
        zoom_start=12,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    # Green = recommended; yellow/red = alternative route distinctions.
    palette = ["#16a34a", "#eab308", "#dc2626"]

    all_points = []

    for i, route in enumerate(routes):
        coordinates = route.get("coordinates", [])

        if not coordinates:
            continue

        color = palette[min(i, len(palette) - 1)]

        folium.PolyLine(
            locations=coordinates,
            color=color,
            weight=7 if i == 0 else 5,
            opacity=0.88,
            tooltip=(
                f"Route {i + 1}: {route.get('strategy', 'Alternative')} | "
                f"{format_number(route.get('distance_km'))} km | "
                f"{format_number(route.get('estimated_time_min'))} min"
            ),
        ).add_to(fmap)

        all_points.extend(coordinates)

    folium.Marker(
        [source["lat"], source["lon"]],
        tooltip="Source: " + source["query"],
        popup=folium.Popup(
            "<b>START</b><br>" + source["address"],
            max_width=320,
        ),
        icon=folium.Icon(color="blue", icon="play"),
    ).add_to(fmap)

    folium.Marker(
        [destination["lat"], destination["lon"]],
        tooltip="Destination: " + destination["query"],
        popup=folium.Popup(
            "<b>DESTINATION</b><br>" + destination["address"],
            max_width=320,
        ),
        icon=folium.Icon(color="darkred", icon="flag"),
    ).add_to(fmap)

    if all_points:
        all_points.extend([
            [source["lat"], source["lon"]],
            [destination["lat"], destination["lon"]],
        ])
        fmap.fit_bounds(all_points, padding=(30, 30))

    legend = """
    <div style="
        position: fixed; bottom: 28px; left: 24px; z-index: 9999;
        background: white; color: #111; padding: 12px 15px;
        border: 1px solid #bbb; border-radius: 8px;
        font-size: 13px; line-height: 1.8;">
        <b>SMARTROUTE — ROUTE LEGEND</b><br>
        <span style="color:#16a34a">━━</span> Recommended route<br>
        <span style="color:#eab308">━━</span> Alternative route 2<br>
        <span style="color:#dc2626">━━</span> Alternative route 3<br>
        <span style="color:#2563eb">●</span> Source<br>
        <span style="color:#991b1b">●</span> Destination
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend))

    return fmap


def show_route_card(route, selected_period, recommended=False):
    heading = (
        "Recommended route" if recommended
        else f"Alternative route {route.get('rank', '')}"
    )

    st.markdown('<div class="route-card">', unsafe_allow_html=True)
    st.markdown(f"### {heading} — {route.get('strategy', 'Route')}")

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Distance",
        f"{format_number(route.get('distance_km'))} km",
    )
    c2.metric(
        "Estimated time",
        f"{format_number(route.get('estimated_time_min'))} min",
    )
    c3.metric(
        "Journey score",
        format_pct(route.get("overall_score")),
    )

    c4, c5, c6 = st.columns(3)

    c4.metric("Road health", format_pct(route.get("road_health_pct")))
    c5.metric(
        f"{selected_period} safety",
        format_pct(route.get("selected_safety_pct")),
    )
    c6.metric(
        "Traffic risk",
        format_pct(route.get("traffic_risk_pct")),
    )

    st.caption(
        f"Road segments: {route.get('segment_count', 'N/A')} | "
        f"ML risk proxy: {format_pct(route.get('ml_risk_proxy_pct'))}"
    )

    if recommended:
        st.success("Highest overall score among the generated candidates.")

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================================
# SIDEBAR — JOURNEY INPUTS
# ============================================================================

with st.sidebar:
    st.header("🔎 Plan Your Journey")
    st.caption("Enter locations within supported Bengaluru coverage.")

    with st.form("dynamic_journey_form"):
        source_query = st.text_input(
            "Source location",
            placeholder="e.g. Majestic",
        )

        destination_query = st.text_input(
            "Destination",
            placeholder="e.g. Whitefield",
        )

        period = st.radio(
            "Journey time",
            ["Daytime", "Nighttime"],
            horizontal=True,
        )

        submitted = st.form_submit_button(
            "Find Safe Routes",
            type="primary",
            use_container_width=True,
        )

    st.divider()
    st.caption("Example locations")
    st.write("Majestic, Indiranagar, Koramangala, Whitefield, Electronic City")

    st.caption(
        "Location search requires internet access and may be rate-limited "
        "by the public geocoding service."
    )

# ============================================================================
# CALCULATE ROUTES
# ============================================================================

if submitted:
    if not source_query.strip() or not destination_query.strip():
        st.session_state.pop("smartroute_result", None)
        st.error("Enter both a source and a destination.")
    else:
        try:
            with st.spinner("Resolving locations and calculating routes..."):
                # Resolve actual user-entered locations.
                source_location = geocode_location(source_query)
                destination_location = geocode_location(destination_query)

                # Load graph and coordinate index only once.
                graph, node_coords, node_index = get_routing_network(
                    str(DATA_DIR)
                )

                # Generate routes using the actual road network.
                calculated_routes = find_route_candidates(
                    graph=graph,
                    node_coords=node_coords,
                    node_index=node_index,
                    source=source_location,
                    destination=destination_location,
                    period=period,
                    max_routes=3,
                )

                st.session_state["smartroute_result"] = {
                    "source": source_location,
                    "destination": destination_location,
                    "period": period,
                    "routes": calculated_routes,
                }

        except Exception as exc:
            st.session_state.pop("smartroute_result", None)
            st.error(f"Unable to calculate routes: {exc}")
            st.info(
                "Check the spelling of both locations, your internet "
                "connection, and whether a connected road route exists."
            )

# ============================================================================
# DISPLAY SAVED RESULT
# ============================================================================

result = st.session_state.get("smartroute_result")

if result:
    source = result["source"]
    destination = result["destination"]
    selected_period = result["period"]
    routes = result["routes"]

    st.success(
        f"Calculated {len(routes)} route candidate(s) for "
        f"{selected_period.lower()} travel."
    )

    left, right = st.columns(2)

    with left:
        st.markdown("**SOURCE**")
        st.write(source["address"])

    with right:
        st.markdown("**DESTINATION**")
        st.write(destination["address"])

    st.caption(
        "Routes are snapped to the nearest road-network nodes. "
        "The snap distances are reported for transparency."
    )

    first = routes[0]

    st.markdown("## Recommended route")

    top1, top2, top3, top4 = st.columns(4)

    top1.metric(
        "Distance",
        f"{format_number(first.get('distance_km'))} km",
    )
    top2.metric(
        "Estimated travel time",
        f"{format_number(first.get('estimated_time_min'))} min",
    )
    top3.metric(
        "Road health",
        format_pct(first.get("road_health_pct")),
    )
    top4.metric(
        "Safety",
        format_pct(first.get("selected_safety_pct")),
    )

    st.metric(
        "Journey Confidence / Overall Score",
        format_pct(first.get("overall_score")),
        help=(
            "Weighted route-ranking score. It is not a calibrated "
            "probability or a guarantee of journey safety."
        ),
    )

    st.markdown("## Bengaluru route map")

    st.caption(
        "Green indicates the highest-ranked candidate, yellow the second, "
        "and red the third. These colors distinguish routes; they do not "
        "represent live road conditions."
    )

    fmap = make_route_map(routes, source, destination)

    st_folium(
        fmap,
        height=650,
        use_container_width=True,
        returned_objects=[],
        key="smartroute_dynamic_map",
    )

    st.markdown("## Compare alternative routes")

    for index, route in enumerate(routes):
        show_route_card(
            route,
            selected_period,
            recommended=(index == 0),
        )

    comparison_rows = []

    for route in routes:
        comparison_rows.append({
            "Rank": route.get("rank"),
            "Strategy": route.get("strategy"),
            "Distance (km)": round(route.get("distance_km", 0), 2),
            "Time (min)": round(route.get("estimated_time_min", 0), 1),
            "Road health (%)": round(route.get("road_health_pct", 0), 1),
            "Safety (%)": round(route.get("selected_safety_pct", 0), 1),
            "Traffic risk (%)": round(route.get("traffic_risk_pct", 0), 1),
            "ML risk proxy (%)": round(route.get("ml_risk_proxy_pct", 0), 1),
            "Overall score": round(route.get("overall_score", 0), 1),
        })

    st.markdown("### Route comparison table")
    st.dataframe(
        pd.DataFrame(comparison_rows),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Route snapping diagnostics")

    d1, d2 = st.columns(2)

    d1.metric(
        "Source snap offset",
        f"{format_number(first.get('source_snap_distance_km', 0), 3)} km",
    )
    d2.metric(
        "Destination snap offset",
        f"{format_number(first.get('destination_snap_distance_km', 0), 3)} km",
    )

    if (
        first.get("source_snap_distance_km", 0) > 1.0
        or first.get("destination_snap_distance_km", 0) > 1.0
    ):
        st.warning(
            "A location is more than 1 km from its matched road node. "
            "Check the location result before relying on this route."
        )

    st.info(
        "Distance is calculated from the road-network edge lengths. "
        "Travel time uses modelled speed and traffic-risk adjustments. "
        "Road health, safety, and ML risk are modelled features, not "
        "verified live measurements. Confirm real-world conditions "
        "before travelling."
    )

else:
    st.markdown("## Plan a safer journey across Bengaluru")

    st.write(
        "Enter your starting point and destination in the sidebar, "
        "choose daytime or nighttime, and select **Find Safe Routes**."
    )

    st.markdown("""
    **What this dashboard provides**
    - Dynamic source and destination geocoding
    - Alternative routes generated from the road network
    - Distance and estimated travel time
    - Road-health and time-aware safety scores
    - Traffic and ML risk proxies
    - A map with distinct route colors
    """)

    st.warning(
        "No journey has been calculated yet. Route metrics appear after "
        "you submit valid locations."
    )

st.divider()
st.caption(
    "SmartRoute | M.Tech research prototype | "
    "Modelled risk estimates are not a substitute for live navigation."
)
