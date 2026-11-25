"""
frontend/ui.py
==============
Modul utilitas UI & Styling untuk Smart Energy Factory.
Design System SaaS Admin:
- Skema warna: Primer Biru #1D6FF2, Latar Halaman Abu Muda #F3F5F9, Kartu Putih #FFFFFF
- Border tipis bersih #E5E8EF, Radius 12-14px, Tipografi Inter
- Sidebar modern dengan indikator aktif solid #1D6FF2
- Badge pills (hijau, amber, merah, abu, biru) dengan kontras tinggi
- Chart Plotly bergaris halus spline, gridline tipis, fill gradien biru/amber
"""

from typing import Optional, List, Dict, Any
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Palet Warna Utama (SaaS Admin Klasik)
# ---------------------------------------------------------------------------
COLOR_PRIMARY = "#1D6FF2"         # Biru solid utama (active sidebar, tombol, garis aktual)
COLOR_PAGE_BG = "#F3F5F9"         # Background aplikasi abu muda sejuk
COLOR_CARD_BG = "#FFFFFF"         # Background kartu putih bersih
COLOR_CARD_BORDER = "#E5E8EF"     # Border tipis kartu & pembatas
COLOR_TEXT_PRIMARY = "#111827"    # Teks utama gelap terbaca
COLOR_TEXT_SECONDARY = "#6B7280"  # Teks label & deskripsi abu-abu

# Status Operasional Mesin (Konsisten di semua halaman)
COLOR_STATUS_RUNNING = "#16A34A"  # Hijau (Running)
COLOR_STATUS_IDLE = "#F59E0B"     # Amber / Kuning Hangat (Standby / Idle)
COLOR_STATUS_OFF = "#9CA3AF"      # Abu-abu Netral (Off / Mati)
COLOR_STATUS_DANGER = "#EF4444"   # Merah Bahaya / High Anomaly

# Palet Badge Pills (Background pucat + Teks solid tegas)
BADGE_BG_GREEN = "#DCFCE7"
BADGE_TXT_GREEN = "#166534"
BADGE_BG_AMBER = "#FEF3C7"
BADGE_TXT_AMBER = "#92400E"
BADGE_BG_RED = "#FEE2E2"
BADGE_TXT_RED = "#991B1B"
BADGE_BG_GREY = "#F3F4F6"
BADGE_TXT_GREY = "#4B5563"
BADGE_BG_BLUE = "#DBEAFE"
BADGE_TXT_BLUE = "#1E40AF"


# ---------------------------------------------------------------------------
# Helper Pemformat Angka & Mata Uang Gaya Indonesia (Sentralisasi)
# ---------------------------------------------------------------------------
def format_id_num(val: float, decimals: int = 1) -> str:
    """Format angka ribuan titik dan desimal koma gaya Indonesia (misal: 3.569,5)."""
    s = f"{val:,.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def format_id_currency(val: float) -> str:
    """Format mata uang Rupiah bulat gaya Indonesia (misal: Rp 1.500)."""
    s = f"{round(val):,}"
    return f"Rp {s.replace(',', '.')}"


