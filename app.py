# ============================================================
# SmartRoute - Safe Navigation Streamlit Application
# Complete updated app.py
# ============================================================

from pathlib import Path
import math

import folium
import streamlit as st
from streamlit_folium import st_folium

from routing_engine import (
    geocode_location,
    load_routing_data,
    find_route_candidates,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="SmartRoute - Safe Navigation",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>
    .main {
        padding-top: 1rem;
    }

    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }

    .route-card {
        padding: 18px;
        border-radius: 12px;
        border: 1px solid #d9d9d9;
        margin-bottom: 15px;
        background-color: #ffffff;
    }

    .metric-card {
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #dddddd;
        text-align: center;
        background-color: #ffffff;
    }

    .small-text {
        color: #666666;
        font-size: 0.9rem;
    }

    .success-box {
        padding: 12px;
        border-radius: 8px;
        background-color: #eaf7ea;
        border: 1px solid #b8ddb8;
    }

    .warning-box {
        padding: 12px;
        border-radius: 8px;
        background-color: #fff8e1;
        border: 1px solid #ead28b;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# CONSTANTS
# ============================================================

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"

BENGALURU_CENTER = [12.9716, 77.5946]

COMMON_LOCATIONS = [
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


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def format_number(value, decimals=1):
    """
    Safely format numeric values.

    This implementation deliberately avoids the malformed
    nested f-string that caused the previous SyntaxError.
    """
    try:
        number = float(value)
        return format(number, ",." + str(decimals) + "f")
    except (TypeError, ValueError):
        return "N/A"


def safe_float(value, default=0.0):
    """Convert a value to float safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_route_value(route, key, default=None):
    """Safely get a route dictionary value."""
    if isinstance(route, dict):
        return route.get(key, default)

    try:
        return getattr(route, key, default)
    except Exception:
        return default


def normalize_coordinates(coordinates):
    """
    Convert route coordinates into a Folium-compatible list.

    Supports:
        [(lat, lon), ...]
        [[lat, lon], ...]
        [(lon, lat), ...] only if clearly identified elsewhere.

    The routing engine is expected to provide coordinates
    as latitude/longitude pairs.
    """
    if not coordinates:
        return []

    result = []

    for point in coordinates:
        try:
            if isinstance(point, dict):
                lat = point.get("lat")
                lon = point.get("lon")

                if lat is None:
                    lat = point.get("latitude")

                if lon is None:
                    lon = point.get("longitude")

                if lat is not None and lon is not None:
                    result.append([float(lat), float(lon)])

            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                result.append(
                    [
                        float(point[0]),
                        float(point[1]),
                    ]
                )

        except (TypeError, ValueError):
            continue

    return result


def route_color(rank):
    """Return a visual color for route ranking."""
    if rank == 1:
        return "green"

    if rank == 2:
        return "orange"

    return "red"


def calculate_map_center(source, destination):
    """Calculate map center between two locations."""
    try:
        source_lat = float(source["lat"])
        source_lon = float(source["lon"])
        destination_lat = float(destination["lat"])
        destination_lon = float(destination["lon"])

        return [
            (source_lat + destination_lat) / 2,
            (source_lon + destination_lon) / 2,
        ]

    except Exception:
        return BENGALURU_CENTER


def make_overview_map():
    """
    Create the initial Bengaluru overview map shown
    before a route search.
    """

    map_object = folium.Map(
        location=BENGALURU_CENTER,
        zoom_start=11,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    folium.TileLayer(
        tiles="CartoDB positron",
        name="Light Map",
        control=True,
    ).add_to(map_object)

    folium.Marker(
        location=BENGALURU_CENTER,
        tooltip="Bengaluru",
        popup="SmartRoute Bengaluru",
        icon=folium.Icon(
            color="blue",
            icon="info-sign",
        ),
    ).add_to(map_object)

    folium.LayerControl().add_to(map_object)

    return map_object


def make_route_map(source, destination, routes):
    """
    Create the interactive route map.
    """

    center = calculate_map_center(
        source,
        destination,
    )

    map_object = folium.Map(
        location=center,
        zoom_start=12,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    folium.TileLayer(
        tiles="CartoDB positron",
        name="Light Map",
        control=True,
    ).add_to(map_object)

    # --------------------------------------------------------
    # Source marker
    # --------------------------------------------------------

    folium.Marker(
        location=[
            float(source["lat"]),
            float(source["lon"]),
        ],
        tooltip="Source",
        popup=(
            "<b>Source</b><br>"
            + str(source.get("address", source.get("query", "Unknown")))
        ),
        icon=folium.Icon(
            color="blue",
            icon="play",
        ),
    ).add_to(map_object)

    # --------------------------------------------------------
    # Destination marker
    # --------------------------------------------------------

    folium.Marker(
        location=[
            float(destination["lat"]),
            float(destination["lon"]),
        ],
        tooltip="Destination",
        popup=(
            "<b>Destination</b><br>"
            + str(
                destination.get(
                    "address",
                    destination.get("query", "Unknown"),
                )
            )
        ),
        icon=folium.Icon(
            color="red",
            icon="flag",
        ),
    ).add_to(map_object)

    # --------------------------------------------------------
    # Draw routes
    # --------------------------------------------------------

    all_points = []

    for index, route in enumerate(routes):

        rank_value = get_route_value(
            route,
            "rank",
            index + 1,
        )

        try:
            rank = int(rank_value)
        except (TypeError, ValueError):
            rank = index + 1

        coordinates = normalize_coordinates(
            get_route_value(
                route,
                "coordinates",
                [],
            )
        )

        if not coordinates:
            continue

        all_points.extend(coordinates)

        strategy = get_route_value(
            route,
            "strategy",
            "Route",
        )

        distance = safe_float(
            get_route_value(
                route,
                "distance_km",
                0,
            )
        )

        eta = safe_float(
            get_route_value(
                route,
                "estimated_time_min",
                0,
            )
        )

        score = safe_float(
            get_route_value(
                route,
                "overall_score",
                0,
            )
        )

        popup_html = (
            "<div style='min-width:220px'>"
            "<b>Route "
            + str(rank)
            + "</b><br><br>"
            "<b>Strategy:</b> "
            + str(strategy)
            + "<br>"
            "<b>Distance:</b> "
            + format_number(distance, 2)
            + " km<br>"
            "<b>Estimated time:</b> "
            + format_number(eta, 1)
            + " min<br>"
            "<b>Safety score:</b> "
            + format_number(score, 1)
            + "</div>"
        )

        folium.PolyLine(
            locations=coordinates,
            color=route_color(rank),
            weight=7 if rank == 1 else 5,
            opacity=0.85,
            tooltip=(
                "Route "
                + str(rank)
                + " - "
                + str(strategy)
            ),
            popup=folium.Popup(
                popup_html,
                max_width=350,
            ),
        ).add_to(map_object)

    # --------------------------------------------------------
    # Fit map to all route points
    # --------------------------------------------------------

    if all_points:
        map_object.fit_bounds(all_points)

    else:
        map_object.fit_bounds(
            [
                [
                    float(source["lat"]),
                    float(source["lon"]),
                ],
                [
                    float(destination["lat"]),
                    float(destination["lon"]),
                ],
            ]
        )

    # --------------------------------------------------------
    # Legend
    # --------------------------------------------------------

    legend_html = """
    <div style="
        position: fixed;
        bottom: 30px;
        left: 30px;
        z-index: 9999;
        background-color: white;
        border: 2px solid #777;
        border-radius: 8px;
        padding: 12px;
        font-size: 13px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    ">
        <b>SmartRoute</b><br>
        <span style="color:green;">━━</span>
        Recommended Route<br>
        <span style="color:orange;">━━</span>
        Alternative Route<br>
        <span style="color:red;">━━</span>
        Higher-Risk Alternative<br>
        🔵 Source<br>
        🔴 Destination
    </div>
    """

    map_object.get_root().html.add_child(
        folium.Element(legend_html)
    )

    folium.LayerControl().add_to(map_object)

    return map_object


def display_route_metrics(route):
    """
    Display metrics for one calculated route.
    """

    distance = safe_float(
        get_route_value(
            route,
            "distance_km",
            0,
        )
    )

    eta = safe_float(
        get_route_value(
            route,
            "estimated_time_min",
            0,
        )
    )

    score = safe_float(
        get_route_value(
            route,
            "overall_score",
            0,
        )
    )

    road_health = safe_float(
        get_route_value(
            route,
            "road_health_pct",
            0,
        )
    )

    safety = safe_float(
        get_route_value(
            route,
            "selected_safety_pct",
            0,
        )
    )

    traffic = safe_float(
        get_route_value(
            route,
            "traffic_risk_pct",
            0,
        )
    )

    ml_risk = safe_float(
        get_route_value(
            route,
            "ml_risk_proxy_pct",
            0,
        )
    )

    strategy = get_route_value(
        route,
        "strategy",
        "Route",
    )

    rank = get_route_value(
        route,
        "rank",
        "-",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Distance",
            format_number(distance, 2) + " km",
        )

    with col2:
        st.metric(
            "Estimated Time",
            format_number(eta, 1) + " min",
        )

    with col3:
        st.metric(
            "Safety Score",
            format_number(score, 1),
        )

    with col4:
        st.metric(
            "Rank",
            str(rank),
        )

    st.markdown(
        "### Route Details"
    )

    detail_col1, detail_col2, detail_col3, detail_col4 = st.columns(4)

    with detail_col1:
        st.write(
            "**Strategy**"
        )
        st.write(
            str(strategy)
        )

    with detail_col2:
        st.write(
            "**Road Health**"
        )
        st.write(
            format_number(road_health, 1) + "%"
        )

    with detail_col3:
        st.write(
            "**Safety Risk Indicator**"
        )
        st.write(
            format_number(safety, 1) + "%"
        )

    with detail_col4:
        st.write(
            "**Traffic Risk**"
        )
        st.write(
            format_number(traffic, 1) + "%"
        )

    st.write(
        "**ML Risk Proxy:** "
        + format_number(ml_risk, 1)
        + "%"
    )


def display_route_card(route, index):
    """Display a compact route comparison card."""

    rank_value = get_route_value(
        route,
        "rank",
        index + 1,
    )

    strategy = get_route_value(
        route,
        "strategy",
        "Route",
    )

    distance = safe_float(
        get_route_value(
            route,
            "distance_km",
            0,
        )
    )

    eta = safe_float(
        get_route_value(
            route,
            "estimated_time_min",
            0,
        )
    )

    score = safe_float(
        get_route_value(
            route,
            "overall_score",
            0,
        )
    )

    st.markdown(
        "<div class='route-card'>"
        "<h4>Route "
        + str(rank_value)
        + " — "
        + str(strategy)
        + "</h4>"
        "<p>"
        "<b>Distance:</b> "
        + format_number(distance, 2)
        + " km &nbsp;&nbsp; "
        "<b>Time:</b> "
        + format_number(eta, 1)
        + " min &nbsp;&nbsp; "
        "<b>Safety:</b> "
        + format_number(score, 1)
        + "</p>"
        "</div>",
        unsafe_allow_html=True,
    )


# ============================================================
# LOAD ROUTING DATA
# ============================================================

@st.cache_resource
def load_network_data():
    """
    Load the routing network once and cache it.
    """

    return load_routing_data(
        str(DATA_DIR)
    )


# ============================================================
# SESSION STATE
# ============================================================

if "source_query" not in st.session_state:
    st.session_state.source_query = ""

if "destination_query" not in st.session_state:
    st.session_state.destination_query = ""

if "period" not in st.session_state:
    st.session_state.period = "Daytime"

if "calculated_routes" not in st.session_state:
    st.session_state.calculated_routes = None

if "source_location" not in st.session_state:
    st.session_state.source_location = None

if "destination_location" not in st.session_state:
    st.session_state.destination_location = None


# ============================================================
# HEADER
# ============================================================

st.title("🚗 SmartRoute")

st.subheader(
    "ML-Assisted Safe Navigation for Bengaluru"
)

st.write(
    "Find and compare safer route alternatives using "
    "road, traffic, safety, and machine-learning risk indicators."
)


# ============================================================
# SIDEBAR
# ============================================================

submitted = False

with st.sidebar:

    st.header("🔎 Plan Your Journey")

    st.markdown(
        "Enter locations or choose a common Bengaluru location."
    )

    # --------------------------------------------------------
    # JOURNEY FORM
    # --------------------------------------------------------

    with st.form(
        "dynamic_journey_form",
        clear_on_submit=False,
    ):

        source_query = st.text_input(
            "📍 Source",
            value=st.session_state.source_query,
            placeholder="Example: Majestic",
        )

        source_choice = st.selectbox(
            "Quick select source",
            [
                "— Type your own source —"
            ]
            + COMMON_LOCATIONS,
        )

        destination_query = st.text_input(
            "🏁 Destination",
            value=st.session_state.destination_query,
            placeholder="Example: Whitefield",
        )

        destination_choice = st.selectbox(
            "Quick select destination",
            [
                "— Type your own destination —"
            ]
            + COMMON_LOCATIONS,
        )

        period_choice = st.radio(
            "🕒 Travel period",
            [
                "☀️ Daytime",
                "🌙 Nighttime",
            ],
            horizontal=True,
        )

        submitted = st.form_submit_button(
            "🚗 Find Safe Routes",
            type="primary",
            use_container_width=True,
        )


# ============================================================
# PROCESS SEARCH
# ============================================================

if submitted:

    # --------------------------------------------------------
    # Determine source
    # --------------------------------------------------------

    if (
        not source_query.strip()
        and source_choice != "— Type your own source —"
    ):
        source_query = source_choice

    # --------------------------------------------------------
    # Determine destination
    # --------------------------------------------------------

    if (
        not destination_query.strip()
        and destination_choice != "— Type your own destination —"
    ):
        destination_query = destination_choice

    # --------------------------------------------------------
    # Determine period
    # --------------------------------------------------------

    if period_choice.startswith("☀️"):
        period = "Daytime"
    else:
        period = "Nighttime"

    # --------------------------------------------------------
    # Validate input
    # --------------------------------------------------------

    if not source_query.strip():
        st.error(
            "Please enter or select a source location."
        )

    elif not destination_query.strip():
        st.error(
            "Please enter or select a destination location."
        )

    else:

        st.session_state.source_query = source_query
        st.session_state.destination_query = destination_query
        st.session_state.period = period

        # ----------------------------------------------------
        # Geocode source
        # ----------------------------------------------------

        with st.spinner(
            "Finding source location..."
        ):
            try:
                source_location = geocode_location(
                    source_query
                )
            except Exception as exc:
                source_location = None
                st.error(
                    "Source geocoding failed: "
                    + str(exc)
                )

        # ----------------------------------------------------
        # Geocode destination
        # ----------------------------------------------------

        with st.spinner(
            "Finding destination location..."
        ):
            try:
                destination_location = geocode_location(
                    destination_query
                )
            except Exception as exc:
                destination_location = None
                st.error(
                    "Destination geocoding failed: "
                    + str(exc)
                )

        # ----------------------------------------------------
        # Check geocoding results
        # ----------------------------------------------------

        if source_location is None:
            st.error(
                "Could not find the source location."
            )

        elif destination_location is None:
            st.error(
                "Could not find the destination location."
            )

        else:

            st.session_state.source_location = (
                source_location
            )

            st.session_state.destination_location = (
                destination_location
            )

            # ------------------------------------------------
            # Load routing network
            # ------------------------------------------------

            with st.spinner(
                "Loading SmartRoute routing network..."
            ):
                try:
                    graph, node_coords, node_index = (
                        load_network_data()
                    )

                except Exception as exc:

                    st.error(
                        "Could not load routing data."
                    )

                    st.exception(exc)

                    st.stop()

            # ------------------------------------------------
            # Calculate routes
            # ------------------------------------------------

            with st.spinner(
                "Calculating safer route alternatives..."
            ):
                try:

                    calculated_routes = (
                        find_route_candidates(
                            graph=graph,
                            node_coords=node_coords,
                            node_index=node_index,
                            source=source_location,
                            destination=destination_location,
                            period=period,
                            max_routes=3,
                        )
                    )

                    st.session_state.calculated_routes = (
                        calculated_routes
                    )

                except Exception as exc:

                    st.session_state.calculated_routes = None

                    st.error(
                        "Route calculation failed."
                    )

                    st.exception(exc)


# ============================================================
# GET CURRENT RESULTS
# ============================================================

routes = st.session_state.calculated_routes

source_location = (
    st.session_state.source_location
)

destination_location = (
    st.session_state.destination_location
)


# ============================================================
# MAP SECTION
# ============================================================

st.markdown("---")

st.header("🗺️ Route Map")

if (
    routes
    and source_location
    and destination_location
):

    st.success(
        "Routes calculated successfully for "
        + st.session_state.period
        + "."
    )

    route_map = make_route_map(
        source_location,
        destination_location,
        routes,
    )

    st_folium(
        route_map,
        height=700,
        use_container_width=True,
        returned_objects=[],
        key="smartroute_dynamic_map",
    )

else:

    st.info(
        "Enter a source and destination from the sidebar "
        "to calculate safe routes."
    )

    overview_map = make_overview_map()

    st_folium(
        overview_map,
        height=550,
        use_container_width=True,
        returned_objects=[],
        key="smartroute_overview_map",
    )


# ============================================================
# RESULTS SECTION
# ============================================================

if routes:

    st.markdown("---")

    st.header("🛣️ Route Comparison")

    st.write(
        "The available route alternatives are ranked "
        "according to the SmartRoute scoring system."
    )

    # --------------------------------------------------------
    # Route cards
    # --------------------------------------------------------

    for index, route in enumerate(routes):

        display_route_card(
            route,
            index,
        )

    # --------------------------------------------------------
    # Detailed route
    # --------------------------------------------------------

    st.markdown("---")

    st.header("📊 Detailed Route Analysis")

    route_labels = []

    for index, route in enumerate(routes):

        rank_value = get_route_value(
            route,
            "rank",
            index + 1,
        )

        strategy = get_route_value(
            route,
            "strategy",
            "Route",
        )

        route_labels.append(
            "Route "
            + str(rank_value)
            + " — "
            + str(strategy)
        )

    selected_route_index = st.selectbox(
        "Select a route for detailed analysis",
        range(len(routes)),
        format_func=lambda x: route_labels[x],
    )

    selected_route = routes[
        selected_route_index
    ]

    display_route_metrics(
        selected_route
    )


# ============================================================
# LOCATION INFORMATION
# ============================================================

if (
    source_location
    and destination_location
):

    st.markdown("---")

    st.header("📍 Journey Information")

    info_col1, info_col2 = st.columns(2)

    with info_col1:

        st.markdown("### Source")

        st.write(
            source_location.get(
                "address",
                source_location.get(
                    "query",
                    st.session_state.source_query,
                ),
            )
        )

        st.write(
            "Latitude: "
            + format_number(
                source_location.get("lat"),
                6,
            )
        )

        st.write(
            "Longitude: "
            + format_number(
                source_location.get("lon"),
                6,
            )
        )

    with info_col2:

        st.markdown("### Destination")

        st.write(
            destination_location.get(
                "address",
                destination_location.get(
                    "query",
                    st.session_state.destination_query,
                ),
            )
        )

        st.write(
            "Latitude: "
            + format_number(
                destination_location.get("lat"),
                6,
            )
        )

        st.write(
            "Longitude: "
            + format_number(
                destination_location.get("lon"),
                6,
            )
        )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "SmartRoute • ML-Assisted Safe Navigation • "
    "Bengaluru"
)
