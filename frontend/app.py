import sys
from pathlib import Path
import streamlit as st

# Setup sys.path agar impor modul api_client berjalan mulus
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
for path in (str(CURRENT_DIR), str(ROOT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from frontend.api_client import check_api
except ImportError:
    from api_client import check_api

# ---------------------------------------------------------------------------
# Konfigurasi Halaman Utama
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar: Status API & Tombol Muat Ulang
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🔌 Koneksi API")
    is_connected = check_api()
    if is_connected:
        st.success("Backend Terhubung", icon="🟢")
    else:
        st.error("Backend Terputus", icon="🔴")

    st.markdown("---")
    if st.button("🔄 Muat ulang data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# Konten Halaman Utama
# ---------------------------------------------------------------------------
st.title("⚡ Smart Factory Energy Management")
st.markdown(
    """
    Selamat datang di platform **Smart Factory Energy Management**.
    Aplikasi ini memonitor penggunaan daya listrik, memprediksi kebutuhan konsumsi energi,
    serta mendeteksi potensi pemborosan di lini produksi pabrik.
    """
)

st.markdown("---")
st.subheader("📌 Navigasi Menu")
st.markdown(
    """
    Gunakan menu navigasi pada sidebar untuk mengakses modul-modul berikut:
    - **📊 Overview**: Ringkasan konsumsi energi per lini produksi, estimasi biaya, dan metrik pabrik.
    - **🏭 Detail Mesin**: Analisis mendalam profil daya (`kW`), energi (`kWh`), tegangan, dan arus per mesin.
    - **📈 Forecast**: Proyeksi konsumsi listrik ke depan menggunakan model machine learning.
    - **⚠️ Waste Alerts**: Deteksi anomali operasional dan peringatan pemborosan energi listrik.
    """
)

if not is_connected:
    st.warning(
        "⚠️ Backend API pada `localhost:8000` belum terdeteksi aktif. "
        "Pastikan backend FastAPI sudah berjalan untuk mendapatkan data aktual.",
        icon="⚠️"
    )
