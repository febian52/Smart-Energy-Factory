import sys
from pathlib import Path
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        get_summary,
        get_machines,
        get_waste_alerts,
        get_energy,
        get_data_range,
        TARIF_PER_KWH,
    )
    from frontend.ui import (
        apply_theme,
        style_plotly_fig,
        format_id_num,
        format_id_currency,
        create_status_donut,
    )
except ImportError:
    from api_client import (
        get_summary,
        get_machines,
        get_waste_alerts,
        get_energy,
        get_data_range,
        TARIF_PER_KWH,
    )
    from ui import (
        apply_theme,
        style_plotly_fig,
        format_id_num,
        format_id_currency,
        create_status_donut,
    )

try:
    st.set_page_config(
        page_title="Dashboard - Smart Energy Factory",
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
# Fungsi Cache untuk Mengambil Data 7 Hari Terakhir (paralel per mesin)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def load_overview_data(start_utc_iso: str, end_utc_iso: str):
    s_utc = datetime.fromisoformat(start_utc_iso)
    e_utc = datetime.fromisoformat(end_utc_iso)

    machines = get_machines()
    total_rated_kw = sum(float(m.get("rated_power_kw", 0)) for m in machines) if machines else 466.0

    # Parallelisasi fetch data per mesin
    all_readings: list[dict] = []
    data_is_truncated = False
    failed_machines: list[str] = []

    def _fetch_energy(m: dict) -> tuple[str, list[dict]]:
        mid = m["machine_id"]
        rows = get_energy(mid, start=s_utc, end=e_utc, limit=10000, timeout=30)
        return mid, rows

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_fetch_energy, m): m for m in machines}
        for fut in as_completed(futs):
            m = futs[fut]
            try:
                mid, rows = fut.result()
                if len(rows) >= 10000:
                    data_is_truncated = True
                all_readings.extend(rows)
            except Exception as exc:
                failed_machines.append(m["machine_id"])

    # Parallelisasi fetch waste_alerts per mesin
    all_alerts: list[dict] = []
    has_mock_alert = False

    def _fetch_alerts(m: dict) -> tuple[list[dict], bool]:
        mid = m["machine_id"]
        res = get_waste_alerts(mid, start=s_utc, end=e_utc, timeout=45)
        alerts = res.get("alerts", [])
        is_mock = bool(res.get("is_mock"))
        return alerts, is_mock

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs_a = {ex.submit(_fetch_alerts, m): m for m in machines}
        for fut in as_completed(futs_a):
            try:
                alerts, is_mock = fut.result()
                all_alerts.extend(alerts)
                if is_mock:
                    has_mock_alert = True
            except Exception:
                pass

    return (
        machines,
        all_readings,
        all_alerts,
        has_mock_alert,
        total_rated_kw,
        data_is_truncated,
        failed_machines,
    )


# ---------------------------------------------------------------------------
# Inisialisasi Rentang Data 7 Hari Terakhir Berdasarkan Data Riil Backend
# ---------------------------------------------------------------------------
try:
    s_dt_raw, e_dt_raw = get_data_range()
    if e_dt_raw.tzinfo is None:
        e_dt_wib = e_dt_raw.replace(tzinfo=UTC_TZ).astimezone(WIB_TZ)
    else:
        e_dt_wib = e_dt_raw.astimezone(WIB_TZ)

    default_end_wib = e_dt_wib
    default_start_wib = default_end_wib - timedelta(days=6)
except Exception:
    default_start_wib = datetime(2026, 6, 24, 0, 0, tzinfo=WIB_TZ)
    default_end_wib = datetime(2026, 6, 30, 23, 59, tzinfo=WIB_TZ)

query_start_wib = datetime.combine(default_start_wib.date(), time.min, tzinfo=WIB_TZ)
query_end_wib = datetime.combine(default_end_wib.date(), time.max.replace(microsecond=0), tzinfo=WIB_TZ)

query_start_utc = query_start_wib.astimezone(UTC_TZ).replace(tzinfo=None)
query_end_utc = query_end_wib.astimezone(UTC_TZ).replace(tzinfo=None)

