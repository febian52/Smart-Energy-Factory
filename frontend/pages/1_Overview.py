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
        aggregate_hourly,
    )
    from frontend.ui import (
        apply_theme,
        style_plotly_fig,
        create_radial_power_gauge,
        render_panel_heatmap_html,
    )
except ImportError:
    from api_client import (
        get_summary,
        get_machines,
        get_waste_alerts,
        get_energy,
        get_data_range,
        aggregate_daily,
        aggregate_hourly,
    )
    from ui import (
        apply_theme,
        style_plotly_fig,
        create_radial_power_gauge,
        render_panel_heatmap_html,
    )

st.set_page_config(
    page_title="Overview - Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
)

# Terapkan Tema Warm Light ala Velora
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
# Pengambilan Data Backend
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
# Header Halaman & Segmented Filter Control (Top Bar)
# ---------------------------------------------------------------------------
header_col1, header_col2 = st.columns([2.2, 1.2])

with header_col1:
    st.markdown(
        """
        <div style="margin-bottom: 12px;">
            <h1 style="color: #1F1A17; font-size: 2.2rem; font-weight: 800; margin: 0 0 4px 0; letter-spacing: -0.03em;">
                Energy Dashboard Overview
            </h1>
            <div style="font-size: 0.78rem; font-weight: 700; color: #6B6259; text-transform: uppercase; letter-spacing: 0.08em;">
                // SITE: PLANT-01 · PRODUCTION LINE A & B · NOVEMBER 2026
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_col2:
    view_granularity = st.radio(
        "Tampilan",
        options=["Hourly", "Daily"],
        horizontal=True,
        label_visibility="collapsed",
    )

# ---------------------------------------------------------------------------
# Pengambilan Data Time-Series untuk Grafik Utama
# ---------------------------------------------------------------------------
all_readings: list[dict] = []
if machines:
    for m in machines:
        mid = m.get("machine_id")
        rows = get_energy(mid, start=start_dt, end=end_dt, limit=10000)
        if rows:
            all_readings.extend(rows)

total_kwh = summary_data.get("total_kwh", 0.0) if summary_data else 0.0
cost_rp = summary_data.get("estimated_cost_rp", 0) if summary_data else 0

# Hitung statistik daya instan / rata-rata
if all_readings:
    df_readings = pd.DataFrame(all_readings)
    cur_power = float(df_readings["power_kw"].iloc[-1]) if not df_readings.empty else 0.0
    avg_power = float(df_readings["power_kw"].mean()) if not df_readings.empty else 0.0
    min_power = float(df_readings["power_kw"].min()) if not df_readings.empty else 0.0
    max_power = float(df_readings["power_kw"].max()) if not df_readings.empty else 0.0
else:
    cur_power, avg_power, min_power, max_power = 0.0, 0.0, 0.0, 0.0

# ---------------------------------------------------------------------------
# Kartu KPI Atas (Gaya Velora: 3 Kolom Bersih dengan Delta & Satuan Terpisah)
# ---------------------------------------------------------------------------
kpi_c1, kpi_c2, kpi_c3 = st.columns(3)

with kpi_c1:
    st.markdown(
        f"""
        <div class="kpi-card-velora">
            <div class="kpi-label">Total Generated / Consumption</div>
            <div>
                <span class="kpi-val">{format_id_num(total_kwh, 1)}</span>
                <span class="kpi-unit">kWh</span>
            </div>
            <div class="kpi-sub">
                <span class="badge-pill-green">▲ +18.4%</span>
                <span style="color:#6B6259; font-weight:500;">vs periode lalu</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with kpi_c2:
    st.markdown(
        f"""
        <div class="kpi-card-velora">
            <div class="kpi-label">Current Output / Power</div>
            <div>
                <span class="kpi-val">{cur_power:.1f}</span>
                <span class="kpi-unit">kW</span>
            </div>
            <div class="kpi-sub">
                <span class="badge-pill-green">● Peak Active</span>
                <span style="color:#6B6259; font-weight:500;">Rata-rata {avg_power:.1f} kW</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with kpi_c3:
    st.markdown(
        f"""
        <div class="kpi-card-velora">
            <div class="kpi-label">Estimasi Biaya Listrik (Grid)</div>
            <div>
                <span class="kpi-val">{format_id_currency(cost_rp)}</span>
            </div>
            <div class="kpi-sub" style="color: #6B6259;">
                <span class="badge-pill-orange">⚡ Tarif Rp 1.500</span>
                <span style="color:#6B6259; font-weight:500;">per kWh</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Baris Tengah: Energy Overview Multi-Line Spline Chart & Power Radial Gauge
# ---------------------------------------------------------------------------
col_mid_left, col_mid_right = st.columns([1.8, 1.05])

with col_mid_left:
    st.markdown(
        """
        <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <div>
                    <h3 style="margin:0; font-size:1.15rem; font-weight:800; color:#1F1A17;">Energy Overview</h3>
                    <div style="font-size:0.75rem; color:#6B6259; font-weight:600;">Kurva beban daya instan & konsumsi energi</div>
                </div>
                <div style="display:flex; gap:16px; font-size:0.76rem; font-weight:700;">
                    <span style="display:flex; align-items:center; gap:5px; color:#E8590C;">
                        <span style="width:12px; height:3px; background:#E8590C; border-radius:2px;"></span> Daya (kW)
                    </span>
                    <span style="display:flex; align-items:center; gap:5px; color:#F2C230;">
                        <span style="width:12px; height:3px; background:#F2C230; border-radius:2px;"></span> Energi (kWh)
                    </span>
                    <span style="display:flex; align-items:center; gap:5px; color:#16A34A;">
                        <span style="width:12px; height:2px; border-top:2px dashed #16A34A;"></span> Target Efisiensi
                    </span>
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )

    if not all_readings:
        st.info("Tidak ada data pembacaan sensor.")
    else:
        if view_granularity == "Hourly":
            df_chart = aggregate_hourly(all_readings)
            df_chart = df_chart.groupby("timestamp", as_index=False).agg({"power_kw": "sum", "energy_kwh": "sum"}).sort_values("timestamp")
            x_vals = df_chart["timestamp"]
        else:
            df_chart = aggregate_daily(all_readings)
            df_chart = df_chart.groupby("date", as_index=False).agg({"power_kw": "sum", "energy_kwh": "sum"}).sort_values("date")
            x_vals = df_chart["date"]

        fig_multi = go.Figure()

        # 1. Seri 1: Daya kW (Oranye Terracotta ala Gambar 1)
        fig_multi.add_trace(
            go.Scatter(
                x=x_vals,
                y=df_chart["power_kw"],
                mode="lines",
                name="Daya (kW)",
                line=dict(color="#E8590C", width=3, shape="spline"),
                fill="tozeroy",
                fillcolor="rgba(232, 89, 12, 0.06)",
                hovertemplate="<b>Waktu</b>: %{x}<br>Daya: <b>%{y:.2f} kW</b><extra></extra>",
            )
        )

        # 2. Seri 2: Konsumsi kWh (Kuning Hangat ala Gambar 1)
        fig_multi.add_trace(
            go.Scatter(
                x=x_vals,
                y=df_chart["energy_kwh"],
                mode="lines",
                name="Energi (kWh)",
                line=dict(color="#F2C230", width=2.5, shape="spline"),
                hovertemplate="<b>Waktu</b>: %{x}<br>Energi: <b>%{y:.2f} kWh</b><extra></extra>",
            )
        )

        # 3. Seri 3: Garis Target Efisiensi (Hijau Putus-putus ala Gambar 1)
        target_line = [avg_power * 0.85] * len(x_vals)
        fig_multi.add_trace(
            go.Scatter(
                x=x_vals,
                y=target_line,
                mode="lines",
                name="Target Efisiensi",
                line=dict(color="#16A34A", width=1.8, dash="dash"),
                hovertemplate="Target Efisiensi: <b>%{y:.2f} kW</b><extra></extra>",
            )
        )

        style_plotly_fig(fig_multi, height=330)
        fig_multi.update_layout(
            showlegend=False,
            margin=dict(l=20, r=20, t=10, b=30),
            hovermode="x unified",
        )
        st.plotly_chart(fig_multi, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

with col_mid_right:
    st.markdown(
        """
        <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04); height:100%;">
            <div style="font-weight:800; font-size:1.15rem; color:#1F1A17; margin-bottom:4px;">Power Meter</div>
            <div style="font-size:0.75rem; color:#6B6259; font-weight:600; margin-bottom:6px;">Indikator Beban Listrik Aktif</div>
        """,
        unsafe_allow_html=True,
    )

    # Render Circular Radial Gauge Dial
    gauge_fig = create_radial_power_gauge(
        val=cur_power if cur_power > 0 else avg_power,
        min_val=min_power,
        max_val=max_power if max_power > 0 else 50.0,
        avg_val=avg_power,
        title="Daya Aktif",
        unit="kW",
    )
    st.plotly_chart(gauge_fig, use_container_width=True)

    # Min / Max / Avg stats bar persis seperti di bawah dial pada Gambar 1
    st.markdown(
        f"""
        <div style="display:flex; justify-content:space-around; text-align:center; padding:8px 0; border-top:1px solid #EFE5D6; margin-top:-10px; margin-bottom:14px;">
            <div>
                <div style="font-size:0.7rem; color:#6B6259; text-transform:uppercase; font-weight:600;">Min</div>
                <div style="font-size:0.95rem; font-weight:700; color:#1F1A17;">{min_power:.1f} <span style="font-size:0.75rem;">kW</span></div>
            </div>
            <div style="border-right:1px solid #EFE5D6;"></div>
            <div>
                <div style="font-size:0.7rem; color:#6B6259; text-transform:uppercase; font-weight:600;">Max</div>
                <div style="font-size:0.95rem; font-weight:700; color:#E8590C;">{max_power:.1f} <span style="font-size:0.75rem;">kW</span></div>
            </div>
            <div style="border-right:1px solid #EFE5D6;"></div>
            <div>
                <div style="font-size:0.7rem; color:#6B6259; text-transform:uppercase; font-weight:600;">Avg</div>
                <div style="font-size:0.95rem; font-weight:700; color:#1F1A17;">{avg_power:.1f} <span style="font-size:0.75rem;">kW</span></div>
            </div>
        </div>

        <div style="display:flex; flex-direction:column; gap:10px;">
            <div>
                <div style="display:flex; justify-content:space-between; font-size:0.78rem; font-weight:600; margin-bottom:4px;">
                    <span style="color:#6B6259;">Beban Running (Aktif)</span>
                    <span style="color:#16A34A; font-weight:700;">Optimal</span>
                </div>
                <div style="background:#F2ECE2; height:7px; border-radius:4px; overflow:hidden;">
                    <div style="background:#16A34A; width:78%; height:100%; border-radius:4px;"></div>
                </div>
            </div>
            <div>
                <div style="display:flex; justify-content:space-between; font-size:0.78rem; font-weight:600; margin-bottom:4px;">
                    <span style="color:#6B6259;">Standby / Idle Load</span>
                    <span style="color:#F2C230; font-weight:700;">22%</span>
                </div>
                <div style="background:#F2ECE2; height:7px; border-radius:4px; overflow:hidden;">
                    <div style="background:#F2C230; width:22%; height:100%; border-radius:4px;"></div>
                </div>
            </div>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Baris Bawah: 3 Kolom (Alerts Breakdown, Impact Metrics, Panel Heatmap)
# ---------------------------------------------------------------------------
b_c1, b_c2, b_c3 = st.columns([1.05, 1.15, 1.4])

with b_c1:
    st.markdown(
        f"""
        <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.03); height:100%;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <div style="font-weight:700; font-size:0.95rem; color:#1F1A17;">Alerts & Anomali</div>
                <span class="badge-pill-orange">{total_waste_alerts} Kasus</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:12px; margin-top:14px;">
                <div style="display:flex; justify-content:space-between; font-size:0.84rem; padding-bottom:6px; border-bottom:1px solid #FAF4E8;">
                    <span style="color:#6B6259;">Idle Excess</span>
                    <span style="font-weight:700; color:#1F1A17;">1 Kasus</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.84rem; padding-bottom:6px; border-bottom:1px solid #FAF4E8;">
                    <span style="color:#6B6259;">Spike Overload</span>
                    <span style="font-weight:700; color:#16A34A;">Normal (0)</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.84rem;">
                    <span style="color:#6B6259;">Model ML</span>
                    <span style="font-weight:700; color:#E8590C;">{'Mock' if has_mock_alert else 'Aktif'}</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with b_c2:
    st.markdown(
        """
        <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.03); height:100%;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <div style="font-weight:700; font-size:0.95rem; color:#1F1A17;">Environmental & Impact</div>
                <span class="badge-pill-green">Pabrik Hijau</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:12px; margin-top:14px;">
                <div style="display:flex; justify-content:space-between; font-size:0.84rem; padding-bottom:6px; border-bottom:1px solid #FAF4E8;">
                    <span style="color:#6B6259;">Estimasi Emisi CO2</span>
                    <span style="font-weight:700; color:#1F1A17;">18.4 Ton</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.84rem; padding-bottom:6px; border-bottom:1px solid #FAF4E8;">
                    <span style="color:#6B6259;">Tingkat Utilisasi</span>
                    <span style="font-weight:700; color:#16A34A;">91.2%</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.84rem;">
                    <span style="color:#6B6259;">Mesin Aktif</span>
                    <span style="font-weight:700; color:#1F1A17;">3 Unit</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with b_c3:
    # Render Panel Heatmap persis seperti di Gambar 1
    st.markdown(
        render_panel_heatmap_html(title="Panel Heatmap", subtitle="24 Sensor Matriks"),
        unsafe_allow_html=True,
    )

# Footer info
st.markdown(
    f"""
    <div style="text-align: right; font-size: 0.78rem; color: #6B6259; margin-top: 20px;">
        Database Sensor: Data aktif <b>{start_dt.strftime('%d %b %Y')}</b> s/d <b>{end_dt.strftime('%d %b %Y')}</b> · Smart Manufacturing Platform
    </div>
    """,
    unsafe_allow_html=True,
)

