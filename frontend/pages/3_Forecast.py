import sys
from pathlib import Path
import streamlit as st

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
for p in (str(CURRENT_DIR.parent), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from frontend.ui import apply_theme
except ImportError:
    from ui import apply_theme

st.set_page_config(
    page_title="Forecast - Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
)

apply_theme()

st.markdown(
    """
    <div style="margin-bottom: 20px;">
        <div style="font-size: 0.8rem; font-weight: 700; color: #F2C230; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
            // PREDIKSI BEBAN LISTRIK
        </div>
        <h1 style="color: #1F1A17; font-size: 2.1rem; font-weight: 800; margin: 0 0 6px 0; letter-spacing: -0.02em;">
            📈 Forecast Konsumsi Energi
        </h1>
        <p style="color: #6B6259; font-size: 0.98rem; margin: 0; line-height: 1.5;">
            Proyeksi kebutuhan daya listrik ke depan (24–72 jam) berbasis model machine learning per mesin.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("<hr/>", unsafe_allow_html=True)
st.info("Modul Forecast siap dikonfigurasi pada tahap selanjutnya.")
