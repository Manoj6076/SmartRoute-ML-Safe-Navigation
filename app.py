# ============================================================
# SmartRoute - Safe Navigation
# Updated app.py
# ============================================================

from pathlib import Path
import folium
import streamlit as st
import streamlit.components.v1 as components

from routing_engine import (
    geocode_location,
    load_routing_data,
    find_route_candidates,
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="SmartRoute - Safe Navigation",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CSS
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
        padding: 16px;
        border-radius: 12px;
        border: 1px solid #d9d9d9;
        margin-bottom: 12px;
        background-color: white;
    }

    .map-title {
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 10px;
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

BENGALURU_CENTER = [
    12.9716,
    77.5946,
]

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
# SESSION STATE
# ============================================================

if "source_query" not in st.session_state:
    st.session_state.source_query = ""

if "destination_query" not in st.session_state:
    st.session_state.destination_query = ""

if "period" not in st.session_state:
    st.session_state.period = "Daytime"

if "routes" not in st.session_state:
    st.session_state.routes = None

if "source_location" not in st.session_state:
    st.session_state.source_location = None

if "destination_location" not in st.session_state:
    st.session_state.destination_location = None


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def format_number(value, decimals=1):
    """
    Safe number formatter.
    Avoids the previous f-string syntax problem.
    """
    try:
        number = float(value)
        return format(number, ",." + str(decimals) + "f")
    except (TypeError, ValueError):
        return "N/A"


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def route_value(route, key, default=None):

    if isinstance(route, dict):
        return route.get(key, default)

    try:
        return getattr(route, key, default)
    except Exception:
        return default


def normalize_coordinates(coordinates):

    if not coordinates:
        return []

    output = []

    for point in coordinates:

        try:

            if isinstance(point, dict):

                lat = point.get("lat")

                if lat is None:
                    lat = point.get("latitude")

                lon = point.get("lon")

                if lon is None:
                    lon = point.get("longitude")

                if lat is not None and lon is not None:
                    output.append(
                        [
                            float(lat),
                            float(lon),
                        ]
                    )

            elif isinstance(point, (list, tuple)):

                if len(point) >= 2:
                    output.append(
                        [
                            float(point[0]),
                            float(point[1]),
                        ]
                    )

        except Exception:
            continue

    return output


def route_color(rank):

    if rank == 1:
        return "green"

    if rank == 2:
        return "orange"

    return "red"


# ============================================================
# CREATE OVERVIEW MAP
# ============================================================

def create_overview_map():

    m = folium.Map(
        location=BENGALURU_CENTER,
        zoom_start=11,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    folium.TileLayer(
        tiles="CartoDB positron",
        name="Light Map",
        control=True,
    ).add_to(m)

    folium.Marker(
        location=BENGALURU_CENTER,
        tooltip="Bengaluru",
        popup="SmartRoute Bengaluru",
        icon=folium.Icon(
            color="blue",
            icon="info-sign",
        ),
    ).add_to(m)

    folium.Circle(
        location=BENGALURU_CENTER,
        radius=12000,
        color="blue",
        fill=False,
        tooltip="SmartRoute Bengaluru Coverage",
    ).add_to(m)

    folium.LayerControl().add_to(m)

    return m


# ============================================================
# CREATE ROUTE MAP
# ============================================================

def create_route_map(
    source,
    destination,
    routes,
):

    source_lat = float(source["lat"])
    source_lon = float(source["lon"])

    destination_lat = float(destination["lat"])
    destination_lon = float(destination["lon"])

    center_lat = (
        source_lat + destination_lat
    ) / 2

    center_lon = (
        source_lon + destination_lon
    ) / 2

    m = folium.Map(
        location=[
            center_lat,
            center_lon,
        ],
        zoom_start=12,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    # --------------------------------------------------------
    # Alternative base map
    # --------------------------------------------------------

    folium.TileLayer(
        tiles="CartoDB positron",
        name="Light Map",
        control=True,
    ).add_to(m)

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    folium.Marker(
        location=[
            source_lat,
            source_lon,
        ],
        tooltip="📍 Source",
        popup=folium.Popup(
            "<b>Source</b><br>"
            + str(
                source.get(
                    "address",
                    source.get(
                        "query",
                        "Source",
                    ),
                )
            ),
            max_width=300,
        ),
        icon=folium.Icon(
            color="blue",
            icon="play",
        ),
    ).add_to(m)

    # --------------------------------------------------------
    # DESTINATION
    # --------------------------------------------------------

    folium.Marker(
        location=[
            destination_lat,
            destination_lon,
        ],
        tooltip="🏁 Destination",
        popup=folium.Popup(
            "<b>Destination</b><br>"
            + str(
                destination.get(
                    "address",
                    destination.get(
                        "query",
                        "Destination",
                    ),
                )
            ),
            max_width=300,
        ),
        icon=folium.Icon(
            color="red",
            icon="flag",
        ),
    ).add_to(m)

    # --------------------------------------------------------
    # ROUTES
    # --------------------------------------------------------

    all_coordinates = []

    for index, route in enumerate(routes):

        rank = route_value(
            route,
            "rank",
            index + 1,
        )

        try:
            rank = int(rank)
        except Exception:
            rank = index + 1

        coordinates = normalize_coordinates(
            route_value(
                route,
                "coordinates",
                [],
            )
        )

        if not coordinates:
            continue

        all_coordinates.extend(
            coordinates
        )

        strategy = route_value(
            route,
            "strategy",
            "Route",
        )

        distance = safe_float(
            route_value(
                route,
                "distance_km",
                0,
            )
        )

        eta = safe_float(
            route_value(
                route,
                "estimated_time_min",
                0,
            )
        )

        score = safe_float(
            route_value(
                route,
                "overall_score",
                0,
            )
        )

        popup = (
            "<div style='min-width:230px;'>"
            "<h4>Route "
            + str(rank)
            + "</h4>"
            "<b>Strategy:</b> "
            + str(strategy)
            + "<br>"
            "<b>Distance:</b> "
            + format_number(distance, 2)
            + " km<br>"
            "<b>Time:</b> "
            + format_number(eta, 1)
            + " min<br>"
            "<b>Safety Score:</b> "
            + format_number(score, 1)
            + "</div>"
        )

        folium.PolyLine(
            locations=coordinates,
            color=route_color(rank),
            weight=8 if rank == 1 else 5,
            opacity=0.9,
            tooltip=(
                "Route "
                + str(rank)
                + " - "
                + str(strategy)
            ),
            popup=folium.Popup(
                popup,
                max_width=350,
            ),
        ).add_to(m)

    # --------------------------------------------------------
    # FIT MAP
    # --------------------------------------------------------

    if all_coordinates:

        m.fit_bounds(
            all_coordinates,
            padding=(30, 30),
        )

    else:

        m.fit_bounds(
            [
                [
                    source_lat,
                    source_lon,
                ],
                [
                    destination_lat,
                    destination_lon,
                ],
            ],
            padding=(30, 30),
        )

    # --------------------------------------------------------
    # LEGEND
    # --------------------------------------------------------

    legend = """
    <div style="
        position: fixed;
        bottom: 25px;
        left: 25px;
        z-index: 9999;
        background: white;
        padding: 12px;
        border: 2px solid #777;
        border-radius: 8px;
        font-size: 13px;
        box-shadow: 0px 2px 8px rgba(0,0,0,0.25);
    ">
        <b>SmartRoute</b><br>
        <span style="color:green;">━━</span>
        Recommended Route<br>
        <span style="color:orange;">━━</span>
        Alternative Route<br>
        <span style="color:red;">━━</span>
        Higher-Risk Route<br>
        🔵 Source<br>
        🔴 Destination
    </div>
    """

    m.get_root().html.add_child(
        folium.Element(legend)
    )

    folium.LayerControl().add_to(m)

    return m


# ============================================================
# DISPLAY MAP
# ============================================================

def display_map(m, height=700):

    """
    IMPORTANT:
    Render Folium directly as HTML instead of using
    st_folium(). This avoids the blank-map rendering
    problem in Streamlit deployments.
    """

    map_html = m.get_root().render()

    components.html(
        map_html,
        height=height,
        scrolling=False,
    )


# ============================================================
# LOAD ROUTING NETWORK
# ============================================================

@st.cache_resource
def get_network():

    return load_routing_data(
        str(DATA_DIR)
    )


# ============================================================
# HEADER
# ============================================================

st.title(
    "🚗 SmartRoute"
)

st.subheader(
    "ML-Assisted Safe Navigation for Bengaluru"
)

st.write(
    "Find safer routes using road condition, "
    "traffic, safety and ML-based risk indicators."
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header(
        "🔎 Plan Your Journey"
    )

    st.caption(
        "Enter locations or select a common Bengaluru location."
    )

    with st.form(
        "journey_form",
        clear_on_submit=False,
    ):

        source_text = st.text_input(
            "📍 Source",
            value=st.session_state.source_query,
            placeholder="Example: Majestic",
        )

        source_select = st.selectbox(
            "Quick select source",
            [
                "— Type your own source —"
            ]
            + COMMON_LOCATIONS,
        )

        destination_text = st.text_input(
            "🏁 Destination",
            value=st.session_state.destination_query,
            placeholder="Example: Whitefield",
        )

        destination_select = st.selectbox(
            "Quick select destination",
            [
                "— Type your own destination —"
            ]
            + COMMON_LOCATIONS,
        )

        period_select = st.radio(
            "🕒 Travel period",
            [
                "☀️ Daytime",
                "🌙 Nighttime",
            ],
            horizontal=True,
        )

        search_button = st.form_submit_button(
            "🚗 Find Safe Routes",
            type="primary",
            use_container_width=True,
        )


# ============================================================
# SEARCH
# ============================================================

if search_button:

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    if (
        not source_text.strip()
        and source_select
        != "— Type your own source —"
    ):

        source_text = source_select

    # --------------------------------------------------------
    # DESTINATION
    # --------------------------------------------------------

    if (
        not destination_text.strip()
        and destination_select
        != "— Type your own destination —"
    ):

        destination_text = destination_select

    # --------------------------------------------------------
    # PERIOD
    # --------------------------------------------------------

    if period_select.startswith("☀️"):
        period = "Daytime"
    else:
        period = "Nighttime"

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not source_text.strip():

        st.error(
            "Please enter or select a source."
        )

        st.stop()

    if not destination_text.strip():

        st.error(
            "Please enter or select a destination."
        )

        st.stop()

    # --------------------------------------------------------
    # SAVE INPUT
    # --------------------------------------------------------

    st.session_state.source_query = (
        source_text
    )

    st.session_state.destination_query = (
        destination_text
    )

    st.session_state.period = period

    # --------------------------------------------------------
    # GEOCODE SOURCE
    # --------------------------------------------------------

    with st.spinner(
        "Finding source location..."
    ):

        try:

            source_location = (
                geocode_location(
                    source_text
                )
            )

        except Exception as error:

            st.error(
                "Source geocoding failed: "
                + str(error)
            )

            st.stop()

    if not source_location:

        st.error(
            "Could not find source location."
        )

        st.stop()

    # --------------------------------------------------------
    # GEOCODE DESTINATION
    # --------------------------------------------------------

    with st.spinner(
        "Finding destination location..."
    ):

        try:

            destination_location = (
                geocode_location(
                    destination_text
                )
            )

        except Exception as error:

            st.error(
                "Destination geocoding failed: "
                + str(error)
            )

            st.stop()

    if not destination_location:

        st.error(
            "Could not find destination location."
        )

        st.stop()

    # --------------------------------------------------------
    # SAVE LOCATIONS
    # --------------------------------------------------------

    st.session_state.source_location = (
        source_location
    )

    st.session_state.destination_location = (
        destination_location
    )

    # --------------------------------------------------------
    # LOAD NETWORK
    # --------------------------------------------------------

    with st.spinner(
        "Loading SmartRoute network..."
    ):

        try:

            graph, node_coords, node_index = (
                get_network()
            )

        except Exception as error:

            st.error(
                "Could not load routing network."
            )

            st.exception(error)

            st.stop()

    # --------------------------------------------------------
    # CALCULATE ROUTES
    # --------------------------------------------------------

    with st.spinner(
        "Calculating safe route alternatives..."
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

        except Exception as error:

            st.error(
                "Route calculation failed."
            )

            st.exception(error)

            st.stop()

    st.session_state.routes = (
        calculated_routes
    )

    st.rerun()


# ============================================================
# CURRENT DATA
# ============================================================

routes = st.session_state.routes

source_location = (
    st.session_state.source_location
)

destination_location = (
    st.session_state.destination_location
)


# ============================================================
# MAP
# ============================================================

st.markdown("---")

st.header(
    "🗺️ Interactive Route Map"
)

if (
    routes
    and source_location
    and destination_location
):

    st.success(
        "Routes calculated for "
        + st.session_state.period
        + "."
    )

    route_map = create_route_map(
        source_location,
        destination_location,
        routes,
    )

    # IMPORTANT:
    # Direct HTML rendering replaces st_folium.
    display_map(
        route_map,
        height=700,
    )

else:

    st.info(
        "Select a source and destination from "
        "the left sidebar to calculate routes."
    )

    overview_map = create_overview_map()

    display_map(
        overview_map,
        height=600,
    )


# ============================================================
# ROUTE RESULTS
# ============================================================

if routes:

    st.markdown("---")

    st.header(
        "🛣️ Route Comparison"
    )

    for index, route in enumerate(routes):

        rank = route_value(
            route,
            "rank",
            index + 1,
        )

        strategy = route_value(
            route,
            "strategy",
            "Route",
        )

        distance = safe_float(
            route_value(
                route,
                "distance_km",
                0,
            )
        )

        eta = safe_float(
            route_value(
                route,
                "estimated_time_min",
                0,
            )
        )

        score = safe_float(
            route_value(
                route,
                "overall_score",
                0,
            )
        )

        st.markdown(
            """
            <div class="route-card">
            <h4>
            Route {rank} — {strategy}
            </h4>

            <b>Distance:</b>
            {distance} km
            &nbsp;&nbsp;&nbsp;

            <b>Estimated Time:</b>
            {eta} min
            &nbsp;&nbsp;&nbsp;

            <b>Safety Score:</b>
            {score}
            </div>
            """.format(
                rank=rank,
                strategy=strategy,
                distance=format_number(
                    distance,
                    2,
                ),
                eta=format_number(
                    eta,
                    1,
                ),
                score=format_number(
                    score,
                    1,
                ),
            ),
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------
    # DETAILED ANALYSIS
    # --------------------------------------------------------

    st.markdown("---")

    st.header(
        "📊 Detailed Route Analysis"
    )

    route_names = []

    for index, route in enumerate(routes):

        rank = route_value(
            route,
            "rank",
            index + 1,
        )

        strategy = route_value(
            route,
            "strategy",
            "Route",
        )

        route_names.append(
            "Route "
            + str(rank)
            + " — "
            + str(strategy)
        )

    selected_index = st.selectbox(
        "Select route",
        range(len(routes)),
        format_func=lambda x: route_names[x],
    )

    selected_route = routes[
        selected_index
    ]

    distance = safe_float(
        route_value(
            selected_route,
            "distance_km",
            0,
        )
    )

    eta = safe_float(
        route_value(
            selected_route,
            "estimated_time_min",
            0,
        )
    )

    score = safe_float(
        route_value(
            selected_route,
            "overall_score",
            0,
        )
    )

    road_health = safe_float(
        route_value(
            selected_route,
            "road_health_pct",
            0,
        )
    )

    safety = safe_float(
        route_value(
            selected_route,
            "selected_safety_pct",
            0,
        )
    )

    traffic = safe_float(
        route_value(
            selected_route,
            "traffic_risk_pct",
            0,
        )
    )

    ml_risk = safe_float(
        route_value(
            selected_route,
            "ml_risk_proxy_pct",
            0,
        )
    )

    strategy = route_value(
        selected_route,
        "strategy",
        "Route",
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        st.metric(
            "Distance",
            format_number(
                distance,
                2,
            )
            + " km",
        )

    with c2:

        st.metric(
            "Estimated Time",
            format_number(
                eta,
                1,
            )
            + " min",
        )

    with c3:

        st.metric(
            "Safety Score",
            format_number(
                score,
                1,
            ),
        )

    with c4:

        st.metric(
            "Road Health",
            format_number(
                road_health,
                1,
            )
            + "%",
        )

    d1, d2, d3 = st.columns(3)

    with d1:

        st.write(
            "**Route Strategy**"
        )

        st.write(
            strategy
        )

    with d2:

        st.write(
            "**Traffic Risk**"
        )

        st.write(
            format_number(
                traffic,
                1,
            )
            + "%"
        )

    with d3:

        st.write(
            "**ML Risk Proxy**"
        )

        st.write(
            format_number(
                ml_risk,
                1,
            )
            + "%"
        )

    st.write(
        "**Selected Safety Indicator:** "
        + format_number(
            safety,
            1,
        )
        + "%"
    )


# ============================================================
# LOCATION INFORMATION
# ============================================================

if (
    source_location
    and destination_location
):

    st.markdown("---")

    st.header(
        "📍 Journey Information"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.subheader(
            "Source"
        )

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
                source_location.get(
                    "lat"
                ),
                6,
            )
        )

        st.write(
            "Longitude: "
            + format_number(
                source_location.get(
                    "lon"
                ),
                6,
            )
        )

    with col2:

        st.subheader(
            "Destination"
        )

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
                destination_location.get(
                    "lat"
                ),
                6,
            )
        )

        st.write(
            "Longitude: "
            + format_number(
                destination_location.get(
                    "lon"
                ),
                6,
            )
        )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "SmartRoute • ML-Assisted Safe Navigation • Bengaluru"
)
