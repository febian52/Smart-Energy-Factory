import sys
from pathlib import Path
from datetime import datetime, time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Setup sys.path agar import api_client dan ui berfungsi dari root atau subfolder
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
for p in (str(CURRENT_DIR.parent), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from frontend.api_client import (
        get_machines,
        get_energy,
        get_data_range,
        to_dataframe,
        aggregate_hourly,
        aggregate_daily,
    )
    from frontend.ui import apply_theme, style_plotly_fig
except ImportError:
    from api_client import (
        get_machines,
        get_energy,
        get_data_range,
        to_dataframe,
        aggregate_hourly,
        aggregate_daily,
    )
    from ui import apply_theme, style_plotly_fig

st.set_page_config(
    page_title="Detail Mesin - Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
)

# Terapkan Tema Elegan Dark Glassmorphism
apply_theme()

# ---------------------------------------------------------------------------
# Header Halaman
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="margin-bottom: 20px;">
        <div style="font-size: 0.8rem; font-weight: 700; color: #10b981; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
            MONITORING TELEMETRI
        </div>
        <h1 style="color: #ffffff; font-size: 2.1rem; font-weight: 800; margin: 0 0 6px 0; letter-spacing: -0.02em;">
            🏭 Detail & Profil Konsumsi Mesin
        </h1>
        <p style="color: #94a3b8; font-size: 0.98rem; margin: 0; line-height: 1.5;">
            Analisis mendalam karakteristik konsumsi daya listrik, status operasional (Running vs Idle), dan parameter kelistrikan mesin.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("<hr/>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Pengambilan Daftar Mesin
# ---------------------------------------------------------------------------
try:
    with st.spinner("Memuat daftar mesin dari backend..."):
        machines = get_machines()
except RuntimeError as exc:
    st.error(
        f"🚨 **Gagal memuat daftar mesin dari API:**\n\n`{exc}`\n\n"
        "Pastikan backend berjalan di `http://localhost:8000`.",
        icon="🚫",
    )
    st.stop()
except Exception as exc:
    st.error(f"Terjadi kesalahan: {exc}", icon="⚠️")
    st.stop()

if not machines:
    st.warning("⚠️ Tidak ada mesin yang terdaftar di database.")
    st.stop()

# ---------------------------------------------------------------------------
# Kontrol Filter: Pilih Mesin, Rentang Tanggal, & Agregasi
# ---------------------------------------------------------------------------
ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([2, 2, 1.5])

with ctrl_c1:
    machine_map = {
        m["machine_id"]: f"{m['machine_id']} - {m['name']} ({m['line']})"
        for m in machines
    }
    selected_machine_id = st.selectbox(
        "Pilih Mesin",
        options=list(machine_map.keys()),
        format_func=lambda mid: machine_map[mid],
    )
    current_machine = next(m for m in machines if m["machine_id"] == selected_machine_id)

with ctrl_c2:
    try:
        def_start, def_end = get_data_range(selected_machine_id)
    except Exception:
        def_start = datetime(2026, 11, 1)
        def_end = datetime(2026, 11, 3, 23, 0)

    date_range_input = st.date_input(
        "Rentang Tanggal",
        value=(def_start.date(), def_end.date()),
        min_value=datetime(2020, 1, 1).date(),
        max_value=datetime(2035, 12, 31).date(),
        help="Default mengambil dari rentang data sensor yang tersedia di database.",
    )

with ctrl_c3:
    agg_selection = st.radio(
        "Agregasi Waktu",
        options=["Per Jam", "Per Hari"],
        horizontal=True,
        help="Pilih granularitas agregasi data time-series.",
    )

if not isinstance(date_range_input, (list, tuple)) or len(date_range_input) != 2:
    st.info("ℹ️ Silakan tentukan tanggal awal dan tanggal akhir pada filter kalender.")
    st.stop()

start_date, end_date = date_range_input
start_dt = datetime.combine(start_date, time.min)
end_dt = datetime.combine(end_date, time.max.replace(microsecond=0))

if start_dt > end_dt:
    st.error("Tanggal awal tidak boleh melebihi tanggal akhir.")
    st.stop()

# ---------------------------------------------------------------------------
# Info Spesifikasi Mesin
# ---------------------------------------------------------------------------
info_c1, info_c2, info_c3, info_c4 = st.columns(4)
with info_c1:
    st.metric("ID Mesin", current_machine.get("machine_id", "-"))
with info_c2:
    st.metric("Lini Produksi", current_machine.get("line", "-"))
with info_c3:
    st.metric("Tipe Mesin", current_machine.get("type", "-"))
with info_c4:
    rated_kw = current_machine.get("rated_power_kw", 0)
    st.metric("Daya Terpasang", f"{rated_kw} kW")

st.markdown("<hr/>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Pengambilan Data Energi Mesin
# ---------------------------------------------------------------------------
try:
    with st.spinner(f"Memuat telemetri {selected_machine_id}..."):
        raw_rows = get_energy(selected_machine_id, start=start_dt, end=end_dt, limit=10000)
except RuntimeError as exc:
    st.error(f"🚨 **Gagal memuat data energi:**\n\n`{exc}`", icon="🚫")
    st.stop()
except Exception as exc:
    st.error(f"Terjadi kesalahan saat memproses data: {exc}", icon="⚠️")
    st.stop()

if not raw_rows:
    st.info(
        f"Tidak ditemukan data pembacaan energi untuk mesin **{selected_machine_id}** "
        f"pada rentang tanggal {start_date} s/d {end_date}."
    )
    st.stop()

df_raw = to_dataframe(raw_rows)

# ---------------------------------------------------------------------------
# Metrik Operasional & Status
# ---------------------------------------------------------------------------
total_readings = len(df_raw)
running_count = (df_raw["status"] == "running").sum()
idle_count = (df_raw["status"] == "idle").sum()
total_energy_kwh = df_raw["energy_kwh"].sum()
avg_power_kw = df_raw["power_kw"].mean()

stat_c1, stat_c2, stat_c3, stat_c4 = st.columns(4)
with stat_c1:
    st.metric("Total Energi Terpakai", f"{total_energy_kwh:,.2f} kWh")
with stat_c2:
    st.metric("Rata-rata Daya Listrik", f"{avg_power_kw:,.2f} kW")
with stat_c3:
    pct_run = (running_count / total_readings * 100) if total_readings else 0
    st.metric("Waktu Running (Beban Aktif)", f"{running_count} Jam", f"{pct_run:.1f}% waktu")
with stat_c4:
    pct_idle = (idle_count / total_readings * 100) if total_readings else 0
    st.metric("Waktu Idle (Stand-by)", f"{idle_count} Jam", f"{pct_idle:.1f}% waktu")

st.markdown("<div style='margin: 1.5rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Grafik Time-Series dengan Penanda Status Berwarna
# ---------------------------------------------------------------------------
if agg_selection == "Per Jam":
    df_chart = aggregate_hourly(raw_rows)
    df_raw["hour"] = df_raw["timestamp"].dt.floor("h")
    status_lookup = df_raw.groupby("hour")["status"].first().to_dict()
    df_chart["status"] = df_chart["timestamp"].map(status_lookup).fillna("idle")

    st.markdown(
        """
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <h3 style="color: #f1f5f9; font-size: 1.15rem; font-weight: 700; margin: 0;">
                📈 Kurva Beban Daya & Energi (Per Jam)
            </h3>
            <div style="display: flex; gap: 14px; font-size: 0.8rem; font-weight: 600;">
                <span style="display: flex; align-items: center; gap: 6px; color: #10b981;">
                    <span style="height: 9px; width: 9px; background: #10b981; border-radius: 50%; box-shadow: 0 0 6px #10b981;"></span> Running (Beban Aktif)
                </span>
                <span style="display: flex; align-items: center; gap: 6px; color: #f59e0b;">
                    <span style="height: 9px; width: 9px; background: #f59e0b; border-radius: 50%; box-shadow: 0 0 6px #f59e0b;"></span> Idle (Stand-by)
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    fig = make_subplots(
        specs=[[{"secondary_y": True}]],
    )

    # 1. Area fill Daya Listrik (kW)
    fig.add_trace(
        go.Scatter(
            x=df_chart["timestamp"],
            y=df_chart["power_kw"],
            mode="lines",
            name="Daya Rata-rata (kW)",
            line=dict(color="#38bdf8", width=2.5, shape="spline"),
            fill="tozeroy",
            fillcolor="rgba(56, 189, 248, 0.08)",
            hovertemplate="<b>Waktu</b>: %{x}<br>Daya: %{y:.2f} kW<extra></extra>",
        ),
        secondary_y=False,
    )

    # 2. Garis Konsumsi Energi (kWh)
    fig.add_trace(
        go.Scatter(
            x=df_chart["timestamp"],
            y=df_chart["energy_kwh"],
            mode="lines",
            name="Energi (kWh)",
            line=dict(color="#a78bfa", width=2, dash="dot"),
            hovertemplate="<b>Waktu</b>: %{x}<br>Energi: %{y:.2f} kWh<extra></extra>",
        ),
        secondary_y=True,
    )

    # 3. Penanda Titik Status Running (🟢 Emerald Green)
    df_running = df_chart[df_chart["status"] == "running"]
    if not df_running.empty:
        fig.add_trace(
            go.Scatter(
                x=df_running["timestamp"],
                y=df_running["power_kw"],
                mode="markers",
                name="Status: Running",
                marker=dict(color="#10b981", size=8, line=dict(color="#047857", width=1.5)),
                hovertemplate="<b>%{x}</b><br>🟢 Status: <b>Running</b><br>Daya: %{y:.2f} kW<extra></extra>",
            ),
            secondary_y=False,
        )

    # 4. Penanda Titik Status Idle (🟠 Amber)
    df_idle = df_chart[df_chart["status"] == "idle"]
    if not df_idle.empty:
        fig.add_trace(
            go.Scatter(
                x=df_idle["timestamp"],
                y=df_idle["power_kw"],
                mode="markers",
                name="Status: Idle",
                marker=dict(color="#f59e0b", size=8, symbol="diamond", line=dict(color="#b45309", width=1.5)),
                hovertemplate="<b>%{x}</b><br>🟠 Status: <b>Idle</b><br>Daya: %{y:.2f} kW<extra></extra>",
            ),
            secondary_y=False,
        )

    fig.update_xaxes(title_text="Waktu Sensor (Timestamp)")
    fig.update_yaxes(title_text="Daya Listrik (kW)", secondary_y=False)
    fig.update_yaxes(title_text="Energi (kWh)", secondary_y=True)
    style_plotly_fig(fig, height=440)
    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

else:
    # Agregasi Harian
    df_chart = aggregate_daily(raw_rows)
    df_raw["date"] = df_raw["timestamp"].dt.date
    daily_status = (
        df_raw.groupby(["date", "status"]).size().unstack(fill_value=0).reset_index()
    )
    if "running" not in daily_status.columns:
        daily_status["running"] = 0
    if "idle" not in daily_status.columns:
        daily_status["idle"] = 0

    df_chart = df_chart.merge(daily_status, on="date", how="left")

    st.markdown(
        """
        <h3 style="color: #f1f5f9; font-size: 1.15rem; font-weight: 700; margin: 0 0 12px 0;">
            📊 Konsumsi Harian & Rata-rata Daya Listrik
        </h3>
        """,
        unsafe_allow_html=True,
    )

    fig = make_subplots(
        specs=[[{"secondary_y": True}]],
    )

    # Batang Total Energi Harian
    fig.add_trace(
        go.Bar(
            x=df_chart["date"],
            y=df_chart["energy_kwh"],
            name="Total Energi (kWh)",
            marker=dict(
                color="#0ea5e9",
                line=dict(color="rgba(255,255,255,0.15)", width=1),
            ),
            opacity=0.85,
            hovertemplate="<b>Tanggal %{x}</b><br>Total Energi: %{y:.2f} kWh<extra></extra>",
        ),
        secondary_y=False,
    )

    # Garis Rata-rata Daya (kW)
    fig.add_trace(
        go.Scatter(
            x=df_chart["date"],
            y=df_chart["power_kw"],
            name="Rata-rata Daya (kW)",
            mode="lines+markers",
            line=dict(color="#f43f5e", width=3),
            marker=dict(size=9, color="#e11d48", line=dict(color="#ffffff", width=1.5)),
            hovertemplate="<b>Tanggal %{x}</b><br>Rata-rata Daya: %{y:.2f} kW<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_xaxes(title_text="Tanggal")
    fig.update_yaxes(title_text="Total Energi (kWh)", secondary_y=False)
    fig.update_yaxes(title_text="Rata-rata Daya (kW)", secondary_y=True)
    style_plotly_fig(fig, height=440)
    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Kartu Proporsi Jam Operasional Harian
    st.markdown("##### ⏱️ Proporsi Jam Operasional Harian")
    col_breakdowns = st.columns(len(df_chart))
    for idx, row in df_chart.iterrows():
        with col_breakdowns[idx]:
            r_hours = row.get("running", 0)
            i_hours = row.get("idle", 0)
            st.metric(
                label=f"📅 {row['date']}",
                value=f"{row['energy_kwh']:.1f} kWh",
                delta=f"🟢 {r_hours}j Running | 🟠 {i_hours}j Idle",
                delta_color="normal",
            )

# ---------------------------------------------------------------------------
# Tabel Rincian Data (Expander)
# ---------------------------------------------------------------------------
with st.expander("🔍 Lihat Rincian Data Sensor (Tabel)"):
    st.dataframe(
        df_chart,
        use_container_width=True,
        hide_index=True,
    )
