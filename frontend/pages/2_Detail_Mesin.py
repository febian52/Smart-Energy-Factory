import io
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
        format_id_num,
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
        format_id_num,
    )

try:
    st.set_page_config(
        page_title="Detail Mesin - Smart Energy Factory",
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
# Header Halaman & Segmented Filter Control
# ---------------------------------------------------------------------------
header_c1, header_c2 = st.columns([2.2, 1.2])

with header_c1:
    st.markdown(
        "".join([
            '<div style="margin-bottom: 14px;">',
            '<h1 style="color: #111827; font-size: 1.65rem; font-weight: 700; margin: 0 0 4px 0; letter-spacing: -0.02em;">',
            'Detail &amp; Profil Operasional Mesin',
            '</h1>',
            '<div style="font-size: 12px; font-weight: 500; color: #6B7280; letter-spacing: 0.02em;">',
            'Monitoring telemetri sensor, profil beban daya aktif dan status operasional mesin',
            '</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with header_c2:
    st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)
    agg_selection = st.segmented_control(
        "Agregasi Waktu",
        options=["Per Jam", "Per Hari"],
        default="Per Jam",
        selection_mode="single",
        label_visibility="collapsed",
    ) or "Per Jam"

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

pct_run = (running_count / total_readings * 100) if total_readings > 0 else 0.0
pct_idle = (idle_count / total_readings * 100) if total_readings > 0 else 0.0
pct_off = (off_count / total_readings * 100) if total_readings > 0 else 0.0

# Status mesin terakhir berdasarkan WIB
last_row = df_raw.sort_values("timestamp_wib").iloc[-1]
last_status = last_row["status"]
last_ts_wib = last_row["timestamp_wib"].strftime("%d %b %Y, %H:%M")

STATUS_BADGE = {
    "running": '<span class="badge-pill-green">Running</span>',
    "idle": '<span class="badge-pill-amber">Idle</span>',
    "off": '<span class="badge-pill-grey">Off</span>',
}
status_badge_html = STATUS_BADGE.get(last_status, f'<span class="badge-pill-grey">{last_status}</span>')


# ---------------------------------------------------------------------------
# Kartu KPI Mesin (4 kolom dengan tinggi kartu sama, Dentexa Style)
# ---------------------------------------------------------------------------
spec_c1, spec_c2, spec_c3, spec_c4 = st.columns(4)

with spec_c1:
    st.markdown(
        "".join([
            '<div class="kpi-card-dentexa" style="height:100%;">',
            '<div class="kpi-label">ID &amp; Tipe Mesin</div>',
            '<div>',
            f'<span class="kpi-val" style="font-size:1.55rem;">{current_machine.get("machine_id", "-")}</span>',
            f'<span class="kpi-unit">({current_machine.get("type", "-")})</span>',
            '</div>',
            f'<div class="kpi-sub">Lini: <b style="color:#111827;">{current_machine.get("line", "-")}</b></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with spec_c2:
    st.markdown(
        "".join([
            '<div class="kpi-card-dentexa" style="height:100%;">',
            '<div class="kpi-label">Total Energi Terpakai</div>',
            '<div>',
            f'<span class="kpi-val">{format_id_num(total_energy_kwh, 1)}</span>',
            '<span class="kpi-unit">kWh</span>',
            '</div>',
            f'<div class="kpi-sub"><span class="badge-pill-green">Akumulasi {format_id_num(total_duration_hours, 1)} jam</span> <span style="color:#6B7280;font-size:12px;">({format_id_num(total_readings, 0)} data)</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with spec_c3:
    st.markdown(
        "".join([
            '<div class="kpi-card-dentexa" style="height:100%;">',
            '<div class="kpi-label">Daya Rata-rata / Puncak</div>',
            '<div>',
            f'<span class="kpi-val">{format_id_num(avg_power_kw, 1)}</span>',
            '<span class="kpi-unit">kW</span>',
            '</div>',
            f'<div class="kpi-sub"><span class="badge-pill-blue">Puncak {format_id_num(peak_power_kw, 1)} kW</span> <span style="color:#6B7280;font-size:12px;">/ Rated {format_id_num(rated_kw, 0)} kW</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

with spec_c4:
    st.markdown(
        "".join([
            '<div class="kpi-card-dentexa" style="height:100%;">',
            '<div class="kpi-label">Status Terakhir (WIB)</div>',
            '<div style="display:flex;align-items:center;gap:10px;margin:4px 0;">',
            status_badge_html,
            '</div>',
            f'<div class="kpi-sub">{last_ts_wib} WIB · {format_id_num(running_hours, 1)}j Run / {format_id_num(idle_hours, 1)}j Idle</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Visualisasi Grafik Time-Series Daya & Donut Rasio Utilisasi
# ---------------------------------------------------------------------------
with st.container(border=True):
    col_curve, col_donut = st.columns([2.0, 1.0])

    with col_curve:
        st.markdown(
            "".join([
                '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">',
                '<div>',
                f'<h3 style="margin:0; font-size:1.05rem; font-weight:700; color:#111827;">Profil Beban Daya - {selected_machine_id}</h3>',
                f'<div style="font-size:12px; color:#6B7280; font-weight:500;">{current_machine.get("name", "")} · Kapasitas Rated {format_id_num(rated_kw, 0)} kW</div>',
                '</div>',
                '<div style="display:flex; gap:16px; font-size:12px; font-weight:600;">',
                '<span style="display:flex; align-items:center; gap:6px; color:#1D6FF2;"><span style="width:12px; height:3px; background:#1D6FF2; border-radius:2px;"></span> Beban Daya (kW)</span>',
                '<span style="display:flex; align-items:center; gap:6px; color:#F59E0B;"><span style="width:10px; height:10px; background:rgba(245,158,11,0.25); border-radius:2px;"></span> Standby (Idle)</span>',
                '</div>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

        if agg_selection == "Per Jam":
            df_raw["hour_wib"] = df_raw["timestamp_wib"].dt.floor("h")
            df_chart = df_raw.groupby("hour_wib", as_index=False).agg({
                "power_kw": "mean",
                "energy_kwh": "sum",
                "status": lambda s: "idle" if (s == "idle").mean() > 0.5 else "running",
            }).sort_values("hour_wib")

            fig = go.Figure()

            # Shading periode idle tipis
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
                    fillcolor="rgba(245, 158, 11, 0.12)",
                    layer="below",
                    line_width=0,
                )

            # Kurva daya utama: Biru Dentexa #1D6FF2
            fig.add_trace(
                go.Scatter(
                    x=df_chart["hour_wib"],
                    y=df_chart["power_kw"],
                    mode="lines",
                    name="Daya Rata-rata (kW)",
                    line=dict(color="#1D6FF2", width=2.2, shape="spline"),
                    fill="tozeroy",
                    fillcolor="rgba(29, 111, 242, 0.06)",
                    hovertemplate="<b>%{x|%d %b %Y, %H:00 WIB}</b><br>Daya: <b>%{y:.2f} kW</b><extra></extra>",
                )
            )

            style_plotly_fig(fig, height=290)
            fig.update_layout(
                margin=dict(l=15, r=15, t=10, b=25),
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
                    marker=dict(color="#1D6FF2", cornerradius=6),
                    hovertemplate="<b>%{x|%d %b %Y}</b><br>Energi: <b>%{y:,.1f} kWh</b><extra></extra>",
                )
            )

            style_plotly_fig(fig, height=290)
            fig.update_layout(
                margin=dict(l=15, r=15, t=10, b=25),
                xaxis=dict(title="", showgrid=False),
                yaxis=dict(title="Energi Harian (kWh)", showgrid=True),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col_donut:
        st.markdown(
            "".join([
                '<div style="margin-bottom:8px;">',
                '<h3 style="margin:0; font-size:1.05rem; font-weight:700; color:#111827;">Rasio Operasional</h3>',
                '<div style="font-size:12px; color:#6B7280; font-weight:500;">Distribusi status mesin periode ini</div>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

        donut_ratio = go.Figure(
            go.Pie(
                labels=["Running", "Idle", "Off"],
                values=[running_hours, idle_hours, off_hours],
                hole=0.68,
                marker=dict(colors=["#16A34A", "#F59E0B", "#9CA3AF"], line=dict(color="#FFFFFF", width=2)),
                textinfo="none",
                hovertemplate="<b>%{label}</b><br>Durasi: %{value:,.1f} jam (%{percent:.1%})<extra></extra>",
                sort=False,
                direction="clockwise",
            )
        )
        donut_ratio.add_annotation(
            text=f"<b style='font-size:22px;color:#111827;'>{pct_run:.0f}%</b><br><span style='font-size:11px;color:#16A34A;font-weight:600;'>Running</span>",
            showarrow=False,
            font=dict(family="Inter, sans-serif"),
            x=0.5,
            y=0.5,
        )
        donut_ratio.update_layout(
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.05,
                xanchor="center",
                x=0.5,
                font=dict(size=11, color="#6B7280"),
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=210,
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(donut_ratio, use_container_width=True, config={"displayModeBar": False})

        st.markdown(
            f"""
            <div style="font-size:11px; color:#6B7280; line-height:1.6; border-top:1px solid #E5E8EF; padding-top:8px;">
                <div>• Running: <b>{format_id_num(running_hours, 1)} jam</b> ({format_id_num(pct_run, 1)}%)</div>
                <div>• Standby (Idle): <b>{format_id_num(idle_hours, 1)} jam</b> ({format_id_num(pct_idle, 1)}%)</div>
                <div>• Mati (Off): <b>{format_id_num(off_hours, 1)} jam</b> ({format_id_num(pct_off, 1)}%)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("<div style='margin:1.4rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tabel Riwayat Telemetri Sensor (Expander, Default Tertutup)
# ---------------------------------------------------------------------------
with st.expander("Riwayat Telemetri Sensor", expanded=False):
    exp_c1, exp_c2, exp_c3 = st.columns([2.4, 1.0, 1.3])
    with exp_c1:
        st.markdown(
            '<div style="font-size:12px; color:#6B7280; font-weight:500; padding-top:8px;">'
            'Data pembacaan telemetri berurutan (WIB) &middot; Maksimal 50 baris terbaru'
            '</div>',
            unsafe_allow_html=True,
        )
    with exp_c3:
        agg_tbl = (
            st.segmented_control(
                "Agregasi Tabel Telemetri",
                options=["Per Jam", "Per 5 Menit"],
                default="Per Jam",
                selection_mode="single",
                label_visibility="collapsed",
                key="tbl_agg_mode",
            )
            or "Per Jam"
        )

    available_cols = ["timestamp_wib", "power_kw", "energy_kwh", "status"]
    if agg_tbl == "Per Jam":
        df_tbl = df_raw[available_cols].copy()
        df_tbl["bucket"] = df_tbl["timestamp_wib"].dt.floor("h")
        df_tbl = (
            df_tbl.groupby("bucket", as_index=False)
            .agg(
                power_kw=("power_kw", "mean"),
                energy_kwh=("energy_kwh", "sum"),
                status=("status", lambda s: s.mode().iloc[0] if len(s) > 0 else "off"),
            )
            .rename(columns={"bucket": "timestamp_wib"})
        )
    else:
        df_tbl = df_raw[available_cols].copy()

    df_tbl = df_tbl.sort_values("timestamp_wib", ascending=False).reset_index(drop=True)

    with exp_c2:
        csv_buf = io.StringIO()
        df_tbl.to_csv(csv_buf, index=False)
        st.download_button(
            "Unduh CSV",
            data=csv_buf.getvalue(),
            file_name=f"telemetri_{selected_machine_id}_{'per_jam' if agg_tbl == 'Per Jam' else '5_menit'}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    display_table = df_tbl.head(50)
    tbl_rows = []
    for _, row in display_table.iterrows():
        st_val = str(row["status"]).lower()
        if st_val == "running":
            pill = '<span class="badge-pill-green">Running</span>'
        elif st_val == "idle":
            pill = '<span class="badge-pill-amber">Idle</span>'
        else:
            pill = '<span class="badge-pill-grey">Off</span>'

        ts_str = row["timestamp_wib"].strftime("%d %b %Y, %H:%M WIB")
        p_str = f"{format_id_num(float(row['power_kw']), 2)} kW"
        e_str = f"{format_id_num(float(row['energy_kwh']), 3)} kWh"

        tbl_rows.append(
            f'<tr>'
            f'<td style="white-space:nowrap; font-weight:600; color:#111827; width:35%;">{ts_str}</td>'
            f'<td style="white-space:nowrap; font-weight:600; color:#1D6FF2; width:22%;">{p_str}</td>'
            f'<td style="white-space:nowrap; color:#111827; width:23%;">{e_str}</td>'
            f'<td style="white-space:nowrap; width:20%;">{pill}</td>'
            f'</tr>'
        )

    table_html = "".join([
        '<div class="dentexa-table-container">',
        '<div style="overflow-x:auto;">',
        '<table class="dentexa-table" style="table-layout:fixed; width:100%;">',
        '<thead>',
        '<tr>',
        '<th style="width:35%;">Waktu (WIB)</th>',
        '<th style="width:22%;">Daya (kW)</th>',
        '<th style="width:23%;">Energi (kWh)</th>',
        '<th style="width:20%;">Status Mesin</th>',
        '</tr>',
        '</thead>',
        '<tbody>',
        "".join(tbl_rows),
        '</tbody>',
        '</table>',
        '</div>',
        '</div>',
    ])
    st.markdown(table_html, unsafe_allow_html=True)

    if len(df_tbl) > 50:
        st.caption(
            f"Menampilkan 50 dari total {format_id_num(len(df_tbl), 0)} baris ({agg_tbl.lower()}) pada rentang tanggal terpilih."
        )
