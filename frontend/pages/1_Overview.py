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
        page_title="Overview - Smart Factory Energy Management",
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

    # ---- Poin 4: Parallelisasi fetch data per mesin ----
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

    # ---- Parallelisasi fetch waste_alerts per mesin ----
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

    return machines, all_readings, all_alerts, has_mock_alert, total_rated_kw, data_is_truncated, failed_machines


# ---------------------------------------------------------------------------
# Pengambilan Data Backend
# ---------------------------------------------------------------------------
try:
    with st.spinner("Mengambil data overview 7 hari terakhir dari server..."):
        # Dapatkan batas asli database
        s_raw, e_raw = get_data_range()
        if e_raw.tzinfo is None:
            e_wib = e_raw.replace(tzinfo=UTC_TZ).astimezone(WIB_TZ)
        else:
            e_wib = e_raw.astimezone(WIB_TZ)

        # Default rentang: 7 hari terakhir dari akhir data asli (WIB)
        default_end_wib = e_wib.date()
        default_start_wib = default_end_wib - timedelta(days=6)

        # Konversi ke UTC untuk query API
        wib_start_dt = datetime.combine(default_start_wib, time.min, tzinfo=WIB_TZ)
        wib_end_dt   = datetime.combine(default_end_wib, time.max.replace(microsecond=0), tzinfo=WIB_TZ)
        query_start_utc = wib_start_dt.astimezone(UTC_TZ).replace(tzinfo=None)
        query_end_utc   = wib_end_dt.astimezone(UTC_TZ).replace(tzinfo=None)

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
    period_str = f"PERIODE: {min_wib} – {max_wib} (WIB)"

    # Total Konsumsi Energi & Estimasi Biaya untuk rentang yang sedang tampil
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

    # Sanity check: Utilisasi daya = avg_power / total_rated_kw * 100
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
            delta_badge_class = "badge-pill-green" if delta_val <= 0 else "badge-pill-orange"
            last_date_str = last_complete_date.strftime("%d %b")
            prev_date_str = prev_complete_date.strftime("%d %b")
            delta_html = f'<span class="{delta_badge_class}">{delta_prefix}{format_id_num(delta_val, 1)}%</span> <span style="color:#6B6259; font-weight:500; font-size:12px;">({last_date_str} vs {prev_date_str})</span>'
        else:
            delta_html = '<span style="color:#6B6259; font-size:12px;">—</span>'
    else:
        delta_html = '<span style="color:#6B6259; font-size:12px;">—</span>'

    # Proporsi Running vs Idle vs Off dari total energi terbaca
    run_kwh = float(df_readings[df_readings["status"] == "running"]["energy_kwh"].sum())
    idle_kwh = float(df_readings[df_readings["status"] == "idle"]["energy_kwh"].sum())
    off_kwh = float(df_readings[df_readings["status"] == "off"]["energy_kwh"].sum())
    tot_status_kwh = total_kwh if total_kwh > 0 else (run_kwh + idle_kwh + off_kwh)
    pct_run_val = (run_kwh / tot_status_kwh * 100) if tot_status_kwh > 0 else 0.0
    pct_idle_val = (idle_kwh / tot_status_kwh * 100) if tot_status_kwh > 0 else 0.0
    pct_off_val = (off_kwh / tot_status_kwh * 100) if tot_status_kwh > 0 else 0.0

else:
    period_str = f"PERIODE: {default_start_wib.strftime('%d %b %Y').upper()} – {default_end_wib.strftime('%d %b %Y').upper()} (WIB)"
    total_kwh, cost_rp = 0.0, 0
    hourly_total = pd.DataFrame()
    cur_power, min_power, max_power, avg_power = 0.0, 0.0, 0.0, 0.0
    utilisasi_pct = 0.0
    run_kwh, idle_kwh, off_kwh = 0.0, 0.0, 0.0
    pct_run_val, pct_idle_val, pct_off_val = 0.0, 0.0, 0.0
    delta_html = '<span style="color:#6B7280; font-size:12px;">—</span>'

# Subjudul halaman: lini + rentang periode yang tampil (WIB) tanpa gaya //
subjudul_halaman = f"{lines_str} · {period_str}"


# ---------------------------------------------------------------------------
# Header Halaman & Filter Granularitas
# ---------------------------------------------------------------------------
header_col1, header_col2 = st.columns([2.2, 1.2])

