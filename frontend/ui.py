"""
frontend/ui.py
==============
Modul utilitas UI & Styling untuk Smart Factory Energy Management.
Menyediakan CSS injection modern (Warm Light Theme ala Velora / Solar Energy Dashboard),
konfigurasi tema Plotly terang dan bersih, serta komponen visual premium seperti
radial gauge dial, circular progress donut, panel heatmap, dan custom metric cards.
"""

import streamlit as st
import plotly.graph_objects as go
from typing import Optional, List, Dict, Any

# ---------------------------------------------------------------------------
# Palet Warna Tema Terang Hangat
# ---------------------------------------------------------------------------
_BG_WHITE = "#FFFFFF"
_BG_CREAM = "#FFF4E0"
_TEXT_PRIMARY = "#1F1A17"
_TEXT_SECONDARY = "#6B6259"
_ACCENT_ORANGE = "#E8590C"
_ACCENT_YELLOW = "#F2C230"
_ACCENT_GREEN = "#16A34A"
_BORDER_WARM = "#EFE5D6"


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
# Injeksi CSS Kustom: Warm Light Theme (Velora Aesthetic)
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
    /* Import Google Font modern: Plus Jakarta Sans */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Sembunyikan tombol deploy dan footer bawaan */
    .stDeployButton, footer, #MainMenu {
        display: none !important;
        visibility: hidden !important;
    }

    /* Header & Kontrol Buka/Tutup Sidebar */
    [data-testid="stHeader"] {
        background-color: transparent !important;
        z-index: 100 !important;
    }

    /* Pastikan tombol buka sidebar (panah kiri atas) dan tombol collapse SELALU terlihat */
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="stSidebarCollapseButton"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        z-index: 1000 !important;
        color: #1F1A17 !important;
    }

    [data-testid="stSidebarCollapsedControl"] button,
    [data-testid="stSidebarCollapseButton"] button {
        color: #1F1A17 !important;
        background-color: #FAF6EF !important;
        border: 1px solid #EFE5D6 !important;
        border-radius: 8px !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05) !important;
    }

    [data-testid="stSidebarCollapsedControl"] svg,
    [data-testid="stSidebarCollapseButton"] svg {
        fill: #1F1A17 !important;
        color: #1F1A17 !important;
    }

    /* Background Utama: gradien putih ke krem hangat sangat lembut */
    .stApp {
        background: radial-gradient(circle at 90% 10%, #FFF8ED 0%, #FFFFFF 45%), 
                    radial-gradient(circle at 10% 90%, #FFF3DE 0%, #FFFFFF 60%);
        background-color: #FAFAF7;
        color: #1F1A17;
    }

    /* Sidebar Styling Premium Warm Light */
    [data-testid="stSidebar"] {
        background-color: #FAF6EF !important;
        border-right: 1px solid #EFE5D6;
    }
    
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] {
        padding-top: 1rem;
    }

    /* Sidebar: teks terbaca jelas */
    [data-testid="stSidebar"], [data-testid="stSidebar"] * {
        color: #1F1A17 !important;
    }

    /* Styling Tautan Menu Navigasi */
    [data-testid="stSidebarNav"] a {
        border-radius: 12px;
        margin: 4px 10px;
        padding: 9px 16px;
        transition: all 0.2s ease-in-out;
        color: #6B6259 !important;
        font-weight: 500;
        font-size: 0.9rem;
    }

    [data-testid="stSidebarNav"] a:hover {
        background: rgba(232, 89, 12, 0.08);
        color: #E8590C !important;
        transform: translateX(3px);
    }

    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background: #FFFFFF !important;
        color: #E8590C !important;
        border-left: 3px solid #E8590C;
        font-weight: 700;
        box-shadow: 0 2px 8px -2px rgba(232, 89, 12, 0.15);
    }

    /* Kartu Metrik (st.metric) — putih bersih, batas hangat */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #EFE5D6;
        border-radius: 16px;
        padding: 20px 22px;
        box-shadow: 0 2px 10px -2px rgba(31, 26, 23, 0.04);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }

    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: #E8590C;
        box-shadow: 0 6px 18px -4px rgba(232, 89, 12, 0.10);
    }

    [data-testid="stMetricLabel"] {
        color: #6B6259 !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }

    [data-testid="stMetricValue"] {
        color: #1F1A17 !important;
        font-size: 1.9rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.03em;
    }

    /* Delta metric */
    [data-testid="stMetricDelta"] {
        color: #16A34A !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
    }

    /* Segmented Pill Radio Style ala Hourly/Daily/Monthly */
    div[data-testid="stRadio"] > div[role="radiogroup"] {
        background: #F3ECE2 !important;
        padding: 4px !important;
        border-radius: 24px !important;
        gap: 4px !important;
        border: 1px solid #EAE0D0 !important;
    }

    div[data-testid="stRadio"] label {
        background: transparent !important;
        border-radius: 20px !important;
        padding: 4px 14px !important;
        margin: 0 !important;
        transition: all 0.2s ease !important;
        font-size: 0.84rem !important;
        font-weight: 600 !important;
        color: #6B6259 !important;
    }

    div[data-testid="stRadio"] label:has(input:checked) {
        background: #FFFFFF !important;
        color: #1F1A17 !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06) !important;
    }

    div[data-testid="stRadio"] label input {
        display: none !important;
    }

    /* Tombol Interaktif Oranye */
    .stButton > button {
        background: linear-gradient(135deg, #E8590C 0%, #D14E0A 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(232, 89, 12, 0.3) !important;
        border-radius: 12px !important;
        padding: 9px 20px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 14px 0 rgba(232, 89, 12, 0.2);
        transition: all 0.25s ease !important;
    }

    .stButton > button:hover {
        background: linear-gradient(135deg, #F06A1E 0%, #E8590C 100%) !important;
        box-shadow: 0 6px 20px 0 rgba(232, 89, 12, 0.3) !important;
        transform: translateY(-1px);
    }

    /* Input & Select Box Elegan */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        background-color: #FFFFFF !important;
        border: 1px solid #EFE5D6 !important;
        border-radius: 12px !important;
        color: #1F1A17 !important;
    }

    div[data-baseweb="select"] > div:hover,
    div[data-baseweb="input"] > div:hover {
        border-color: #E8590C !important;
    }

    /* Expander Styling */
    [data-testid="stExpander"] {
        background: #FFFFFF;
        border: 1px solid #EFE5D6 !important;
        border-radius: 14px !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02) !important;
    }

    /* Garis Pemisah Halus */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, rgba(239,229,214,0) 0%, #EFE5D6 50%, rgba(239,229,214,0) 100%);
        margin: 1.25rem 0;
    }

    /* Container Kartu Kustom */
    .glass-card {
        background: #FFFFFF;
        border: 1px solid #EFE5D6;
        border-radius: 16px;
        padding: 22px 24px;
        box-shadow: 0 2px 10px -2px rgba(31, 26, 23, 0.04);
        margin-bottom: 1.25rem;
    }

    .badge-mock {
        display: inline-block;
        background: rgba(232, 89, 12, 0.10);
        color: #E8590C;
        border: 1px solid rgba(232, 89, 12, 0.30);
        border-radius: 6px;
        padding: 2px 8px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }

    .badge-pill-green {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        background: rgba(22, 163, 74, 0.10);
        color: #16A34A;
        border-radius: 20px;
        padding: 3px 10px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }

    .badge-pill-orange {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        background: rgba(232, 89, 12, 0.10);
        color: #E8590C;
        border-radius: 20px;
        padding: 3px 10px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }

    /* Pastikan heading & body text selalu terbaca */
    h1, h2, h3, h4, h5, h6 {
        color: #1F1A17 !important;
        font-weight: 800;
        letter-spacing: -0.02em;
    }

    p, span, label, .stMarkdown {
        color: #1F1A17;
    }

    .stCaption, [data-testid="stCaptionContainer"] {
        color: #6B6259 !important;
    }

    /* Custom KPI Stat Card */
    .kpi-card-velora {
        background: #FFFFFF;
        border: 1px solid #EFE5D6;
        border-radius: 16px;
        padding: 20px 22px;
        box-shadow: 0 2px 10px -2px rgba(31, 26, 23, 0.04);
        position: relative;
    }
    .kpi-card-velora .kpi-label {
        font-size: 0.78rem;
        font-weight: 600;
        color: #6B6259;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 6px;
    }
    .kpi-card-velora .kpi-val {
        font-size: 2.1rem;
        font-weight: 800;
        color: #1F1A17;
        letter-spacing: -0.03em;
        line-height: 1.1;
    }
    .kpi-card-velora .kpi-unit {
        font-size: 1rem;
        font-weight: 500;
        color: #6B6259;
        margin-left: 4px;
    }
    .kpi-card-velora .kpi-sub {
        margin-top: 8px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #16A34A;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* ---- Chart Card: st.container(border=True) ---- */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: #FFFFFF !important;
        border: 1px solid #EFE5D6 !important;
        border-radius: 18px !important;
        box-shadow: 0 2px 10px -2px rgba(31, 26, 23, 0.04) !important;
        padding: 16px 18px !important;
    }

    /* Segmented Control & Pills ala Velora Warm Light */
    [data-testid="stSegmentedControl"], [data-testid="stPills"] {
        background: #F3ECE2 !important;
        padding: 4px !important;
        border-radius: 24px !important;
        border: 1px solid #EAE0D0 !important;
    }

    [data-testid="stSegmentedControl"] button, [data-testid="stPills"] button {
        border-radius: 20px !important;
        border: none !important;
        background: transparent !important;
        color: #6B6259 !important;
        font-weight: 600 !important;
        font-size: 0.84rem !important;
        padding: 5px 16px !important;
        transition: all 0.2s ease !important;
    }

    [data-testid="stSegmentedControl"] button[aria-selected="true"],
    [data-testid="stPills"] button[aria-selected="true"] {
        background: #FFFFFF !important;
        color: #1F1A17 !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08) !important;
        font-weight: 700 !important;
    }

    /* ---- Equal-height bottom-row cards ---- */
    .equal-height-card {
        min-height: 260px;
    }

    /* ---- Date Input Warm Style ---- */
    [data-testid="stDateInput"] input {
        border: 1px solid #EFE5D6 !important;
        border-radius: 10px !important;
        font-size: 13px !important;
    }

    /* ---- Download Button Secondary Style ---- */
    [data-testid="stDownloadButton"] > button {
        background: #FFFFFF !important;
        color: #E8590C !important;
        border: 1px solid #E8590C !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        box-shadow: none !important;
    }

    [data-testid="stDownloadButton"] > button:hover {
        background: rgba(232, 89, 12, 0.06) !important;
        box-shadow: 0 4px 12px rgba(232, 89, 12, 0.12) !important;
        transform: translateY(-1px);
    }

    /* ---- Text Wrap & Padding untuk Sel Tabel st.dataframe ---- */
    [data-testid="stDataFrame"] div[role="gridcell"] {
        white-space: normal !important;
        word-break: break-word !important;
        line-height: 1.4 !important;
    }


