import sys
from pathlib import Path
import streamlit as st

# Setup sys.path agar impor modul api_client dan ui berjalan mulus
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
for path in (str(CURRENT_DIR), str(ROOT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from frontend.api_client import check_api
    from frontend.ui import apply_theme
except ImportError:
    from api_client import check_api
    from ui import apply_theme

# ---------------------------------------------------------------------------
# Konfigurasi Halaman Utama
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Terapkan Tema Elegan Dark Glassmorphism
apply_theme()

# ---------------------------------------------------------------------------
# Sidebar: Status API & Tombol Muat Ulang
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 10px 0 16px 0;">
            <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #64748b; font-weight: 700;">
                Platform Monitoring
            </div>
            <div style="font-size: 1.1rem; font-weight: 800; color: #f8fafc; display: flex; align-items: center; gap: 8px;">
                <span>⚡ Smart Energy</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 🔌 Koneksi API")
    is_connected = check_api()
    if is_connected:
        st.markdown(
            """
            <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 8px; padding: 10px 14px; display: flex; align-items: center; gap: 10px;">
                <span style="height: 10px; width: 10px; background-color: #10b981; border-radius: 50%; box-shadow: 0 0 8px #10b981; display: inline-block;"></span>
                <span style="color: #6ee7b7; font-weight: 600; font-size: 0.88rem;">Backend Terhubung</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 8px; padding: 10px 14px; display: flex; align-items: center; gap: 10px;">
                <span style="height: 10px; width: 10px; background-color: #ef4444; border-radius: 50%; box-shadow: 0 0 8px #ef4444; display: inline-block;"></span>
                <span style="color: #fca5a5; font-weight: 600; font-size: 0.88rem;">Backend Terputus</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Muat ulang data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        """
        <div style="margin-top: 2rem; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); font-size: 0.76rem; color: #64748b;">
            💡 <b>Info Sistem</b>: Data sensor dikumpulkan real-time via REST API & dianalisis dengan model ML.
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Konten Halaman Utama: Hero Banner & Module Grid
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="background: linear-gradient(135deg, rgba(14, 165, 233, 0.12) 0%, rgba(99, 102, 241, 0.08) 100%); 
                border: 1px solid rgba(56, 189, 248, 0.25); 
                border-radius: 16px; 
                padding: 32px 36px; 
                margin-bottom: 24px;
                backdrop-filter: blur(14px);
                box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.3);">
        <div style="display: inline-block; background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 4px 12px; border-radius: 20px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.06em; margin-bottom: 12px;">
            SMART MANUFACTURING INTELLIGENCE
        </div>
        <h1 style="color: #ffffff; font-size: 2.3rem; font-weight: 800; margin: 0 0 12px 0; letter-spacing: -0.02em;">
            ⚡ Smart Factory Energy Management
        </h1>
        <p style="color: #94a3b8; font-size: 1.05rem; margin: 0; max-width: 820px; line-height: 1.6;">
            Platform komprehensif untuk pengawasan efisiensi kelistrikan pabrik cerdas:
            pelacakan konsumsi energi real-time, peramalan beban daya presisi, dan deteksi dini pemborosan operasional.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not is_connected:
    st.warning(
        "⚠️ **Backend API pada `localhost:8000` belum terdeteksi aktif.** "
        "Jalankan backend FastAPI terlebih dahulu untuk mendapatkan data sensor langsung dari MongoDB.",
        icon="⚠️",
    )

st.markdown("### 📌 Fitur & Navigasi Modul")

c1, c2 = st.columns(2)
with c1:
    st.markdown(
        """
        <div class="glass-card" style="border-top: 2px solid #38bdf8;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                <span style="font-size: 1.5rem;">📊</span>
                <h3 style="color: #f8fafc; margin: 0; font-size: 1.2rem; font-weight: 700;">1. Overview Pabrik</h3>
            </div>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px;">
                Agregasi total konsumsi energi (kWh), estimasi tagihan biaya listrik (Rp 1.500/kWh), 
                distribusi penggunaan per lini produksi, dan tren harian seluruh mesin.
            </p>
            <span style="color: #38bdf8; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: <b>Overview</b> →</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="glass-card" style="border-top: 2px solid #818cf8;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                <span style="font-size: 1.5rem;">📈</span>
                <h3 style="color: #f8fafc; margin: 0; font-size: 1.2rem; font-weight: 700;">3. Forecast Energi</h3>
            </div>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px;">
                Model prediktif machine learning untuk peramalan beban konsumsi listrik (24–72 jam ke depan) 
                guna perencanaan kapasitas dan manajemen beban puncak.
            </p>
            <span style="color: #818cf8; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: <b>Forecast</b> →</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        """
        <div class="glass-card" style="border-top: 2px solid #34d399;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                <span style="font-size: 1.5rem;">🏭</span>
                <h3 style="color: #f8fafc; margin: 0; font-size: 1.2rem; font-weight: 700;">2. Detail Mesin</h3>
            </div>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px;">
                Inspeksi time-series daya (kW) dan energi (kWh) spesifik per mesin. Dilengkapi penanda visual 
                berwarna untuk status operasional aktif (Running) dan kondisi tanpa beban (Idle).
            </p>
            <span style="color: #34d399; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: <b>Detail Mesin</b> →</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="glass-card" style="border-top: 2px solid #f59e0b;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                <span style="font-size: 1.5rem;">⚠️</span>
                <h3 style="color: #f8fafc; margin: 0; font-size: 1.2rem; font-weight: 700;">4. Waste Alerts</h3>
            </div>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px;">
                Sistem deteksi anomali operasional: pemborosan daya saat idle, konsumsi melampaui rated power, 
                serta lonjakan daya saat jam beban puncak pabrik.
            </p>
            <span style="color: #f59e0b; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: <b>Waste Alerts</b> →</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
