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

# Terapkan Tema Warm Light secara global
apply_theme()


# ---------------------------------------------------------------------------
# Sidebar: Status API & Tombol Muat Ulang
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 10px 0 16px 0;">
            <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #6B6259; font-weight: 700;">
                // PLATFORM MONITORING
            </div>
            <div style="font-size: 1.1rem; font-weight: 800; color: #1F1A17; display: flex; align-items: center; gap: 8px;">
                <span>⚡ Smart Energy</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Koneksi API")
    is_connected = check_api()
    if is_connected:
        st.markdown(
            """
            <div style="background: rgba(22, 163, 74, 0.08); border: 1px solid rgba(22, 163, 74, 0.30); border-radius: 8px; padding: 10px 14px; display: flex; align-items: center; gap: 10px;">
                <span style="height: 10px; width: 10px; background-color: #16A34A; border-radius: 50%; box-shadow: 0 0 6px rgba(22,163,74,0.4); display: inline-block;"></span>
                <span style="color: #16A34A; font-weight: 600; font-size: 0.88rem;">Backend Terhubung</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="background: rgba(220, 38, 38, 0.08); border: 1px solid rgba(220, 38, 38, 0.30); border-radius: 8px; padding: 10px 14px; display: flex; align-items: center; gap: 10px;">
                <span style="height: 10px; width: 10px; background-color: #DC2626; border-radius: 50%; box-shadow: 0 0 6px rgba(220,38,38,0.4); display: inline-block;"></span>
                <span style="color: #DC2626; font-weight: 600; font-size: 0.88rem;">Backend Terputus</span>
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
        <div style="margin-top: 2rem; padding: 12px; background: rgba(255,244,224,0.5); border-radius: 8px; border: 1px solid #EFE5D6; font-size: 0.76rem; color: #6B6259;">
            💡 <b>Info Sistem</b>: Data sensor dikumpulkan real-time via REST API & dianalisis dengan model ML.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Fungsi Render Halaman Beranda (Landing)
# ---------------------------------------------------------------------------
def render_beranda():
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, rgba(232, 89, 12, 0.06) 0%, rgba(242, 194, 48, 0.06) 100%); 
                    border: 1px solid #EFE5D6; 
                    border-radius: 16px; 
                    padding: 32px 36px; 
                    margin-bottom: 24px;
                    box-shadow: 0 4px 16px -4px rgba(31, 26, 23, 0.06);">
            <div style="display: inline-block; background: rgba(232, 89, 12, 0.10); color: #E8590C; padding: 4px 12px; border-radius: 20px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.06em; margin-bottom: 12px;">
                // SMART MANUFACTURING INTELLIGENCE
            </div>
            <h1 style="color: #1F1A17; font-size: 2.3rem; font-weight: 800; margin: 0 0 12px 0; letter-spacing: -0.02em;">
                ⚡ Smart Factory Energy Management
            </h1>
            <p style="color: #6B6259; font-size: 1.05rem; margin: 0; max-width: 820px; line-height: 1.6;">
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

    st.markdown("<h3 style='color: #1F1A17; font-weight: 800;'>📌 Fitur & Navigasi Modul</h3>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            """
            <div class="glass-card" style="border-top: 2px solid #E8590C;">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                    <h3 style="color: #1F1A17; margin: 0; font-size: 1.2rem; font-weight: 700;">1. Overview Pabrik</h3>
                </div>
                <p style="color: #6B6259; font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px;">
                    Agregasi total konsumsi energi (kWh), estimasi tagihan biaya listrik (Rp 1.500/kWh), 
                    distribusi penggunaan per lini produksi, dan tren harian seluruh mesin.
                </p>
                <span style="color: #E8590C; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: <b>Overview</b> →</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="glass-card" style="border-top: 2px solid #F2C230;">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                    <h3 style="color: #1F1A17; margin: 0; font-size: 1.2rem; font-weight: 700;">3. Forecast Energi</h3>
                </div>
                <p style="color: #6B6259; font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px;">
                    Model prediktif machine learning untuk peramalan beban konsumsi listrik (24–72 jam ke depan) 
                    guna perencanaan kapasitas dan manajemen beban puncak.
                </p>
                <span style="color: #F2C230; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: <b>Forecast</b> →</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            """
            <div class="glass-card" style="border-top: 2px solid #16A34A;">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                    <h3 style="color: #1F1A17; margin: 0; font-size: 1.2rem; font-weight: 700;">2. Detail Mesin</h3>
                </div>
                <p style="color: #6B6259; font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px;">
                    Inspeksi time-series daya (kW) dan energi (kWh) spesifik per mesin. Dilengkapi penanda visual 
                    berwarna untuk status operasional aktif (Running) dan kondisi tanpa beban (Idle).
                </p>
                <span style="color: #16A34A; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: <b>Detail Mesin</b> →</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="glass-card" style="border-top: 2px solid #E8590C;">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                    <h3 style="color: #1F1A17; margin: 0; font-size: 1.2rem; font-weight: 700;">4. Waste Alerts</h3>
                </div>
                <p style="color: #6B6259; font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px;">
                    Sistem deteksi anomali operasional: pemborosan daya saat idle, konsumsi melampaui rated power, 
                    serta lonjakan daya saat jam beban puncak pabrik.
                </p>
                <span style="color: #E8590C; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: <b>Waste Alerts</b> →</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Konfigurasi Navigasi Multi-Page Modern (st.navigation)
# Mengganti label menu default "app" menjadi "Beranda" secara bersih
# ---------------------------------------------------------------------------
PAGES_DIR = CURRENT_DIR / "pages"

pages = [
    st.Page(render_beranda, title="Beranda", icon=":material/home:", default=True),
    st.Page(str(PAGES_DIR / "1_Overview.py"), title="Overview", icon=":material/dashboard:"),
    st.Page(str(PAGES_DIR / "2_Detail_Mesin.py"), title="Detail Mesin", icon=":material/precision_manufacturing:"),
    st.Page(str(PAGES_DIR / "3_Forecast.py"), title="Forecast", icon=":material/trending_up:"),
    st.Page(str(PAGES_DIR / "4_Waste_Alerts.py"), title="Waste Alerts", icon=":material/warning:"),
]

pg = st.navigation(pages, position="sidebar")
pg.run()