# ---------------------------------------------------------------------------
# Injeksi CSS Kustom: Dentexa Design System
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
    /* Google Font: Inter (SaaS Admin Standar) */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"], [data-testid="stAppViewContainer"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }

    /* Sembunyikan elemen bawaan yang tidak diperlukan */
    .stDeployButton, footer, #MainMenu {
        display: none !important;
        visibility: hidden !important;
    }

    /* Header aplikasi transparan agar menyatu dengan background */
    [data-testid="stHeader"] {
        background-color: transparent !important;
        z-index: 100 !important;
    }

    /* Tombol Buka/Tutup Sidebar SELALU terlihat */
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="stSidebarCollapseButton"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        z-index: 1000 !important;
        color: #111827 !important;
    }

    [data-testid="stSidebarCollapsedControl"] button,
    [data-testid="stSidebarCollapseButton"] button {
        color: #111827 !important;
        background-color: #FFFFFF !important;
        border: 1px solid #E5E8EF !important;
        border-radius: 8px !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
    }

    [data-testid="stSidebarCollapsedControl"] svg,
    [data-testid="stSidebarCollapseButton"] svg {
        fill: #111827 !important;
        color: #111827 !important;
    }

    /* Background Utama Aplikasi */
    .stApp {
        background-color: #F3F5F9 !important;
        color: #111827 !important;
    }

    /* Sidebar Styling: Background #F8F9FC dengan garis batas kanan bersih */
    [data-testid="stSidebar"] {
        background-color: #F8F9FC !important;
        border-right: 1px solid #E5E8EF !important;
    }

    [data-testid="stSidebar"] [data-testid="stSidebarNav"] {
        padding-top: 0.5rem;
    }

    /* Menu Sidebar Items */
    [data-testid="stSidebarNav"] a {
        border-radius: 8px !important;
        margin: 3px 12px !important;
        padding: 8px 14px !important;
        transition: all 0.15s ease-in-out !important;
        color: #6B7280 !important;
        font-weight: 500 !important;
        font-size: 0.88rem !important;
        border-left: none !important;
    }

    [data-testid="stSidebarNav"] a:hover {
        background-color: #EEF2F6 !important;
        color: #111827 !important;
    }

    /* Item Aktif Sidebar: Biru Solid #1D6FF2 dengan teks putih */
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background-color: #1D6FF2 !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        box-shadow: 0 2px 6px rgba(29, 111, 242, 0.25) !important;
    }

    [data-testid="stSidebarNav"] a[aria-current="page"] span,
    [data-testid="stSidebarNav"] a[aria-current="page"] svg {
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
    }

    /* Kartu Container Bawaan st.container(border=True) */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E8EF !important;
        border-radius: 14px !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
        padding: 16px 18px !important;
    }

    /* Tombol Utama (Primary Button) */
    .stButton > button {
        background-color: #1D6FF2 !important;
        color: #FFFFFF !important;
        border: 1px solid #1D6FF2 !important;
        border-radius: 8px !important;
        padding: 8px 18px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        box-shadow: 0 1px 2px rgba(29, 111, 242, 0.15) !important;
        transition: all 0.15s ease-in-out !important;
    }

    .stButton > button:hover {
        background-color: #1558C0 !important;
        border-color: #1558C0 !important;
        box-shadow: 0 3px 8px rgba(29, 111, 242, 0.25) !important;
    }

    /* Tombol Unduh / Secondary Button */
    [data-testid="stDownloadButton"] > button {
        background-color: #FFFFFF !important;
        color: #111827 !important;
        border: 1px solid #E5E8EF !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.86rem !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;
        transition: all 0.15s ease !important;
    }

    [data-testid="stDownloadButton"] > button:hover {
        background-color: #F9FAFB !important;
        border-color: #D1D5DB !important;
        color: #1D6FF2 !important;
    }

    /* Input & Select Box */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    [data-testid="stDateInput"] input {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E8EF !important;
        border-radius: 8px !important;
        color: #111827 !important;
        font-size: 0.88rem !important;
    }

    div[data-baseweb="select"] > div:hover,
    div[data-baseweb="input"] > div:hover,
    [data-testid="stDateInput"] input:hover {
        border-color: #1D6FF2 !important;
    }

    /* Segmented Control & Pills: abu muda dengan item aktif putih bershadow */
    [data-testid="stSegmentedControl"], [data-testid="stPills"] {
        background-color: #F3F4F6 !important;
        padding: 3px !important;
        border-radius: 10px !important;
        border: 1px solid #E5E8EF !important;
    }

    [data-testid="stSegmentedControl"] button, [data-testid="stPills"] button {
        border-radius: 8px !important;
        border: none !important;
        background: transparent !important;
        color: #6B7280 !important;
        font-weight: 500 !important;
        font-size: 0.84rem !important;
        padding: 5px 14px !important;
        transition: all 0.15s ease !important;
    }

    [data-testid="stSegmentedControl"] button[aria-selected="true"],
    [data-testid="stPills"] button[aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #111827 !important;
        border: 1px solid #E5E8EF !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06) !important;
        font-weight: 600 !important;
    }

    /* Styling Tabs: Border Bawah Biru Aktif */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent !important;
        border-bottom: 1px solid #E5E8EF !important;
        padding-bottom: 0px !important;
    }

    [data-testid="stTabs"] [data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        color: #6B7280 !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        padding: 8px 16px !important;
        border-radius: 0 !important;
    }

    [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
        color: #1D6FF2 !important;
        border-bottom: 2px solid #1D6FF2 !important;
        font-weight: 600 !important;
    }

    /* Kartu KPI */
    .kpi-card-dentexa, .kpi-card-velora {
        background-color: #FFFFFF;
        border: 1px solid #E5E8EF;
        border-radius: 14px;
        padding: 18px 20px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        position: relative;
    }

    .kpi-card-dentexa .kpi-label, .kpi-card-velora .kpi-label {
        font-size: 0.76rem;
        font-weight: 600;
        color: #6B7280;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }

    .kpi-card-dentexa .kpi-val, .kpi-card-velora .kpi-val {
        font-size: 1.85rem;
        font-weight: 700;
        color: #111827;
        letter-spacing: -0.02em;
        line-height: 1.15;
    }

    .kpi-card-dentexa .kpi-unit, .kpi-card-velora .kpi-unit {
        font-size: 0.95rem;
        font-weight: 500;
        color: #6B7280;
        margin-left: 4px;
    }

    .kpi-card-dentexa .kpi-sub, .kpi-card-velora .kpi-sub {
        margin-top: 8px;
        font-size: 0.8rem;
        color: #6B7280;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* Badge Pills */
    .badge-pill-green {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background-color: #DCFCE7 !important;
        color: #166534 !important;
        border-radius: 20px;
        padding: 2.5px 9px;
        font-size: 0.74rem;
        font-weight: 600;
    }

    .badge-pill-amber, .badge-pill-orange {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background-color: #FEF3C7 !important;
        color: #92400E !important;
        border-radius: 20px;
        padding: 2.5px 9px;
        font-size: 0.74rem;
        font-weight: 600;
    }

    .badge-pill-red {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background-color: #FEE2E2 !important;
        color: #991B1B !important;
        border-radius: 20px;
        padding: 2.5px 9px;
        font-size: 0.74rem;
        font-weight: 600;
    }

    .badge-pill-grey {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background-color: #F3F4F6 !important;
        color: #4B5563 !important;
        border-radius: 20px;
        padding: 2.5px 9px;
        font-size: 0.74rem;
        font-weight: 600;
    }

    .badge-pill-blue {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background-color: #DBEAFE !important;
        color: #1E40AF !important;
        border-radius: 20px;
        padding: 2.5px 9px;
        font-size: 0.74rem;
        font-weight: 600;
    }

    .badge-mock {
        display: inline-block;
        background-color: #FEF3C7;
        color: #92400E;
        border: 1px solid #FDE68A;
        border-radius: 6px;
        padding: 2px 7px;
        font-size: 0.74rem;
        font-weight: 600;
    }

    /* Headings */
    h1, h2, h3, h4, h5, h6 {
        color: #111827 !important;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    p, span, label, .stMarkdown {
        color: #111827;
    }

    .stCaption, [data-testid="stCaptionContainer"] {
        color: #6B7280 !important;
        font-size: 0.8rem !important;
    }

    /* Tabel Data (Treatments Style) */
    .dentexa-table-container {
        background-color: #FFFFFF;
        border: 1px solid #E5E8EF;
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    }

    .dentexa-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        text-align: left;
    }

    .dentexa-table thead tr {
        background-color: #F8F9FC;
        border-bottom: 1px solid #E5E8EF;
        color: #6B7280;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .dentexa-table th {
        padding: 10px 14px;
    }

    .dentexa-table td {
        padding: 12px 14px;
        border-bottom: 1px solid #F3F4F6;
        color: #111827;
        vertical-align: top;
    }

    .dentexa-table tbody tr:hover {
        background-color: #F9FAFB;
    }

    /* Sidebar info box */
    .sidebar-info-box {
        margin-top: 1.5rem;
        padding: 12px 14px;
        background-color: #FFFFFF;
        border-radius: 10px;
        border: 1px solid #E5E8EF;
        font-size: 0.78rem;
        color: #6B7280;
        line-height: 1.45;
    }
</style>
"""


def apply_theme():
    """Terapkan CSS kustom Smart Energy Factory ke halaman aktif."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Konfigurasi Styling Plotly (Clean & Modern)
# ---------------------------------------------------------------------------
def style_plotly_fig(fig: go.Figure, height: int = 360) -> go.Figure:
    """Modifikasi figure Plotly dengan palet warna bersih, tipis, terbaca."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        font=dict(family="Inter, -apple-system, sans-serif", color="#111827", size=12),
        height=height,
        margin=dict(l=20, r=20, t=30, b=30),
        xaxis=dict(
            gridcolor="rgba(107, 114, 128, 0.10)",
            gridwidth=1,
            griddash="dot",
            linecolor="rgba(107, 114, 128, 0.20)",
            zeroline=False,
            tickfont=dict(size=11, color="#6B7280"),
        ),
        yaxis=dict(
            gridcolor="rgba(107, 114, 128, 0.10)",
            gridwidth=1,
            griddash="dot",
            linecolor="rgba(107, 114, 128, 0.20)",
            zeroline=False,
            tickfont=dict(size=11, color="#6B7280"),
        ),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor="#E5E8EF",
            font_size=12,
            font_color="#111827",
            font_family="Inter, sans-serif",
        ),
    )
    return fig


# ---------------------------------------------------------------------------
# Komponen Donut Chart (Gaya 'Expenses' SaaS Admin)
# ---------------------------------------------------------------------------
def create_status_donut(
    run_pct: float,
    idle_pct: float,
    off_pct: float,
    run_kwh: float,
    idle_kwh: float,
    off_kwh: float,
    total_label: str = "Total Energi",
    total_val_str: Optional[str] = None,
    height: int = 215,
) -> go.Figure:
    """
    Membuat Donut Chart sebaran status operasional (Running, Idle, Off)
    dengan cutout di tengah berisi total nilai dan legend di kanan.
    Hole = 0.76 agar anotasi teks tidak menimpa cincin.
    """
    labels = ["Running", "Idle", "Off"]
    values = [run_kwh, idle_kwh, off_kwh]
    colors = [COLOR_STATUS_RUNNING, COLOR_STATUS_IDLE, COLOR_STATUS_OFF]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.76,
            domain={"x": [0.0, 0.62], "y": [0.0, 1.0]},
            marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2.5)),
            textinfo="none",
            hoverinfo="label+percent+value",
            hovertemplate="<b>%{label}</b><br>Energi: %{value:,.1f} kWh<br>Porsi: <b>%{percent:.1%}</b><extra></extra>",
            sort=False,
            direction="clockwise",
        )
    )

    # Anotasi dua baris di tengah lubang: label abu di atas, angka bold di bawah
    if total_val_str:
        fig.add_annotation(
            text=f"<span style='font-size:9px;color:#6B7280;font-weight:600;text-transform:uppercase;'>{total_label}</span><br><b style='font-size:13px;color:#111827;font-weight:800;'>{total_val_str}</b>",
            x=0.31,
            y=0.5,
            showarrow=False,
            align="center",
            font=dict(family="Inter, sans-serif"),
            xanchor="center",
            yanchor="middle",
        )

    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=0.65,
            font=dict(size=11, color="#111827", family="Inter, sans-serif"),
            itemwidth=30,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=5, r=5, t=5, b=5),
    )
    return fig


def render_dentexa_topbar(page_title: str = "Dashboard", welcome_sub: str = "Smart Energy Factory"):
    """
    Merender Topbar Header SaaS Admin dengan judul halaman dan info koneksi.
    Hanya menampilkan judul + sub-info berbasis data (tanpa elemen dekoratif).
    """
    topbar_html = "".join([
        '<div style="border-bottom:1px solid #E5E8EF; margin-bottom:20px; padding-bottom:14px;">',
        '  <div style="display:flex; justify-content:space-between; align-items:baseline;">',
        f'    <span style="font-size:1.5rem; font-weight:700; color:#111827; letter-spacing:-0.02em;">{page_title}</span>',
        f'    <span style="font-size:0.8rem; color:#6B7280; font-weight:500;">{welcome_sub}</span>',
        '  </div>',
        '</div>',
    ])
    st.markdown(topbar_html, unsafe_allow_html=True)


def create_type_donut(type_counts: Dict[str, int], height: int = 260) -> go.Figure:
    """
    Membuat Donut Chart sebaran kategori anomali/pemborosan.
    """
    labels = [k.replace("_", " ").title() for k in type_counts.keys()]
    values = list(type_counts.values())
    colors = ["#1D6FF2", "#F59E0B", "#6366F1", "#10B981", "#EC4899", "#8B5CF6"]
    slice_colors = [colors[i % len(colors)] for i in range(len(labels))]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.66,
            marker=dict(colors=slice_colors, line=dict(color="#FFFFFF", width=2)),
            textinfo="none",
            hovertemplate="<b>%{label}</b><br>Jumlah: %{value:,} kasus (%{percent:.1%})<extra></extra>",
            sort=False,
            direction="clockwise",
        )
    )

    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.02,
            font=dict(size=11, color="#6B7280"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


# ---------------------------------------------------------------------------
# Komponen Radial Gauge (Biru #1D6FF2 + Track Abu Muda #E5E8EF)
# ---------------------------------------------------------------------------
def create_radial_power_gauge(
    val: float,
    rated_kw: float,
    min_val: float,
    max_val: float,
    avg_val: float,
    title: str = "Daya Total Jam Terakhir",
    unit: str = "kW",
    height: int = 195,
) -> go.Figure:
    """
    Membuat Radial Gauge dengan gaya modern:
    - Dial melingkar biru #1D6FF2 dengan track abu muda #E5E8EF
    - Skala 0 sampai rated_kw
    """
    upper_bound = rated_kw if rated_kw > 0 else max(max_val * 1.1, 10.0)

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=round(val, 2),
            domain={"x": [0.05, 0.95], "y": [0.15, 0.95]},
            title={
                "text": f"<span style='font-size:11px;color:#6B7280;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;'>{title}</span>",
                "font": {"size": 12, "family": "Inter, sans-serif"},
            },
            number={
                "suffix": f" <span style='font-size:13px;color:#6B7280;font-weight:500;'>{unit}</span>",
                "font": {"size": 32, "color": "#111827", "family": "Inter, sans-serif"},
            },
            gauge={
                "axis": {
                    "range": [0, upper_bound],
                    "tickwidth": 1,
                    "tickcolor": "#D1D5DB",
                    "ticklen": 5,
                    "nticks": 7,
                    "tickfont": {"size": 10, "color": "#6B7280"},
                },
                "bar": {"color": COLOR_PRIMARY, "thickness": 0.15},
                "bgcolor": "#F3F4F6",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, upper_bound], "color": "#F3F4F6"},
                ],
            },
        )
    )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=15, r=15, t=20, b=10),
    )
    return fig