</style>
"""


def apply_theme():
    """Terapkan CSS kustom ke halaman aktif."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Konfigurasi Styling Plotly agar Senada dengan Tema Terang Hangat
# ---------------------------------------------------------------------------
def style_plotly_fig(fig: go.Figure, height: int = 400) -> go.Figure:
    """Modifikasi figure Plotly dengan palet warm-light modern."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        font=dict(family="Plus Jakarta Sans, sans-serif", color="#1F1A17", size=12),
        height=height,
        margin=dict(l=25, r=25, t=40, b=35),
        xaxis=dict(
            gridcolor="rgba(107, 98, 89, 0.10)",
            linecolor="rgba(107, 98, 89, 0.18)",
            zerolinecolor="rgba(107, 98, 89, 0.12)",
        ),
        yaxis=dict(
            gridcolor="rgba(107, 98, 89, 0.10)",
            linecolor="rgba(107, 98, 89, 0.18)",
            zerolinecolor="rgba(107, 98, 89, 0.12)",
        ),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor="#E8590C",
            font_size=12,
            font_color="#1F1A17",
            font_family="Plus Jakarta Sans, sans-serif",
        ),
    )
    return fig


# ---------------------------------------------------------------------------
# Komponen Visual Kustom ala Dashboard Referensi (Radial Gauge & Matrix)
# ---------------------------------------------------------------------------
def create_radial_power_gauge(
    val: float,
    min_val: float,
    max_val: float,
    avg_val: float,
    title: str = "Power",
    unit: str = "kW",
) -> go.Figure:
    """
    Membuat Circular Radial Gauge dial seperti pada referensi gambar:
    - Dial melingkar dengan tick marks
    - Nilai utama di tengah besar tebal
    - Nilai Min, Max, Avg di bawah
    """
    upper_bound = max(max_val * 1.15, val * 1.15, 10.0)

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=round(val, 1),
            domain={"x": [0.05, 0.95], "y": [0.15, 0.95]},
            title={
                "text": f"<span style='font-size:12px;color:#6B6259;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;'>{title}</span>",
                "font": {"size": 13, "family": "Plus Jakarta Sans"},
            },
            number={
                "suffix": f" <span style='font-size:13px;color:#6B6259;font-weight:500;'>{unit}</span>",
                "font": {"size": 34, "color": "#1F1A17", "family": "Plus Jakarta Sans"},
            },
            gauge={
                "axis": {
                    "range": [0, upper_bound],
                    "tickwidth": 1.5,
                    "tickcolor": "#C4B5A5",
                    "ticklen": 6,
                    "nticks": 8,
                    "tickfont": {"size": 10, "color": "#6B6259"},
                },
                "bar": {"color": "#E8590C", "thickness": 0.12},
                "bgcolor": "#FFF7EB",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, upper_bound], "color": "#FAF4E8"},
                ],
            },
        )
    )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=220,
        margin=dict(l=15, r=15, t=30, b=10),
    )
    return fig


def create_donut_gauge(
    pct: float,
    center_text: Optional[str] = None,
    sub_text: str = "+2%/hour",
    status_label: str = "Active",
    color: str = "#E8590C",
) -> go.Figure:
    """
    Membuat Donut Gauge melingkar ala 'Battery Storage / Efisiensi' pada gambar referensi.
    """
    clamped_pct = max(0.0, min(100.0, pct))
    main_text = center_text if center_text else f"{int(round(clamped_pct))}%"

    fig = go.Figure(
        go.Pie(
            values=[clamped_pct, 100.0 - clamped_pct],
            hole=0.76,
            marker_colors=[color, "#F2ECE2"],
            textinfo="none",
            hoverinfo="none",
            sort=False,
            direction="clockwise",
        )
    )

    fig.add_annotation(
        text=f"<b style='font-size:26px;color:#1F1A17;'>{main_text}</b><br><span style='font-size:11px;color:#16A34A;font-weight:600;'>{sub_text}</span>",
        showarrow=False,
        font=dict(family="Plus Jakarta Sans"),
        x=0.5,
        y=0.5,
    )

    fig.update_layout(
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=180,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


def render_panel_heatmap_html(title: str = "Machine Activity Heatmap", subtitle: str = "24 Jam Operasional") -> str:
    """
    Menghasilkan HTML matriks rounded-square seperti 'Panel Heatmap' di gambar referensi.
    """
    # Warna intensitas representasi panel / sensor jam 1..12 baris A & B
    row_a = ["#FDE68A", "#FCD34D", "#FDE68A", "#FDE68A", "#E8590C", "#FCD34D", "#FEF3C7", "#FEF3C7", "#FDE68A", "#FEF3C7", "#FDE68A", "#FEF3C7"]
    row_b = ["#FEF3C7", "#FDE68A", "#FDE68A", "#FCD34D", "#FCD34D", "#FDE68A", "#FDE68A", "#FEF3C7", "#FDE68A", "#FCD34D", "#FEF3C7", "#FEF3C7"]

    def make_tiles(colors):
        return "".join(
            f'<div style="flex:1; aspect-ratio:1; background:{c}; border-radius:6px; min-width:14px; max-width:28px;"></div>'
            for c in colors
        )

    cols_labels = "".join(
        f'<div style="flex:1; text-align:center; font-size:0.65rem; color:#8C827A; font-weight:600;">{i+1}</div>'
        for i in range(12)
    )

    return f"""
    <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.03);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <div style="font-weight:700; font-size:0.95rem; color:#1F1A17;">{title}</div>
            <div style="font-size:0.75rem; color:#6B6259; font-weight:600;">{subtitle}</div>
        </div>
        <div style="display:flex; flex-direction:column; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:0.75rem; font-weight:700; color:#8C827A; width:14px;">A</span>
                <div style="display:flex; gap:6px; flex:1;">{make_tiles(row_a)}</div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:0.75rem; font-weight:700; color:#8C827A; width:14px;">B</span>
                <div style="display:flex; gap:6px; flex:1;">{make_tiles(row_b)}</div>
            </div>
            <div style="display:flex; align-items:center; gap:8px; margin-top:2px;">
                <span style="width:14px;"></span>
                <div style="display:flex; gap:6px; flex:1;">{cols_labels}</div>
            </div>
        </div>
    </div>
    """