with header_col1:
    st.markdown(
        f"""
        <div style="margin-bottom: 14px;">
            <h1 style="color: #111827; font-size: 1.75rem; font-weight: 700; margin: 0 0 4px 0; letter-spacing: -0.02em;">
                Energy Dashboard Overview
            </h1>
            <div style="font-size: 12px; font-weight: 500; color: #6B7280; letter-spacing: 0.02em;">
                {subjudul_halaman}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_col2:
    st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)
    view_granularity = st.segmented_control(
        "Tampilan",
        options=["Hourly", "Daily"],
        default="Hourly",
        selection_mode="single",
        label_visibility="collapsed",
    ) or "Hourly"


# ---------------------------------------------------------------------------
# Kartu KPI Atas (Semua KPI memakai rentang periode yang sama)
# ---------------------------------------------------------------------------
kpi_c1, kpi_c2, kpi_c3 = st.columns(3)

with kpi_c1:
    st.markdown(
        f"""
        <div class="kpi-card-dentexa" style="height:100%;">
            <div class="kpi-label">Total Konsumsi Energi</div>
            <div>
                <span class="kpi-val">{format_id_num(total_kwh, 1)}</span>
                <span class="kpi-unit">kWh</span>
            </div>
            <div class="kpi-sub">
                {delta_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with kpi_c2:
    st.markdown(
        f"""
        <div class="kpi-card-dentexa" style="height:100%;">
            <div class="kpi-label">Daya Total Jam Terakhir Data</div>
            <div>
                <span class="kpi-val">{format_id_num(cur_power, 1)}</span>
                <span class="kpi-unit">kW</span>
            </div>
            <div class="kpi-sub">
                <span style="color:#6B7280; font-weight:500; font-size:12px;">Rata-rata periode: <b style="color:#111827;">{format_id_num(avg_power, 1)} kW</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with kpi_c3:
    st.markdown(
        f"""
        <div class="kpi-card-dentexa" style="height:100%;">
            <div class="kpi-label">Estimasi Biaya Listrik (Grid)</div>
            <div>
                <span class="kpi-val">{format_id_currency(cost_rp)}</span>
            </div>
            <div class="kpi-sub">
                <span class="badge-pill-blue">⚡ Tarif {format_id_currency(TARIF_PER_KWH)}</span>
                <span style="color:#6B7280; font-weight:500; font-size:12px;">per kWh</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Baris Tengah: Energy Overview Line Chart (Kiri) & Distribusi Beban Status (Kanan)
# ---------------------------------------------------------------------------
col_mid_left, col_mid_right = st.columns([1.75, 1.15])

with col_mid_left:
    with st.container(border=True):
        st.markdown(
            """
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <div>
                    <h3 style="margin:0; font-size:1.05rem; font-weight:700; color:#111827;">Energy Overview</h3>
                    <div style="font-size:12px; color:#6B7280; font-weight:500;">Profil beban daya total seluruh lini mesin pabrik (kW)</div>
                </div>
                <div style="display:flex; gap:16px; font-size:12px; font-weight:600;">
                    <span style="display:flex; align-items:center; gap:6px; color:#1D6FF2;">
                        <span style="width:12px; height:3px; background:#1D6FF2; border-radius:2px;"></span> Daya Total (kW)
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if hourly_total.empty:
            st.info("Tidak ada data pembacaan sensor.")
        else:
            if view_granularity == "Hourly":
                df_chart = hourly_total
                x_vals = df_chart["hour_wib"]
                y_vals = df_chart["power_kw"]
            else:
                # Agregasi Harian: Rata-rata daya per jam di hari tersebut
                df_chart = (
                    hourly_total.assign(date_wib=hourly_total["hour_wib"].dt.date)
                    .groupby("date_wib", as_index=False)["power_kw"]
                    .mean()
                    .sort_values("date_wib")
                )
                x_vals = df_chart["date_wib"]
                y_vals = df_chart["power_kw"]

            fig_multi = go.Figure()

            # Garis daya total pabrik (kW) - Biru Dentexa #1D6FF2 dengan gradasi halus
            fig_multi.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=y_vals,
                    mode="lines",
                    name="Daya Total (kW)",
                    line=dict(color="#1D6FF2", width=2.5, shape="spline"),
                    fill="tozeroy",
                    fillcolor="rgba(29, 111, 242, 0.08)",
                    hovertemplate="<b>%{x|%d %b %Y, %H:00 WIB}</b><br>Daya Total: <b>%{y:.2f} kW</b><extra></extra>",
                )
            )

            style_plotly_fig(fig_multi, height=330)
            fig_multi.update_layout(
                margin=dict(l=15, r=15, t=10, b=25),
                hovermode="x unified",
            )
            st.plotly_chart(fig_multi, use_container_width=True, config={"displayModeBar": False})

with col_mid_right:
    # Caption timestamp jam terakhir data untuk kartu status
    if not hourly_total.empty:
        last_hour_str = hourly_total["hour_wib"].iloc[-1].strftime("%d %b %Y, %H:00 WIB")
    else:
        last_hour_str = "—"

    with st.container(border=True):
        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
                <div>
                    <h3 style="margin:0; font-size:1.05rem; font-weight:700; color:#111827;">Sebaran Status Beban</h3>
                    <div style="font-size:12px; color:#6B7280; font-weight:500;">
                        Kapasitas Total: {format_id_num(total_rated_kw, 1)} kW
                    </div>
                </div>
                <div style="font-size:11px; color:#6B7280; text-align:right;">
                    {last_hour_str}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Donut Chart gaya 'Expenses' Dentexa (Running / Idle / Off)
        donut_fig = create_status_donut(
            run_pct=pct_run_val,
            idle_pct=pct_idle_val,
            off_pct=pct_off_val,
            run_kwh=run_kwh,
            idle_kwh=idle_kwh,
            off_kwh=off_kwh,
            height=160,
        )
        st.plotly_chart(donut_fig, use_container_width=True, config={"displayModeBar": False})

        # Bar statistik Min / Max / Rata-rata daya total per jam
        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-around; text-align:center; padding:8px 0; border-top:1px solid #E5E8EF; margin-top:-4px; margin-bottom:10px;">
                <div>
                    <div style="font-size:11px; color:#6B7280; text-transform:uppercase; font-weight:600;">Min</div>
                    <div style="font-size:13px; font-weight:700; color:#111827;">{format_id_num(min_power, 1)} <span style="font-size:11px; font-weight:500; color:#6B7280;">kW</span></div>
                </div>
                <div style="border-right:1px solid #E5E8EF;"></div>
                <div>
                    <div style="font-size:11px; color:#6B7280; text-transform:uppercase; font-weight:600;">Max</div>
                    <div style="font-size:13px; font-weight:700; color:#1D6FF2;">{format_id_num(max_power, 1)} <span style="font-size:11px; font-weight:500; color:#6B7280;">kW</span></div>
                </div>
                <div style="border-right:1px solid #E5E8EF;"></div>
                <div>
                    <div style="font-size:11px; color:#6B7280; text-transform:uppercase; font-weight:600;">Rata-rata</div>
                    <div style="font-size:13px; font-weight:700; color:#111827;">{format_id_num(avg_power, 1)} <span style="font-size:11px; font-weight:500; color:#6B7280;">kW</span></div>
                </div>
            </div>

            <div style="display:flex; flex-direction:column; gap:7px;">
                <div>
                    <div style="display:flex; justify-content:space-between; font-size:11px; font-weight:500; margin-bottom:3px;">
                        <span style="color:#6B7280;">Running</span>
                        <span style="color:#16A34A; font-weight:600;">{format_id_num(pct_run_val, 1)}% ({format_id_num(run_kwh, 1)} kWh)</span>
                    </div>
                    <div style="background:#F3F4F6; height:5px; border-radius:3px; overflow:hidden;">
                        <div style="background:#16A34A; width:{pct_run_val:.1f}%; height:100%; border-radius:3px;"></div>
                    </div>
                </div>
                <div>
                    <div style="display:flex; justify-content:space-between; font-size:11px; font-weight:500; margin-bottom:3px;">
                        <span style="color:#6B7280;">Standby (Idle)</span>
                        <span style="color:#F59E0B; font-weight:600;">{format_id_num(pct_idle_val, 1)}% ({format_id_num(idle_kwh, 1)} kWh)</span>
                    </div>
                    <div style="background:#F3F4F6; height:5px; border-radius:3px; overflow:hidden;">
                        <div style="background:#F59E0B; width:{pct_idle_val:.1f}%; height:100%; border-radius:3px;"></div>
                    </div>
                </div>
                <div>
                    <div style="display:flex; justify-content:space-between; font-size:11px; font-weight:500; margin-bottom:3px;">
                        <span style="color:#6B7280;">Mati (Off)</span>
                        <span style="color:#6B7280; font-weight:600;">{format_id_num(pct_off_val, 1)}% ({format_id_num(off_kwh, 1)} kWh)</span>
                    </div>
                    <div style="background:#F3F4F6; height:5px; border-radius:3px; overflow:hidden;">
                        <div style="background:#9CA3AF; width:{pct_off_val:.1f}%; height:100%; border-radius:3px;"></div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Baris Bawah: 3 Kolom (Peringatan, Ringkasan Operasional, Heatmap Beban)
# ---------------------------------------------------------------------------
b_c1, b_c2, b_c3 = st.columns([1.05, 1.15, 1.6])

with b_c1:
    mock_badge_html = '<span class="badge-mock">Data contoh</span>' if has_mock_alert else ""

    rows_parts = []
    if alert_type_counts:
        for atype, count in sorted(alert_type_counts.items(), key=lambda x: -x[1]):
            readable_type = atype.replace("_", " ").title()
            rows_parts.append(
                f'<div style="display:flex; justify-content:space-between; align-items:center; font-size:12px; padding:6px 0; border-bottom:1px solid #F3F4F6;">'
                f'<span style="color:#6B7280; font-weight:500;">{readable_type}</span>'
                f'<span style="font-weight:600; color:#111827;">{count} Kasus</span>'
                f'</div>'
            )
    else:
        rows_parts.append(
            '<div style="font-size:12px; color:#6B7280; padding: 12px 0;">'
            'Tidak ada pemborosan terdeteksi pada rentang waktu ini.'
            '</div>'
        )

    alert_rows_html = "".join(rows_parts)
    with st.container(border=True):
        st.markdown(
            "".join([
                '<div style="min-height:295px; display:flex; flex-direction:column; justify-content:flex-start;">',
                '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">',
                f'<div style="font-weight:700; font-size:0.95rem; color:#111827;">Peringatan Pemborosan {mock_badge_html}</div>',
                f'<span class="badge-pill-amber">{total_waste_alerts} Kasus</span>',
                '</div>',
                '<div style="display:flex; flex-direction:column; gap:4px; margin-top:4px;">',
                alert_rows_html,
                '</div>',
                '</div>',
            ]),
            unsafe_allow_html=True,
        )

with b_c2:
    with st.container(border=True):
        st.markdown(
            f"""
            <div style="min-height:295px; display:flex; flex-direction:column; justify-content:flex-start;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <div style="font-weight:700; font-size:0.95rem; color:#111827;">Ringkasan Operasional</div>
                    <span class="badge-pill-green">Aktif</span>
                </div>
                <div style="display:flex; flex-direction:column; gap:10px; margin-top:6px;">
                    <div style="display:flex; justify-content:space-between; font-size:12px; padding-bottom:6px; border-bottom:1px solid #F3F4F6;">
                        <span style="color:#6B7280; font-weight:500;">Tingkat Utilisasi Daya</span>
                        <span style="font-weight:600; color:#111827;">{format_id_num(utilisasi_pct, 1)}%</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:12px; padding-bottom:6px; border-bottom:1px solid #F3F4F6;">
                        <span style="color:#6B7280; font-weight:500;">Jumlah Mesin Terdaftar</span>
                        <span style="font-weight:600; color:#111827;">{len(machines)} Mesin</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:12px; padding-bottom:6px; border-bottom:1px solid #F3F4F6;">
                        <span style="color:#6B7280; font-weight:500;">Total Kapasitas Terpasang</span>
                        <span style="font-weight:600; color:#111827;">{format_id_num(total_rated_kw, 1)} kW</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:12px;">
                        <span style="color:#6B7280; font-weight:500;">Total Konsumsi 7 Hari</span>
                        <span style="font-weight:600; color:#111827;">{format_id_num(total_kwh, 1)} kWh</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with b_c3:
    with st.container(border=True):
        st.markdown(
            """
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <div style="font-weight:700; font-size:0.95rem; color:#111827;">Peta Beban Mesin (Heatmap)</div>
                <span style="font-size:11px; color:#6B7280; font-weight:500;">Jam 00–23 (WIB)</span>
            </div>
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

            # Skala Biru Dentexa: #EAF2FF (beban sangat rendah) ke #1D6FF2 (beban tinggi)
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
                        title=dict(text="Beban", font=dict(size=11, color="#6B7280")),
                        tickformat=".0%",
                        tickfont=dict(size=10, color="#6B7280"),
                        len=0.9,
                        thickness=10,
                    ),
                    hovertemplate="<b>Mesin %{y}</b><br>Jam: %{x}:00 WIB<br>Rasio Beban: <b>%{z:.1%}</b><extra></extra>",
                )
            )
            fig_heatmap.update_xaxes(
                title_text="Jam WIB",
                tickfont=dict(size=10, color="#6B7280"),
                title_font=dict(size=11, color="#6B7280"),
            )
            fig_heatmap.update_yaxes(
                autorange="reversed",
                tickmode="linear",
                dtick=1,
                tickfont=dict(size=10, color="#6B7280"),
            )
            style_plotly_fig(fig_heatmap, height=255)
            fig_heatmap.update_layout(
                margin=dict(l=10, r=10, t=10, b=25),
            )
            st.plotly_chart(fig_heatmap, use_container_width=True, config={"displayModeBar": False})
