import sys
from pathlib import Path
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

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
    )
    from frontend.ui import (
        apply_theme,
        style_plotly_fig,
    )
except ImportError:
    from api_client import (
        get_machines,
        get_energy,
        get_data_range,
        to_dataframe,
    )
    from ui import (
        apply_theme,
        style_plotly_fig,
    )

try:
    st.set_page_config(
        page_title="Detail Mesin - Smart Factory Energy Management",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

apply_theme()

WIB_TZ = ZoneInfo("Asia/Jakarta")
UTC_TZ = ZoneInfo("UTC")

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
    st.warning("Tidak ada mesin yang terdaftar di database.")
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
# Panel Filter: Pilih Mesin & Rentang Tanggal (Default 7 Hari Terakhir WIB)
# ---------------------------------------------------------------------------
filter_c1, filter_c2 = st.columns([1.6, 2.4])

with filter_c1:
    machine_map = {
        m["machine_id"]: f"{m['machine_id']} - {m['name']} ({m.get('line', 'Lini')})"
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
        def_start_raw, def_end_raw = get_data_range(selected_machine_id)
        if def_end_raw.tzinfo is None:
            def_end_wib = def_end_raw.replace(tzinfo=UTC_TZ).astimezone(WIB_TZ)
        else:
            def_end_wib = def_end_raw.astimezone(WIB_TZ)
        # Default rentang: 7 hari terakhir dari akhir data asli
        init_end_date = def_end_wib.date()
        init_start_date = init_end_date - timedelta(days=6)
    except Exception:
        init_start_date = datetime(2026, 6, 24).date()
        init_end_date = datetime(2026, 6, 30).date()

    date_range_input = st.date_input(
        "Rentang Tanggal Sensor (WIB)",
        value=(init_start_date, init_end_date),
        min_value=datetime(2020, 1, 1).date(),
        max_value=datetime(2035, 12, 31).date(),
    )

if not isinstance(date_range_input, (list, tuple)) or len(date_range_input) != 2:
    st.info("ℹ️ Silakan tentukan tanggal awal dan tanggal akhir pada filter kalender.")
    st.stop()

start_date, end_date = date_range_input
if start_date > end_date:
    st.error("Tanggal awal tidak boleh melebihi tanggal akhir.")
    st.stop()

# Konversi filter WIB ke UTC untuk query backend
wib_start = datetime.combine(start_date, time.min, tzinfo=WIB_TZ)
wib_end   = datetime.combine(end_date, time.max.replace(microsecond=0), tzinfo=WIB_TZ)
query_start_utc = wib_start.astimezone(UTC_TZ).replace(tzinfo=None)
query_end_utc   = wib_end.astimezone(UTC_TZ).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Pengambilan Data Energi Mesin (Cached)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def fetch_machine_telemetry(mid: str, s_iso: str, e_iso: str) -> list[dict]:
    s = datetime.fromisoformat(s_iso)
    e = datetime.fromisoformat(e_iso)
    return get_energy(mid, start=s, end=e, limit=10000, page_all=True, timeout=45)


try:
    with st.spinner(f"Memuat telemetri {selected_machine_id}..."):
        raw_rows = fetch_machine_telemetry(selected_machine_id, query_start_utc.isoformat(), query_end_utc.isoformat())
except RuntimeError as exc:
    st.error(f"🚨 **Gagal memuat data energi:**\n\n`{exc}`", icon="🚫")
    st.stop()
except Exception as exc:
    st.error(f"Terjadi kesalahan saat memproses data: {exc}", icon="⚠️")
    st.stop()

if not raw_rows:
    st.warning("Tidak ada data pembacaan sensor pada rentang tanggal dan mesin yang dipilih.")
    st.stop()

# Konversi dan filter tanggal lokal WIB
df_raw = pd.DataFrame(raw_rows)
df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
if df_raw["timestamp"].dt.tz is None:
    df_raw["timestamp"] = df_raw["timestamp"].dt.tz_localize("UTC")
df_raw["timestamp_wib"] = df_raw["timestamp"].dt.tz_convert("Asia/Jakarta")

df_raw = df_raw[
    (df_raw["timestamp_wib"].dt.date >= start_date) &
    (df_raw["timestamp_wib"].dt.date <= end_date)
].copy()

if df_raw.empty:
    st.warning("Tidak ada data sensor pada rentang tanggal yang dipilih.")
    st.stop()

total_readings = len(df_raw)
running_count = int((df_raw["status"] == "running").sum())
idle_count = int((df_raw["status"] == "idle").sum())
off_count = int((df_raw["status"] == "off").sum())

total_energy_kwh = float(df_raw["energy_kwh"].sum())
avg_power_kw = float(df_raw["power_kw"].mean())
peak_power_kw = float(df_raw["power_kw"].max())
rated_kw = float(current_machine.get("rated_power_kw", 0))

# ---------------------------------------------------------------------------
# Perhitungan Durasi Jam Nyata (Berdasarkan Interval Selisih Timestamp)
# ---------------------------------------------------------------------------
if len(df_raw) > 1:
    diffs = df_raw["timestamp"].sort_values().diff().dropna()
    median_sec = diffs.dt.total_seconds().median()
    interval_hours = median_sec / 3600.0 if median_sec and median_sec > 0 else (5.0 / 60.0)
else:
    interval_hours = 5.0 / 60.0

total_duration_hours = total_readings * interval_hours
running_hours = running_count * interval_hours
idle_hours = idle_count * interval_hours
off_hours = off_count * interval_hours

# Status mesin terakhir berdasarkan WIB
last_row = df_raw.sort_values("timestamp_wib").iloc[-1]
last_status = last_row["status"]
last_ts_wib = last_row["timestamp_wib"].strftime("%d %b %Y, %H:%M")

STATUS_BADGE = {
    "running": '<span class="badge-pill-green">Running</span>',
    "idle": '<span class="badge-pill-orange">Idle</span>',
    "off": '<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(107,98,89,0.10);color:#6B6259;border-radius:20px;padding:3px 10px;font-size:0.75rem;font-weight:700;">Off</span>',
}
status_badge_html = STATUS_BADGE.get(last_status, f'<span class="badge-pill-orange">{last_status}</span>')


# ---------------------------------------------------------------------------
# Kartu KPI Mesin (4 kolom dengan tinggi kartu sama)
# ---------------------------------------------------------------------------
spec_c1, spec_c2, spec_c3, spec_c4 = st.columns(4)

with spec_c1:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora" style="height:100%;">',
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
            '<div class="kpi-card-velora" style="height:100%;">',
            '<div class="kpi-label">Total Energi Terpakai</div>',
            '<div>',
            f'<span class="kpi-val">{total_energy_kwh:,.1f}</span>',
            '<span class="kpi-unit">kWh</span>',
            '</div>',
            f'<div class="kpi-sub"><span class="badge-pill-green">Akumulasi {total_duration_hours:.1f} jam</span> <span style="color:#8C827A;font-size:11px;">({total_readings:,} data)</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with spec_c3:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora" style="height:100%;">',
            '<div class="kpi-label">Daya Rata-rata / Puncak</div>',
            '<div>',
            f'<span class="kpi-val">{avg_power_kw:.1f}</span>',
            '<span class="kpi-unit">kW</span>',
            '</div>',
            f'<div class="kpi-sub"><span class="badge-pill-orange">Puncak {peak_power_kw:.1f} kW</span> <span style="color:#6B6259;font-size:12px;">/ Rated {rated_kw:.0f} kW</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with spec_c4:
    st.markdown(
        "".join([
            '<div class="kpi-card-velora" style="height:100%;">',
            '<div class="kpi-label">Status Terakhir (WIB)</div>',
            '<div style="display:flex;align-items:center;gap:10px;margin:4px 0;">',
            status_badge_html,
            '</div>',
            f'<div class="kpi-sub" style="color:#6B6259;font-size:12px;">{last_ts_wib} WIB · {running_hours:.1f}j Running / {idle_hours:.1f}j Idle</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Visualisasi Grafik Time-Series Daya
# Satu kurva power_kw, tanpa marker, status idle ditandai shading tipis
# ---------------------------------------------------------------------------
chart_card_header = "".join([
    '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04); margin-bottom:1.2rem;">',
    '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">',
    '<div>',
    f'<h3 style="margin:0; font-size:1.15rem; font-weight:800; color:#1F1A17;">Profil Beban Daya - {selected_machine_id}</h3>',
    f'<div style="font-size:12px; color:#6B6259; font-weight:600;">{current_machine.get("name", "")} · Kapasitas Rated {rated_kw:.0f} kW</div>',
    '</div>',
    '<div style="display:flex; gap:16px; font-size:12px; font-weight:600;">',
    '<span style="display:flex; align-items:center; gap:5px; color:#E8590C;"><span style="width:12px; height:3px; background:#E8590C; border-radius:2px;"></span> Beban Daya (kW)</span>',
    '<span style="display:flex; align-items:center; gap:5px; color:#C4B5A5;"><span style="width:10px; height:10px; background:rgba(200,190,180,0.35); border-radius:2px;"></span> Kondisi Standby (Idle)</span>',
    '</div>',
    '</div>',
])
st.markdown(chart_card_header, unsafe_allow_html=True)

if agg_selection == "Per Jam":
    df_raw["hour_wib"] = df_raw["timestamp_wib"].dt.floor("h")
    # Agregasi per jam: rata-rata kW
    df_chart = df_raw.groupby("hour_wib", as_index=False).agg({
        "power_kw": "mean",
        "energy_kwh": "sum",
        "status": lambda s: "idle" if (s == "idle").mean() > 0.5 else "running",
    }).sort_values("hour_wib")

    fig = go.Figure()

    # Identifikasi periode idle untuk shading background
    idle_blocks = []
    current_block = []
    for _, row in df_chart.iterrows():
        if row["status"] == "idle":
            current_block.append(row["hour_wib"])
        else:
            if current_block:
                idle_blocks.append((current_block[0], current_block[-1]))
                current_block = []
    if current_block:
        idle_blocks.append((current_block[0], current_block[-1]))

    for b_start, b_end in idle_blocks:
        x1_val = b_end + pd.Timedelta(hours=1) if b_start == b_end else b_end
        fig.add_shape(
            type="rect",
            x0=b_start,
            x1=x1_val,
            y0=0,
            y1=1,
            yref="paper",
            fillcolor="rgba(196, 181, 165, 0.20)",
            layer="below",
            line_width=0,
        )

    # Satu kurva power_kw tanpa marker
    fig.add_trace(
        go.Scatter(
            x=df_chart["hour_wib"],
            y=df_chart["power_kw"],
            mode="lines",
            name="Daya Rata-rata (kW)",
            line=dict(color="#E8590C", width=2.2, shape="spline"),
            fill="tozeroy",
            fillcolor="rgba(232, 89, 12, 0.05)",
            hovertemplate="<b>%{x|%d %b %Y, %H:00 WIB}</b><br>Daya: <b>%{y:.2f} kW</b><extra></extra>",
        )
    )

    style_plotly_fig(fig, height=330)
    fig.update_layout(
        margin=dict(l=20, r=20, t=10, b=30),
        xaxis=dict(title="", showgrid=True),
        yaxis=dict(title="Daya Rata-rata (kW)", showgrid=True),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

else:
    df_raw["date_wib"] = df_raw["timestamp_wib"].dt.date
    df_daily = df_raw.groupby("date_wib", as_index=False).agg({
        "energy_kwh": "sum",
        "power_kw": "mean",
    }).sort_values("date_wib")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df_daily["date_wib"],
            y=df_daily["energy_kwh"],
            name="Total Energi (kWh)",
            marker=dict(color="#E8590C", cornerradius=6),
            hovertemplate="<b>%{x|%d %b %Y}</b><br>Energi: <b>%{y:,.1f} kWh</b><extra></extra>",
        )
    )

    style_plotly_fig(fig, height=330)
    fig.update_layout(
        margin=dict(l=20, r=20, t=10, b=30),
        xaxis=dict(title="", showgrid=False),
        yaxis=dict(title="Energi Harian (kWh)", showgrid=True),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tabel Riwayat Telemetri
# ---------------------------------------------------------------------------
st.markdown(
    "".join([
        '<div style="font-weight:800; font-size:1.1rem; color:#1F1A17; margin-bottom:4px;">Riwayat Telemetri Pembacaan Sensor</div>',
        '<div style="font-size:0.75rem; color:#6B6259; font-weight:600; margin-bottom:10px;">Zona Waktu WIB · Kolom machine_id ditiadakan karena telah tertera pada judul</div>',
    ]),
    unsafe_allow_html=True,
)

available_cols = ["timestamp_wib", "power_kw", "energy_kwh", "status"]
col_rename = {
    "timestamp_wib": "Waktu (WIB)",
    "power_kw": "Daya (kW)",
    "energy_kwh": "Energi (kWh)",
    "status": "Status",
}

if "voltage" in df_raw.columns:
    available_cols.append("voltage")
    col_rename["voltage"] = "Tegangan (V)"
if "current" in df_raw.columns:
    available_cols.append("current")
    col_rename["current"] = "Arus (A)"

df_table = df_raw[available_cols].copy()
df_table = df_table.sort_values("timestamp_wib", ascending=False).reset_index(drop=True)
df_table["timestamp_wib"] = df_table["timestamp_wib"].dt.strftime("%d %b %Y, %H:%M WIB")
df_table["status"] = df_table["status"].str.capitalize()
df_table = df_table.rename(columns=col_rename)

# Tampilkan maksimal 100 baris terbaru untuk responsivitas render
st.dataframe(
    df_table.head(100),
    use_container_width=True,
    hide_index=True,
)
if len(df_table) > 100:
    st.caption(f"Menampilkan 100 dari total {len(df_table):,} pembacaan sensor pada rentang tanggal terpilih.")
