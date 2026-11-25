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
    page_title="Smart Energy Factory",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Terapkan tema global
apply_theme()


# ---------------------------------------------------------------------------
# Sidebar: Logo, Brand Header, Status API & Tombol Muat Ulang
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        "".join([
            '<div style="padding: 6px 4px 14px 4px; margin-bottom: 8px;">',
            '<div style="display: flex; align-items: center; gap: 10px;">',
            '<div style="width: 32px; height: 32px; background: #1D6FF2; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: #FFFFFF; font-weight: 800; font-size: 15px;">',
            '⚡',
            '</div>',
            '<div>',
            '<div style="font-size: 1.0rem; font-weight: 800; color: #111827; line-height: 1.2; letter-spacing:-0.02em;">Smart Energy Factory</div>',
            '<div style="font-size: 0.72rem; color: #6B7280; font-weight: 500;">Monitoring via REST API</div>',
            '</div>',
            '</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size: 0.75rem; font-weight: 600; color: #6B7280; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;">Koneksi API</div>',
        unsafe_allow_html=True,
    )

    is_connected = check_api()
    if is_connected:
        st.markdown(
            "".join([
                '<div style="background: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 8px; padding: 9px 12px; display: flex; align-items: center; gap: 9px;">',
                '<span style="height: 8px; width: 8px; background-color: #16A34A; border-radius: 50%; display: inline-block;"></span>',
                '<span style="color: #166534; font-weight: 600; font-size: 0.82rem;">Backend Terhubung</span>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "".join([
                '<div style="background: #FEF2F2; border: 1px solid #FEE2E2; border-radius: 8px; padding: 9px 12px; display: flex; align-items: center; gap: 9px;">',
                '<span style="height: 8px; width: 8px; background-color: #EF4444; border-radius: 50%; display: inline-block;"></span>',
                '<span style="color: #991B1B; font-weight: 600; font-size: 0.82rem;">Backend Terputus</span>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin: 1rem 0;'></div>", unsafe_allow_html=True)
    if st.button("Muat Ulang Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        "".join([
            '<div class="sidebar-info-box">',
            '<div style="font-weight: 600; color: #111827; margin-bottom: 3px;">Koneksi Backend</div>',
            '<div>Data telemetri 12 mesin pabrik terhubung via REST API.</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Fungsi Render Halaman Beranda (Landing SaaS Style)
# ---------------------------------------------------------------------------
def render_beranda():
    st.markdown(
        "".join([
            '<div style="background: #FFFFFF; border: 1px solid #E5E8EF; border-radius: 14px; padding: 28px 32px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">',
            '<div style="display: inline-block; background: #DBEAFE; color: #1E40AF; padding: 3px 10px; border-radius: 16px; font-size: 0.74rem; font-weight: 600; letter-spacing: 0.04em; margin-bottom: 10px;">',
            'SISTEM MONITORING ENERGI',
            '</div>',
            '<h1 style="color: #111827; font-size: 1.85rem; font-weight: 700; margin: 0 0 8px 0; letter-spacing: -0.02em;">',
            'Smart Factory Energy Management',
            '</h1>',
            '<p style="color: #6B7280; font-size: 0.95rem; margin: 0; max-width: 820px; line-height: 1.55;">',
            'Platform manajemen energi pabrik cerdas: pemantauan konsumsi daya via REST API, '
            'peramalan beban listrik multi-horizon, dan deteksi anomali pemborosan operasional.',
            '</p>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

    if not is_connected:
        st.warning(
            "Backend API pada `localhost:8000` belum aktif. "
            "Pastikan uvicorn berjalan untuk memuat data sensor aktual dari database.",
            icon="⚠️",
        )

    st.markdown(
        '<div style="font-weight: 700; font-size: 1.15rem; color: #111827; margin-bottom: 14px;">Modul Operasional</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            "".join([
                '<div style="background: #FFFFFF; border: 1px solid #E5E8EF; border-left: 4px solid #1D6FF2; border-radius: 12px; padding: 20px 22px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">',
                '<h3 style="color: #111827; margin: 0 0 6px 0; font-size: 1.05rem; font-weight: 700;">Overview Pabrik</h3>',
                '<p style="color: #6B7280; font-size: 0.88rem; line-height: 1.5; margin-bottom: 12px;">',
                'Agregasi total konsumsi energi (kWh), estimasi tagihan listrik, sebaran beban per lini produksi, dan analisis profil daya total.',
                '</p>',
                '<span style="color: #1D6FF2; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: Overview &rarr;</span>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

        st.markdown(
            "".join([
                '<div style="background: #FFFFFF; border: 1px solid #E5E8EF; border-left: 4px solid #F59E0B; border-radius: 12px; padding: 20px 22px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">',
                '<h3 style="color: #111827; margin: 0 0 6px 0; font-size: 1.05rem; font-weight: 700;">Forecast Energi</h3>',
                '<p style="color: #6B6259; font-size: 0.88rem; line-height: 1.5; margin-bottom: 12px;">',
                'Proyeksi beban konsumsi daya listrik 24 jam hingga 7 hari (168 jam) ke depan menggunakan model inferensi langsung XGBoost.',
                '</p>',
                '<span style="color: #1D6FF2; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: Forecast &rarr;</span>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            "".join([
                '<div style="background: #FFFFFF; border: 1px solid #E5E8EF; border-left: 4px solid #10B981; border-radius: 12px; padding: 20px 22px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">',
                '<h3 style="color: #111827; margin: 0 0 6px 0; font-size: 1.05rem; font-weight: 700;">Detail Mesin</h3>',
                '<p style="color: #6B6259; font-size: 0.88rem; line-height: 1.5; margin-bottom: 12px;">',
                'Pemantauan telemetri per mesin (daya kW, energi kWh, status Running/Idle/Off), durasi akumulasi jam kerja, dan tabel riwayat sensor.',
                '</p>',
                '<span style="color: #1D6FF2; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: Detail Mesin &rarr;</span>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

        st.markdown(
            "".join([
                '<div style="background: #FFFFFF; border: 1px solid #E5E8EF; border-left: 4px solid #EF4444; border-radius: 12px; padding: 20px 22px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">',
                '<h3 style="color: #111827; margin: 0 0 6px 0; font-size: 1.05rem; font-weight: 700;">Waste Alerts</h3>',
                '<p style="color: #6B6259; font-size: 0.88rem; line-height: 1.5; margin-bottom: 12px;">',
                'Deteksi anomali operasional: pemborosan standby (idle waste), beban berlebih di atas rated power, dan lonjakan jam beban puncak.',
                '</p>',
                '<span style="color: #1D6FF2; font-size: 0.82rem; font-weight: 600;">Akses via menu sidebar: Waste Alerts &rarr;</span>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Konfigurasi Navigasi Multi-Page Modern (st.navigation) dengan Grup Menu
# ---------------------------------------------------------------------------
PAGES_DIR = CURRENT_DIR / "pages"

pages = {
    "NAVIGASI": [
        st.Page(render_beranda, title="Beranda", icon=":material/home:", default=True),
    ],
    "MONITORING": [
        st.Page(str(PAGES_DIR / "1_Overview.py"), title="Overview", icon=":material/dashboard:"),
        st.Page(str(PAGES_DIR / "2_Detail_Mesin.py"), title="Detail Mesin", icon=":material/precision_manufacturing:"),
    ],
    "ANALISIS": [
        st.Page(str(PAGES_DIR / "3_Forecast.py"), title="Forecast", icon=":material/trending_up:"),
        st.Page(str(PAGES_DIR / "4_Waste_Alerts.py"), title="Waste Alerts", icon=":material/warning:"),
    ],
}

pg = st.navigation(pages, position="sidebar")
pg.run()