# Muat data secara paralel dan ter-cache
try:
    with st.spinner("Memuat data dashboard pabrik..."):
        (
            machines,
            all_readings,
            all_alerts,
            has_mock_alert,
            total_rated_kw,
            data_is_truncated,
            failed_machines,
        ) = load_overview_data(query_start_utc.isoformat(), query_end_utc.isoformat())

        if failed_machines:
            st.warning(f"⚠️ Gagal mengambil data dari mesin: {', '.join(failed_machines)}. Data yang ditampilkan mungkin tidak lengkap.")

        total_waste_alerts = len(all_alerts)
        alert_type_counts: dict[str, int] = {}
        for a in all_alerts:
            t = a.get("type", "unknown")
            alert_type_counts[t] = alert_type_counts.get(t, 0) + 1

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

if data_is_truncated:
    st.warning("⚠️ **Peringatan Batas Data:** Sebagian data mencapai batas 10.000 baris. Menampilkan data sebagian.")

# Derivasi informasi lini produksi dari get_machines()
unique_lines = sorted(list({str(m.get("line")).strip() for m in machines if m.get("line")}))
if unique_lines:
    lines_str = f"{len(unique_lines)} LINI PRODUKSI ({', '.join(unique_lines).upper()})"
else:
    lines_str = f"{len(machines)} MESIN"


# ---------------------------------------------------------------------------
# Pemrosesan Data & Agregasi Daya Sesuai Formula Fisik
# Total kW per jam = rata-rata power_kw per (mesin, jam), lalu dijumlahkan antar mesin
# ---------------------------------------------------------------------------
if all_readings:
    df_readings = pd.DataFrame(all_readings)
    df_readings["timestamp"] = pd.to_datetime(df_readings["timestamp"])
    if df_readings["timestamp"].dt.tz is None:
        df_readings["timestamp"] = df_readings["timestamp"].dt.tz_localize("UTC")
    df_readings["timestamp_wib"] = df_readings["timestamp"].dt.tz_convert("Asia/Jakarta")
    df_readings["hour_wib"] = df_readings["timestamp_wib"].dt.floor("h")
    df_readings["date_wib"] = df_readings["timestamp_wib"].dt.date

    # Derivasi rentang periode dari data yang tampil dalam format WIB
    min_wib = df_readings["timestamp_wib"].min().strftime("%d %b %Y").upper()
    max_wib = df_readings["timestamp_wib"].max().strftime("%d %b %Y").upper()
    period_str = f"{min_wib} – {max_wib} (WIB)"

    # Total Konsumsi Energi & Estimasi Biaya
    total_kwh = float(df_readings["energy_kwh"].sum())
    cost_rp = total_kwh * TARIF_PER_KWH

    # 1. Rata-rata power_kw per (mesin, jam_wib)
    mach_hourly_kw = (
        df_readings.groupby(["machine_id", "hour_wib"], as_index=False)["power_kw"]
        .mean()
    )

    # 2. Total kW per jam pabrik = jumlah antar mesin
    hourly_total = (
        mach_hourly_kw.groupby("hour_wib", as_index=False)["power_kw"]
        .sum()
        .sort_values("hour_wib")
    )

    # 3. Energi per jam = jumlah energy_kwh
    hourly_energy = (
        df_readings.groupby("hour_wib", as_index=False)["energy_kwh"]
        .sum()
        .sort_values("hour_wib")
    )
    hourly_total["energy_kwh"] = hourly_energy["energy_kwh"]

    cur_power = float(hourly_total["power_kw"].iloc[-1]) if not hourly_total.empty else 0.0
    min_power = float(hourly_total["power_kw"].min()) if not hourly_total.empty else 0.0
    max_power = float(hourly_total["power_kw"].max()) if not hourly_total.empty else 0.0
    avg_power = float(hourly_total["power_kw"].mean()) if not hourly_total.empty else 0.0

    # Utilisasi daya = avg_power / total_rated_kw * 100
    utilisasi_pct = (avg_power / total_rated_kw * 100) if total_rated_kw > 0 else 0.0

    # Perhitungan Delta Konsumsi: Membandingkan dua hari WIB LENGKAP (24 jam penuh) terakhir
    df_readings["hour_int"] = df_readings["timestamp_wib"].dt.hour
    hours_per_day = df_readings.groupby("date_wib")["hour_int"].nunique()
    complete_days = hours_per_day[hours_per_day >= 24].index.sort_values().tolist()

    if len(complete_days) >= 2:
        last_complete_date = complete_days[-1]
        prev_complete_date = complete_days[-2]
        daily_complete = (
            df_readings[df_readings["date_wib"].isin([last_complete_date, prev_complete_date])]
            .groupby("date_wib")["energy_kwh"]
            .sum()
        )
        last_day_val = float(daily_complete.loc[last_complete_date])
        prev_day_val = float(daily_complete.loc[prev_complete_date])
        if prev_day_val > 0:
            delta_val = ((last_day_val - prev_day_val) / prev_day_val) * 100
            delta_prefix = "+" if delta_val >= 0 else ""
            delta_badge_class = "badge-pill-green" if delta_val <= 0 else "badge-pill-amber"
            last_date_str = last_complete_date.strftime("%d %b")
            prev_date_str = prev_complete_date.strftime("%d %b")
            delta_html = f'<span class="{delta_badge_class}">{delta_prefix}{format_id_num(delta_val, 1)}%</span> <span style="color:#6B7280; font-weight:500; font-size:12px;">({last_date_str} vs {prev_date_str})</span>'
        else:
            delta_html = '<span style="color:#6B7280; font-size:12px;">—</span>'
    else:
        delta_html = '<span style="color:#6B7280; font-size:12px;">—</span>'

    # Proporsi Running vs Idle vs Off dari total energi terbaca
    run_kwh = float(df_readings[df_readings["status"] == "running"]["energy_kwh"].sum())
    idle_kwh = float(df_readings[df_readings["status"] == "idle"]["energy_kwh"].sum())
    off_kwh = float(df_readings[df_readings["status"] == "off"]["energy_kwh"].sum())
    tot_status_kwh = total_kwh if total_kwh > 0 else (run_kwh + idle_kwh + off_kwh)
    pct_run_val = (run_kwh / tot_status_kwh * 100) if tot_status_kwh > 0 else 0.0
    pct_idle_val = (idle_kwh / tot_status_kwh * 100) if tot_status_kwh > 0 else 0.0
    pct_off_val = (off_kwh / tot_status_kwh * 100) if tot_status_kwh > 0 else 0.0

