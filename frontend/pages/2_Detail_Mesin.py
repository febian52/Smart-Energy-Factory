import sys
from pathlib import Path
from datetime import datetime, time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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
# Header Halaman & Segmented Filter Control (judul kiri, kontrol kanan)
# ---------------------------------------------------------------------------
header_c1, header_c2 = st.columns([2.2, 1.2])

with header_c1:
    st.markdown(
        "".join([
            '<div style="margin-bottom: 12px;">',
            '<h1 style="color: #1F1A17; font-size: 2.2rem; font-weight: 800; margin: 0 0 4px 0; letter-spacing: -0.03em;">',
            'Detail &amp; Profil Operasional Mesin',
            '</h1>',
            '<div style="font-size: 0.78rem; font-weight: 700; color: #6B6259; text-transform: uppercase; letter-spacing: 0.08em;">',
            '// MONITORING TELEMETRI · BEBAN DAYA AKTIF &amp; STANDBY',
            '</div>',
            '</div>',
        ]),
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
filter_c1, filter_c2 = st.columns([1.6, 2.4])

with filter_c1:
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

with filter_c2:
    try:
        def_start, def_end = get_data_range(selected_machine_id)
    except Exception:
        def_start = datetime(2026, 11, 1)
        def_end = datetime(2026, 11, 3, 23, 0)

    # Tampilkan label rentang tanggal dalam WIB
    def_start_wib = pd.Timestamp(def_start, tz="UTC").tz_convert("Asia/Jakarta").date()
    def_end_wib = pd.Timestamp(def_end, tz="UTC").tz_convert("Asia/Jakarta").date() if getattr(def_end, "tzinfo", None) else def_end.date()

    date_range_input = st.date_input(
        "Rentang Tanggal Sensor (WIB)",
        value=(def_start_wib, def_end_wib),
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
        f"pada rentang tanggal {start_date} s/d {end_date} (WIB)."
    )
    st.stop()

if len(raw_rows) >= 10000:
    st.warning("⚠️ **Peringatan Batas Data:** Pembacaan mencapai batas 10.000 baris. Beberapa data mungkin terpotong.")

df_raw = to_dataframe(raw_rows)

# Konversi timestamp ke WIB secara eksplisit
if df_raw["timestamp"].dt.tz is None:
    df_raw["timestamp"] = df_raw["timestamp"].dt.tz_localize("UTC")
df_raw["timestamp_wib"] = df_raw["timestamp"].dt.tz_convert("Asia/Jakarta")

total_readings = len(df_raw)
running_count = int((df_raw["status"] == "running").sum())
idle_count = int((df_raw["status"] == "idle").sum())
total_energy_kwh = float(df_raw["energy_kwh"].sum())
avg_power_kw = float(df_raw["power_kw"].mean())
peak_power_kw = float(df_raw["power_kw"].max())
rated_kw = float(current_machine.get("rated_power_kw", 0))
pct_run = (running_count / total_readings * 100) if total_readings else 0.0
pct_idle = (idle_count / total_readings * 100) if total_readings else 0.0

# Status mesin terakhir berdasarkan WIB
last_status = df_raw.sort_values("timestamp_wib").iloc[-1]["status"] if not df_raw.empty else "—"
last_ts_wib = df_raw.sort_values("timestamp_wib").iloc[-1]["timestamp_wib"].strftime("%d %b %Y, %H:00") if not df_raw.empty else "—"

STATUS_BADGE = {
    "running": '<span class="badge-pill-green">Running</span>',
    "idle": '<span class="badge-pill-orange">Idle</span>',
    "off": '<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(107,98,89,0.10);color:#6B6259;border-radius:20px;padding:3px 10px;font-size:0.75rem;font-weight:700;">Off</span>',
}
status_badge_html = STATUS_BADGE.get(last_status, f'<span class="badge-pill-orange">{last_status}</span>')

# ---------------------------------------------------------------------------
# Kartu KPI Mesin (4 kolom)
# ---------------------------------------------------------------------------
spec_c1, spec_c2, spec_c3, spec_c4 = st.columns(4)

with spec_c1:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora">',
            '<div class="kpi-label">ID &amp; Tipe Mesin</div>',
            '<div>',
            f'<span class="kpi-val" style="font-size:1.6rem;">{current_machine.get("machine_id", "-")}</span>',
            f'<span class="kpi-unit">({current_machine.get("type", "-")})</span>',
            '</div>',
            f'<div class="kpi-sub" style="color:#6B6259;">Lini: <b>{current_machine.get("line", "-")}</b></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with spec_c2:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora">',
            '<div class="kpi-label">Total Energi Terpakai</div>',
            '<div>',
            f'<span class="kpi-val">{total_energy_kwh:,.1f}</span>',
            '<span class="kpi-unit">kWh</span>',
            '</div>',
            f'<div class="kpi-sub"><span class="badge-pill-green">Akumulasi {total_readings} jam</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with spec_c3:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora">',
            '<div class="kpi-label">Daya Rata-rata / Puncak</div>',
            '<div>',
            f'<span class="kpi-val">{avg_power_kw:.1f}</span>',
            '<span class="kpi-unit">kW rata-rata</span>',
            '</div>',
            f'<div class="kpi-sub"><span class="badge-pill-orange">Puncak {peak_power_kw:.1f} kW</span> <span style="color:#6B6259;font-size:12px;">/ Rated {rated_kw:.0f} kW</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with spec_c4:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora">',
            '<div class="kpi-label">Status Terakhir (WIB)</div>',
            '<div style="display:flex;align-items:center;gap:10px;margin:4px 0;">',
            status_badge_html,
            '</div>',
            f'<div class="kpi-sub" style="color:#6B6259;font-size:12px;">{last_ts_wib} WIB · {running_count}j Running / {idle_count}j Idle</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Bagian Tengah: Donut Gauge (Kiri) & Kurva Time-Series (Kanan)
# ---------------------------------------------------------------------------
mid_c1, mid_c2 = st.columns([1.05, 1.95])

with mid_c1:
    st.markdown(
        "".join([
            '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04); height:100%;">',
            '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">',
            '<div style="font-weight:800; font-size:1.1rem; color:#1F1A17;">Utilisasi Mesin</div>',
            '<span class="badge-pill-green">Aktif</span>',
            '</div>',
            '<div style="font-size:0.75rem; color:#6B6259; font-weight:600; margin-bottom:10px;">Rasio Operasional vs Standby</div>',
        ]),
        unsafe_allow_html=True,
    )

    donut_fig = create_donut_gauge(
        pct=pct_run,
        center_text=f"{int(round(pct_run))}%",
        sub_text="Running Ratio",
        color="#E8590C",
    )
    st.plotly_chart(donut_fig, use_container_width=True)

    load_pct = (avg_power_kw / rated_kw * 100) if rated_kw else 0
    st.markdown(
        "".join([
            '<div style="display:flex; flex-direction:column; gap:10px; border-top:1px solid #EFE5D6; padding-top:14px;">',
            '<div style="display:flex; justify-content:space-between; font-size:0.84rem;">',
            '<span style="color:#6B6259;">Daya Terpasang</span>',
            f'<span style="font-weight:700; color:#1F1A17;">{rated_kw:.1f} kW</span>',
            '</div>',
            '<div style="display:flex; justify-content:space-between; font-size:0.84rem;">',
            '<span style="color:#6B6259;">Rata-rata Periode</span>',
            f'<span style="font-weight:700; color:#E8590C;">{avg_power_kw:.1f} kW</span>',
            '</div>',
            '<div style="display:flex; justify-content:space-between; font-size:0.84rem;">',
            '<span style="color:#6B6259;">Efisiensi Muatan</span>',
            f'<span style="font-weight:700; color:#16A34A;">{load_pct:.1f}%</span>',
            '</div>',
            '</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Chart Per Jam: SATU kurva power_kw + shading idle
# ---------------------------------------------------------------------------
with mid_c2:
    if agg_selection == "Per Jam":
        df_chart = aggregate_hourly(raw_rows)

        # Pastikan timestamp dalam WIB sebelum digambar
        if "timestamp" in df_chart.columns:
            if df_chart["timestamp"].dt.tz is None:
                df_chart["timestamp"] = df_chart["timestamp"].dt.tz_localize("UTC")
            df_chart["timestamp"] = df_chart["timestamp"].dt.tz_convert("Asia/Jakarta")

        # Mapping status per jam (WIB)
        df_raw["hour_wib"] = df_raw["timestamp_wib"].dt.floor("h")
        status_lookup = df_raw.groupby("hour_wib")["status"].first().to_dict()
        df_chart["status"] = df_chart["timestamp"].map(status_lookup).fillna("idle")

        st.markdown(
            "".join([
                '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04);">',
                '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">',
                '<div>',
                '<h3 style="margin:0; font-size:1.15rem; font-weight:800; color:#1F1A17;">Kurva Beban Daya (kW)</h3>',
                '<div style="font-size:0.75rem; color:#6B6259; font-weight:600;">Time-series per jam · WIB · Area abu tipis = periode Idle</div>',
                '</div>',
                '<div style="display:flex; gap:14px; font-size:0.78rem; font-weight:700;">',
                '<span style="display:flex; align-items:center; gap:5px; color:#E8590C;">',
                '<span style="width:24px; height:3px; background:#E8590C; border-radius:2px; display:inline-block;"></span> Daya (kW)',
                '</span>',
                '<span style="display:flex; align-items:center; gap:5px; color:#6B6259;">',
                '<span style="width:12px; height:10px; background:rgba(107,98,89,0.10); border-radius:2px; display:inline-block;"></span> Idle',
                '</span>',
                '</div>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

        fig = go.Figure()

        # Satu kurva daya (kW) — tanpa marker
        fig.add_trace(
            go.Scatter(
                x=df_chart["timestamp"],
                y=df_chart["power_kw"],
                mode="lines",
                name="Daya (kW)",
                line=dict(color="#E8590C", width=2.5, shape="spline"),
                fill="tozeroy",
                fillcolor="rgba(232, 89, 12, 0.07)",
                hovertemplate="<b>%{x|%d %b %Y, %H:00} WIB</b><br>Daya: <b>%{y:.2f} kW</b><extra></extra>",
            )
        )

        # Shading periode idle sebagai vrect (highlight area, bukan marker titik)
        df_idle_hrs = df_chart[df_chart["status"] == "idle"]
        for _, row in df_idle_hrs.iterrows():
            t_start = row["timestamp"]
            t_end = t_start + pd.Timedelta(hours=1)
            fig.add_shape(
                type="rect",
                x0=t_start, x1=t_end,
                y0=0, y1=1,
                yref="paper",
                fillcolor="rgba(107, 98, 89, 0.06)",
                line_width=0,
                layer="below",
            )

        fig.update_xaxes(
            title_text="Waktu (WIB)",
            tickfont=dict(size=12, color="#6B6259"),
            title_font=dict(size=12, color="#6B6259"),
        )
        fig.update_yaxes(
            title_text="Daya (kW)",
            tickfont=dict(size=12, color="#6B6259"),
            title_font=dict(size=12, color="#6B6259"),
        )
        style_plotly_fig(fig, height=360)
        fig.update_layout(
            hovermode="x unified",
            showlegend=False,
            margin=dict(l=20, r=20, t=10, b=30),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    else:
        # Agregasi Harian — tampilkan bar energi + garis rata-rata daya
        df_chart = aggregate_daily(raw_rows)

        if "date" in df_chart.columns:
            pass  # aggregate_daily sudah dalam format date
        else:
            df_chart["date"] = df_chart["timestamp"].dt.date

        st.markdown(
            "".join([
                '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04);">',
                '<h3 style="margin:0 0 10px 0; font-size:1.15rem; font-weight:800; color:#1F1A17;">Konsumsi Harian (kWh) &amp; Rata-rata Daya (kW)</h3>',
            ]),
            unsafe_allow_html=True,
        )

        fig = go.Figure()

        # Batang total energi harian (kWh) — batang oranye
        fig.add_trace(
            go.Bar(
                x=df_chart["date"] if "date" in df_chart.columns else df_chart["timestamp"],
                y=df_chart["energy_kwh"],
                name="Total Energi (kWh)",
                marker=dict(color="#E8590C", line=dict(color="rgba(31,26,23,0.08)", width=1)),
                opacity=0.88,
                hovertemplate="<b>%{x}</b><br>Total Energi: %{y:.2f} kWh<extra></extra>",
            )
        )

        # Garis rata-rata daya harian (kW) — kuning hangat, tanpa marker
        fig.add_trace(
            go.Scatter(
                x=df_chart["date"] if "date" in df_chart.columns else df_chart["timestamp"],
                y=df_chart["power_kw"],
                name="Rata-rata Daya (kW)",
                mode="lines",
                line=dict(color="#F2C230", width=2.5, shape="spline"),
                hovertemplate="<b>%{x}</b><br>Rata-rata Daya: %{y:.2f} kW<extra></extra>",
                yaxis="y2",
            )
        )

        style_plotly_fig(fig, height=360)
        fig.update_layout(
            hovermode="x unified",
            showlegend=False,
            margin=dict(l=20, r=20, t=10, b=30),
            yaxis=dict(title="Total Energi (kWh)", tickfont=dict(size=12, color="#6B6259")),
            yaxis2=dict(
                title="Rata-rata Daya (kW)",
                overlaying="y",
                side="right",
                tickfont=dict(size=12, color="#F2C230"),
                title_font=dict(color="#F2C230"),
                showgrid=False,
            ),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Tabel Rincian Data Sensor (Expander) — hapus machine_id & power_factor
# ---------------------------------------------------------------------------
with st.expander("🔍 Lihat Rincian Data Sensor (Tabel)"):
    display_cols = ["timestamp_wib", "power_kw", "energy_kwh", "status"]
    if "voltage" in df_raw.columns:
        display_cols.append("voltage")
    if "current" in df_raw.columns:
        display_cols.append("current")

    df_display = df_raw[display_cols].copy()
    df_display = df_display.rename(columns={
        "timestamp_wib": "Waktu (WIB)",
        "power_kw": "Daya (kW)",
        "energy_kwh": "Energi (kWh)",
        "status": "Status",
        "voltage": "Tegangan (V)",
        "current": "Arus (A)",
    })
    # Format timestamp agar mudah dibaca
    df_display["Waktu (WIB)"] = df_display["Waktu (WIB)"].dt.strftime("%d %b %Y, %H:%M WIB")

    st.dataframe(df_display, use_container_width=True, hide_index=True)
