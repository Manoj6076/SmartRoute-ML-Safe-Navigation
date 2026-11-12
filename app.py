from pathlib import Path
import json

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

st.markdown(
    """
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

    .route-card {
        padding: 15px;
        border: 1px solid rgba(128,128,128,.35);
        border-radius: 12px;
        margin-bottom: 12px;
    }

    .search-box {
        padding: 12px;
        border: 1px solid rgba(128,128,128,.30);
        border-radius: 10px;
        margin-bottom: 10px;
    }

    [data-testid="stSidebar"] {
        min-width: 340px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# HEADER
# ============================================================================

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
# LOAD ROUTING NETWORK
# ============================================================================

@st.cache_resource(show_spinner="Loading Bengaluru road network...")
def get_routing_network(data_directory):
    return load_routing_data(Path(data_directory))


# ============================================================================
# CACHED GEOCODING
# ============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def cached_geocode_location(query):
    """
    Cache successful location lookups for 24 hours.
    """
    return geocode_location(query.strip())


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_number(value, decimals=1):
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def format_pct(value):
    return f"{format_number(value)}%"


# ============================================================================
# DEFAULT BENGALURU MAP
# ============================================================================

def create_bengaluru_overview_map():
    """
    Display a Bengaluru overview map before the user calculates a route.
    """

    fmap = folium.Map(
        location=[12.9716, 77.5946],
        zoom_start=11,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    # Alternative light map
    folium.TileLayer(
        tiles="CartoDB positron",
        name="Light Map",
        control=True,
    ).add_to(fmap)

    # Bengaluru marker
    folium.Marker(
        location=[12.9716, 77.5946],
        tooltip="Bengaluru",
        popup=(
            "<b>SmartRoute Bengaluru</b><br>"
            "Safe route recommendation coverage"
        ),
        icon=folium.Icon(
            color="blue",
            icon="info-sign",
        ),
    ).add_to(fmap)

    # Approximate coverage circle
    folium.Circle(
        location=[12.9716, 77.5946],
        radius=30000,
        color="#2563eb",
        fill=False,
        tooltip="Approximate Bengaluru SmartRoute coverage",
    ).add_to(fmap)

    folium.LayerControl().add_to(fmap)

    return fmap


# ============================================================================
# ACTUAL ROUTE MAP
# ============================================================================

def make_route_map(routes, source, destination):
    """
    Build interactive Folium map using calculated route paths.
    """

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

    # Alternative map layer
    folium.TileLayer(
        tiles="CartoDB positron",
        name="Light Map",
        control=True,
    ).add_to(fmap)

    # Route colors
    palette = [
        "#16a34a",   # Green - recommended
        "#eab308",   # Yellow - alternative 2
        "#dc2626",   # Red - alternative 3
    ]

    all_points = []

    # ------------------------------------------------------------------------
    # DRAW ROUTES
    # ------------------------------------------------------------------------

    for i, route in enumerate(routes):

        coordinates = route.get("coordinates", [])

        if not coordinates:
            continue

        color = palette[min(i, len(palette) - 1)]

        folium.PolyLine(
            locations=coordinates,
            color=color,
            weight=8 if i == 0 else 5,
            opacity=0.90,
            tooltip=(
                f"Route {i + 1}: "
                f"{route.get('strategy', 'Alternative')} | "
                f"{format_number(route.get('distance_km'))} km | "
                f"{format_number(route.get('estimated_time_min'))} min"
            ),
        ).add_to(fmap)

        all_points.extend(coordinates)

    # ------------------------------------------------------------------------
    # SOURCE MARKER
    # ------------------------------------------------------------------------

    folium.Marker(
        location=[
            source["lat"],
            source["lon"],
        ],
        tooltip="START: " + source["query"],
        popup=folium.Popup(
            "<b>START</b><br>"
            + source["address"],
            max_width=350,
        ),
        icon=folium.Icon(
            color="blue",
            icon="play",
        ),
    ).add_to(fmap)

    # ------------------------------------------------------------------------
    # DESTINATION MARKER
    # ------------------------------------------------------------------------

    folium.Marker(
        location=[
            destination["lat"],
            destination["lon"],
        ],
        tooltip="DESTINATION: " + destination["query"],
        popup=folium.Popup(
            "<b>DESTINATION</b><br>"
            + destination["address"],
            max_width=350,
        ),
        icon=folium.Icon(
            color="darkred",
            icon="flag",
        ),
    ).add_to(fmap)

    # ------------------------------------------------------------------------
    # FIT MAP TO ROUTE
    # ------------------------------------------------------------------------

    all_points.extend(
        [
            [source["lat"], source["lon"]],
            [destination["lat"], destination["lon"]],
        ]
    )

    if all_points:
        fmap.fit_bounds(
            all_points,
            padding=(35, 35),
        )

    # ------------------------------------------------------------------------
    # MAP LEGEND
    # ------------------------------------------------------------------------

    legend = """
    <div style="
        position: fixed;
        bottom: 25px;
        left: 25px;
        z-index: 9999;
        background: white;
        color: #111;
        padding: 12px 15px;
        border: 1px solid #aaa;
        border-radius: 8px;
        font-size: 13px;
        line-height: 1.8;
        box-shadow: 0 2px 8px rgba(0,0,0,.2);
    ">

        <b>SMARTROUTE</b><br>

        <span style="color:#16a34a">━━</span>
        Recommended route<br>

        <span style="color:#eab308">━━</span>
        Alternative route 2<br>

        <span style="color:#dc2626">━━</span>
        Alternative route 3<br>

        <span style="color:#2563eb">●</span>
        Source<br>

        <span style="color:#991b1b">●</span>
        Destination

    </div>
    """

    fmap.get_root().html.add_child(
        folium.Element(legend)
    )

    folium.LayerControl().add_to(fmap)

    return fmap


# ============================================================================
# ROUTE CARD
# ============================================================================

def show_route_card(
    route,
    selected_period,
    recommended=False,
):

    heading = (
        "🏆 Recommended route"
        if recommended
        else f"Alternative route {route.get('rank', '')}"
    )

    st.markdown(
        '<div class="route-card">',
        unsafe_allow_html=True,
    )

    st.markdown(
        f"### {heading} — {route.get('strategy', 'Route')}"
    )

    # First row
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

    # Second row
    c4, c5, c6 = st.columns(3)

    c4.metric(
        "Road health",
        format_pct(route.get("road_health_pct")),
    )

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
        st.success(
            "Highest overall score among the generated candidates."
        )

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


# ============================================================================
# SIDEBAR — PLAN YOUR JOURNEY
# ============================================================================

with st.sidebar:

    st.header("🔎 Plan Your Journey")

    st.caption(
        "Enter or select locations within supported Bengaluru coverage."
    )

    # Common Bengaluru locations
    common_locations = [
        "Majestic",
        "Indiranagar",
        "Koramangala",
        "Whitefield",
        "Electronic City",
        "MG Road",
        "Marathahalli",
        "Bellandur",
        "HSR Layout",
        "BTM Layout",
        "Hebbal",
        "Yelahanka",
        "KR Puram",
        "Bengaluru Airport",
    ]

    with st.form(
        "dynamic_journey_form",
        clear_on_submit=False,
    ):

        # --------------------------------------------------------------------
        # SOURCE
        # --------------------------------------------------------------------

        st.markdown("### 📍 Start Location")

        source_query = st.text_input(
            "Source location",
            placeholder="Example: Majestic",
            help=(
                "Type a Bengaluru area, landmark, road, "
                "or supported location."
            ),
        )

        source_choice = st.selectbox(
            "Quick select source",
            [
                "— Type your own source —"
            ] + common_locations,
        )

        # --------------------------------------------------------------------
        # DESTINATION
        # --------------------------------------------------------------------

        st.markdown("### 🎯 Destination")

        destination_query = st.text_input(
            "Destination",
            placeholder="Example: Indiranagar",
            help=(
                "Type your Bengaluru destination."
            ),
        )

        destination_choice = st.selectbox(
            "Quick select destination",
            [
                "— Type your own destination —"
            ] + common_locations,
        )

        # --------------------------------------------------------------------
        # DAY / NIGHT
        # --------------------------------------------------------------------

        st.markdown("### 🕐 Journey Time")

        period = st.radio(
            "Select travel period",
            [
                "☀️ Daytime",
                "🌙 Nighttime",
            ],
            horizontal=True,
        )

        # --------------------------------------------------------------------
        # BUTTON
        # --------------------------------------------------------------------

        submitted = st.form_submit_button(
            "🚗 Find Safe Routes",
            type="primary",
            use_container_width=True,
        )

    # ------------------------------------------------------------------------
    # USE QUICK SELECT WHEN TEXT BOX IS EMPTY
    # ------------------------------------------------------------------------

    if submitted:

        if (
            not source_query.strip()
            and source_choice != "— Type your own source —"
        ):
            source_query = source_choice

        if (
            not destination_query.strip()
            and destination_choice
            != "— Type your own destination —"
        ):
            destination_query = destination_choice

        if period.startswith("☀️"):
            period = "Daytime"
        else:
            period = "Nighttime"

    # ------------------------------------------------------------------------
    # EXAMPLES
    # ------------------------------------------------------------------------

    st.divider()

    st.markdown("### 💡 Example journeys")

    st.write(
        "📍 Majestic → Indiranagar"
    )

    st.write(
        "📍 Koramangala → Whitefield"
    )

    st.write(
        "📍 Electronic City → Majestic"
    )

    st.caption(
        "Common Bengaluru locations use the local geocoder. "
        "Other locations can use Nominatim/Photon."
    )


# ============================================================================
# CALCULATE ROUTES
# ============================================================================

if submitted:

    # Clear previous result
    st.session_state.pop(
        "smartroute_result",
        None,
    )

    # ------------------------------------------------------------------------
    # VALIDATE INPUT
    # ------------------------------------------------------------------------

    if (
        not source_query.strip()
        or not destination_query.strip()
    ):

        st.error(
            "Enter or select both a source and destination."
        )

    elif (
        source_query.strip().lower()
        == destination_query.strip().lower()
    ):

        st.error(
            "Source and destination cannot be the same."
        )

    else:

        try:

            with st.spinner(
                "📍 Resolving locations and calculating safe routes..."
            ):

                # ------------------------------------------------------------
                # GEOCODE SOURCE
                # ------------------------------------------------------------

                source_location = cached_geocode_location(
                    source_query
                )

                # ------------------------------------------------------------
                # GEOCODE DESTINATION
                # ------------------------------------------------------------

                destination_location = cached_geocode_location(
                    destination_query
                )

                # ------------------------------------------------------------
                # LOAD ROUTING GRAPH
                # ------------------------------------------------------------

                graph, node_coords, node_index = (
                    get_routing_network(
                        str(DATA_DIR)
                    )
                )

                # ------------------------------------------------------------
                # CALCULATE ROUTES
                # ------------------------------------------------------------

                calculated_routes = find_route_candidates(
                    graph=graph,
                    node_coords=node_coords,
                    node_index=node_index,
                    source=source_location,
                    destination=destination_location,
                    period=period,
                    max_routes=3,
                )

                # ------------------------------------------------------------
                # SAVE RESULT
                # ------------------------------------------------------------

                st.session_state[
                    "smartroute_result"
                ] = {
                    "source": source_location,
                    "destination": destination_location,
                    "period": period,
                    "routes": calculated_routes,
                }

                st.success(
                    f"Found {len(calculated_routes)} "
                    f"route candidate(s)."
                )

        except ValueError as exc:

            st.error(
                f"Invalid location or route: {exc}"
            )

            st.info(
                "Check the spelling of both locations "
                "and select locations within Bengaluru."
            )

        except FileNotFoundError as exc:

            st.error(
                f"Routing dataset error: {exc}"
            )

            st.info(
                "Check that the following files exist:"
            )

            st.code(
                "data/nodes.csv.gz\n"
                "data/edges.csv.gz"
            )

        except Exception as exc:

            st.error(
                f"Unable to calculate routes: {exc}"
            )

            st.info(
                "Check the location names and routing "
                "dataset. Common Bengaluru locations can "
                "be selected from the Quick Select boxes."
            )


# ============================================================================
# DISPLAY CALCULATED RESULT
# ============================================================================

result = st.session_state.get(
    "smartroute_result"
)


if result:

    source = result["source"]
    destination = result["destination"]
    selected_period = result["period"]
    routes = result["routes"]

    # ========================================================================
    # SUCCESS MESSAGE
    # ========================================================================

    st.success(
        f"Calculated {len(routes)} route candidate(s) "
        f"for {selected_period.lower()} travel."
    )

    # ========================================================================
    # JOURNEY INFORMATION
    # ========================================================================

    st.markdown("## 📍 Journey")

    left, right = st.columns(2)

    with left:

        st.markdown("### 🔵 START")

        st.info(
            source["address"]
        )

    with right:

        st.markdown("### 🔴 DESTINATION")

        st.info(
            destination["address"]
        )

    st.caption(
        f"Source provider: "
        f"{source.get('geocoding_provider', 'Unknown')} | "
        f"Destination provider: "
        f"{destination.get('geocoding_provider', 'Unknown')}"
    )

    st.caption(
        "Routes are snapped to the nearest road-network nodes."
    )

    # ========================================================================
    # RECOMMENDED ROUTE
    # ========================================================================

    first = routes[0]

    st.markdown(
        "## 🏆 Recommended Route"
    )

    top1, top2, top3, top4 = st.columns(4)

    top1.metric(
        "Distance",
        f"{format_number(first.get('distance_km'))} km",
    )

    top2.metric(
        "Travel time",
        f"{format_number(first.get('estimated_time_min'))} min",
    )

    top3.metric(
        "Road health",
        format_pct(
            first.get("road_health_pct")
        ),
    )

    top4.metric(
        "Safety",
        format_pct(
            first.get("selected_safety_pct")
        ),
    )

    st.metric(
        "Journey Confidence / Overall Score",
        format_pct(
            first.get("overall_score")
        ),
        help=(
            "Weighted route-ranking score. "
            "It is not a calibrated probability "
            "or a guarantee of journey safety."
        ),
    )

    # ========================================================================
    # ACTUAL ROUTE MAP
    # ========================================================================

    st.markdown(
        "## 🗺️ Interactive Bengaluru Route Map"
    )

    st.caption(
        "🟢 Recommended route | "
        "🟡 Alternative route 2 | "
        "🔴 Alternative route 3"
    )

    st.caption(
        "Click the route lines or START/DESTINATION markers "
        "to view additional information."
    )

    fmap = make_route_map(
        routes,
        source,
        destination,
    )

    st_folium(
        fmap,
        height=700,
        width=None,
        use_container_width=True,
        returned_objects=[],
        key="smartroute_dynamic_map",
    )

    # ========================================================================
    # ROUTE COMPARISON
    # ========================================================================

    st.markdown(
        "## 📊 Compare Alternative Routes"
    )

    for index, route in enumerate(routes):

        show_route_card(
            route,
            selected_period,
            recommended=(index == 0),
        )

    # ========================================================================
    # COMPARISON TABLE
    # ========================================================================

    comparison_rows = []

    for route in routes:

        comparison_rows.append(
            {
                "Rank": route.get("rank"),

                "Strategy": route.get(
                    "strategy"
                ),

                "Distance (km)": round(
                    route.get(
                        "distance_km",
                        0,
                    ),
                    2,
                ),

                "Time (min)": round(
                    route.get(
                        "estimated_time_min",
                        0,
                    ),
                    1,
                ),

                "Road health (%)": round(
                    route.get(
                        "road_health_pct",
                        0,
                    ),
                    1,
                ),

                "Safety (%)": round(
                    route.get(
                        "selected_safety_pct",
                        0,
                    ),
                    1,
                ),

                "Traffic risk (%)": round(
                    route.get(
                        "traffic_risk_pct",
                        0,
                    ),
                    1,
                ),

                "ML risk proxy (%)": round(
                    route.get(
                        "ml_risk_proxy_pct",
                        0,
                    ),
                    1,
                ),

                "Overall score": round(
                    route.get(
                        "overall_score",
                        0,
                    ),
                    1,
                ),
            }
        )

    st.markdown(
        "### 📋 Route Comparison Table"
    )

    st.dataframe(
        pd.DataFrame(
            comparison_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ========================================================================
    # ROUTE SNAP DIAGNOSTICS
    # ========================================================================

    st.markdown(
        "### 📡 Route Snapping Diagnostics"
    )

    d1, d2 = st.columns(2)

    d1.metric(
        "Source snap offset",
        (
            f"{format_number("
            f"first.get('source_snap_distance_km', 0), "
            f"3)} km"
        ),
    )

    d2.metric(
        "Destination snap offset",
        (
            f"{format_number("
            f"first.get('destination_snap_distance_km', 0), "
            f"3)} km"
        ),
    )

    # Warning if snapping is too far
    if (
        first.get(
            "source_snap_distance_km",
            0,
        ) > 1.0
        or
        first.get(
            "destination_snap_distance_km",
            0,
        ) > 1.0
    ):

        st.warning(
            "A location is more than 1 km from its "
            "matched road node. Check the location "
            "result before relying on this route."
        )

    # ========================================================================
    # DISCLAIMER
    # ========================================================================

    st.info(
        "Distance is calculated from road-network edge lengths. "
        "Travel time uses modelled speed and traffic-risk adjustments. "
        "Road health, safety, and ML risk are modelled features, "
        "not verified live measurements. Confirm real-world conditions "
        "before travelling."
    )


# ============================================================================
# INITIAL DASHBOARD SCREEN
# ============================================================================

else:

    st.markdown(
        "## Plan a safer journey across Bengaluru"
    )

    st.write(
        "Use the **Plan Your Journey** panel on the left "
        "to enter or select your source and destination."
    )

    # ========================================================================
    # DAY / NIGHT EXPLANATION
    # ========================================================================

    st.markdown(
        "### 🕐 Choose your journey time"
    )

    day_col, night_col = st.columns(2)

    with day_col:

        st.info(
            "☀️ **Daytime**\n\n"
            "Routes are ranked using daytime safety "
            "features."
        )

    with night_col:

        st.info(
            "🌙 **Nighttime**\n\n"
            "Routes are ranked using nighttime safety "
            "features."
        )

    # ========================================================================
    # DEFAULT BENGALURU MAP
    # ========================================================================

    st.markdown(
        "### 🗺️ Bengaluru Coverage Map"
    )

    st.caption(
        "Interactive map shown before route calculation."
    )

    overview_map = create_bengaluru_overview_map()

    st_folium(
        overview_map,
        height=550,
        width=None,
        use_container_width=True,
        returned_objects=[],
        key="smartroute_overview_map",
    )

    # ========================================================================
    # FEATURES
    # ========================================================================

    st.markdown(
        "### What this dashboard provides"
    )

    feature_col1, feature_col2 = st.columns(2)

    with feature_col1:

        st.markdown(
            """
            - 📍 Source and destination search
            - ☀️ Daytime / 🌙 Nighttime selection
            - 🛣️ Alternative road routes
            - 📏 Distance calculation
            """
        )

    with feature_col2:

        st.markdown(
            """
            - ⏱️ Estimated travel time
            - 🛡️ Safety and road-health scores
            - 🚦 Traffic-risk proxy
            - 🤖 ML-risk proxy
            """
        )

    st.warning(
        "No journey has been calculated yet. "
        "Enter or select locations in the sidebar "
        "and click **Find Safe Routes**."
    )


# ============================================================================
# FOOTER
# ============================================================================

st.divider()

st.caption(
    "SmartRoute | M.Tech research prototype | "
    "Modelled risk estimates are not a substitute for live navigation."
)
