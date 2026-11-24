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
    )
    from frontend.ui import (
        apply_theme,
        style_plotly_fig,
    )
except ImportError:
    from api_client import (
        get_summary,
        get_machines,
        get_waste_alerts,
        get_energy,
        get_data_range,
    )
    from ui import (
        apply_theme,
        style_plotly_fig,
    )

st.set_page_config(
    page_title="Overview - Smart Factory Energy Management",
    page_icon="⚡",
    layout="wide",
)

# Terapkan Tema Warm Light
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

        # Ambil semua alert pemborosan untuk rentang yang sedang tampil
        all_alerts: list[dict] = []
        has_mock_alert = False

        if machines:
            for m in machines:
                mid = m.get("machine_id")
                try:
                    waste_res = get_waste_alerts(mid, start=start_dt, end=end_dt)
                    alerts_list = waste_res.get("alerts", [])
                    all_alerts.extend(alerts_list)
                    if waste_res.get("is_mock"):
                        has_mock_alert = True
                except Exception:
                    # Jika endpoint error atau timeout, jangan hentikan seluruh halaman
                    pass

        total_waste_alerts = len(all_alerts)

        # Hitung sebaran alert per tipe apa adanya dari data
        alert_type_counts: dict[str, int] = {}
        for a in all_alerts:
            t = a.get("type", "unknown")
            alert_type_counts[t] = alert_type_counts.get(t, 0) + 1

        # Pengambilan Data Time-Series Pembacaan Sensor
        all_readings: list[dict] = []
        data_is_truncated = False

        if machines:
            for m in machines:
                mid = m.get("machine_id")
                rows = get_energy(mid, start=start_dt, end=end_dt, limit=10000)
                if len(rows) >= 10000:
                    data_is_truncated = True
                if rows:
                    all_readings.extend(rows)

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
    st.warning("⚠️ **Peringatan Batas Data:** Data pembacaan energi mencapai batas maksimal 10.000 baris. Beberapa data mungkin terpotong.")

total_kwh = summary_data.get("total_kwh", 0.0) if summary_data else 0.0
cost_rp = summary_data.get("estimated_cost_rp", 0) if summary_data else 0
total_rated_kw = sum(float(m.get("rated_power_kw", 0)) for m in machines) if machines else 1.0

# Derivasi informasi lini produksi dari get_machines()
unique_lines = sorted(list({str(m.get("line")).strip() for m in machines if m.get("line")}))
if unique_lines:
    lines_str = f"{len(unique_lines)} LINI PRODUKSI ({', '.join(unique_lines).upper()})"
else:
    lines_str = f"{len(machines)} MESIN"

# ---------------------------------------------------------------------------
# Pemrosesan Data & Konversi Waktu UTC ke WIB
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
    if min_wib == max_wib:
        period_str = f"PERIODE: {min_wib} (WIB)"
    else:
        period_str = f"PERIODE: {min_wib} – {max_wib} (WIB)"

    # Deret TOTAL daya semua mesin per jam
    hourly_total = (
        df_readings.groupby("hour_wib", as_index=False)
        .agg({"power_kw": "sum", "energy_kwh": "sum"})
        .sort_values("hour_wib")
    )

    cur_power = float(hourly_total["power_kw"].iloc[-1]) if not hourly_total.empty else 0.0
    min_power = float(hourly_total["power_kw"].min()) if not hourly_total.empty else 0.0
    max_power = float(hourly_total["power_kw"].max()) if not hourly_total.empty else 0.0
    avg_power = float(hourly_total["power_kw"].mean()) if not hourly_total.empty else 0.0

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
            delta_html = f'<span class="{delta_badge_class}">{delta_prefix}{delta_val:.1f}%</span> <span style="color:#6B6259; font-weight:500; font-size:12px;">vs hari sebelumnya</span>'
        else:
            delta_html = '<span style="color:#6B6259; font-size:12px;">—</span>'
    else:
        delta_html = '<span style="color:#6B6259; font-size:12px;">—</span>'

    # Utilisasi = rata-rata daya total dibagi jumlah rated_power_kw
    utilisasi_pct = (avg_power / total_rated_kw * 100) if total_rated_kw > 0 else 0.0

    # Proporsi Running vs Idle dari total energi terbaca
    run_kwh = float(df_readings[df_readings["status"] == "running"]["energy_kwh"].sum())
    idle_kwh = float(df_readings[df_readings["status"] == "idle"]["energy_kwh"].sum())
    tot_status_kwh = run_kwh + idle_kwh
    pct_run_val = (run_kwh / tot_status_kwh * 100) if tot_status_kwh > 0 else 0.0
    pct_idle_val = (idle_kwh / tot_status_kwh * 100) if tot_status_kwh > 0 else 0.0