else:
    period_str = f"{default_start_wib.strftime('%d %b %Y').upper()} – {default_end_wib.strftime('%d %b %Y').upper()} (WIB)"
    total_kwh, cost_rp = 0.0, 0
    hourly_total = pd.DataFrame()
    cur_power, min_power, max_power, avg_power = 0.0, 0.0, 0.0, 0.0
    utilisasi_pct = 0.0
    run_kwh, idle_kwh, off_kwh = 0.0, 0.0, 0.0
    pct_run_val, pct_idle_val, pct_off_val = 0.0, 0.0, 0.0
    delta_html = '<span style="color:#6B7280; font-size:12px;">—</span>'


# ---------------------------------------------------------------------------
# 1. Header Halaman Berbasis Data
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <div style="margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #E5E8EF;">
        <h1 style="color: #111827; font-size: 1.55rem; font-weight: 700; margin: 0 0 4px 0; letter-spacing: -0.02em;">
            Energy Dashboard Overview
        </h1>
        <div style="font-size: 13px; font-weight: 500; color: #6B7280;">
            {lines_str} &middot; Periode Data: <b style="color:#111827;">{period_str}</b>
            <span style="display:inline-block; margin-left:8px; padding:2px 8px; border-radius:999px; background:#ECFDF5; border:1px solid #D1FAE5; color:#047857; font-size:11px; font-weight:600; white-space:nowrap;">
                &#9679; Data terakhir (dataset simulasi): {default_end_wib.strftime('%d %b %Y, %H:%M WIB')}
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 2. Baris Utama (Row 1): Revenue Style (Kiri) & Expenses Style (Kanan)
# ---------------------------------------------------------------------------
row1_left, row1_right = st.columns([1.8, 1.2])

