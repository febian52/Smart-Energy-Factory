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
    from frontend.ui import (
        apply_theme,
        style_plotly_fig,
        create_donut_gauge,
    )
except ImportError:
    from api_client import (
        get_machines,
        get_energy,
        get_data_range,
        to_dataframe,
        aggregate_hourly,
        aggregate_daily,
    )
    from ui import (
        apply_theme,
        style_plotly_fig,
        create_donut_gauge,
    )

st.set_page_config(
    page_title="Detail Mesin - Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
)

# Terapkan Tema Warm Light ala Velora
apply_theme()

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
# Header Halaman & Segmented Filter Control
# ---------------------------------------------------------------------------
header_c1, header_c2 = st.columns([2.2, 1.2])

with header_c1:
    st.markdown(
        """
        <div style="margin-bottom: 12px;">
            <h1 style="color: #1F1A17; font-size: 2.2rem; font-weight: 800; margin: 0 0 4px 0; letter-spacing: -0.03em;">
                Detail & Profil Operasional Mesin
            </h1>
            <div style="font-size: 0.78rem; font-weight: 700; color: #6B6259; text-transform: uppercase; letter-spacing: 0.08em;">
                // MONITORING TELEMETRI · BEBAN DAYA AKTIF & STANDBY
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_c2:
    agg_selection = st.radio(
        "Agregasi Waktu",
        options=["Per Jam", "Per Hari"],
        horizontal=True,
        label_visibility="collapsed",
    )

# ---------------------------------------------------------------------------
# Panel Filter: Pilih Mesin & Rentang Tanggal
# ---------------------------------------------------------------------------
filter_card_c1, filter_card_c2 = st.columns([1.6, 2.4])

with filter_card_c1:
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

with filter_card_c2:
    try:
        def_start, def_end = get_data_range(selected_machine_id)
    except Exception:
        def_start = datetime(2026, 11, 1)
        def_end = datetime(2026, 11, 3, 23, 0)

    date_range_input = st.date_input(
        "Rentang Tanggal Sensor",
        value=(def_start.date(), def_end.date()),
        min_value=datetime(2020, 1, 1).date(),
        max_value=datetime(2035, 12, 31).date(),
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
total_readings = len(df_raw)
running_count = int((df_raw["status"] == "running").sum())
idle_count = int((df_raw["status"] == "idle").sum())
total_energy_kwh = float(df_raw["energy_kwh"].sum())
avg_power_kw = float(df_raw["power_kw"].mean())
rated_kw = float(current_machine.get("rated_power_kw", 0))
pct_run = (running_count / total_readings * 100) if total_readings else 0.0

# ---------------------------------------------------------------------------
# Kartu KPI Mesin (Gaya Velora)
# ---------------------------------------------------------------------------
spec_c1, spec_c2, spec_c3, spec_c4 = st.columns(4)

with spec_c1:
    st.markdown(
        f"""
        <div class="kpi-card-velora">
            <div class="kpi-label">ID & Tipe Mesin</div>
            <div>
                <span class="kpi-val" style="font-size:1.6rem;">{current_machine.get("machine_id", "-")}</span>
                <span class="kpi-unit">({current_machine.get("type", "-")})</span>
            </div>
            <div class="kpi-sub" style="color:#6B6259;">
                <span>Lini: <b>{current_machine.get("line", "-")}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with spec_c2:
    st.markdown(
        f"""
        <div class="kpi-card-velora">
            <div class="kpi-label">Total Energi Terpakai</div>
            <div>
                <span class="kpi-val">{total_energy_kwh:,.1f}</span>
                <span class="kpi-unit">kWh</span>
            </div>
            <div class="kpi-sub">
                <span class="badge-pill-green">Akumulasi {total_readings} jam</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with spec_c3:
    st.markdown(
        f"""
        <div class="kpi-card-velora">
            <div class="kpi-label">Rata-rata Daya Listrik</div>
            <div>
                <span class="kpi-val">{avg_power_kw:.1f}</span>
                <span class="kpi-unit">kW</span>
            </div>
            <div class="kpi-sub">
                <span class="badge-pill-orange">Rated {rated_kw:.0f} kW</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with spec_c4:
    st.markdown(
        f"""
        <div class="kpi-card-velora">
            <div class="kpi-label">Waktu Operasional</div>
            <div>
                <span class="kpi-val">{running_count}</span>
                <span class="kpi-unit">Jam Aktif</span>
            </div>
            <div class="kpi-sub">
                <span class="badge-pill-green">{pct_run:.1f}% Running</span>
                <span style="color:#6B6259;">· {idle_count}j Idle</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Bagian Tengah: Donut Gauge Efisiensi (Kiri) & Kurva Time-Series (Kanan)
# ---------------------------------------------------------------------------
mid_c1, mid_c2 = st.columns([1.05, 1.95])

with mid_c1:
    st.markdown(
        """
        <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04); height:100%;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <div style="font-weight:800; font-size:1.1rem; color:#1F1A17;">Utilisasi Mesin</div>
                <span class="badge-pill-green">Aktif</span>
            </div>
            <div style="font-size:0.75rem; color:#6B6259; font-weight:600; margin-bottom:10px;">Rasio Operasional vs Standby</div>
        """,
        unsafe_allow_html=True,
    )

    # Render Circular Progress Donut ala 'Battery Storage' di Gambar 2 & 4
    donut_fig = create_donut_gauge(
        pct=pct_run,
        center_text=f"{int(round(pct_run))}%",
        sub_text="Running Ratio",
        color="#E8590C",
    )
    st.plotly_chart(donut_fig, use_container_width=True)

    st.markdown(
        f"""
        <div style="display:flex; flex-direction:column; gap:10px; border-top:1px solid #EFE5D6; padding-top:14px;">
            <div style="display:flex; justify-content:space-between; font-size:0.84rem;">
                <span style="color:#6B6259;">Daya Terpasang</span>
                <span style="font-weight:700; color:#1F1A17;">{rated_kw:.1f} kW</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.84rem;">
                <span style="color:#6B6259;">Beban Rata-rata</span>
                <span style="font-weight:700; color:#E8590C;">{avg_power_kw:.1f} kW</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.84rem;">
                <span style="color:#6B6259;">Efisiensi Muatan</span>
                <span style="font-weight:700; color:#16A34A;">{(avg_power_kw / rated_kw * 100 if rated_kw else 0):.1f}%</span>
            </div>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with mid_c2:
    if agg_selection == "Per Jam":
        df_chart = aggregate_hourly(raw_rows)
        df_raw["hour"] = df_raw["timestamp"].dt.floor("h")
        status_lookup = df_raw.groupby("hour")["status"].first().to_dict()
        df_chart["status"] = df_chart["timestamp"].map(status_lookup).fillna("idle")

        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div>
                        <h3 style="margin:0; font-size:1.15rem; font-weight:800; color:#1F1A17;">Kurva Beban Daya & Energi</h3>
                        <div style="font-size:0.75rem; color:#6B6259; font-weight:600;">Time-series per jam dengan status operasional</div>
                    </div>
                    <div style="display:flex; gap:14px; font-size:0.78rem; font-weight:700;">
                        <span style="display:flex; align-items:center; gap:5px; color:#16A34A;">
                            <span style="width:8px; height:8px; background:#16A34A; border-radius:50%;"></span> Running
                        </span>
                        <span style="display:flex; align-items:center; gap:5px; color:#E8590C;">
                            <span style="width:8px; height:8px; background:#E8590C; border-radius:50%;"></span> Idle
                        </span>
                    </div>
                </div>
            """,
            unsafe_allow_html=True,
        )

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # 1. Daya (kW) - Spline Area
        fig.add_trace(
            go.Scatter(
                x=df_chart["timestamp"],
                y=df_chart["power_kw"],
                mode="lines",
                name="Daya Listrik (kW)",
                line=dict(color="#E8590C", width=2.5, shape="spline"),
                fill="tozeroy",
                fillcolor="rgba(232, 89, 12, 0.06)",
                hovertemplate="<b>%{x}</b><br>Daya: <b>%{y:.2f} kW</b><extra></extra>",
            ),
            secondary_y=False,
        )

        # 2. Energi (kWh) - Dot Line
        fig.add_trace(
            go.Scatter(
                x=df_chart["timestamp"],
                y=df_chart["energy_kwh"],
                mode="lines",
                name="Energi (kWh)",
                line=dict(color="#F2C230", width=2, dash="dot"),
                hovertemplate="<b>%{x}</b><br>Energi: <b>%{y:.2f} kWh</b><extra></extra>",
            ),
            secondary_y=True,
        )

        # 3. Running Markers (Hijau)
        df_running = df_chart[df_chart["status"] == "running"]
        if not df_running.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_running["timestamp"],
                    y=df_running["power_kw"],
                    mode="markers",
                    name="Running",
                    marker=dict(color="#16A34A", size=8, line=dict(color="#15803D", width=1.5)),
                    hovertemplate="🟢 <b>Running</b><br>Daya: %{y:.2f} kW<extra></extra>",
                ),
                secondary_y=False,
            )

        # 4. Idle Markers (Oranye)
        df_idle = df_chart[df_chart["status"] == "idle"]
        if not df_idle.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_idle["timestamp"],
                    y=df_idle["power_kw"],
                    mode="markers",
                    name="Idle",
                    marker=dict(color="#E8590C", size=8, symbol="diamond", line=dict(color="#C2410C", width=1.5)),
                    hovertemplate="🟠 <b>Idle</b><br>Daya: %{y:.2f} kW<extra></extra>",
                ),
                secondary_y=False,
            )

        fig.update_xaxes(title_text="")
        fig.update_yaxes(title_text="Daya (kW)", secondary_y=False)
        fig.update_yaxes(title_text="Energi (kWh)", secondary_y=True)
        style_plotly_fig(fig, height=360)
        fig.update_layout(
            hovermode="x unified",
            showlegend=False,
            margin=dict(l=20, r=20, t=10, b=30),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

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
            <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04);">
                <h3 style="margin:0 0 10px 0; font-size:1.15rem; font-weight:800; color:#1F1A17;">
                    Konsumsi Harian & Rata-rata Daya Listrik
                </h3>
            """,
            unsafe_allow_html=True,
        )

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Batang Total Energi Harian
        fig.add_trace(
            go.Bar(
                x=df_chart["date"],
                y=df_chart["energy_kwh"],
                name="Total Energi (kWh)",
                marker=dict(color="#E8590C", line=dict(color="rgba(31,26,23,0.08)", width=1)),
                opacity=0.9,
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
                line=dict(color="#F2C230", width=3),
                marker=dict(size=9, color="#D4A018", line=dict(color="#1F1A17", width=1.5)),
                hovertemplate="<b>Tanggal %{x}</b><br>Rata-rata Daya: %{y:.2f} kW<extra></extra>",
            ),
            secondary_y=True,
        )

        fig.update_xaxes(title_text="")
        fig.update_yaxes(title_text="Total Energi (kWh)", secondary_y=False)
        fig.update_yaxes(title_text="Rata-rata Daya (kW)", secondary_y=True)
        style_plotly_fig(fig, height=360)
        fig.update_layout(
            hovermode="x unified",
            showlegend=False,
            margin=dict(l=20, r=20, t=10, b=30),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Tabel Rincian Data Sensor (Expander)
# ---------------------------------------------------------------------------
with st.expander("🔍 Lihat Rincian Data Sensor (Tabel)"):
    st.dataframe(
        df_chart,
        use_container_width=True,
        hide_index=True,
    )

