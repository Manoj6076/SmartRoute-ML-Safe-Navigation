
from pathlib import Path
import json
import html
import traceback

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

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

# Import the routing engine only after Streamlit is configured.
# If the deployed module is stale, malformed, or missing a dependency,
# display the real exception instead of Streamlit's shortened traceback.
try:
    import routing_engine

    geocode_location = routing_engine.geocode_location
    load_routing_data = routing_engine.load_routing_data
    find_route_candidates = routing_engine.find_route_candidates

except Exception as exc:
    st.error("SmartRoute could not load routing_engine.py")
    st.write("**Actual exception:**", f"{type(exc).__name__}: {exc}")
    st.code(traceback.format_exc(), language="text")
    st.info(
        "Check that routing_engine.py is in the same GitHub folder as app.py, "
        "that Streamlit is deploying the correct branch and main file, and "
        "that requirements.txt installs all dependencies."
    )
    st.stop()


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

st.caption("Bengaluru road routing prototype | Distance, road health, time-aware safety and risk-based recommendations")