# --- Kartu Kiri: Revenue Style (Energy Consumption) ---
with row1_left:
    with st.container(border=True):
        rev_head_col, rev_ctrl_col = st.columns([2.2, 1.2])

        with rev_head_col:
            st.markdown(
                f"""
                <div>
                    <div style="font-size: 0.95rem; font-weight: 700; color: #111827; margin-bottom: 2px;">
                        Energy Consumption
                    </div>
                    <div style="font-size: 11px; font-weight: 600; color: #6B7280; letter-spacing: 0.05em; text-transform: uppercase;">
                        Total Konsumsi Energi
                    </div>
                    <div style="display: flex; align-items: baseline; gap: 10px; margin-top: 4px;">
                        <span style="font-size: 2.1rem; font-weight: 800; color: #111827; letter-spacing: -0.03em;">
                            {format_id_num(total_kwh, 1)}
                        </span>
                        <span style="font-size: 1.1rem; font-weight: 600; color: #6B7280;">kWh</span>
                        <div style="margin-left: 6px;">
                            {delta_html}
                        </div>
                    </div>
                    <div style="font-size: 12px; color: #6B7280; font-weight: 500; margin-top: 6px;">
                        Estimasi biaya listrik: <b style="color: #111827;">{format_id_currency(cost_rp)}</b>
                        <span style="color: #9CA3AF;">&middot; tarif {format_id_currency(TARIF_PER_KWH)}/kWh</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with rev_ctrl_col:
            st.markdown(f'<div style="text-align:right; font-size:11px; color:#6B7280; font-weight:500; margin-bottom:6px;">{period_str}</div>', unsafe_allow_html=True)
            view_granularity = st.segmented_control(
                "Granularitas",
                options=["Hourly", "Daily"],
                default="Hourly",
                selection_mode="single",
                label_visibility="collapsed",
            ) or "Hourly"

        # Chart: Spline Line Chart biru dengan Area Fill Gradien Halus
        if hourly_total.empty:
            st.info("Tidak ada data pembacaan sensor.")
        else:
            if view_granularity == "Hourly":
                df_chart = hourly_total
                x_vals = df_chart["hour_wib"]
                y_vals = df_chart["power_kw"]
            else:
                df_chart = (
                    hourly_total.assign(date_wib=hourly_total["hour_wib"].dt.date)
                    .groupby("date_wib", as_index=False)["power_kw"]
                    .mean()
                    .sort_values("date_wib")
                )
                x_vals = df_chart["date_wib"]
                y_vals = df_chart["power_kw"]

            fig_rev = go.Figure()

            # Garis spline biru dengan area fill gradien halus
            fig_rev.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=y_vals,
                    mode="lines",
                    name="Daya Total (kW)",
                    line=dict(color="#1D6FF2", width=2.5, shape="spline"),
                    fill="tozeroy",
                    fillcolor="rgba(29, 111, 242, 0.10)",
                    hovertemplate="<b>%{x|%d %b %Y, %H:00 WIB}</b><br>Daya Total: <b>%{y:.2f} kW</b><extra></extra>",
                )
            )

            style_plotly_fig(fig_rev, height=270)
            fig_rev.update_layout(
                margin=dict(l=15, r=15, t=10, b=20),
                hovermode="x unified",
            )
            st.plotly_chart(fig_rev, use_container_width=True, config={"displayModeBar": False})


# --- Kartu Kanan: Expenses Style (Status Operasional) ---
with row1_right:
    with st.container(border=True):
        st.markdown(
            """
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <div style="font-size:0.95rem; font-weight:700; color:#111827;">Status Operasional</div>
                <div style="font-size:11px; color:#6B7280; font-weight:500;">7 Hari Terakhir</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Donut Chart dengan Anotasi Total Energi di Tengah & Legend di Kanan
        total_kwh_rounded_str = f"{format_id_num(total_kwh, 0)} kWh"
        donut_fig = create_status_donut(
            run_pct=pct_run_val,
            idle_pct=pct_idle_val,
            off_pct=pct_off_val,
            run_kwh=run_kwh,
            idle_kwh=idle_kwh,
            off_kwh=off_kwh,
            total_label="Total Energi",
            total_val_str=total_kwh_rounded_str,
            height=270,
        )
        st.plotly_chart(donut_fig, use_container_width=True, config={"displayModeBar": False})

        # Section: MAJOR STATUS (3 Box Kartu Kecil Berdampingan seperti Major Expenses di Gambar 1)
        st.markdown(
            """
            <div style="font-size:11px; font-weight:700; color:#6B7280; letter-spacing:0.04em; text-transform:uppercase; margin:4px 0 8px 0;">
                Rincian Status Mesin
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px;">
                <div style="background:#F9FAFB; border:1px solid #E5E8EF; border-radius:10px; padding:8px 10px;">
                    <div style="display:flex; align-items:center; gap:5px; font-size:11px; font-weight:600; color:#16A34A; margin-bottom:2px;">
                        <span style="width:6px; height:6px; background:#16A34A; border-radius:50%;"></span> Running
                    </div>
                    <div style="font-size:13px; font-weight:700; color:#111827;">{format_id_num(run_kwh, 0)} <span style="font-size:10px; color:#6B7280; font-weight:500;">kWh</span></div>
                    <div style="font-size:10px; color:#6B7280; font-weight:500;">{format_id_num(pct_run_val, 1)}%</div>
                </div>
                <div style="background:#F9FAFB; border:1px solid #E5E8EF; border-radius:10px; padding:8px 10px;">
                    <div style="display:flex; align-items:center; gap:5px; font-size:11px; font-weight:600; color:#F59E0B; margin-bottom:2px;">
                        <span style="width:6px; height:6px; background:#F59E0B; border-radius:50%;"></span> Idle
                    </div>
                    <div style="font-size:13px; font-weight:700; color:#111827;">{format_id_num(idle_kwh, 0)} <span style="font-size:10px; color:#6B7280; font-weight:500;">kWh</span></div>
                    <div style="font-size:10px; color:#6B7280; font-weight:500;">{format_id_num(pct_idle_val, 1)}%</div>
                </div>
                <div style="background:#F9FAFB; border:1px solid #E5E8EF; border-radius:10px; padding:8px 10px;">
                    <div style="display:flex; align-items:center; gap:5px; font-size:11px; font-weight:600; color:#9CA3AF; margin-bottom:2px;">
                        <span style="width:6px; height:6px; background:#9CA3AF; border-radius:50%;"></span> Off
                    </div>
                    <div style="font-size:13px; font-weight:700; color:#111827;">{format_id_num(off_kwh, 0)} <span style="font-size:10px; color:#6B7280; font-weight:500;">kWh</span></div>
                    <div style="font-size:10px; color:#6B7280; font-weight:500;">{format_id_num(pct_off_val, 1)}%</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div style='padding-bottom:18px;'></div>",
            unsafe_allow_html=True,
        )

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 3. Baris Kedua (Row 2): Financial Overview Bar, Patient Data, & Inventory Alert
# ---------------------------------------------------------------------------
row2_c1, row2_c2, row2_c3 = st.columns([1.25, 1.05, 1.1])

# --- Kolom 1: Konsumsi Energi (per Mesin / Lini / Shift) ---
with row2_c1:
    with st.container(border=True):
        st.markdown(
            '<div style="font-size:0.95rem; font-weight:700; color:#111827; margin-bottom:6px;">Konsumsi Energi</div>',
            unsafe_allow_html=True,
        )

        view_mode = st.segmented_control(
            "Tampilan konsumsi",
            options=["Mesin", "Lini", "Shift"],
            default="Mesin",
            selection_mode="single",
            label_visibility="collapsed",
            key="overview_consumption_view",
        ) or "Mesin"

        if all_readings:
            if view_mode == "Lini":
                line_map = {
                    m["machine_id"]: (str(m.get("line", "")).strip() or "Tanpa Lini")
                    for m in machines
                }
                tmp = df_readings.copy()
                tmp["line"] = tmp["machine_id"].map(line_map).fillna("Tanpa Lini")
                agg = (
                    tmp.groupby("line", as_index=False)["energy_kwh"]
                    .sum()
                    .sort_values("energy_kwh", ascending=True)
                )
                agg["label"] = agg["line"]
                subtitle = "Akumulasi energi listrik per lini produksi"
                count_label = f"{agg['line'].nunique()} lini"
                bar_color = "#10B981"
            elif view_mode == "Shift":
                def _shift_label(hour: int) -> str:
                    if 7 <= hour < 15:
                        return "Pagi (07-15)"
                    if 15 <= hour < 23:
                        return "Siang (15-23)"
                    return "Malam (23-07)"

                tmp = df_readings.copy()
                tmp["shift"] = tmp["timestamp_wib"].dt.hour.map(_shift_label)
                agg = tmp.groupby("shift", as_index=False)["energy_kwh"].sum()
                order = {"Pagi (07-15)": 0, "Siang (15-23)": 1, "Malam (23-07)": 2}
                agg["_order"] = agg["shift"].map(order)
                # Horizontal bar: urutan dibalik agar Pagi tampil paling atas.
                agg = agg.sort_values("_order", ascending=False)
                agg["label"] = agg["shift"]
                subtitle = "Akumulasi energi listrik per shift kerja (WIB)"
                count_label = "3 shift"
                bar_color = "#F59E0B"
            else:
                agg = (
                    df_readings.groupby("machine_id", as_index=False)["energy_kwh"]
                    .sum()
                    .sort_values("energy_kwh", ascending=True)
                )
                agg["label"] = agg["machine_id"]
                subtitle = "Akumulasi energi listrik per ID mesin"
                count_label = f"{df_readings['machine_id'].nunique()} mesin"
                bar_color = "#1D6FF2"

            st.markdown(
                f'<div style="font-size:11px; color:#6B7280; margin:6px 0 8px 0;">'
                f'{subtitle} &middot; <b style="color:#111827;">{count_label}</b></div>',
                unsafe_allow_html=True,
            )

            fig_bar_mach = go.Figure(
                go.Bar(
                    x=agg["energy_kwh"],
                    y=agg["label"],
                    orientation="h",
                    marker=dict(
                        color=bar_color,
                        cornerradius=5,
                    ),
                    text=agg["energy_kwh"].apply(lambda v: f"{format_id_num(v, 0)}"),
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(size=10, color="#111827", family="Inter, sans-serif"),
                    hovertemplate="<b>%{y}</b><br>Konsumsi: %{x:,.1f} kWh<extra></extra>",
                )
            )
            style_plotly_fig(fig_bar_mach, height=220)
            fig_bar_mach.update_layout(
                margin=dict(l=10, r=55, t=5, b=10),
                xaxis=dict(title="", showgrid=True, zeroline=False),
                yaxis=dict(title="", tickfont=dict(size=10, color="#111827"), dtick=1),
            )
            st.plotly_chart(fig_bar_mach, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Data konsumsi belum tersedia.")


# --- Kolom 2: Patient Data Style (Utilisasi Daya & Kapasitas) ---
with row2_c2:
    with st.container(border=True):
        util_html = "".join([
            '<div style="min-height: 280px; display: flex; flex-direction: column; justify-content: space-between;">',
            '<div>',
            '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">',
            '<div style="font-size:0.95rem; font-weight:700; color:#111827;">Utilisasi Daya</div>',
            '<span class="badge-pill-blue">Daya Terpasang</span>',
            '</div>',
            '<div style="font-size:12px; color:#6B7280; margin-bottom:18px;">Beban saat ini terhadap kapasitas total pabrik</div>',
            '<div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px;">',
            '<div>',
            '<span style="font-size:11px; color:#6B7280; font-weight:600; text-transform:uppercase;">Jam Terakhir</span>',
            f'<div style="font-size:1.55rem; font-weight:800; color:#111827;">{format_id_num(cur_power, 1)} <span style="font-size:12px; font-weight:500; color:#6B7280;">kW</span></div>',
            '</div>',
            '<div style="text-align:right;">',
            '<span style="font-size:11px; color:#6B7280; font-weight:600; text-transform:uppercase;">Kapasitas</span>',
            f'<div style="font-size:1.2rem; font-weight:700; color:#6B7280;">{format_id_num(total_rated_kw, 0)} <span style="font-size:12px; font-weight:500;">kW</span></div>',
            '</div>',
            '</div>',
            '<div style="display:flex; justify-content:space-between; font-size:12px; font-weight:600; color:#1D6FF2; margin-bottom:6px;">',
            '<span>Rasio Beban</span>',
            f'<span>{format_id_num(utilisasi_pct, 1)}%</span>',
            '</div>',
            '<div style="background:#F3F4F6; height:8px; border-radius:4px; overflow:hidden; margin-bottom:16px;">',
            f'<div style="background:#1D6FF2; width:{min(100.0, utilisasi_pct):.1f}%; height:100%; border-radius:4px;"></div>',
            '</div>',
            '</div>',
            '<div style="display:flex; justify-content:space-between; padding-top:12px; border-top:1px solid #E5E8EF; font-size:12px;">',
            f'<div><span style="color:#6B7280;">Min Beban:</span><b style="color:#111827; margin-left:3px;">{format_id_num(min_power, 1)} kW</b></div>',
            f'<div><span style="color:#6B7280;">Puncak:</span><b style="color:#1D6FF2; margin-left:3px;">{format_id_num(max_power, 1)} kW</b></div>',
            f'<div><span style="color:#6B7280;">Rata-rata:</span><b style="color:#111827; margin-left:3px;">{format_id_num(avg_power, 1)} kW</b></div>',
            '</div>',
            '</div>',
        ])
        st.markdown(util_html, unsafe_allow_html=True)


# --- Kolom 3: Inventory Status Style (Peringatan Pemborosan Energi) ---
with row2_c3:
    with st.container(border=True):
        mock_badge_html = '<span class="badge-mock">Contoh</span>' if has_mock_alert else ""
        # Hitung sebaran severity secara dinamis dari data API
        sev_badges = []
        if all_alerts:
            df_a = pd.DataFrame(all_alerts)
            df_a["severity"] = df_a["severity"].astype(str).str.lower()
            sev_counts = df_a["severity"].value_counts().to_dict()
            sev_order = ["high", "medium", "low"] + [
                s for s in sorted(sev_counts.keys()) if s not in ("high", "medium", "low")
            ]
            sev_cls_map = {
                "high": "badge-pill-red",
                "medium": "badge-pill-amber",
                "low": "badge-pill-green",
            }
            for s in sev_order:
                if s in sev_counts:
                    cls = sev_cls_map.get(s, "badge-pill-grey")
                    sev_badges.append(
                        f'<span class="{cls}" style="flex:1; text-align:center;">{s.title()}: {format_id_num(sev_counts[s], 0)}</span>'
                    )
        if not sev_badges:
            sev_badges.append('<span class="badge-pill-grey" style="flex:1; text-align:center;">Tidak ada alert</span>')

        # List anomali teratas
        rows_parts = []
        if alert_type_counts:
            for atype, count in sorted(alert_type_counts.items(), key=lambda x: -x[1])[:3]:
                readable_type = atype.replace("_", " ").title()
                rows_parts.append(
                    f'<div style="display:flex; justify-content:space-between; align-items:center; font-size:12px; padding:7px 0; border-bottom:1px solid #F3F4F6;">'
                    f'<span style="color:#6B7280; font-weight:500;">{readable_type}</span>'
                    f'<span style="font-weight:700; color:#111827;">{format_id_num(count, 0)}</span>'
                    f'</div>'
                )
        else:
            rows_parts.append('<div style="font-size:12px; color:#6B7280; padding:10px 0;">Tidak ada anomali terdeteksi.</div>')

        alert_card_html = "".join([
            '<div style="min-height: 280px; display: flex; flex-direction: column; justify-content: space-between;">',
            '<div>',
            '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">',
            f'<div style="font-size:0.95rem; font-weight:700; color:#111827;">Peringatan Pemborosan {mock_badge_html}</div>',
            f'<span class="badge-pill-amber">{format_id_num(total_waste_alerts, 0)} Kasus</span>',
            '</div>',
            '<div style="font-size:12px; color:#6B7280; margin-bottom:14px;">Ringkasan anomali konsumsi daya terdeteksi</div>',
            '<div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;">',
            "".join(sev_badges),
            '</div>',
            "".join(rows_parts),
            '</div>',
            '<div style="font-size:12px; color:#6B7280; padding-top:10px; border-top:1px solid #E5E8EF;">',
            'Lihat detail rekomendasi pada halaman <b style="color:#1D6FF2;">Waste Alerts</b>',
            '</div>',
            '</div>',
        ])
        st.markdown(alert_card_html, unsafe_allow_html=True)

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 4. Baris Ketiga (Row 3): Heatmap Beban Listrik Pabrik 24 Jam
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown(
        """
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <div style="font-size:0.95rem; font-weight:700; color:#111827;">Peta Intensitas Beban Mesin (Heatmap 24 Jam)</div>
            <span style="font-size:11px; color:#6B7280; font-weight:500;">Jam 00–23 (WIB)</span>
        </div>
        <div style="font-size:11px; color:#6B7280; margin-bottom:10px;">Distribusi rasio beban kerja per mesin sepanjang 24 jam operasional pabrik</div>
        """,
        unsafe_allow_html=True,
    )

    if not all_readings or not machines:
        st.info("Data pembacaan sensor belum tersedia.")
    else:
        df_readings["hour_num"] = df_readings["timestamp_wib"].dt.hour
        sorted_machines = sorted(machines, key=lambda m: m.get("machine_id", ""))
        machine_ids = [m["machine_id"] for m in sorted_machines]
        hours_labels = [f"{h:02d}" for h in range(24)]

        # Matriks Beban: z[m_idx][h] = rata-rata power_kw / rated_power_kw
        matrix_z: list[list[float]] = []
        for m in sorted_machines:
            mid = m["machine_id"]
            rated_kw = float(m.get("rated_power_kw", 0)) or 1.0
            df_m = df_readings[df_readings["machine_id"] == mid]

            row_z: list[float] = []
            for h in range(24):
                df_mh = df_m[df_m["hour_num"] == h]
                if not df_mh.empty:
                    avg_h_p = float(df_mh["power_kw"].mean())
                    ratio = avg_h_p / rated_kw
                else:
                    ratio = 0.0
                row_z.append(round(ratio, 4))
            matrix_z.append(row_z)

        # Skala Biru: #EAF2FF (beban sangat rendah) ke #1D6FF2 (beban tinggi)
        fig_heatmap = go.Figure(
            data=go.Heatmap(
                z=matrix_z,
                x=hours_labels,
                y=machine_ids,
                xgap=2,
                ygap=2,
                colorscale=[
                    [0.0, "#EAF2FF"],
                    [0.5, "#93C5FD"],
                    [1.0, "#1D6FF2"],
                ],
                colorbar=dict(
                    title=dict(text="Rasio", font=dict(size=11, color="#6B7280")),
                    tickformat=".0%",
                    tickfont=dict(size=10, color="#6B7280"),
                    len=0.9,
                    thickness=10,
                ),
                hovertemplate="<b>Mesin %{y}</b><br>Jam: %{x}:00 WIB<br>Rasio Beban: <b>%{z:.1%}</b><extra></extra>",
            )
        )
        fig_heatmap.update_xaxes(
            title_text="Jam Operasional WIB",
            tickfont=dict(size=10, color="#6B7280"),
            title_font=dict(size=11, color="#6B7280"),
        )
        fig_heatmap.update_yaxes(
            autorange="reversed",
            tickmode="linear",
            dtick=1,
            tickfont=dict(size=10, color="#6B7280"),
        )
        style_plotly_fig(fig_heatmap, height=265)
        fig_heatmap.update_layout(
            margin=dict(l=10, r=10, t=10, b=25),
        )
        st.plotly_chart(fig_heatmap, use_container_width=True, config={"displayModeBar": False})
