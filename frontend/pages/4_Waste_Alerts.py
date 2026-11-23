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
    page_title="Waste Alerts - Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
)

apply_theme()

st.markdown(
    """
    <div style="margin-bottom: 20px;">
        <div style="font-size: 0.8rem; font-weight: 700; color: #f59e0b; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
            DETEKSI ANOMALI OPERASIONAL
        </div>
        <h1 style="color: #ffffff; font-size: 2.1rem; font-weight: 800; margin: 0 0 6px 0; letter-spacing: -0.02em;">
            ⚠️ Waste Alerts (Deteksi Pemborosan)
        </h1>
        <p style="color: #94a3b8; font-size: 0.98rem; margin: 0; line-height: 1.5;">
            Peringatan otomatis pemborosan daya listrik saat stand-by/idle dan anomali konsumsi mesin.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("<hr/>", unsafe_allow_html=True)
st.info("Modul Waste Alerts siap dikonfigurasi pada tahap selanjutnya.")
