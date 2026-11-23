"""
frontend/ui.py
==============
Modul utilitas UI & Styling untuk Smart Factory Energy Management.
Menyediakan CSS injection modern (Industrial Dark Glassmorphism),
konfigurasi tema Plotly gelap dan elegan, serta komponen visual premium.
"""

import streamlit as st
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Injeksi CSS Kustom: Dark Modern Glassmorphism
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
    /* Import Google Font modern: Plus Jakarta Sans */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Sembunyikan tombol Deploy bawaan Streamlit & header bawaan yang mengganggu */
    .stDeployButton, [data-testid="stToolbar"], footer, #MainMenu {
        display: none !important;
        visibility: hidden !important;
    }

    /* Background Utama & Gradasi Ambient Halus */
    .stApp {
        background: radial-gradient(circle at 15% 15%, #0f172a 0%, #070b14 100%);
        color: #f1f5f9;
    }

    /* Sidebar Styling Premium */
    [data-testid="stSidebar"] {
        background-color: #0b111e !important;
        border-right: 1px solid rgba(255, 255, 255, 0.07);
    }
    
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] {
        padding-top: 1rem;
    }

    /* Styling Tautan Menu Navigasi */
    [data-testid="stSidebarNav"] a {
        border-radius: 10px;
        margin: 2px 8px;
        padding: 8px 14px;
        transition: all 0.2s ease-in-out;
        color: #94a3b8 !important;
    }

    [data-testid="stSidebarNav"] a:hover {
        background: rgba(255, 255, 255, 0.05);
        color: #38bdf8 !important;
        transform: translateX(3px);
    }

    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background: linear-gradient(90deg, rgba(14, 165, 233, 0.15) 0%, rgba(14, 165, 233, 0.03) 100%) !important;
        color: #38bdf8 !important;
        border-left: 3px solid #38bdf8;
        font-weight: 600;
    }

    /* Kartu Metrik (st.metric) Glassmorphism */
    [data-testid="stMetric"] {
        background: rgba(18, 26, 43, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-top: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 14px;
        padding: 18px 20px;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 24px -4px rgba(0, 0, 0, 0.35);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }

    [data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        border-color: rgba(56, 189, 248, 0.45);
        box-shadow: 0 12px 28px -4px rgba(14, 165, 233, 0.15);
    }

    [data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 1.85rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em;
    }

    /* Tombol Interaktif Elegan */
    .stButton > button {
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 10px !important;
        padding: 8px 18px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 14px 0 rgba(2, 132, 199, 0.35);
        transition: all 0.25s ease !important;
    }

    .stButton > button:hover {
        background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%) !important;
        box-shadow: 0 6px 20px 0 rgba(14, 165, 233, 0.5) !important;
        transform: translateY(-1px);
    }

    /* Input & Select Box Elegan */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        background-color: rgba(15, 23, 42, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 10px !important;
        color: #f8fafc !important;
    }

    div[data-baseweb="select"] > div:hover,
    div[data-baseweb="input"] > div:hover {
        border-color: #38bdf8 !important;
    }

    /* Radio Pills Elegan */
    [data-testid="stRadio"] > div {
        background: rgba(15, 23, 42, 0.6);
        padding: 6px 12px;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Expander Styling */
    [data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
    }

    /* Garis Pemisah Halus */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.12) 50%, rgba(255,255,255,0) 100%);
        margin: 1.5rem 0;
    }

    /* Container Kartu Kustom */
    .glass-card {
        background: rgba(18, 26, 43, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 14px;
        padding: 24px;
        backdrop-filter: blur(10px);
        margin-bottom: 1.25rem;
    }

    .badge-mock {
        display: inline-block;
        background: rgba(245, 158, 11, 0.15);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.35);
        border-radius: 6px;
        padding: 2px 8px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
</style>
"""


def apply_theme():
    """Terapkan CSS kustom ke halaman aktif."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Konfigurasi Styling Plotly agar Senada dengan Tema Dark Modern
# ---------------------------------------------------------------------------
def style_plotly_fig(fig: go.Figure, height: int = 400) -> go.Figure:
    """Modifikasi figure Plotly dengan palet industrial modern."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        font=dict(family="Plus Jakarta Sans, sans-serif", color="#cbd5e1", size=12),
        height=height,
        margin=dict(l=30, r=30, t=50, b=40),
        xaxis=dict(
            gridcolor="rgba(255, 255, 255, 0.06)",
            linecolor="rgba(255, 255, 255, 0.1)",
            zerolinecolor="rgba(255, 255, 255, 0.08)",
        ),
        yaxis=dict(
            gridcolor="rgba(255, 255, 255, 0.06)",
            linecolor="rgba(255, 255, 255, 0.1)",
            zerolinecolor="rgba(255, 255, 255, 0.08)",
        ),
        hoverlabel=dict(
            bgcolor="#0f172a",
            bordercolor="#38bdf8",
            font_size=12,
            font_family="Plus Jakarta Sans, sans-serif",
        ),
    )
    return fig
