import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Setup sys.path agar import api_client dan ui berfungsi dari root atau subfolder
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
for p in (str(CURRENT_DIR.parent), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from frontend.api_client import (
        get_summary,
        get_machines,
        get_waste_alerts,
        get_energy,
        get_data_range,
        aggregate_daily,
    )
    from frontend.ui import apply_theme, style_plotly_fig
except ImportError:
    from api_client import (
        get_summary,
        get_machines,
        get_waste_alerts,
        get_energy,
        get_data_range,
        aggregate_daily,
    )
    from ui import apply_theme, style_plotly_fig

st.set_page_config(
    page_title="Overview - Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
)

# Terapkan Tema Elegan Dark Glassmorphism
apply_theme()


# ---------------------------------------------------------------------------
# Helper Pemformat Angka Gaya Indonesia
# ---------------------------------------------------------------------------
def format_id_num(val: float, decimals: int = 1) -> str:
    """Format angka ribuan titik dan desimal koma (misal: 3.569,5)."""
    s = f"{val:,.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def format_id_currency(val: float) -> str:
    """Format mata uang Rupiah bulat (misal: Rp 5.354.250)."""
    s = f"{round(val):,}"
    return f"Rp {s.replace(',', '.')}"


# ---------------------------------------------------------------------------
# Header Halaman
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="margin-bottom: 20px;">
        <div style="font-size: 0.8rem; font-weight: 700; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
            DASHBOARD UTAMA
        </div>
        <h1 style="color: #ffffff; font-size: 2.1rem; font-weight: 800; margin: 0 0 6px 0; letter-spacing: -0.02em;">
            📊 Overview Konsumsi Energi Pabrik
        </h1>
        <p style="color: #94a3b8; font-size: 0.98rem; margin: 0; line-height: 1.5;">
            Pantauan terpadu performa konsumsi daya listrik seluruh lini produksi, estimasi biaya operasional, dan indikator peringatan pemborosan.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("<hr/>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Pengambilan Data
# ---------------------------------------------------------------------------
try:
    with st.spinner("Mengambil data overview dari server..."):
        summary_data = get_summary()
        machines = get_machines()
        start_dt, end_dt = get_data_range()

        # Hitung jumlah alert pemborosan dari tiap mesin
        total_waste_alerts = 0
        has_mock_alert = False

        if machines:
            for m in machines:
                mid = m.get("machine_id")
                waste_res = get_waste_alerts(mid, start=start_dt, end=end_dt)
                alerts_list = waste_res.get("alerts", [])
                total_waste_alerts += len(alerts_list)
                if waste_res.get("is_mock"):
                    has_mock_alert = True

except RuntimeError as exc:
    st.error(
        f"🚨 **Gagal memuat data dari API Backend:**\n\n`{exc}`\n\n"
        "Pastikan backend berjalan di `http://localhost:8000` atau periksa koneksi jaringan Anda.",
        icon="🚫",
    )
    st.stop()
except Exception as exc:
    st.error(f"Terjadi kesalahan saat memproses data: {exc}", icon="⚠️")
    st.stop()

# ---------------------------------------------------------------------------
# Kartu KPI (st.metric)
# ---------------------------------------------------------------------------
if not summary_data:
    st.warning("Data ringkasan energi belum tersedia di sistem.")
else:
    kpi1, kpi2, kpi3 = st.columns(3)

    with kpi1:
        total_kwh = summary_data.get("total_kwh", 0.0)
        st.metric(
            label="⚡ Total Konsumsi Energi",
            value=f"{format_id_num(total_kwh, 2)} kWh",
        )
        st.caption("Akumulasi seluruh mesin yang terdaftar")

    with kpi2:
        cost_rp = summary_data.get("estimated_cost_rp", 0)
        st.metric(
            label="💰 Estimasi Biaya Listrik",
            value=format_id_currency(cost_rp),
        )
        st.caption("Tarif Rp 1.500/kWh")

    with kpi3:
        st.metric(
            label="⚠️ Peringatan Pemborosan",
            value=f"{total_waste_alerts} Kasus",
        )
        if has_mock_alert:
            st.markdown("<span class='badge-mock'>Data contoh</span> <span style='font-size:0.75rem; color:#94a3b8;'>(model ML belum aktif)</span>", unsafe_allow_html=True)
        else:
            st.caption("Peringatan anomali terverifikasi")

st.markdown("<hr/>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Grafik 1 & 2: Bar Konsumsi per Lini & Line Tren Harian
# ---------------------------------------------------------------------------
per_line = summary_data.get("per_line", {}) if summary_data else {}

col_chart_left, col_chart_right = st.columns([1, 1])

with col_chart_left:
    st.markdown(
        """
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <h3 style="color: #f1f5f9; font-size: 1.15rem; font-weight: 700; margin: 0;">
                🏭 Konsumsi Energi per Lini
            </h3>
            <span style="font-size: 0.78rem; color: #38bdf8; font-weight: 600;">Distribusi Beban</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not per_line:
        st.info("Belum ada data konsumsi per lini produksi.")
    else:
        df_per_line = pd.DataFrame(
            [{"Lini": k, "Konsumsi (kWh)": v} for k, v in per_line.items()]
        ).sort_values("Lini")

        fig_bar = px.bar(
            df_per_line,
            x="Lini",
            y="Konsumsi (kWh)",
            text="Konsumsi (kWh)",
            color="Lini",
            color_discrete_sequence=["#0ea5e9", "#8b5cf6", "#10b981", "#f59e0b"],
        )
        fig_bar.update_traces(
            texttemplate="<b>%{text:,.2f}</b> kWh",
            textposition="outside",
            marker_line_width=0,
            marker_pattern_shape="",
            hovertemplate="<b>Lini: %{x}</b><br>Konsumsi: %{y:,.2f} kWh<extra></extra>",
        )
        fig_bar.update_layout(
            xaxis_title="",
            yaxis_title="Total Energi (kWh)",
            showlegend=False,
        )
        style_plotly_fig(fig_bar, height=390)
        st.plotly_chart(fig_bar, use_container_width=True)

with col_chart_right:
    st.markdown(
        """
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <h3 style="color: #f1f5f9; font-size: 1.15rem; font-weight: 700; margin: 0;">
                📈 Tren Konsumsi Energi Harian
            </h3>
            <span style="font-size: 0.78rem; color: #a78bfa; font-weight: 600;">Semua Mesin</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    daily_records: list[pd.DataFrame] = []

    if machines:
        with st.spinner("Menghitung agregasi harian..."):
            for m in machines:
                mid = m.get("machine_id")
                rows = get_energy(mid, start=start_dt, end=end_dt, limit=10000)
                if rows:
                    df_d = aggregate_daily(rows)
                    if not df_d.empty:
                        daily_records.append(df_d)

    if not daily_records:
        st.info(f"Tidak ada data pembacaan energi untuk rentang {start_dt.date()} s/d {end_dt.date()}.")
    else:
        df_all_daily = pd.concat(daily_records, ignore_index=True)
        df_total_daily = (
            df_all_daily.groupby("date", as_index=False)["energy_kwh"]
            .sum()
            .sort_values("date")
        )

        fig_line = go.Figure()
        fig_line.add_trace(
            go.Scatter(
                x=df_total_daily["date"],
                y=df_total_daily["energy_kwh"],
                mode="lines+markers",
                name="Total Energi",
                line=dict(color="#38bdf8", width=3, shape="spline"),
                marker=dict(size=9, color="#0284c7", line=dict(color="#38bdf8", width=2)),
                fill="tozeroy",
                fillcolor="rgba(14, 165, 233, 0.12)",
                hovertemplate="<b>Tanggal</b>: %{x}<br><b>Total Energi</b>: %{y:,.2f} kWh<extra></extra>",
            )
        )
        fig_line.update_layout(
            xaxis_title="Tanggal",
            yaxis_title="Total Energi (kWh)",
            showlegend=False,
        )
        style_plotly_fig(fig_line, height=390)
        st.plotly_chart(fig_line, use_container_width=True)

st.markdown(
    f"""
    <div style="text-align: right; font-size: 0.8rem; color: #64748b; margin-top: 10px;">
        Database Sensor: Data aktif <b>{start_dt.strftime('%d %b %Y')}</b> s/d <b>{end_dt.strftime('%d %b %Y')}</b>
    </div>
    """,
    unsafe_allow_html=True,
)