else:
    period_str = f"PERIODE: {start_dt.strftime('%d %b %Y').upper()} – {end_dt.strftime('%d %b %Y').upper()} (WIB)"
    hourly_total = pd.DataFrame()
    cur_power, min_power, max_power, avg_power = 0.0, 0.0, 0.0, 0.0
    utilisasi_pct = 0.0
    run_kwh, idle_kwh = 0.0, 0.0
    pct_run_val, pct_idle_val = 0.0, 0.0
    delta_html = '<span style="color:#6B6259; font-size:12px;">—</span>'

# Subjudul halaman diturunkan langsung dari data
subjudul_halaman = f"// {lines_str} · {period_str}"

# ---------------------------------------------------------------------------
# Header Halaman & Segmented Filter Control (Top Bar)
# ---------------------------------------------------------------------------
header_col1, header_col2 = st.columns([2.2, 1.2])

with header_col1:
    st.markdown(
        f"""
        <div style="margin-bottom: 12px;">
            <h1 style="color: #1F1A17; font-size: 2.2rem; font-weight: 800; margin: 0 0 4px 0; letter-spacing: -0.03em;">
                Energy Dashboard Overview
            </h1>
            <div style="font-size: 12px; font-weight: 700; color: #6B6259; text-transform: uppercase; letter-spacing: 0.08em;">
                {subjudul_halaman}
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
# Kartu KPI Atas (3 Kolom: Total Konsumsi, Daya Saat Ini, Estimasi Biaya)
# ---------------------------------------------------------------------------
kpi_c1, kpi_c2, kpi_c3 = st.columns(3)

with kpi_c1:
    st.markdown(
        f"""
        <div class="kpi-card-velora">
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
        <div class="kpi-card-velora">
            <div class="kpi-label">Daya total jam terakhir data</div>
            <div>
                <span class="kpi-val">{cur_power:.1f}</span>
                <span class="kpi-unit">kW</span>
            </div>
            <div class="kpi-sub">
                <span style="color:#6B6259; font-weight:600; font-size:12px;">Rata-rata periode: <b>{avg_power:.1f} kW</b></span>
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
            <div class="kpi-sub">
                <span class="badge-pill-orange">⚡ Tarif Rp 1.500</span>
                <span style="color:#6B6259; font-weight:500; font-size:12px;">per kWh</span>
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
                    <div style="font-size:12px; color:#6B6259; font-weight:600;">Kurva beban daya instan seluruh mesin per jam (WIB)</div>
                </div>
                <div style="display:flex; gap:16px; font-size:12px; font-weight:700;">
                    <span style="display:flex; align-items:center; gap:5px; color:#E8590C;">
                        <span style="width:12px; height:3px; background:#E8590C; border-radius:2px;"></span> Daya Total (kW)
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
        else:
            df_chart = (
                df_readings.groupby("date_wib", as_index=False)
                .agg({"power_kw": "sum", "energy_kwh": "sum"})
                .sort_values("date_wib")
            )
            x_vals = df_chart["date_wib"]

        fig_multi = go.Figure()

        # Satu garis daya total per jam (kW)
        fig_multi.add_trace(
            go.Scatter(
                x=x_vals,
                y=df_chart["power_kw"],
                mode="lines",
                name="Daya Total (kW)",
                line=dict(color="#E8590C", width=3, shape="spline"),
                fill="tozeroy",
                fillcolor="rgba(232, 89, 12, 0.06)",
                hovertemplate="<b>Waktu (WIB)</b>: %{x}<br>Daya Total: <b>%{y:.2f} kW</b><extra></extra>",
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
    # Caption timestamp jam terakhir data untuk gauge
    if not hourly_total.empty:
        last_hour_str = hourly_total["hour_wib"].iloc[-1].strftime("%d %b %Y, %H:00 WIB")
    else:
        last_hour_str = "—"
    st.markdown(
        f"""
        <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04); height:100%;">
            <div style="font-weight:800; font-size:1.15rem; color:#1F1A17; margin-bottom:4px;">Power Meter</div>
            <div style="font-size:12px; color:#6B6259; font-weight:600; margin-bottom:2px;">
                Total Daya Semua Mesin (Kapasitas: {total_rated_kw:.0f} kW)
            </div>
            <div style="font-size:11px; color:#8C827A; margin-bottom:6px;">
                Jam terakhir data: {last_hour_str}
            </div>
        """,
        unsafe_allow_html=True,
    )

    # Dial Radial Gauge: Skala 0 sampai total rated_power_kw semua mesin
    gauge_fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=round(cur_power, 2),
            domain={"x": [0.05, 0.95], "y": [0.15, 0.95]},
            title={
                "text": "<span style='font-size:12px;color:#6B6259;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;'>Daya total jam terakhir data</span>",
                "font": {"size": 13, "family": "Plus Jakarta Sans"},
            },
            number={
                "suffix": " <span style='font-size:13px;color:#6B6259;font-weight:500;'>kW</span>",
                "font": {"size": 34, "color": "#1F1A17", "family": "Plus Jakarta Sans"},
            },
            gauge={
                "axis": {
                    "range": [0, total_rated_kw],
                    "tickwidth": 1.5,
                    "tickcolor": "#C4B5A5",
                    "ticklen": 6,
                    "nticks": 8,
                    "tickfont": {"size": 12, "color": "#6B6259"},
                },
                "bar": {"color": "#E8590C", "thickness": 0.14},
                "bgcolor": "#FFF7EB",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, total_rated_kw], "color": "#FAF4E8"},
                ],
            },
        )
    )
    gauge_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=220,
        margin=dict(l=15, r=15, t=30, b=10),
    )
    st.plotly_chart(gauge_fig, use_container_width=True)

    # Min / Max / Avg bar dihitung dari deret TOTAL daya semua mesin per jam
    st.markdown(
        f"""
        <div style="display:flex; justify-content:space-around; text-align:center; padding:8px 0; border-top:1px solid #EFE5D6; margin-top:-10px; margin-bottom:14px;">
            <div>
                <div style="font-size:12px; color:#6B6259; text-transform:uppercase; font-weight:600;">Min</div>
                <div style="font-size:14px; font-weight:700; color:#1F1A17;">{min_power:.2f} <span style="font-size:12px;">kW</span></div>
            </div>
            <div style="border-right:1px solid #EFE5D6;"></div>
            <div>
                <div style="font-size:12px; color:#6B6259; text-transform:uppercase; font-weight:600;">Max</div>
                <div style="font-size:14px; font-weight:700; color:#E8590C;">{max_power:.2f} <span style="font-size:12px;">kW</span></div>
            </div>
            <div style="border-right:1px solid #EFE5D6;"></div>
            <div>
                <div style="font-size:12px; color:#6B6259; text-transform:uppercase; font-weight:600;">Rata-rata</div>
                <div style="font-size:14px; font-weight:700; color:#1F1A17;">{avg_power:.2f} <span style="font-size:12px;">kW</span></div>
            </div>
        </div>

        <div style="display:flex; flex-direction:column; gap:10px;">
            <div>
                <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:600; margin-bottom:4px;">
                    <span style="color:#6B6259;">Konsumsi Beban Running</span>
                    <span style="color:#16A34A; font-weight:700;">{pct_run_val:.1f}% ({run_kwh:,.1f} kWh)</span>
                </div>
                <div style="background:#F2ECE2; height:7px; border-radius:4px; overflow:hidden;">
                    <div style="background:#16A34A; width:{pct_run_val:.1f}%; height:100%; border-radius:4px;"></div>
                </div>
            </div>
            <div>
                <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:600; margin-bottom:4px;">
                    <span style="color:#6B6259;">Konsumsi Beban Standby (Idle)</span>
                    <span style="color:#F2C230; font-weight:700;">{pct_idle_val:.1f}% ({idle_kwh:,.1f} kWh)</span>
                </div>
                <div style="background:#F2ECE2; height:7px; border-radius:4px; overflow:hidden;">
                    <div style="background:#F2C230; width:{pct_idle_val:.1f}%; height:100%; border-radius:4px;"></div>
                </div>
            </div>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Baris Bawah: 3 Kolom (Alerts per Tipe, Impact Operasional, Peta Beban Mesin)
# ---------------------------------------------------------------------------
b_c1, b_c2, b_c3 = st.columns([1.05, 1.15, 1.6])

with b_c1:
    mock_badge_html = '<span class="badge-mock">Data contoh</span>' if has_mock_alert else ""

    # Bangun string HTML tanpa indentasi di awal baris dan tanpa baris kosong
    # agar tidak dianggap oleh parser Markdown sebagai blok kode (4-space indented code block)
    rows_parts = []
    if alert_type_counts:
        for atype, count in sorted(alert_type_counts.items(), key=lambda x: -x[1]):
            readable_type = atype.replace("_", " ").title()
            rows_parts.append(
                f'<div style="display:flex; justify-content:space-between; font-size:13px; padding-bottom:6px; border-bottom:1px solid #FAF4E8;">'
                f'<span style="color:#6B6259;">{readable_type}</span>'
                f'<span style="font-weight:700; color:#1F1A17;">{count} Kasus</span>'
                f'</div>'
            )
    else:
        rows_parts.append(
            '<div style="font-size:13px; color:#6B6259; padding: 12px 0;">'
            'Tidak ada pemborosan terdeteksi pada rentang waktu ini.'
            '</div>'
        )

    alert_rows_html = "".join(rows_parts)
    alerts_card_html = "".join([
        '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.03); height:100%;">',
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">',
        f'<div style="font-weight:700; font-size:14px; color:#1F1A17;">Peringatan Pemborosan {mock_badge_html}</div>',
        f'<span class="badge-pill-orange">{total_waste_alerts} Kasus</span>',
        '</div>',
        '<div style="display:flex; flex-direction:column; gap:10px; margin-top:14px;">',
        alert_rows_html,
        '</div>',
        '</div>',
    ])
    st.markdown(alerts_card_html, unsafe_allow_html=True)

with b_c2:
    st.markdown(
        f"""
        <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.03); height:100%;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <div style="font-weight:700; font-size:14px; color:#1F1A17;">Ringkasan Operasional</div>
                <span class="badge-pill-green">Aktif</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:12px; margin-top:14px;">
                <div style="display:flex; justify-content:space-between; font-size:13px; padding-bottom:6px; border-bottom:1px solid #FAF4E8;">
                    <span style="color:#6B6259;">Tingkat Utilisasi Daya</span>
                    <span style="font-weight:700; color:#1F1A17;">{utilisasi_pct:.1f}%</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:13px; padding-bottom:6px; border-bottom:1px solid #FAF4E8;">
                    <span style="color:#6B6259;">Jumlah Mesin Terdaftar</span>
                    <span style="font-weight:700; color:#1F1A17;">{len(machines)} Mesin</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:13px;">
                    <span style="color:#6B6259;">Total Konsumsi Energi</span>
                    <span style="font-weight:700; color:#1F1A17;">{format_id_num(total_kwh, 2)} kWh</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with b_c3:
    st.markdown(
        """
        <div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.03); height:100%;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <div style="font-weight:700; font-size:14px; color:#1F1A17;">Peta Beban Mesin</div>
                <span style="font-size:12px; color:#6B6259; font-weight:600;">Jam 00–23 (WIB)</span>
            </div>
        """,
        unsafe_allow_html=True,
    )

    if not all_readings or not machines:
        st.info("Data pembacaan sensor belum tersedia.")
    else:
        df_readings["hour_num"] = df_readings["timestamp_wib"].dt.hour
        # Urutkan baris mesin dari atas ke bawah (M01 di atas)
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

        fig_heatmap = go.Figure(
            data=go.Heatmap(
                z=matrix_z,
                x=hours_labels,
                y=machine_ids,
                xgap=3,
                ygap=3,
                colorscale=[
                    [0.0, "#FFF9DB"],
                    [0.5, "#FCD34D"],
                    [1.0, "#E8590C"],
                ],
                colorbar=dict(
                    title=dict(text="Beban", font=dict(size=12, color="#6B6259")),
                    tickformat=".0%",
                    tickfont=dict(size=12, color="#6B6259"),
                    len=0.9,
                    thickness=12,
                ),
                hovertemplate="<b>Mesin %{y}</b><br>Jam: %{x}:00 WIB<br>Rasio Beban: <b>%{z:.1%}</b><extra></extra>",
            )
        )
        fig_heatmap.update_xaxes(
            title_text="Jam WIB",
            tickfont=dict(size=12, color="#6B6259"),
            title_font=dict(size=12, color="#6B6259"),
        )
        fig_heatmap.update_yaxes(
            autorange="reversed",
            tickfont=dict(size=12, color="#6B6259"),
        )
        style_plotly_fig(fig_heatmap, height=195)
        fig_heatmap.update_layout(
            margin=dict(l=10, r=10, t=10, b=25),
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)

        st.markdown(
            """
            <div style="font-size:12px; color:#6B6259; margin-top:2px; text-align:center;">
                Keterangan Skala: Kuning pucat = Beban Rendah/Idle (0%) ➔ Oranye Pekat = Beban Tinggi (≥100%)
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)

# Footer info
st.markdown(
    f"""
    <div style="text-align: right; font-size: 12px; color: #6B6259; margin-top: 20px;">
        Database Sensor: Data aktif <b>{start_dt.strftime('%d %b %Y')}</b> s/d <b>{end_dt.strftime('%d %b %Y')}</b> (Rentang Server) · Ditampilkan dalam Waktu Indonesia Barat (WIB)
    </div>
    """,
    unsafe_allow_html=True,
)


