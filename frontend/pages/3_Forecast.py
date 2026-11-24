import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
for p in (str(CURRENT_DIR.parent), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    import frontend.api_client as ac
    from frontend.api_client import (
        get_machines,
        get_forecast,
        get_energy,
        get_data_range,
    )
    from frontend.ui import (
        apply_theme,
        style_plotly_fig,
    )
except ImportError:
    import api_client as ac
    from api_client import (
        get_machines,
        get_forecast,
        get_energy,
        get_data_range,
    )
    from ui import (
        apply_theme,
        style_plotly_fig,
    )

# Model ML memprediksi hingga 168 jam secara autoregresif (168 langkah inferensi).
# Tingkatkan batas waktu timeout runtime ke 45 detik agar kalkulasi 7 hari tidak terputus.
if hasattr(ac, "TIMEOUT"):
    ac.TIMEOUT = 45

try:
    st.set_page_config(
        page_title="Forecast - Smart Factory Energy Management",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

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
# 1. Pengambilan Daftar Mesin (Dropdown)
# ---------------------------------------------------------------------------
try:
    machines = get_machines()
    if not machines:
        st.error("🚨 Tidak ada data mesin yang ditemukan dari backend.", icon="🚫")
        st.stop()
except RuntimeError as exc:
    st.error(
        f"🚨 **Gagal memuat daftar mesin dari API Backend:**\n\n`{exc}`\n\n"
        "Pastikan backend berjalan di `http://localhost:8000` atau periksa koneksi jaringan Anda.",
        icon="🚫",
    )
    st.stop()
except Exception as exc:
    st.error(f"Terjadi kesalahan saat memuat daftar mesin: {exc}", icon="⚠️")
    st.stop()

# ---------------------------------------------------------------------------
# Kontrol Pilihan Mesin & Horizon Prediksi
# ---------------------------------------------------------------------------
ctrl_c1, ctrl_c2 = st.columns([2.2, 1.4])

with ctrl_c1:
    machine_options = {
        m["machine_id"]: f"{m['machine_id']} - {m.get('name', 'Mesin')} ({m.get('line', 'Line')})"
        for m in machines
    }
    selected_machine_id = st.selectbox(
        "Pilih Mesin",
        options=list(machine_options.keys()),
        format_func=lambda mid: machine_options[mid],
    )
    selected_machine = next((m for m in machines if m["machine_id"] == selected_machine_id), {})
    rated_kw = float(selected_machine.get("rated_power_kw", 0.0))

with ctrl_c2:
    horizon_label = st.radio(
        "Horizon Prediksi",
        options=["24 Jam", "7 Hari (168 Jam)"],
        horizontal=True,
    )
    selected_hours = 24 if horizon_label == "24 Jam" else 168

# Header Halaman Bersih & Dinamis
header_title_html = "".join([
    '<div style="margin: 12px 0 16px 0;">',
    '<h1 style="color: #1F1A17; font-size: 2.2rem; font-weight: 800; margin: 0 0 4px 0; letter-spacing: -0.03em;">',
    'Forecast Konsumsi Energi',
    '</h1>',
    '<div style="font-size: 12px; font-weight: 700; color: #6B6259; text-transform: uppercase; letter-spacing: 0.08em;">',
    f'// {selected_machine_id} - {selected_machine.get("name", "MESIN").upper()} · {selected_machine.get("line", "LINE").upper()} · HORIZON: {selected_hours} JAM (WIB)',
    '</div>',
    '</div>',
])
st.markdown(header_title_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 2. Pengambilan Data Prediksi Model ML
# ---------------------------------------------------------------------------
try:
    with st.spinner(f"Memuat prediksi untuk {selected_machine_id} ({selected_hours} jam)..."):
        forecast_res = get_forecast(selected_machine_id, hours=selected_hours)
except RuntimeError as exc:
    st.error(
        f"🚨 **Gagal memuat prediksi dari API Backend:**\n\n`{exc}`",
        icon="🚫",
    )
    st.stop()
except Exception as exc:
    st.error(f"Terjadi kesalahan saat memuat prediksi: {exc}", icon="⚠️")
    st.stop()

is_mock = forecast_res.get("is_mock", False) if isinstance(forecast_res, dict) else False
predictions = forecast_res.get("predictions", []) if isinstance(forecast_res, dict) else forecast_res

if not predictions:
    st.error("🚨 Data prediksi kosong dari API backend untuk mesin ini.", icon="⚠️")
    st.stop()

# ---------------------------------------------------------------------------
# 3. Pengambilan Data Aktual 72 Jam Terakhir
# ---------------------------------------------------------------------------
try:
    start_dt, end_dt = get_data_range(selected_machine_id)
    actual_start = end_dt - timedelta(hours=72)
    actual_rows = get_energy(selected_machine_id, start=actual_start, end=end_dt, limit=10000)
except Exception as exc:
    st.warning(f"⚠️ Gagal memuat data energi aktual 72 jam: {exc}")
    actual_rows = []

if len(actual_rows) >= 10000:
    st.warning("⚠️ **Peringatan Batas Data:** Data pembacaan aktual mencapai batas 10.000 baris. Beberapa data mungkin terpotong.")

# ---------------------------------------------------------------------------
# 4. Konversi Waktu dari UTC ke WIB untuk Aktual dan Prediksi
# ---------------------------------------------------------------------------
# Pemrosesan Data Aktual
if actual_rows:
    df_actual = pd.DataFrame(actual_rows)
    df_actual["timestamp"] = pd.to_datetime(df_actual["timestamp"])
    if df_actual["timestamp"].dt.tz is None:
        df_actual["timestamp"] = df_actual["timestamp"].dt.tz_localize("UTC")
    df_actual["timestamp_wib"] = df_actual["timestamp"].dt.tz_convert("Asia/Jakarta")
    df_actual["hour_wib"] = df_actual["timestamp_wib"].dt.floor("h")

    # Agregasi per jam dengan menjumlahkan energy_kwh
    df_actual_hourly = (
        df_actual.groupby("hour_wib", as_index=False)["energy_kwh"]
        .sum()
        .sort_values("hour_wib")
    )
else:
    df_actual_hourly = pd.DataFrame(columns=["hour_wib", "energy_kwh"])

# Pemrosesan Data Prediksi
df_preds = pd.DataFrame(predictions)
df_preds["forecast_time"] = pd.to_datetime(df_preds["forecast_time"])
if df_preds["forecast_time"].dt.tz is None:
    df_preds["forecast_time"] = df_preds["forecast_time"].dt.tz_localize("UTC")
df_preds["timestamp_wib"] = df_preds["forecast_time"].dt.tz_convert("Asia/Jakarta")
df_preds["hour_wib"] = df_preds["timestamp_wib"].dt.floor("h")
df_preds["predicted_kwh"] = df_preds["predicted_kwh"].astype(float)
df_preds = df_preds.sort_values("hour_wib")

# ---------------------------------------------------------------------------
# 5. Tiga Kartu Ringkas (KPI)
# ---------------------------------------------------------------------------
total_pred_kwh = float(df_preds["predicted_kwh"].sum())
cost_pred = total_pred_kwh * 1500  # Tarif Rp 1.500/kWh

if not df_preds.empty:
    peak_idx = df_preds["predicted_kwh"].idxmax()
    peak_row = df_preds.loc[peak_idx]
    peak_time_str = peak_row["timestamp_wib"].strftime("%d %b %Y, %H:00 WIB")
    peak_val = float(peak_row["predicted_kwh"])
else:
    peak_time_str = "—"
    peak_val = 0.0

mock_badge = '<span class="badge-mock">Data contoh</span>' if is_mock else ""

kpi_c1, kpi_c2, kpi_c3 = st.columns(3)

with kpi_c1:
    card1_html = "".join([
        '<div class="kpi-card-velora">',
        f'<div class="kpi-label">Total Prediksi Energi {mock_badge}</div>',
        '<div>',
        f'<span class="kpi-val">{format_id_num(total_pred_kwh, 1)}</span>',
        '<span class="kpi-unit">kWh</span>',
        '</div>',
        '<div class="kpi-sub" style="margin-top:4px;">',
        f'<span style="color:#6B6259; font-weight:600; font-size:12px;">Horizon: <b>{selected_hours} Jam</b> ({len(df_preds)} titik jam)</span>',
        '</div>',
        '</div>',
    ])
    st.markdown(card1_html, unsafe_allow_html=True)

with kpi_c2:
    card2_html = "".join([
        '<div class="kpi-card-velora">',
        '<div class="kpi-label">Jam Puncak Prediksi (WIB)</div>',
        '<div>',
        f'<span class="kpi-val" style="font-size:1.45rem;">{peak_time_str}</span>',
        '</div>',
        '<div class="kpi-sub" style="margin-top:4px;">',
        f'<span class="badge-pill-orange">Beban Puncak: {peak_val:.2f} kWh</span>',
        '</div>',
        '</div>',
    ])
    st.markdown(card2_html, unsafe_allow_html=True)

with kpi_c3:
    card3_html = "".join([
        '<div class="kpi-card-velora">',
        '<div class="kpi-label">Estimasi Biaya Prediksi</div>',
        '<div>',
        f'<span class="kpi-val">{format_id_currency(cost_pred)}</span>',
        '</div>',
        '<div class="kpi-sub" style="margin-top:4px;">',
        '<span class="badge-pill-orange">⚡ Tarif Rp 1.500</span> ',
        '<span style="color:#6B6259; font-weight:500; font-size:12px;">per kWh</span>',
        '</div>',
        '</div>',
    ])
    st.markdown(card3_html, unsafe_allow_html=True)

st.markdown("<div style='margin: 1.25rem 0;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 3 & 6. Pembuatan Grafik Plotly & Pengecekan Kapasitas
# ---------------------------------------------------------------------------
fig = go.Figure()

# Titik plotting prediksi (menyambung langsung dari titik akhir aktual)
pred_x = list(df_preds["hour_wib"])
pred_y = list(df_preds["predicted_kwh"])

if not df_actual_hourly.empty:
    last_actual_time = df_actual_hourly["hour_wib"].iloc[-1]
    last_actual_val = float(df_actual_hourly["energy_kwh"].iloc[-1])
    pred_plot_x = [last_actual_time] + pred_x
    pred_plot_y = [last_actual_val] + pred_y
else:
    last_actual_time = None
    pred_plot_x = pred_x
    pred_plot_y = pred_y

# 1. Garis Aktual: Oranye Terracotta Solid
if not df_actual_hourly.empty:
    fig.add_trace(
        go.Scatter(
            x=df_actual_hourly["hour_wib"],
            y=df_actual_hourly["energy_kwh"],
            mode="lines",
            name="Aktual 72 Jam (kWh)",
            line=dict(color="#E8590C", width=3, shape="spline"),
            fill="tozeroy",
            fillcolor="rgba(232, 89, 12, 0.06)",
            hovertemplate="<b>Aktual</b><br>Waktu: %{x|%d %b %Y, %H:00} WIB<br>Konsumsi: <b>%{y:.2f} kWh</b><extra></extra>",
        )
    )

# 2. Garis Prediksi: Kuning Hangat Putus-putus
fig.add_trace(
    go.Scatter(
        x=pred_plot_x,
        y=pred_plot_y,
        mode="lines",
        name=f"Prediksi {selected_hours} Jam (kWh)",
        line=dict(color="#F2C230", width=2.5, dash="dash", shape="spline"),
        fill="tozeroy",
        fillcolor="rgba(242, 194, 48, 0.06)",
        hovertemplate="<b>Prediksi</b><br>Waktu: %{x|%d %b %Y, %H:00} WIB<br>Prediksi: <b>%{y:.2f} kWh</b><extra></extra>",
    )
)

# 3. Garis Vertikal Pemisah Tipis di Akhir Data Aktual
if last_actual_time is not None:
    fig.add_shape(
        type="line",
        x0=last_actual_time,
        x1=last_actual_time,
        y0=0,
        y1=1,
        yref="paper",
        line=dict(color="#6B6259", width=1.5, dash="dot"),
    )
    fig.add_annotation(
        x=last_actual_time,
        y=1,
        yref="paper",
        text="Batas Aktual / Mulai Prediksi",
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
        font=dict(size=12, color="#6B6259"),
    )

style_plotly_fig(fig, height=380)
fig.update_layout(
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        font=dict(size=12, color="#6B6259"),
    ),
    margin=dict(l=20, r=20, t=30, b=30),
    hovermode="x unified",
)
fig.update_xaxes(
    title_text="Waktu (WIB)",
    tickfont=dict(size=12, color="#6B6259"),
    title_font=dict(size=12, color="#6B6259"),
)
fig.update_yaxes(
    title_text="Konsumsi Energi (kWh)",
    tickfont=dict(size=12, color="#6B6259"),
    title_font=dict(size=12, color="#6B6259"),
)

# Tampilkan Kontainer Kartu Grafik
chart_card_header = "".join([
    '<div style="background:#FFFFFF; border:1px solid #EFE5D6; border-radius:16px; padding:20px 22px; box-shadow:0 2px 10px -2px rgba(31,26,23,0.04);">',
    '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">',
    '<div>',
    f'<h3 style="margin:0; font-size:1.15rem; font-weight:800; color:#1F1A17;">Proyeksi Beban Konsumsi: {selected_machine_id}</h3>',
    f'<div style="font-size:12px; color:#6B6259; font-weight:600;">Kurva komparasi data riil 72 jam terakhir terhadap proyeksi model ML {selected_hours} jam ke depan (WIB)</div>',
    '</div>',
    '</div>',
])
st.markdown(chart_card_header, unsafe_allow_html=True)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# 6. Pengecekan apakah angka prediksi per jam melebihi rated_power_kw mesin
# Jangan menyesuaikan atau memotong angka prediksi, hanya tampilkan peringatan
exceeded_mask = df_preds["predicted_kwh"] > rated_kw
exceeded_count = int(exceeded_mask.sum())
if rated_kw > 0 and exceeded_count > 0:
    max_pred_val = float(df_preds["predicted_kwh"].max())
    warning_capacity_html = "".join([
        '<div style="font-size:12px; color:#E8590C; font-weight:600; padding:8px 12px; background:rgba(232,89,12,0.06); border-radius:8px; border:1px solid rgba(232,89,12,0.2); margin-top:8px; display:flex; align-items:center; gap:8px;">',
        '<span>⚠️</span>',
        f'<span><b>Prediksi melebihi kapasitas mesin:</b> Terdeteksi {exceeded_count} jam proyeksi dengan beban di atas rated power ({rated_kw:.1f} kW), nilai tertinggi mencapai {max_pred_val:.2f} kWh.</span>',
        '</div>',
    ])
    st.markdown(warning_capacity_html, unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# Footer Info
st.markdown(
    "".join([
        '<div style="text-align: right; font-size: 12px; color: #6B6259; margin-top: 20px;">',
        f'Mesin: <b>{selected_machine_id}</b> (Kapasitas: <b>{rated_kw:.1f} kW</b>) · Horizon Prediksi: <b>{selected_hours} Jam</b> · Ditampilkan dalam Waktu Indonesia Barat (WIB)',
        '</div>',
    ]),
    unsafe_allow_html=True,
)
